#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
海外财经新闻邮件抓取器

数据源：QQ 邮箱 IMAP → hszxboss@qq.com 转发的彭博/路透/WSJ 等一手新闻
频率：每天 08:30 / 20:30 两次（配合 overseas_digest.py）
职责：只管抓取 + 入库，不做分析
"""
import imaplib
import email
import re
import json
import hashlib
from email.header import decode_header
from pathlib import Path
from datetime import datetime, timedelta

# ==================== 路径配置 ====================
SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "email_config.json"
CACHE_DIR = SCRIPT_DIR / "cache"
CACHE_DIR.mkdir(exist_ok=True)
DB_FILE = CACHE_DIR / "email_news_db.json"
UID_STATE_FILE = CACHE_DIR / "email_news_last_uid.txt"

# ==================== 加载配置 ====================
def load_config():
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(f"配置文件不存在: {CONFIG_FILE}")
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

# ==================== 邮件解析 ====================
def decode_subject(raw):
    """解码邮件标题（中文/混合编码）"""
    if not raw:
        return ""
    parts = decode_header(raw)
    out = []
    for s, enc in parts:
        if isinstance(s, bytes):
            out.append(s.decode(enc or 'utf-8', errors='ignore'))
        else:
            out.append(s)
    return ''.join(out).strip()

def get_body_plain(msg):
    """取纯文本正文"""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == 'text/plain':
                try:
                    payload = part.get_payload(decode=True)
                    charset = part.get_content_charset() or 'utf-8'
                    return payload.decode(charset, errors='ignore')
                except Exception:
                    continue
        # 退而求其次取 html 再剥标签
        for part in msg.walk():
            if part.get_content_type() == 'text/html':
                try:
                    payload = part.get_payload(decode=True)
                    charset = part.get_content_charset() or 'utf-8'
                    html = payload.decode(charset, errors='ignore')
                    return re.sub(r'<[^>]+>', ' ', html)
                except Exception:
                    continue
    else:
        try:
            payload = msg.get_payload(decode=True)
            charset = msg.get_content_charset() or 'utf-8'
            return payload.decode(charset, errors='ignore')
        except Exception:
            return str(msg.get_payload())
    return ""

def parse_subject(subject):
    """拆标题 -> (source, title)
    形如 '华尔街日报：长和以 58 亿美元退出沃达丰合资公司'
    """
    m = re.match(r'^\s*([^：:]{1,30})[：:]\s*(.+)$', subject)
    if m:
        source = m.group(1).strip()
        title = m.group(2).strip()
        return source, title
    return "未知来源", subject

def extract_url(body):
    """正文里抠原文链接"""
    m = re.search(r'原文链接\s*[：:]\s*(https?://\S+)', body)
    if m:
        return m.group(1).rstrip('.,;)】')
    # 兜底：第一个 http 链接
    m = re.search(r'(https?://\S+)', body)
    return m.group(1).rstrip('.,;)】') if m else ""

def extract_summary(body, max_len=400):
    """取正文摘要（去掉原文链接尾巴，保留前段内容）"""
    # 去掉"原文链接：..."及其之后
    cut = re.split(r'原文链接\s*[：:]', body, maxsplit=1)[0]
    # 去多余空行
    cut = re.sub(r'\n\s*\n+', '\n', cut).strip()
    return cut[:max_len]

def parse_internaldate(data):
    """从 IMAP fetch 返回里抠 INTERNALDATE
    data 可能是 bytes / str / list / tuple，遍历全部取值"""
    candidates = []
    def walk(x):
        if isinstance(x, bytes):
            candidates.append(x.decode(errors='ignore'))
        elif isinstance(x, str):
            candidates.append(x)
        elif isinstance(x, (list, tuple)):
            for item in x:
                walk(item)
    walk(data)
    combined = " ".join(candidates)
    m = re.search(r'INTERNALDATE "([^"]+)"', combined)
    if not m:
        return None
    try:
        # 日期可能是 '1-May-2026' 或 '01-May-2026'，两种都试
        dt_str = m.group(1)
        for fmt in ("%d-%b-%Y %H:%M:%S %z",):
            try:
                return datetime.strptime(dt_str, fmt)
            except ValueError:
                continue
        # 宽松处理：补零
        parts = dt_str.split(' ')
        if parts and '-' in parts[0]:
            day_part, rest = parts[0].split('-', 1)
            dt_str2 = f"{int(day_part):02d}-{rest} {' '.join(parts[1:])}"
            return datetime.strptime(dt_str2, "%d-%b-%Y %H:%M:%S %z")
    except Exception:
        return None
    return None

# ==================== 去重指纹 ====================
def make_fingerprint(title, source, summary):
    """三级去重指纹：去源前缀的标题 + 摘要前 50 字 hash"""
    title_key = title.strip()
    summary_key = summary[:50].strip() if summary else ""
    raw = f"{title_key}||{summary_key}".encode('utf-8')
    return hashlib.md5(raw).hexdigest()[:16]

# ==================== 本地库 ====================
def load_db():
    if not DB_FILE.exists():
        return {"items": {}, "last_uid": 0}
    with open(DB_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_db(db):
    # 控制库大小：只保留最近 60 天
    cutoff = (datetime.now() - timedelta(days=60)).isoformat()
    db["items"] = {
        k: v for k, v in db["items"].items()
        if v.get("received_at", "") >= cutoff
    }
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

# ==================== IMAP 抓取 ====================
def fetch_emails(since_days=None, since_uid=None):
    """
    抓取邮件。两种模式：
      - since_days: 回填模式，按日期搜索
      - since_uid: 增量模式，从指定 UID 之后
    返回解析后的新闻条目 list
    """
    cfg = load_config()
    im = cfg["imap"]
    M = imaplib.IMAP4_SSL(im["host"], im["port"], timeout=30)
    M.login(im["user"], im["auth_code"])
    M.select(im["mailbox"])

    sender = im["sender_filter"]

    if since_uid is not None and since_uid > 0:
        # IMAP UID 搜索
        typ, data = M.uid('SEARCH', None, 'FROM', sender,
                          f'UID {since_uid+1}:*')
        uids = data[0].split() if data and data[0] else []
    else:
        # 按日期回填
        days = since_days or cfg.get("fetch", {}).get("backfill_days", 3)
        since_date = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
        typ, data = M.uid('SEARCH', None, 'FROM', sender,
                          f'SINCE {since_date}')
        uids = data[0].split() if data and data[0] else []

    items = []
    max_uid = since_uid or 0

    if not uids:
        M.logout()
        return items, max_uid

    print(f"  命中 {len(uids)} 封新邮件，开始解析...")

    for uid_bytes in uids:
        try:
            uid = int(uid_bytes)
            max_uid = max(max_uid, uid)

            typ, msg_data = M.uid('FETCH', uid_bytes,
                                  '(RFC822 INTERNALDATE)')
            if not msg_data or not msg_data[0]:
                continue

            # msg_data 结构：[(meta_header, raw_email), b'INTERNALDATE "..."']
            raw_email = None
            for part in msg_data:
                if isinstance(part, tuple) and len(part) >= 2:
                    raw_email = part[1]
                    break
            if not raw_email:
                continue

            internal_dt = parse_internaldate(msg_data)
            msg = email.message_from_bytes(raw_email)

            subject = decode_subject(msg.get('Subject', ''))
            if not subject:
                continue

            body = get_body_plain(msg)
            source, title = parse_subject(subject)
            summary = extract_summary(body)
            url = extract_url(body)
            fp = make_fingerprint(title, source, summary)

            items.append({
                "uid": uid,
                "received_at": internal_dt.isoformat() if internal_dt else "",
                "source": source,
                "title": title,
                "summary": summary,
                "url": url,
                "fingerprint": fp,
            })
        except Exception as e:
            print(f"  ⚠️ 解析 UID {uid_bytes} 失败: {e}")
            continue

    M.logout()
    return items, max_uid

# ==================== 主逻辑 ====================
def run(mode="incremental"):
    """
    mode: "incremental" | "backfill"
    """
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 邮件抓取模式: {mode}")

    db = load_db()
    existing_fps = {v.get("fingerprint") for v in db["items"].values()}
    last_uid = db.get("last_uid", 0)

    if mode == "backfill":
        items, new_max_uid = fetch_emails(since_days=3)
    else:
        items, new_max_uid = fetch_emails(since_uid=last_uid)

    added = 0
    dup = 0
    for item in items:
        fp = item["fingerprint"]
        if fp in existing_fps:
            dup += 1
            continue
        # 用 fingerprint 做 key，天然去重
        db["items"][fp] = item
        existing_fps.add(fp)
        added += 1

    if new_max_uid > last_uid:
        db["last_uid"] = new_max_uid

    save_db(db)

    # 当日快照
    today = datetime.now().strftime("%Y%m%d")
    snapshot_file = CACHE_DIR / f"email_news_{today}.json"
    today_items = [
        v for v in db["items"].values()
        if v.get("received_at", "").startswith(datetime.now().strftime("%Y-%m-%d"))
    ]
    today_items.sort(key=lambda x: x.get("received_at", ""), reverse=True)
    with open(snapshot_file, 'w', encoding='utf-8') as f:
        json.dump({
            "date": datetime.now().strftime("%Y-%m-%d"),
            "updated_at": datetime.now().isoformat(),
            "count": len(today_items),
            "items": today_items,
        }, f, ensure_ascii=False, indent=2)

    print(f"✅ 完成：新增 {added} 条，重复 {dup} 条，今日共 {len(today_items)} 条")
    print(f"   累计库: {len(db['items'])} 条，最大 UID: {db['last_uid']}")
    return db

# ==================== CLI ====================
if __name__ == '__main__':
    import sys
    mode = "incremental"
    if len(sys.argv) > 1 and sys.argv[1] == "--backfill":
        mode = "backfill"
    run(mode=mode)

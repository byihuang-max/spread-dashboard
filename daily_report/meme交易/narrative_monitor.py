#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
叙事监控系统 - 基于 Tushare 新闻 + LLM 分析 + 价格背离检测
每天 08:30 和 20:30 推送到飞书
"""
import tushare as ts
import json
import requests
import yfinance as yf
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path

# ==================== 配置 ====================
TUSHARE_TOKEN = "8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae"
FEISHU_APP_ID = "cli_a91c36caf5785cb2"
FEISHU_APP_SECRET = "HWhYR833N0xObKumrjNCKdRSHq3jg0zi"
RONI_OPEN_ID = "ou_4f9c4d14f2e27f4863a5e2743dba3482"

# 8 个核心叙事定义
# 原则：关键词要专一，只有"文章主要在说这个叙事"才能命中
# 避免使用泛化词（如 "AI"、"中国"、"价格"），改用专有名词或复合词
NARRATIVES = {
    "AI_CapEx": {
        "name": "AI CapEx 超级周期",
        "keywords": [
            # 美国核心算力公司
            "英伟达", "NVIDIA", "博通", "Broadcom", "AMD",
            # 具体芯片/产品型号
            "H100", "H200", "B200", "B100", "GB200", "Blackwell", "Hopper",
            "HBM", "CoWoS", "AI芯片", "GPU集群", "算力集群",
            # 云平台算力 & 资本开支
            "AI数据中心", "AI资本开支", "AI CapEx",
            "AWS算力", "Azure AI", "谷歌TPU",
            # 大模型厂商
            "OpenAI融资", "Anthropic", "大模型训练", "推理算力",
        ],
        "description": "美国核心AI算力公司及产业链，芯片资本支出周期"
    },
    "去美元化": {
        "name": "去美元化 / 货币贬值",
        "keywords": [
            "央行购金", "黄金储备", "去美元化", "黄金ETF",
            "BRICS结算", "人民币国际化", "储备货币多元化",
            "美元霸权", "SWIFT替代", "抛售美债",
            "金价创新高", "黄金价格",
        ],
        "description": "全球货币体系重构、黄金需求、货币贬值预期"
    },
    "全球再武装": {
        "name": "全球再武装",
        "keywords": [
            "国防预算", "军费增加", "北约", "NATO",
            "欧洲军备", "德国军费", "防务支出", "军事开支",
            "洛克希德", "雷神", "军工股", "武器出口",
            "军备竞赛", "防务预算",
        ],
        "description": "全球军费开支增加、国防工业需求"
    },
    "财政主导": {
        "name": "财政主导 / 实际利率压制",
        "keywords": [
            # 美国财政
            "美国国债", "美国赤字", "美国债务上限", "DOGE", "美联储资产负债表",
            # 中国财政
            "特别国债", "地方政府债务", "城投债", "中国财政赤字",
            # 日本财政
            "YCC", "日本国债", "植田和男", "日本央行政策",
            # 通用
            "收益率曲线控制", "财政扩张",
        ],
        "description": "财政扩张（中美日）、央行压制长端利率、实际利率走低"
    },
    "地缘风险": {
        "name": "地缘风险",
        "keywords": [
            # 中东冲突（实体名，不用复合词）
            "以色列", "伊朗", "哈马斯", "加沙", "黎巴嫩真主党",
            # 俄乌
            "俄乌", "乌克兰", "泽连斯基",
            # 台海
            "台海", "台湾军事", "台海紧张",
            # 朝核
            "朝鲜导弹", "朝鲜核",
            # 制裁/管制
            "出口管制", "贸易战", "关税报复",
            # 通用风险词（足够具体）
            "军事打击", "空袭", "停火协议", "地缘政治风险",
        ],
        "description": "地缘政治紧张、战争风险、避险情绪"
    },
    "美国衰退": {
        "name": "美国衰退预期",
        "keywords": [
            # 就业数据
            "非农就业", "美国失业率", "初请失业金",
            # GDP & 消费
            "美国GDP收缩", "美国经济衰退", "美国消费者信心",
            # 企业裁员
            "科技裁员", "大规模裁员", "美国消费疲软",
            # 先行指标
            "ISM制造业", "美国零售销售下滑",
        ],
        "description": "美国经济衰退预期（就业/消费/PMI）"
    },
    "中国刺激": {
        "name": "中国刺激预期",
        "keywords": [
            # 货币政策
            "降息", "降准", "PBOC宽松", "中国货币政策",
            # 财政/消费刺激
            "消费补贴", "以旧换新", "房地产救市", "限购取消",
            # 宏观数据与政策目标
            "两会GDP", "政府工作报告增长目标", "中国PMI", "中国社零",
            "中国经济刺激",
        ],
        "description": "中国刺激政策与宏观经济数据"
    },
    "通胀通缩": {
        "name": "通胀/通缩预期",
        "keywords": [
            # ── 美国通胀数据 ──
            "美国CPI", "美国PCE", "美国PPI", "核心通胀", "服务通胀", "薪资通胀",
            # ── 美联储利率决策 ──
            "美联储加息", "美联储降息", "FOMC", "美联储利率",
            # ── 日本央行 ──
            "日本央行加息", "日银加息", "日本利率", "植田和男通胀",
            # ── 中国通胀/通缩 ──
            "中国CPI", "中国PPI", "中国通缩", "中国物价",
            # ── 通胀驱动因素 ──
            "能源通胀", "大宗商品通胀", "供应链通胀", "粮食价格",
            # ── 预期 ──
            "通胀预期", "通缩压力", "滞涨", "再通胀", "盈亏平衡通胀率",
        ],
        "description": "通胀/通缩预期（中美日央行利率决策 + 关键数据 + 驱动因素）"
    }
}

# ==================== 初始化 ====================
ts.set_token(TUSHARE_TOKEN)
pro = ts.pro_api()

SCRIPT_DIR = Path(__file__).parent
CACHE_DIR = SCRIPT_DIR / "cache"
CACHE_DIR.mkdir(exist_ok=True)
HISTORY_FILE = CACHE_DIR / "narrative_history.json"

# ==================== 历史数据管理 ====================
def load_history():
    """加载历史评分数据"""
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_history(analysis):
    """保存当前评分到历史"""
    history = load_history()
    today = datetime.now().strftime('%Y-%m-%d')
    
    history[today] = {
        key: data['score'] for key, data in analysis.items()
    }
    
    # 只保留最近 400 天（超过1年，保证历史分位有足够窗口）
    dates = sorted(history.keys())
    if len(dates) > 400:
        for old_date in dates[:-400]:
            del history[old_date]
    
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def get_trend(key, days=7):
    """计算叙事趋势"""
    history = load_history()
    dates = sorted(history.keys())[-days:]
    
    if len(dates) < 2:
        return "➡️", 0
    
    scores = [history[d].get(key, 0) for d in dates]
    change = scores[-1] - scores[0]
    
    if change > 2:
        return "📈", change
    elif change < -2:
        return "📉", change
    else:
        return "➡️", change

def get_lifecycle(key, current_score):
    """判断叙事生命周期"""
    history = load_history()
    dates = sorted(history.keys())[-7:]
    
    if len(dates) < 3:
        return "观察中"
    
    scores = [history[d].get(key, 0) for d in dates]
    
    # 萌芽：从低位快速上升
    if scores[0] < 4 and current_score >= 5 and (current_score - scores[0]) > 3:
        return "🌱萌芽"
    
    # 加速：持续上升
    if all(scores[i] <= scores[i+1] for i in range(len(scores)-1)) and current_score >= 5:
        return "🚀加速"
    
    # 共识：高位震荡
    if current_score >= 7 and max(scores) - min(scores) < 2:
        return "🔥共识"
    
    # 饱和：极高且稳定
    if current_score >= 9 and all(s >= 8 for s in scores[-3:]):
        return "⚠️饱和"
    
    return "➡️稳定"

# ==================== 叙事-资产映射 ====================
NARRATIVE_ASSETS = {
    "AI_CapEx": {
        "利好": ["纳指", "半导体ETF", "铜", "电力"],
        "利空": ["传统能源"]
    },
    "去美元化": {
        "利好": ["黄金", "人民币", "BTC"],
        "利空": ["美元", "美债"]
    },
    "全球再武装": {
        "利好": ["国防股", "稀有金属"],
        "利空": []
    },
    "财政主导": {
        "利好": ["黄金", "实物资产"],
        "利空": ["长端美债"]
    },
    "地缘风险": {
        "利好": ["黄金", "原油", "国防股"],
        "利空": ["风险资产", "新兴市场"]
    },
    "美国衰退": {
        "利好": ["美债", "黄金", "防御股"],
        "利空": ["股票", "高收益债"]
    },
    "中国刺激": {
        "利好": ["A股", "港股", "铜", "铁矿"],
        "利空": []
    },
    "通胀通缩": {
        "利好": ["黄金", "大宗商品"],
        "利空": ["债券", "成长股"]
    }
}

# ==================== 叙事-价格映射 ====================
# 每条叙事对应的可监控资产（yfinance ticker → 展示名）
NARRATIVE_PRICE_MAP = {
    "AI_CapEx":  {"QQQ": "纳指ETF", "NVDA": "英伟达", "HG=F": "铜"},
    "去美元化":  {"GC=F": "黄金", "BTC-USD": "BTC"},
    "全球再武装": {"GC=F": "黄金", "CL=F": "原油"},
    "财政主导":  {"GC=F": "黄金", "TLT": "美债20Y"},
    "地缘风险":  {"GC=F": "黄金", "CL=F": "原油"},
    "美国衰退":  {"GC=F": "黄金", "QQQ": "纳指ETF"},
    "中国刺激":  {"3033.HK": "恒生科技ETF", "000300.SS": "沪深300"},
    "通胀通缩":  {"GC=F": "黄金", "HG=F": "铜"},
}

def fetch_asset_prices():
    """
    拉取所有叙事关联资产的近期涨跌幅（1D / 1W / 1M）
    返回：{ticker: {"name": ..., "1D": %, "1W": %, "1M": %}}
    """
    # 汇总所有 ticker
    all_tickers = {}
    for mapping in NARRATIVE_PRICE_MAP.values():
        all_tickers.update(mapping)

    results = {}

    for ticker, name in all_tickers.items():
        try:
            # 沪深300走Tushare
            if ticker == "000300.SS":
                ret = _fetch_a_stock_return("000300.SH")
                if ret:
                    results[ticker] = {"name": name, **ret}
                continue

            # 其余走 yfinance（直连，不走代理）
            data = yf.download(
                ticker,
                period="35d",
                interval="1d",
                progress=False,
                auto_adjust=True,
            )
            if data.empty or len(data) < 2:
                continue

            # 新版 yfinance 下载单 ticker 时 Close 是 DataFrame（MultiIndex）
            closes = data["Close"].squeeze().dropna()
            if len(closes) < 2:
                continue

            last   = float(closes.iloc[-1])
            prev1  = float(closes.iloc[-2])
            prev5  = float(closes.iloc[-6])  if len(closes) >= 6  else float(closes.iloc[0])
            prev22 = float(closes.iloc[-23]) if len(closes) >= 23 else float(closes.iloc[0])

            results[ticker] = {
                "name":  name,
                "price": round(last, 2),
                "1D":    round((last / prev1  - 1) * 100, 2),
                "1W":    round((last / prev5  - 1) * 100, 2),
                "1M":    round((last / prev22 - 1) * 100, 2),
            }
        except Exception:
            pass

    return results


def _fetch_a_stock_return(ts_code):
    """用Tushare HTTP API拉A股指数近期涨跌幅"""
    try:
        url = "https://api.tushare.pro"
        payload = {
            "api_name": "index_daily",
            "token": TUSHARE_TOKEN,
            "params": {"ts_code": ts_code, "limit": 25},
            "fields": "trade_date,close"
        }
        resp = requests.post(url, json=payload, timeout=15)
        data = resp.json().get("data", {})
        items = data.get("items", [])
        if len(items) < 2:
            return None
        # items按日期倒序，items[0]=最新
        closes = [float(r[1]) for r in items if r[1] is not None]
        if len(closes) < 2:
            return None
        last = closes[0]
        return {
            "price": round(last, 2),
            "1D": round((closes[0] / closes[1] - 1) * 100, 2),
            "1W": round((closes[0] / closes[min(5, len(closes)-1)] - 1) * 100, 2),
            "1M": round((closes[0] / closes[min(22, len(closes)-1)] - 1) * 100, 2),
        }
    except Exception:
        return None


def get_divergence_signal(narrative_key, score, prices):
    """
    叙事-价格背离检测
    返回：(信号emoji, 信号文字) 或 None
    """
    mapping = NARRATIVE_PRICE_MAP.get(narrative_key, {})
    if not mapping or score < 5:
        return None

    signals = []
    for ticker, name in mapping.items():
        p = prices.get(ticker)
        if not p:
            continue
        w1 = p.get("1W", 0)
        w4 = p.get("1M", 0)

        # 叙事热但价格没动 → 未price in，潜在机会
        if score >= 7 and w1 < 1.0:
            signals.append(f"💡{name}1W仅+{w1:.1f}%，叙事未price in")
        # 叙事热且价格已大涨 → 追顶风险
        elif score >= 7 and w1 >= 8.0:
            signals.append(f"⚠️{name}1W已+{w1:.1f}%，追顶风险")
        # 叙事强但资产近月已涨很多 → 小心反转
        elif score >= 6 and w4 >= 15.0:
            signals.append(f"🔔{name}1M+{w4:.1f}%，注意叙事衰退")

    return signals if signals else None


# ==================== 飞书认证 ====================
def get_feishu_token():
    """获取飞书 access_token"""
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    payload = {
        "app_id": FEISHU_APP_ID,
        "app_secret": FEISHU_APP_SECRET
    }
    resp = requests.post(url, json=payload)
    return resp.json()["tenant_access_token"]

# ==================== 拉取新闻 ====================
def fetch_news(hours=12):
    """拉取最近 N 小时的新闻"""
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=hours)
    
    all_news = []
    sources = ['wallstreetcn', 'cls', 'sina']  # 华尔街见闻 + 财联社 + 新浪
    
    for src in sources:
        try:
            df = pro.news(
                src=src,
                start_date=start_time.strftime('%Y-%m-%d %H:%M:%S'),
                end_date=end_time.strftime('%Y-%m-%d %H:%M:%S')
            )
            if len(df) > 0:
                for _, row in df.iterrows():
                    all_news.append({
                        "time": row['datetime'],
                        "title": row.get('title', ''),
                        "content": row.get('content', ''),
                        "source": src
                    })
        except Exception as e:
            print(f"拉取 {src} 失败: {e}")
    
    # 按时间倒序
    all_news.sort(key=lambda x: x['time'], reverse=True)
    return all_news

# ==================== LLM 分析叙事 ====================
def analyze_narratives(news_list):
    """
    关键词匹配分析叙事热度

    改进点（v2）：
    1. 跨源去重：同一标题不管来自几个源，只计1次
    2. 精准匹配：
       - 标题命中 ≥1 个关键词 → 算匹配（标题更精准）
       - 标题未命中，正文命中 ≥2 个关键词 → 才算匹配（过滤万金油文章）
    3. key_news 按命中关键词数降序排列，最相关的排前面
    """
    # ── Step 1：按标题去重（相同标题只保留第一条）──
    seen_titles, deduped = set(), []
    for news in news_list:
        title = str(news.get('title', '')).strip()
        if not title or title == 'nan':
            continue
        if title not in seen_titles:
            seen_titles.add(title)
            deduped.append(news)

    results = {}
    for key, narrative in NARRATIVES.items():
        keywords = narrative['keywords']
        matched_news = []  # [(news, hit_count), ...]

        for news in deduped:
            title   = str(news.get('title', '')).strip()
            content = str(news.get('content', '')).strip()

            # 标题匹配：任意1个关键词即算（标题足够精准）
            title_lower = title.lower()
            title_hits  = sum(1 for kw in keywords if kw.lower() in title_lower)
            if title_hits >= 1:
                matched_news.append((news, title_hits + 10))  # 标题命中加权+10
                continue

            # 正文匹配：至少2个关键词（防止万金油文章污染）
            content_lower = content.lower()
            content_hits  = sum(1 for kw in keywords if kw.lower() in content_lower)
            if content_hits >= 2:
                matched_news.append((news, content_hits))

        # 按命中关键词数降序（最相关的排前）
        matched_news.sort(key=lambda x: x[1], reverse=True)
        matched_count = len(matched_news)

        # 评分：匹配条数占去重后总量的比例
        match_ratio = matched_count / max(len(deduped), 1) * 100
        score = min(10, int(match_ratio * 2))  # 5% 匹配率 = 10分

        sentiment = "利好" if score >= 5 else "中性" if score >= 3 else "利空"

        results[key] = {
            "score": score,
            "sentiment": sentiment,
            "summary": f"匹配到 {matched_count} 条相关新闻（去重后 {len(deduped)} 条，{match_ratio:.1f}%）",
            "key_news": [
                str(n.get('title', ''))[:60]
                for n, _ in matched_news[:3]
                if str(n.get('title', '')) not in ('', 'nan')
            ]
        }

    return results

# ==================== 生成报告 ====================
def generate_report(analysis, news_count, prices=None):
    """生成简洁版飞书报告（含价格背离信号）"""
    now = datetime.now().strftime("%m-%d %H:%M")
    
    # 按分数排序
    sorted_narratives = sorted(
        analysis.items(), 
        key=lambda x: x[1]['score'], 
        reverse=True
    )
    
    report = f"📊 叙事监控 {now} | 分析 {news_count} 条新闻\n\n"
    
    for key, data in sorted_narratives:
        score = data['score']
        sentiment = data['sentiment']
        
        # 获取趋势和生命周期
        trend_emoji, trend_val = get_trend(key, days=7)
        lifecycle = get_lifecycle(key, score)
        
        # 获取资产关联
        assets = NARRATIVE_ASSETS.get(key, {})
        asset_text = ""
        if sentiment == "利好" and assets.get("利好"):
            asset_text = f" → {'/'.join(assets['利好'][:3])}"
        elif sentiment == "利空" and assets.get("利空"):
            asset_text = f" → {'/'.join(assets['利空'][:3])}"
        
        # 简洁输出
        report += f"{lifecycle} {NARRATIVES[key]['name']}\n"
        report += f"   {score}/10 {trend_emoji} | {sentiment}{asset_text}\n"
        
        # 价格层：显示关联资产涨跌幅
        if prices:
            mapping = NARRATIVE_PRICE_MAP.get(key, {})
            price_parts = []
            for ticker, name in mapping.items():
                p = prices.get(ticker)
                if p:
                    w1 = p.get("1W", 0)
                    sign = "+" if w1 >= 0 else ""
                    price_parts.append(f"{name} 1W:{sign}{w1:.1f}%")
            if price_parts:
                report += f"   💰 {' | '.join(price_parts)}\n"
            
            # 背离信号
            div_signals = get_divergence_signal(key, score, prices)
            if div_signals:
                for sig in div_signals:
                    report += f"   {sig}\n"
        
        # 只显示高分叙事的关键新闻
        if score >= 7 and data['key_news']:
            report += f"   📌 {data['key_news'][0]}\n"
        
        report += "\n"
    
    return report

# ==================== 推送到飞书 ====================
def send_to_feishu(report):
    """推送报告到飞书"""
    token = get_feishu_token()
    url = "https://open.feishu.cn/open-apis/im/v1/messages"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "receive_id": RONI_OPEN_ID,
        "msg_type": "text",
        "content": json.dumps({"text": report})
    }
    
    params = {"receive_id_type": "open_id"}
    resp = requests.post(url, headers=headers, json=payload, params=params)
    return resp.json()

# ==================== 主函数 ====================
def main():
    print(f"[{datetime.now()}] 开始叙事监控...")
    
    # 1. 拉取新闻
    news = fetch_news(hours=12)
    print(f"✅ 拉取到 {len(news)} 条新闻")
    
    # 2. 分析叙事
    analysis = analyze_narratives(news)
    print(f"✅ 完成叙事分析")
    
    # 3. 保存历史
    save_history(analysis)
    print(f"✅ 保存历史数据")

    # 4. 拉取资产价格
    print(f"⏳ 拉取资产价格...")
    prices = fetch_asset_prices()
    print(f"✅ 获取到 {len(prices)} 个资产价格")
    
    # 5. 生成报告
    report = generate_report(analysis, len(news), prices=prices)
    print(f"✅ 生成报告")
    
    # 6. 推送飞书
    result = send_to_feishu(report)
    print(f"✅ 推送飞书: {result.get('code')}")
    
    # 7. 保存到本地
    cache_file = CACHE_DIR / f"narrative_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump({"analysis": analysis, "report": report, "prices": prices}, f, ensure_ascii=False, indent=2)
    print(f"✅ 保存到 {cache_file}")

if __name__ == "__main__":
    main()


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
NARRATIVES = {
    "AI_CapEx": {
        "name": "AI CapEx 超级周期",
        "keywords": ["AI", "人工智能", "英伟达", "NVIDIA", "算力", "芯片", "半导体", "HBM", "数据中心", "CapEx", "资本开支"],
        "description": "AI 基础设施投资、芯片需求、算力扩张"
    },
    "去美元化": {
        "name": "去美元化 / 货币贬值",
        "keywords": ["美元", "去美元化", "人民币", "黄金", "央行购金", "储备货币", "SWIFT", "BRICS", "货币贬值", "通胀"],
        "description": "全球货币体系重构、黄金需求、货币贬值预期"
    },
    "全球再武装": {
        "name": "全球再武装",
        "keywords": ["国防", "军费", "武器", "军工", "北约", "军事", "国防预算", "军备"],
        "description": "全球军费开支增加、国防工业需求"
    },
    "财政主导": {
        "name": "财政主导 / 实际利率压制",
        "keywords": ["财政赤字", "国债", "财政政策", "实际利率", "收益率曲线", "QE", "量化宽松", "央行"],
        "description": "财政扩张、央行压制长端利率、实际利率走低"
    },
    "地缘风险": {
        "name": "地缘风险",
        "keywords": ["俄乌", "中东", "台海", "伊朗", "以色列", "战争", "冲突", "制裁", "地缘政治"],
        "description": "地缘政治紧张、战争风险、避险情绪"
    },
    "美国衰退": {
        "name": "美国衰退预期",
        "keywords": ["衰退", "经济放缓", "失业率", "非农", "GDP", "消费疲软", "企业盈利", "裁员"],
        "description": "美国经济衰退预期、就业市场恶化"
    },
    "中国刺激": {
        "name": "中国刺激预期",
        "keywords": ["中国", "刺激", "降息", "降准", "财政政策", "基建", "房地产", "消费券", "政策宽松"],
        "description": "中国经济刺激政策、宽松预期"
    },
    "通胀通缩": {
        "name": "通胀/通缩预期",
        "keywords": ["通胀", "通缩", "CPI", "PPI", "物价", "价格", "通胀预期", "通缩风险"],
        "description": "通胀/通缩预期变化"
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
    
    # 只保留最近60天
    dates = sorted(history.keys())
    if len(dates) > 60:
        for old_date in dates[:-60]:
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
    """用简单规则 + 关键词匹配分析叙事（先用简单版本）"""
    results = {}
    
    for key, narrative in NARRATIVES.items():
        matched_news = []
        for news in news_list:
            title = str(news.get('title', ''))
            content = str(news.get('content', ''))
            
            # 跳过空标题
            if title == 'nan' or not title.strip():
                continue
                
            text = (title + ' ' + content).lower()
            
            if any(kw.lower() in text for kw in narrative['keywords']):
                matched_news.append(news)
        
        # 调整评分：按匹配新闻占比计算（更合理）
        match_ratio = len(matched_news) / max(len(news_list), 1) * 100
        score = min(10, int(match_ratio * 2))  # 5%匹配率 = 10分
        
        # 判断情感（简化版）
        sentiment = "利好" if score >= 5 else "中性" if score >= 3 else "利空"
        
        results[key] = {
            "score": score,
            "sentiment": sentiment,
            "summary": f"匹配到 {len(matched_news)} 条相关新闻 ({match_ratio:.1f}%)",
            "key_news": [str(n.get('title', ''))[:50] for n in matched_news[:3] if str(n.get('title', '')) != 'nan']
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


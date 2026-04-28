# -*- coding: utf-8 -*-
"""
修正Dashboard中收益列的展示：第一列周收益，第二列今年以来收益
"""
import sys
import pandas as pd
import json
from datetime import datetime, timedelta
sys.path.append('/Users/huangqingmeng/.openclaw/workspace/huofuniu-sdk/mall_sdk')

from fof99 import FundCompanyPrice, FundPrice

# 配置
APP_ID = "hfnogbr8zceiiygdkhw"
APP_KEY = "c6e941fd6aad65ceede2d780262d11ee"

# GAMT核心基金列表（带策略分类）
GAMT_FUNDS = [
    {"name": "顽岩量化选股1号", "code": "SATW62", "category": "量选类", "display_name": "量化选股（顽岩量化选股1号）"},
    {"name": "正仁股票择时一期", "code": "SARD76", "category": "量选类", "display_name": "股票择时（正仁股票择时一期）"},
    {"name": "正仁双创择时一号", "code": "SXG834", "category": "风格类", "display_name": "双创择时（正仁双创）"},
    {"name": "瀚鑫纸鸢量化优选", "code": "SZC020", "category": "风格类", "display_name": "微盘择时（瀚鑫纸鸢量化优选）", "source": "platform"},
    {"name": "积沐领航者", "code": "SAJJ91", "category": "风格类", "display_name": "1000指增（积沐领航者）"},
    {"name": "太衍光年中证2000指数增强2号", "code": "SBCA75", "category": "风格类", "display_name": "2000指增T0（太衍光年中证2000指数增强2号）"},
    {"name": "时间序列红利增强1号", "code": "SSV122", "category": "风格类", "display_name": "红利指增（时间序列红利增强）", "source": "platform"},
    {"name": "赢仕安盈二号", "code": "SLQ349", "category": "风格类", "display_name": "转债多头-集中类（赢仕安盈二号）"},
    {"name": "具力芒种1号", "code": "STE836", "category": "风格类", "display_name": "转债多头-分散类（具力芒种1号）"},
    {"name": "旌安思源1号B类", "code": "AEU46B", "category": "绝对收益", "display_name": "短线择时（旌安思源1号B类）"},
    {"name": "创世纪顾锝灵活多策略1号", "code": "SBDC67", "category": "绝对收益", "display_name": "趋势策略（创世纪顾锝灵活多策略1号）"},
    {"name": "立心-私募学院菁英353号", "code": "SCJ476", "category": "绝对收益", "display_name": "主线择时（立心-私募学院菁英353号）"},
    {"name": "翔云50二号A类", "code": "VB166A", "category": "绝对收益", "display_name": "大盘择时（翔云50二号A类）"},
    {"name": "特夫郁金香全量化", "code": "SQX078", "category": "绝对收益", "display_name": "量化打板（特夫郁金香全量化）"},
    {"name": "铭跃行远均衡一号", "code": "SVZ009", "category": "商品类", "display_name": "量化时序cta（铭跃行远均衡一号)"},
    {"name": "碳硅1号", "code": "SXJ836", "category": "商品类", "display_name": "化工-碳硅1号"},
    {"name": "涌泉君安三号", "code": "SZM385", "category": "商品类", "display_name": "黑色-涌泉君安三号"},
    {"name": "海鹏扬帆", "code": "SSR379", "category": "商品类", "display_name": "农产品-海鹏扬帆"},
    {"name": "格林基金鲲鹏6号", "code": "SVZ638", "category": "多策略", "display_name": "黄金大类（格林基金鲲鹏六号）"},
    {"name": "波克宏观配置1号", "code": "SARZ77", "category": "多策略", "display_name": "宏观大类（波克宏观配置一号）"},
]

def fetch_fund_history(fund_code, start_date="2025-01-01", source="team"):
    if source == "platform":
        req = FundPrice(APP_ID, APP_KEY)
    else:
        req = FundCompanyPrice(APP_ID, APP_KEY)
    req.set_params(reg_code=fund_code, start_date=start_date, order_by='price_date', order=1)
    data = req.do_request(use_df=False)
    return data, req.get_debug_info()

def calculate_returns(history):
    """计算：
    - 周收益：本周一(3-22) ~ 本周五(3-26)
    - 今年以来：2026-01-01 ~ 最新
    - 最新净值
    - 最大回撤
    """
    if not history or len(history) == 0:
        return None
    
    sorted_history = sorted(history, key=lambda x: x["price_date"])
    latest = sorted_history[-1]
    latest_cum_nav = latest["cumulative_nav"]
    
    returns = {}
    returns["latest_nav"] = latest["nav"]
    returns["latest_cum_nav"] = latest_cum_nav
    returns["latest_date"] = latest["price_date"]
    returns["daily_change"] = latest.get("price_change", 0) * 100
    
    # 周收益：3月22日 ~ 3月26日
    def find_nav_before(target_date):
        for item in reversed(sorted_history):
            if item["price_date"] <= target_date:
                return item["cumulative_nav"]
        return sorted_history[0]["cumulative_nav"]
    
    week_start_nav = find_nav_before("2026-03-22")
    week_end_nav = find_nav_before("2026-03-26")
    returns["week_return"] = (week_end_nav / week_start_nav - 1) * 100
    
    # 今年以来：2026-01-01 ~ 最新
    ytd_start_nav = find_nav_before("2026-01-01")
    returns["ytd_return"] = (latest_cum_nav / ytd_start_nav - 1) * 100
    
    # 最大回撤
    cumulative = [item["cumulative_nav"] for item in sorted_history]
    max_so_far = cumulative[0]
    max_drawdown = 0
    for nav in cumulative:
        if nav > max_so_far:
            max_so_far = nav
        drawdown = (max_so_far - nav) / max_so_far * 100
        if drawdown > max_drawdown:
            max_drawdown = drawdown
    returns["max_drawdown"] = max_drawdown
    
    return returns, sorted_history

def main():
    print("=== 重新计算收益（周收益+今年以来）===")
    all_results = []
    all_histories = {}
    
    for fund in GAMT_FUNDS:
        source = fund.get("source", "team")
        print(f"获取 {fund['display_name']} ...")
        history, _ = fetch_fund_history(fund["code"], start_date="2025-01-01", source=source)
        
        if not history:
            print(f"  ✗ 无数据")
            result = fund.copy()
            result["has_data"] = False
            all_results.append(result)
            continue
        
        returns_data, sorted_history = calculate_returns(history)
        all_histories[fund["code"]] = sorted_history
        
        result = fund.copy()
        result.update(returns_data)
        result["has_data"] = True
        all_results.append(result)
        
        import time
        time.sleep(0.2)
    
    # 统计
    has_data_count = sum(1 for r in all_results if r["has_data"])
    print(f"\n完成：{has_data_count}/{len(all_results)} 只有数据")
    
    # 输出对比
    print("\n=== 和你面板对比（周收益 / 今年以来收益）===")
    dream_panel = {
        "量化选股（顽岩量化选股1号）": {"week": -1.33, "ytd": +6.74},
        "股票择时（正仁股票择时一期）": {"week": -0.82, "ytd": +0.84},
        "双创择时（正仁双创）": {"week": None, "ytd": +4.03},
        "微盘择时（瀚鑫纸鸢量化优选）": {"week": -0.84, "ytd": +0.89},
        "1000指增（积沐领航者）": {"week": -2.76, "ytd": +3.87},
        "2000指增T0（太衍光年中证2000指数增强2号）": {"week": -2.75, "ytd": +2.94},
        "红利指增（时间序列红利增强）": {"week": +0.50, "ytd": +0.70},
        "转债多头-集中类（赢仕安盈二号）": {"week": -1.62, "ytd": -0.96},
        "转债多头-分散类（具力芒种1号）": {"week": -1.63, "ytd": -0.33},
        "短线择时（旌安思源1号B类）": {"week": -1.13, "ytd": -1.23},
        "趋势策略（创世纪顾锝灵活多策略1号）": {"week": -1.32, "ytd": -1.52},
        "主线择时（立心-私募学院菁英353号）": {"week": +0.27, "ytd": +1.63},
        "大盘择时（翔云50二号A类）": {"week": -1.80, "ytd": +2.11},
        "量化打板（特夫郁金香全量化）": {"week": -2.51, "ytd": +3.21},
        "量化时序cta（铭跃行远均衡一号)": {"week": -1.23, "ytd": -1.60},
        "化工-碳硅1号": {"week": -2.31, "ytd": -0.80},
        "黑色-涌泉君安三号": {"week": +1.14, "ytd": +4.74},
        "农产品-海鹏扬帆": {"week": -1.36, "ytd": +0.09},
        "黄金大类（格林基金鲲鹏六号）": {"week": +0.79, "ytd": +6.35},
        "宏观大类（波克宏观配置一号）": {"week": -0.13, "ytd": +3.31},
    }
    
    print(f"{'序号':<3} {'显示名称':<30} {'我的周':>8} {'面板周':>8} {'我的年':>8} {'面板年':>8}")
    print("-" * 75)
    for i, r in enumerate(all_results, 1):
        if not r["has_data"]:
            continue
        name = r["display_name"]
        if name in dream_panel:
            dp = dream_panel[name]
            my_week_str = f"{r['week_return']:>7.2f}%" if r.get('week_return') is not None else "   N/A  "
            my_ytd_str = f"{r['ytd_return']:>7.2f}%" if r.get('ytd_return') is not None else "   N/A  "
            dp_week_str = f"{dp['week']:>7.2f}%" if dp['week'] is not None else "   N/A  "
            dp_ytd_str = f"{dp['ytd']:>7.2f}%"
            print(f"{i:<3} {name:<30} {my_week_str} {dp_week_str} {my_ytd_str} {dp_ytd_str}")
    
    # 保存完整CSV
    all_dfs = []
    for code, history in all_histories.items():
        df = pd.DataFrame(history)
        df["code"] = code
        all_dfs.append(df)
    if all_dfs:
        full_df = pd.concat(all_dfs, ignore_index=True)
        csv_path = "/Users/huangqingmeng/.openclaw/workspace/all_full_nav_data_final.csv"
        full_df.to_csv(csv_path, index=False, encoding='utf-8')
        print(f"\n✓ 完整数据保存到 {csv_path}")
    
    # 更新HTML
    template_path = "/Users/huangqingmeng/.openclaw/workspace/GAMT_Dashboard_final_20260329.html"
    output_path = "/Users/huangqingmeng/.openclaw/workspace/GAMT_Dashboard_final.html"
    
    with open(template_path, 'r', encoding='utf-8') as f:
        html = f.read()
    
    data_json = json.dumps(all_results, ensure_ascii=False, indent=2)
    
    search_text = "const fundData = "
    if search_text in html:
        parts = html.split(search_text)
        if ";" in parts[1]:
            new_html = parts[0] + search_text + data_json + ";" + parts[1].split(";", 1)[1]
        else:
            new_html = parts[0] + search_text + data_json
    else:
        new_html = html.replace("<head>", f"<head>\n<script>\nconst fundData = {data_json};\n</script>")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(new_html)
    
    print(f"✓ 更新后的HTML保存到 {output_path}")

if __name__ == "__main__":
    main()

"""AI 算力链轮动监控 — 日更入口

用法：
    python run_daily.py              # 默认今天
    python run_daily.py 20260425     # 指定日期
"""

import sys
import json
import datetime as dt
from pathlib import Path

# 确保能 import 同目录模块
sys.path.insert(0, str(Path(__file__).parent))

from data_fetcher import fetch_all
from signal_engine import (
    calc_all_pair_zscores,
    calc_all_vol_price,
    etf_flow_summary,
    calc_etf_flow,
    composite_signal,
    label_zscore,
)

OUTPUT_DIR = Path(__file__).parent / "data"
OUTPUT_DIR.mkdir(exist_ok=True)


def run(end_date: str = None):
    if end_date is None:
        end_date = dt.date.today().strftime("%Y%m%d")

    print(f"{'='*50}")
    print(f"  AI 算力链轮动监控 — {end_date}")
    print(f"{'='*50}\n")

    # 1. 拉数据
    data = fetch_all(end_date=end_date)

    # 2. 信号层 ① — 比价 Z-score
    print("\n[信号层①] 比价 Z-score")
    pair_zscores = calc_all_pair_zscores(data["basket_prices"])
    zscore_summary = {}
    for label, df in pair_zscores.items():
        last_z = df["zscore"].dropna().iloc[-1] if not df["zscore"].dropna().empty else None
        lbl = label_zscore(last_z) if last_z is not None else "无数据"
        zscore_summary[label] = {"zscore": round(last_z, 3) if last_z else None, "label": lbl}
        print(f"  {label}: Z={last_z:.3f} → {lbl}" if last_z else f"  {label}: 无数据")

    # 3. 信号层 ② — 量价状态
    print("\n[信号层②] 量价状态分类")
    vp = calc_all_vol_price(data["basket_prices"], data["basket_amounts"])
    for name, info in vp.items():
        print(f"  {name}: {info['emoji']} {info['state']} "
              f"(5日涨幅{info.get('price_chg_5d','')}%, 量比{info.get('vol_ratio','')})")

    # 4. 信号层 ③ — ETF 资金流
    print("\n[信号层③] ETF 资金流")
    etf_sum = etf_flow_summary(data["etf_shares"])
    for name, info in etf_sum.items():
        print(f"  {name}: {info['direction']} (近5日累计 {info['recent_chg']}亿份)")

    # 5. 综合信号
    print("\n[综合信号]")
    sig = composite_signal(pair_zscores, vp, etf_sum)
    print(f"  {sig['emoji']} {sig['level']}: {sig['detail']}")

    # 6. 输出 JSON
    output = {
        "date": end_date,
        "zscore": zscore_summary,
        "vol_price": vp,
        "etf_flow": etf_sum,
        "composite": {
            "level": sig["level"],
            "emoji": sig["emoji"],
            "detail": sig["detail"],
        },
    }
    out_file = OUTPUT_DIR / f"signal_{end_date}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n✅ 结果已保存: {out_file}")

    # 同时保存一份 latest
    latest = OUTPUT_DIR / "signal_latest.json"
    with open(latest, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)

    return output


if __name__ == "__main__":
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    run(date_arg)

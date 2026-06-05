#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
接龙股票池跟踪引擎
- 解析接龙 JSON
- UQER 拉行情（基准日 + 最新）
- 计算: 共识度、绝对收益、相对沪深300超额、动量
- 输出: 个股跟踪表 + 推荐人胜率榜 + 题材热度
用法: /opt/homebrew/bin/python3 track.py [接龙json] [最新交易日YYYYMMDD]
"""
from __future__ import annotations
import json, sys
from pathlib import Path
from collections import defaultdict, Counter

BASE = Path(__file__).resolve().parent
TOKEN_FILE = Path("/Users/apple/Desktop/quant-backtest/timing_model/config/uqer_token.json")

# 题材映射
SECTOR = {
    "688347":"半导体代工","603986":"半导体存储","688008":"半导体存储","688798":"半导体封测",
    "688396":"功率半导体","688052":"功率半导体","688630":"半导体设备","603078":"半导体材料",
    "002824":"液冷/算力","300903":"液冷/算力","000700":"机器人/散热",
    "300088":"玻璃基板/TGV","301188":"玻璃基板/TGV",
    "300394":"光通信/CPO","300620":"光通信/CPO","301205":"光通信/CPO","603083":"光通信/CPO",
    "688143":"光通信/CPO","600105":"光通信/CPO","300814":"光通信/CPO",
    "603678":"MLCC/被动","002859":"MLCC/被动","300408":"MLCC/被动","002484":"MLCC/被动","688601":"MLCC/被动",
    "002851":"工控/电源","300870":"工控/电源","603063":"工控/电源","688612":"工控/电源","688663":"工控/电源",
    "300679":"消费电子","002463":"PCB","002428":"战略材料","600459":"战略材料","600330":"战略材料",
    "301021":"激光设备","688301":"检测设备","301236":"华为生态","603501":"图像传感器",
    "688146":"特种气体","600367":"军工化工","605277":"其他电子","603687":"包装","300566":"光学膜",
    "688371":"涂层","003036":"电子织造","002536":"汽车零部件","000725":"面板","600246":"地产",
    "688668":"连接器","301528":"PCB耗材","688798":"半导体封测",
}

def load_token():
    return json.loads(TOKEN_FILE.read_text(encoding="utf-8"))["token"]

def main():
    jl_file = sys.argv[1] if len(sys.argv) > 1 else str(BASE/"data/jielong_2026-06-03.json")
    jl = json.loads(Path(jl_file).read_text(encoding="utf-8"))
    base_date = jl["date"].replace("-", "")
    latest = sys.argv[2] if len(sys.argv) > 2 else base_date

    # 收集有效 ticker
    tickers = set()
    ticker_names = {}
    rec_by_ticker = defaultdict(list)   # ticker -> [推荐人]
    person_tickers = defaultdict(list)  # 推荐人 -> [ticker]
    for p in jl["picks"]:
        for t in p["tickers"]:
            tk = t["ticker"].strip()
            if tk:
                tickers.add(tk)
                ticker_names[tk] = t["name"]
                rec_by_ticker[tk].append(p["person"])
                person_tickers[p["person"]].append((tk, t["name"]))

    import uqer
    from uqer import DataAPI
    uqer.Client(token=load_token())

    def fetch(date):
        df = DataAPI.MktEqudAdjGet(
            ticker=",".join(sorted(tickers)), beginDate=date, endDate=date,
            field="ticker,secShortName,closePrice,turnoverRate,negMarketValue", pandas="1")
        return {r["ticker"]: r for _, r in df.iterrows()}

    base = fetch(base_date)
    cur = fetch(latest) if latest != base_date else base

    # 沪深300 超额基准
    def idx_ret():
        try:
            d = DataAPI.MktIdxdGet(ticker="000300", beginDate=base_date, endDate=latest,
                                   field="tradeDate,closeIndex", pandas="1")
            if len(d) >= 2:
                return (d.iloc[-1]["closeIndex"]/d.iloc[0]["closeIndex"]-1)*100
        except Exception:
            pass
        return 0.0
    hs300 = idx_ret()

    # 个股表
    rows = []
    invalid = []
    for tk in sorted(tickers):
        if tk not in base:
            invalid.append(f"{ticker_names.get(tk,'?')}({tk})")
            continue
        bp = base[tk]["closePrice"]
        cp = cur.get(tk, {}).get("closePrice", bp)
        ret = (cp/bp-1)*100 if bp else 0
        rows.append({
            "ticker": tk, "name": base[tk]["secShortName"],
            "consensus": len(rec_by_ticker[tk]),
            "base": bp, "cur": cp, "ret": ret, "excess": ret-hs300,
            "sector": SECTOR.get(tk, "其他"),
            "recs": rec_by_ticker[tk],
        })

    # 推荐人胜率
    person_perf = []
    rmap = {r["ticker"]: r["ret"] for r in rows}
    for person, tks in person_tickers.items():
        rets = [rmap[tk] for tk, _ in tks if tk in rmap]
        if rets:
            person_perf.append({"person": person, "n": len(rets),
                                "avg": sum(rets)/len(rets),
                                "picks": [(nm, rmap.get(tk)) for tk, nm in tks if tk in rmap]})

    # 题材热度
    sector_cnt = Counter(r["sector"] for r in rows)

    print(json.dumps({
        "base_date": base_date, "latest": latest, "hs300_ret": round(hs300,2),
        "n_valid": len(rows), "invalid_tickers": invalid,
        "stocks": sorted(rows, key=lambda x: (-x["consensus"], -x["ret"])),
        "persons": sorted(person_perf, key=lambda x: -x["avg"]),
        "sectors": sector_cnt.most_common(),
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()

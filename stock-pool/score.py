#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
接龙股票池 - 多因子量价打分引擎 v2（含缠论多级别）
四层模型:
  A. 量价选股层: RS相对强度 / 量能确认 / 趋势(MA站位) / 拥挤度惩罚
  B. Barra择时层: 小市值+动量因子滚动收益 -> 风格顺风度系数(0~1)
  C. 共识层: 接龙被推荐人数
  D. 缠论多级别层:
       大级别(60日日线)   -> 趋势方向系数
       中级别(20日日线)   -> 中枢位置 + 背驰信号
       小级别(10日日线)   -> 买卖点信号

综合分 = (w_rs*RS + w_vol*量能 + w_trend*MA + w_con*共识 - w_crowd*拥挤
          + w_chan*缠论分) * Barra环境系数 * 大级别趋势系数
用法: /opt/homebrew/bin/python3 score.py [接龙json] [截止日YYYYMMDD]
"""
from __future__ import annotations
import json, sys
from pathlib import Path
from collections import defaultdict, Counter
import pandas as pd
import numpy as np

BASE = Path(__file__).resolve().parent
TOKEN_FILE = Path("/Users/apple/Desktop/quant-backtest/timing_model/config/uqer_token.json")
LOOKBACK = 20

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
    "688668":"连接器","301528":"PCB耗材",
}

def zscore(s):
    s = pd.Series(s, dtype="float64")
    if s.std(ddof=0) == 0 or s.isna().all():
        return pd.Series([0.0]*len(s), index=s.index)
    return (s - s.mean()) / s.std(ddof=0)

# ── 缠论信号 -> 分值映射 ──────────────────────────────────────────────
CHAN_SIGNAL_SCORE = {
    "一类买点(底背驰)":   2.0,   # 强买入信号
    "三类买点(中枢上突)": 1.5,   # 中强
    None:                 0.0,   # 无信号
    "三类卖点(中枢下破)":-1.5,   # 中强卖出
    "一类卖点(顶背驰)":  -2.0,   # 强卖出信号
}
CHAN_POS_SCORE = {
    "中枢上方(强)":  0.5,
    "中枢内(震荡)":  0.0,
    "中枢下方(弱)": -0.5,
    None:            0.0,
}
CHAN_TREND_COEF = {
    "上涨趋势": 1.20,
    "上行(未完成笔)": 1.15,
    "上行":     1.10,
    "中枢震荡": 1.00,
    "震荡":     1.00,
    "下行":     0.85,
    "下行(未完成笔)": 0.80,
    "下跌趋势": 0.70,
}

def chan_score_for(daily_g, weekly_g, min30_g, ticker):
    """真三级别缠论打分: 周线(大)/日线(中)/30分钟(小)。
    返回 (chan_score, trend_coef, details)。"""
    from chan import analyze_multi
    res = analyze_multi(daily_g, weekly_g, min30_g)

    trend_coef = CHAN_TREND_COEF.get(res.get("big_trend", "震荡"), 1.0)

    # 中级别: 中枢位置 + 背驰
    mid_score = CHAN_POS_SCORE.get(res.get("mid_pos"), 0.0)
    if res.get("mid_div") == "bot": mid_score += 1.0
    elif res.get("mid_div") == "top": mid_score -= 1.0

    # 小级别: 买卖点信号（30分钟，精度更高）
    small_score = CHAN_SIGNAL_SCORE.get(res.get("small_signal"), 0.0)
    # 小级别背驰也计入
    if res.get("small_div") == "bot": small_score += 0.5
    elif res.get("small_div") == "top": small_score -= 0.5

    chan_raw = mid_score * 0.6 + small_score * 0.4

    details = {
        "big_trend":    res.get("big_trend"),
        "mid_pos":      res.get("mid_pos"),
        "mid_div":      res.get("mid_div"),
        "small_signal": res.get("small_signal"),
        "small_div":    res.get("small_div"),
        "chan_score":   round(chan_raw, 2),
        "trend_coef":   trend_coef,
    }
    return chan_raw, trend_coef, details


def main():
    jl_file = sys.argv[1] if len(sys.argv) > 1 else str(BASE/"data/jielong_2026-06-03.json")
    jl = json.loads(Path(jl_file).read_text(encoding="utf-8"))
    end_date = sys.argv[2] if len(sys.argv) > 2 else "20260605"

    tickers, names = set(), {}
    rec_by_ticker = defaultdict(list)
    for p in jl["picks"]:
        for t in p["tickers"]:
            tk = t["ticker"].strip()
            if tk:
                tickers.add(tk); names[tk] = t["name"]
                rec_by_ticker[tk].append(p["person"])

    import datafeed as F
    import uqer
    from uqer import DataAPI
    uqer.Client(token=json.loads(TOKEN_FILE.read_text())["token"])

    cal = DataAPI.TradeCalGet(exchangeCD="XSHG", beginDate="20260101", endDate=end_date,
                              field="calendarDate,isOpen", pandas="1")
    opens = [d.replace("-","") for d, o in zip(cal["calendarDate"], cal["isOpen"]) if o == 1]
    win = opens[-(60+1):]   # 最近60日给量价用
    begin = win[0]

    tickers_sorted = sorted(tickers)
    # 日线(量价+缠论中级别) / 周线(缠论大级别) / 30分钟(缠论小级别)
    daily_map  = F.get_daily(tickers_sorted, begin, end_date)
    weekly_map = F.get_weekly(tickers_sorted, "20250901", end_date)
    # 30分钟: 最近约20交易日窗口
    m30_begin = f"{win[-20][:4]}-{win[-20][4:6]}-{win[-20][6:]} 09:00:00" if len(win) >= 20 else f"{begin[:4]}-{begin[4:6]}-{begin[6:]} 09:00:00"
    m30_end   = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:]} 15:30:00"

    # Barra 择时
    barra = F.get_barra_factor_returns(begin, end_date)
    sml5  = -barra["SIZE"].astype(float).tail(5).sum()
    mom5  = barra["MOMENTUM"].astype(float).tail(5).sum()
    rv5   = barra["RESVOL"].astype(float).tail(5).sum()
    raw_env = sml5*0.5 + mom5*0.3 + rv5*0.1
    env_coef = float(1/(1+np.exp(-raw_env*30)))

    # 逐票打分
    rows = []
    for tk in tickers_sorted:
        g = daily_map.get(tk)
        if g is None or len(g) < 6: continue
        close = g["close"].astype(float).values
        tr    = g["turn"].astype(float).values
        hi    = g["high"].astype(float).values
        lo    = g["low"].astype(float).values
        pc    = g["preclose"].astype(float).values
        vcol  = g["vol"].astype(float).values

        # 量价层（取最近20日）
        g20 = g.tail(LOOKBACK+1)
        c20 = g20["close"].astype(float).values
        v20 = g20["vol"].astype(float).values
        ret20 = (c20[-1]/c20[0]-1)*100
        ret5  = (c20[-1]/c20[-6]-1)*100 if len(c20)>6 else ret20
        ma5   = c20[-5:].mean(); ma20 = c20.mean()
        ma_pos = (1 if c20[-1]>ma5 else 0)+(1 if c20[-1]>ma20 else 0)+(1 if ma5>ma20 else 0)
        vol_ratio = v20[-1]/v20[-6:-1].mean() if v20[-6:-1].mean()>0 else 1.0
        up = c20[-1] >= pc[-1]
        vol_confirm = vol_ratio if up else -vol_ratio
        crowd = tr[-1] + ((hi[-5:].max()-lo[-5:].min())/c20[-1])*100*0.3

        # 缠论层（真三级别）
        wk = weekly_map.get(tk)
        m30 = F.get_30min(tk, m30_begin, m30_end)
        chan_s, trend_coef, chan_detail = chan_score_for(g, wk, m30, tk)

        rows.append({
            "ticker": tk, "name": names[tk], "sector": SECTOR.get(tk,"其他"),
            "consensus": len(rec_by_ticker[tk]), "recs": rec_by_ticker[tk],
            "ret20": ret20, "ret5": ret5, "ma_pos": ma_pos,
            "vol_ratio": vol_ratio, "vol_confirm": vol_confirm, "turn": tr[-1], "crowd": crowd,
            "chan_score": chan_s, "trend_coef": trend_coef, **chan_detail,
        })

    df = pd.DataFrame(rows)

    # ── 两个正交维度，避免动量因子被重复打分 ──────────────────
    # 维度1: 质量分(quality) = 结构 + 共识 + 环境，刻意不含动量
    #   缠论(中枢/买卖点) + 共识度 + 量能配合 - 拥挤度
    # 维度2: 动量分(momentum) = 纯涨幅，独立展示，不混入质量
    Wq = dict(chan=0.45, con=0.25, vol=0.20, crowd=0.10)
    df["z_chan"]  = zscore(df["chan_score"])
    df["z_con"]   = zscore(df["consensus"])
    df["z_vol"]   = zscore(df["vol_confirm"])
    df["z_crowd"] = zscore(df["crowd"])
    df["quality"] = (Wq["chan"]*df["z_chan"] + Wq["con"]*df["z_con"]
                     + Wq["vol"]*df["z_vol"] - Wq["crowd"]*df["z_crowd"])
    # 质量分仍受风格环境调节（逆风时结构再好也打折），但不再乘趋势系数（趋势=动量，已独立）
    df["quality"] = df["quality"] * env_coef

    # 动量分: 20日(0.6)+5日(0.4) 标准化，纯粹反映"最近涨了多少"
    df["momentum"] = zscore(df["ret20"])*0.6 + zscore(df["ret5"])*0.4

    # 综合分: 质量为主(0.65) + 动量为辅(0.35)，但二者都会在前端独立展示
    df["score"] = df["quality"]*0.65 + df["momentum"]*0.35
    df["base_score"] = df["quality"]   # 兼容旧字段
    df = df.sort_values("score", ascending=False).reset_index(drop=True)
    df["rank"] = df.index + 1

    # 四象限分类: 质量高低 × 动量高低（中位数切分）
    q_med = df["quality"].median(); m_med = df["momentum"].median()
    def quadrant(r):
        hq = r["quality"] >= q_med
        hm = r["momentum"] >= m_med
        if hq and hm:  return "买点(质优+动量)"
        if hq and not hm: return "埋伏(质优+待启动)"
        if not hq and hm: return "追高(动量+结构弱)"
        return "回避(双弱)"
    df["quadrant"] = df.apply(quadrant, axis=1)

    sec_mood = df.groupby("sector")["ret20"].agg(["mean","count"]).sort_values("mean", ascending=False)

    out = {
        "end_date": end_date, "lookback": LOOKBACK,
        "env": {"coef": round(env_coef,3), "sml5": round(sml5,3),
                "mom5": round(mom5,3), "rv5": round(rv5,3),
                "verdict": "顺风" if env_coef>0.55 else ("逆风" if env_coef<0.45 else "中性")},
        "ranking": df[[
            "rank","name","ticker","sector","consensus","score","quality","momentum","quadrant",
            "ret20","ret5","ma_pos","vol_ratio","turn","crowd",
            "chan_score","big_trend","mid_pos","mid_div","small_signal","trend_coef","recs"
        ]].to_dict("records"),
        "sector_mood": [{"sector":s,"avg_ret20":round(r["mean"],2),"n":int(r["count"])}
                        for s,r in sec_mood.iterrows()],
    }
    print(json.dumps(out, ensure_ascii=False, indent=2, default=float))

if __name__ == "__main__":
    main()

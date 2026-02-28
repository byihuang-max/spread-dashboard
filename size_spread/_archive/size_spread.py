#!/usr/bin/env python3
"""中证2000-沪深300 大小盘轧差策略净值图 (iFind版)"""
import json, requests, datetime, csv, os, time

# === iFind 配置 ===
IFIND_BASE = "https://quantapi.51ifind.com/api/v1"
REFRESH_TOKEN = "eyJzaWduX3RpbWUiOiIyMDI2LTAyLTA5IDE5OjE3OjQwIn0=.eyJ1aWQiOiI4NDQ3MzY2NjMiLCJ1c2VyIjp7ImFjY291bnQiOiJncnN6aDAwMSIsImF1dGhVc2VySW5mbyI6eyJhcGlGb3JtYWwiOiIxIn0sImNvZGVDU0kiOltdLCJjb2RlWnpBdXRoIjpbXSwiaGFzQUlQcmVkaWN0IjpmYWxzZSwiaGFzQUlUYWxrIjpmYWxzZSwiaGFzQ0lDQyI6ZmFsc2UsImhhc0NTSSI6ZmFsc2UsImhhc0V2ZW50RHJpdmUiOmZhbHNlLCJoYXNGVFNFIjpmYWxzZSwiaGFzRmFzdCI6ZmFsc2UsImhhc0Z1bmRWYWx1YXRpb24iOmZhbHNlLCJoYXNISyI6dHJ1ZSwiaGFzTE1FIjpmYWxzZSwiaGFzTGV2ZWwyIjpmYWxzZSwiaGFzUmVhbENNRSI6ZmFsc2UsImhhc1RyYW5zZmVyIjpmYWxzZSwiaGFzVVMiOmZhbHNlLCJoYXNVU0FJbmRleCI6ZmFsc2UsImhhc1VTREVCVCI6ZmFsc2UsIm1hcmtldEF1dGgiOnsiRENFIjpmYWxzZX0sIm1heE9uTGluZSI6MSwibm9EaXNrIjpmYWxzZSwicHJvZHVjdFR5cGUiOiJTVVBFUkNPTU1BTkRQUk9EVUNUIiwicmVmcmVzaFRva2VuRXhwaXJlZFRpbWUiOiIyMDI2LTAzLTA5IDE5OjAwOjU1Iiwic2Vzc3Npb24iOiI0YzRjYjhhNTdiNWQwYzA3N2UxNTEwMzIxN2M2YWNjYSIsInNpZEluZm8iOns2NDoiMTExMTExMTExMTExMTExMTExMTExMTExIiwxOiIxMDEiLDI6IjEiLDY3OiIxMDExMTExMTExMTExMTExMTExMTExMTEiLDM6IjEiLDY5OiIxMTExMTExMTExMTExMTExMTExMTExMTExIiw1OiIxIiw2OiIxIiw3MToiMTExMTExMTExMTExMTExMTExMTExMTAwIiw3OiIxMTExMTExMTExMSIsODoiMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDEiLDEzODoiMTExMTExMTExMTExMTExMTExMTExMTExMSIsMTM5OiIxMTExMTExMTExMTExMTExMTExMTExMTExIiwxNDA6IjExMTExMTExMTExMTExMTExMTExMTExMTEiLDE0MToiMTExMTExMTExMTExMTExMTExMTExMTExMSIsMTQyOiIxMTExMTExMTExMTExMTExMTExMTExMTExIiwxNDM6IjExIiw4MDoiMTExMTExMTExMTExMTExMTExMTExMTExIiw4MToiMTExMTExMTExMTExMTExMTExMTExMTExIiw4MjoiMTExMTExMTExMTExMTExMTExMTEwMTEwIiw4MzoiMTExMTExMTExMTExMTExMTExMDAwMDAwIiw4NToiMDExMTExMTExMTExMTExMTExMTExMTExIiw4NzoiMTExMTExMTEwMDExMTExMDExMTExMTExIiw4OToiMTExMTExMTEwMTEwMTExMTExMTAxMTExIiw5MDoiMTExMTEwMTExMTExMTExMTExMTExMTExMTAiLDkzOiIxMTExMTExMTExMTExMTExMTAwMDAxMTExIiw5NDoiMTExMTExMTExMTExMTExMTExMTExMTExMSIsOTY6IjExMTExMTExMTExMTExMTExMTExMTExMTEiLDk5OiIxMDAiLDEwMDoiMTExMTAxMTExMTExMTExMTExMCIsMTAyOiIxIiw0NDoiMTEiLDEwOToiMSIsNTM6IjExMTExMTExMTExMTExMTExMTExMTExMSIsNTQ6IjExMDAwMDAwMDAxMTAwMDAwMTAxMDAwMDAxMDAxMDAwMDAwIiw1NzoiMDAwMDAwMDAwMDAwMDAwMDAwMDAxMDAwMDAwMDAiLDYyOiIxMTExMTExMTExMTExMTExMTExMTExMTEiLDYzOiIxMTExMTExMTExMTExMTExMTExMTExMTEifSwidGltZXN0YW1wIjoiMTc3MDYzNTg2MDcxOSIsInRyYW5zQXV0aCI6ZmFsc2UsInR0bFZhbHVlIjowLCJ1aWQiOiI4NDQ3MzY2NjMiLCJ1c2VyVHlwZSI6Ik9GRklDSUFMIiwid2lmaW5kTGltaXRNYXAiOnt9fX0=.7AAB9445C9074F4FD9C933A4ECF96C3359428E3393255673AFE507504D9E7270"

# === Tushare 配置（备用） ===
TS_TOKEN = "8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae"
TS_URL = "https://api.tushare.pro"

def ts(api, params, fields=''):
    body = {"api_name": api, "token": TS_TOKEN, "params": params}
    if fields:
        body["fields"] = fields
    for attempt in range(3):
        try:
            r = requests.post(TS_URL, json=body, timeout=30)
            if not r.text.strip():
                print(f"  TS空响应，重试 {attempt+1}/3...")
                time.sleep(2)
                continue
            d = r.json()
            if d.get("data") and d["data"].get("fields") and d["data"].get("items"):
                return [dict(zip(d["data"]["fields"], row)) for row in d["data"]["items"]]
            return []
        except Exception as e:
            print(f"  TS请求失败: {e}，重试 {attempt+1}/3...")
            time.sleep(2)
    return []

def get_ifind_token():
    r = requests.post(f"{IFIND_BASE}/get_access_token",
                      json={"refresh_token": REFRESH_TOKEN}, timeout=15)
    d = r.json()
    if d.get("data", {}).get("access_token"):
        return d["data"]["access_token"]
    raise Exception(f"iFind token 失败: {d}")

def ifind_date_seq(at, code, indicator, start, end):
    """iFind date_sequence 拉历史数据"""
    for attempt in range(2):
        try:
            r = requests.post(f"{IFIND_BASE}/date_sequence",
                headers={"access_token": at, "Content-Type": "application/json"},
                json={
                    "codes": code,
                    "indicators": indicator,
                    "startdate": start,
                    "enddate": end,
                },
                timeout=30)
            d = r.json()
            if d.get("errorcode") == 0 and d.get("tables"):
                return d["tables"]
            print(f"  iFind返回: {d.get('errmsg', d)}")
            return None
        except Exception as e:
            print(f"  iFind请求失败: {e}，重试...")
            time.sleep(2)
    return None

# === 主逻辑 ===
today = datetime.date.today()
start = (today - datetime.timedelta(days=70)).strftime("%Y-%m-%d")
end = today.strftime("%Y-%m-%d")
start_ts = (today - datetime.timedelta(days=70)).strftime("%Y%m%d")
end_ts = today.strftime("%Y%m%d")

print("获取 iFind access_token...")
at = get_ifind_token()
print("  OK")

# 先尝试 iFind
print(f"拉中证2000 收盘价 ({start} ~ {end})...")
zz2000_tables = ifind_date_seq(at, "932000.CSI", "close", start, end)

print(f"拉沪深300 收盘价 ({start} ~ {end})...")
hs300_tables = ifind_date_seq(at, "000300.SH", "close", start, end)

# 解析 iFind 数据
def parse_ifind_table(tables):
    """从 iFind date_sequence 返回值解析日期→收盘价"""
    if not tables or not tables[0].get("table"):
        return {}
    t = tables[0]["table"]
    dates = t.get("time", [])
    values = t.get("close", t.get("value", []))
    # 如果 close 不在，尝试第一个非 time 的 key
    if not values:
        for k, v in t.items():
            if k != "time" and isinstance(v, list):
                values = v
                break
    result = {}
    for i, dt in enumerate(dates):
        if i < len(values) and values[i] is not None:
            result[dt.replace("-", "")] = float(values[i])
    return result

zz2000_data = parse_ifind_table(zz2000_tables) if zz2000_tables else {}
hs300_data = parse_ifind_table(hs300_tables) if hs300_tables else {}

print(f"  中证2000: {len(zz2000_data)} 天")
print(f"  沪深300: {len(hs300_data)} 天")

# 如果 iFind 失败，回退到 Tushare
if not zz2000_data:
    print("iFind 中证2000 失败，尝试 Tushare...")
    d = ts('index_daily', {'ts_code': '932000.CSI', 'start_date': start_ts, 'end_date': end_ts}, fields='trade_date,close')
    if d:
        zz2000_data = {r['trade_date']: float(r['close']) for r in d}
        print(f"  Tushare 中证2000: {len(zz2000_data)} 天")

if not hs300_data:
    print("iFind 沪深300 失败，尝试 Tushare...")
    d = ts('index_daily', {'ts_code': '000300.SH', 'start_date': start_ts, 'end_date': end_ts}, fields='trade_date,close')
    if d:
        hs300_data = {r['trade_date']: float(r['close']) for r in d}
        print(f"  Tushare 沪深300: {len(hs300_data)} 天")

if not zz2000_data or not hs300_data:
    print("❌ 数据不足，无法生成")
    exit(1)

# 找共同日期，按升序排列
common_dates = sorted(set(zz2000_data.keys()) & set(hs300_data.keys()))
print(f"共同交易日: {len(common_dates)} 天 ({common_dates[0]} ~ {common_dates[-1]})")

# 计算每日涨跌幅和轧差
rows = []
nav = 1.0
prev_zz = None
prev_hs = None
for dt in common_dates:
    zz_close = zz2000_data[dt]
    hs_close = hs300_data[dt]
    if prev_zz is not None and prev_hs is not None:
        zz_chg = (zz_close / prev_zz - 1) * 100
        hs_chg = (hs_close / prev_hs - 1) * 100
        spread = zz_chg - hs_chg
        nav *= (1 + spread / 100)
        rows.append({
            'date': dt,
            'zz2000_close': round(zz_close, 2),
            'hs300_close': round(hs_close, 2),
            'zz2000_chg': round(zz_chg, 4),
            'hs300_chg': round(hs_chg, 4),
            'spread': round(spread, 4),
            'nav': round(nav, 6)
        })
    prev_zz = zz_close
    prev_hs = hs_close

# 写CSV
csv_path = os.path.expanduser("~/Desktop/size_spread.csv")
with open(csv_path, 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['date', 'zz2000_close', 'hs300_close', 'zz2000_chg', 'hs300_chg', 'spread', 'nav'])
    w.writeheader()
    w.writerows(rows)
print(f"CSV 已保存: {csv_path} ({len(rows)} 行)")

# 生成 HTML 净值图
html_path = os.path.expanduser("~/Desktop/size_spread.html")
dates_js = [r['date'] for r in rows]
navs_js = [r['nav'] for r in rows]
spreads_js = [r['spread'] for r in rows]

# 格式化日期显示
dates_fmt = [f"{d[4:6]}/{d[6:8]}" for d in dates_js]

html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>大小盘轧差策略净值</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
body{{font-family:'PingFang SC',sans-serif;max-width:1000px;margin:40px auto;padding:0 20px;background:#fafafa}}
h2{{text-align:center;color:#333}}
p.sub{{text-align:center;color:#888;font-size:14px;margin-top:-10px}}
.stats{{display:flex;justify-content:center;gap:30px;margin:20px 0;font-size:14px}}
.stat{{background:#fff;padding:12px 20px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.1)}}
.stat .label{{color:#888;font-size:12px}}
.stat .value{{font-size:20px;font-weight:bold;margin-top:4px}}
.pos{{color:#e74c3c}} .neg{{color:#2ecc71}}
canvas{{margin-top:20px;background:#fff;border-radius:8px;padding:10px;box-shadow:0 1px 3px rgba(0,0,0,0.1)}}
</style>
</head><body>
<h2>中证2000 - 沪深300 大小盘轧差策略</h2>
<p class="sub">每日轧差 = 中证2000涨跌幅 - 沪深300涨跌幅 | 归1复利净值 | {dates_js[0]}~{dates_js[-1]}</p>

<div class="stats">
  <div class="stat">
    <div class="label">最终净值</div>
    <div class="value {'pos' if navs_js[-1]>=1 else 'neg'}">{navs_js[-1]:.4f}</div>
  </div>
  <div class="stat">
    <div class="label">累计收益</div>
    <div class="value {'pos' if navs_js[-1]>=1 else 'neg'}">{(navs_js[-1]-1)*100:+.2f}%</div>
  </div>
  <div class="stat">
    <div class="label">最大轧差</div>
    <div class="value pos">{max(spreads_js):+.2f}%</div>
  </div>
  <div class="stat">
    <div class="label">最小轧差</div>
    <div class="value neg">{min(spreads_js):+.2f}%</div>
  </div>
</div>

<canvas id="navChart" height="100"></canvas>
<canvas id="spreadChart" height="80"></canvas>
<script>
const dates = {json.dumps(dates_fmt)};
const navs = {json.dumps(navs_js)};
const spreads = {json.dumps(spreads_js)};

new Chart(document.getElementById('navChart'), {{
  type: 'line',
  data: {{
    labels: dates,
    datasets: [{{
      label: '归1净值',
      data: navs,
      borderColor: '#e74c3c',
      backgroundColor: 'rgba(231,76,60,0.08)',
      fill: true,
      tension: 0.3,
      pointRadius: 1.5,
      borderWidth: 2
    }}]
  }},
  options: {{
    plugins: {{
      title: {{display: true, text: '大小盘轧差策略净值（归1）', font: {{size: 14}}}},
      legend: {{display: false}}
    }},
    scales: {{
      x: {{ticks: {{maxTicksLimit: 12}}}},
      y: {{title: {{display: true, text: '净值'}}}}
    }}
  }}
}});

new Chart(document.getElementById('spreadChart'), {{
  type: 'bar',
  data: {{
    labels: dates,
    datasets: [{{
      label: '每日轧差(%)',
      data: spreads,
      backgroundColor: spreads.map(v => v >= 0 ? 'rgba(231,76,60,0.6)' : 'rgba(52,152,219,0.6)'),
      borderRadius: 2
    }}]
  }},
  options: {{
    plugins: {{
      title: {{display: true, text: '每日涨跌幅轧差（中证2000 - 沪深300）', font: {{size: 14}}}},
      legend: {{display: false}}
    }},
    scales: {{
      x: {{ticks: {{maxTicksLimit: 12}}}},
      y: {{title: {{display: true, text: '%'}}}}
    }}
  }}
}});
</script>
</body></html>"""

with open(html_path, 'w') as f:
    f.write(html)
print(f"净值图已保存: {html_path}")
print(f"\n✅ 完成！最终净值 {navs_js[-1]:.4f}，累计收益 {(navs_js[-1]-1)*100:+.2f}%")

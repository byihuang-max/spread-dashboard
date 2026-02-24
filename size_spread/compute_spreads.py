import json
import statistics
import os
import csv

CACHE_FILE_PATH = os.path.expanduser('~/Desktop/gamt-dashboard/size_spread/style_spread_cache.json')
STYLE_SPREAD_JSON_PATH = os.path.expanduser('~/Desktop/gamt-dashboard/data/style_spread.json')
SHEET1_CSV_PATH = os.path.expanduser('~/Desktop/gamt-dashboard/size_spread/style_spread_sheet1.csv')
SHEET2_CSV_PATH = os.path.expanduser('~/Desktop/gamt-dashboard/size_spread/style_spread_sheet2.csv')
SHEET3_CSV_PATH = os.path.expanduser('~/Desktop/gamt-dashboard/size_spread/style_spread_sheet3.csv')
SHEET4_CSV_PATH = os.path.expanduser('~/Desktop/gamt-dashboard/size_spread/style_spread_sheet4.csv')

# Ensure directory exists
os.makedirs(os.path.dirname(STYLE_SPREAD_JSON_PATH), exist_ok=True)
os.makedirs(os.path.dirname(SHEET1_CSV_PATH), exist_ok=True)

# Load cache data
def load_cache_data():
    with open(CACHE_FILE_PATH, 'r') as f:
        return json.load(f)

cache_data = load_cache_data()
index_daily = cache_data.get('index_daily', {})
sw_daily = cache_data.get('sw_daily', {})

# Sheet1: 风格轧差
def compute_style_spread(index_daily):
    pairs = [
        ('000922.CSI', '000688.SH', '中证红利', '科创50'),
        ('399303.SZ', '000985.CSI', '微盘股', '中证全指'),
        ('932000.CSI', '000300.SH', '中证2000', '沪深300'),
    ]

    results = {}
    for idx1, idx2, long_name, short_name in pairs:
        if idx1 not in index_daily or idx2 not in index_daily:
            continue

        data1 = index_daily[idx1]['data']
        data2 = index_daily[idx2]['data']

        common_dates = set(data1.keys()).intersection(set(data2.keys()))
        common_dates = sorted(common_dates)

        spreads, navs = [], []
        nav = 1.0
        for date in common_dates:
            spread = data1[date]['pct_chg'] - data2[date]['pct_chg']
            nav *= (1 + spread / 100)
            spreads.append(spread)
            navs.append(nav)

        key_name = f'{long_name}-{short_name}'
        results[key_name] = {
            'dates': [d[4:6] + '/' + d[-2:] for d in common_dates],  # MM/DD
            'navs': navs,
            'spreads': spreads,
        }
    return results

# Sheet2: 双创等权
def compute_dual_innovation(index_daily):
    cyb_code = '399006.SZ'
    kc50_code = '000688.SH'

    cyb_data = index_daily[cyb_code]['data']
    kc50_data = index_daily[kc50_code]['data']

    common_dates = set(cyb_data.keys()).intersection(set(kc50_data.keys()))
    common_dates = sorted(common_dates)

    navs, cyb_chg, kc50_chg = [], [], []
    nav = 1.0
    for date in common_dates:
        avg_chg = (cyb_data[date]['pct_chg'] + kc50_data[date]['pct_chg']) / 2
        nav *= (1 + avg_chg / 100)
        navs.append(nav)
        cyb_chg.append(cyb_data[date]['pct_chg'])
        kc50_chg.append(kc50_data[date]['pct_chg'])

    return {
        'dates': [d[4:6] + '/' + d[-2:] for d in common_dates],  # MM/DD
        'navs': navs,
        'cyb_chg': cyb_chg,
        'kc50_chg': kc50_chg,
    }

# Sheet3: 经济敏感轧差
def compute_eco_sensitive(sw_daily):
    cycle_codes = ['801050.SI', '801950.SI', '801040.SI']
    defense_codes = ['801120.SI', '801150.SI']

    navs, cycle_chg, defense_chg, spreads = [], [], [], []
    nav = 1.0

    # Assume all codes have the same dates
    common_dates = sorted(list(sw_daily[cycle_codes[0]]['data'].keys()))

    for date in common_dates:
        avg_cycle_chg = sum(sw_daily[code]['data'][date]['pct_change'] for code in cycle_codes) / len(cycle_codes)
        avg_defense_chg = sum(sw_daily[code]['data'][date]['pct_change'] for code in defense_codes) / len(defense_codes)

        spread = avg_cycle_chg - avg_defense_chg
        nav *= (1 + spread / 100)

        cycle_chg.append(avg_cycle_chg)
        defense_chg.append(avg_defense_chg)
        spreads.append(spread)
        navs.append(nav)

    return {
        'cycle_names': [sw_daily[code]['name'] for code in cycle_codes],
        'defense_names': [sw_daily[code]['name'] for code in defense_codes],
        'dates': [d[4:6] + '/' + d[-2:] for d in common_dates],  # MM/DD
        'cycle_chg': cycle_chg,
        'defense_chg': defense_chg,
        'spreads': spreads,
        'navs': navs,
    }

# Sheet4: 拥挤-反身性轧差
def compute_crowding(sw_daily):
    sw_all_codes = [
        '801010.SI', '801030.SI', '801040.SI', '801050.SI', '801080.SI', '801880.SI',
        '801110.SI', '801120.SI', '801130.SI', '801140.SI', '801150.SI', '801160.SI',
        '801170.SI', '801180.SI', '801200.SI', '801210.SI', '801780.SI', '801790.SI',
        '801230.SI', '801710.SI', '801720.SI', '801730.SI', '801890.SI', '801740.SI',
        '801750.SI', '801760.SI', '801770.SI', '801950.SI', '801960.SI', '801970.SI',
        '801980.SI',
    ]
    LOOKBACK = 20
    TOP_N = 6

    navs, top_chg, bot_chg, spreads, top_names, bot_names = [], [], [], [], [], []
    nav = 1.0

    common_dates = sorted(sw_daily[sw_all_codes[0]]['data'].keys())
    for i in range(LOOKBACK, len(common_dates)):
        current_date = common_dates[i]
        lookback_dates = common_dates[i-LOOKBACK:i]

        # Compute average amount and vol rank
        amt_vol_data = []
        for code in sw_all_codes:
            amounts = [sw_daily[code]['data'][d]['amount'] for d in lookback_dates]
            pct_changes = [sw_daily[code]['data'][d]['pct_change'] for d in lookback_dates]
            avg_amount = sum(amounts) / LOOKBACK
            volatility = statistics.stdev(pct_changes)
            amt_vol_data.append((code, avg_amount, volatility))

        amt_vol_data.sort(key=lambda x: (x[1], x[2]))
        composite_rank = {code: idx for idx, (code, _, _) in enumerate(amt_vol_data)}

        # Calculate spread
        top_codes = sorted(composite_rank, key=composite_rank.get)[:TOP_N]
        bot_codes = sorted(composite_rank, key=composite_rank.get, reverse=True)[:TOP_N]

        top_pct = [sw_daily[code]['data'][current_date]['pct_change'] for code in top_codes]
        bot_pct = [sw_daily[code]['data'][current_date]['pct_change'] for code in bot_codes]

        spread = statistics.mean(top_pct) - statistics.mean(bot_pct)
        nav *= (1 + spread / 100)

        # Record data
        top_chg.append(statistics.mean(top_pct))
        bot_chg.append(statistics.mean(bot_pct))
        spreads.append(spread)
        navs.append(nav)
        top_names.append([sw_daily[code]['name'] for code in top_codes])
        bot_names.append([sw_daily[code]['name'] for code in bot_codes])

    return {
        'dates': [d[4:6] + '/' + d[-2:] for d in common_dates[LOOKBACK:]],  # MM/DD
        'top_chg': top_chg,
        'bot_chg': bot_chg,
        'spreads': spreads,
        'navs': navs,
        'top_names': top_names,
        'bot_names': bot_names,
    }

# Generate all sheets data
def generate_all_sheets():
    style_spread_data = compute_style_spread(index_daily)
    dual_innovation_data = compute_dual_innovation(index_daily)
    eco_sensitive_data = compute_eco_sensitive(sw_daily)
    crowding_data = compute_crowding(sw_daily)

    return {
        "update_time": cache_data['last_updated'],
        "style_spread": {
            "pairs": [{'long': '中证红利', 'short': '科创50'}, {'long': '微盘股', 'short': '中证全指'}, {'long': '中证2000', 'short': '沪深300'}],
            "data": style_spread_data
        },
        "dual_innovation": dual_innovation_data,
        "eco_sensitive": eco_sensitive_data,
        "crowding": crowding_data,
    }

# Write JSON results for dashboard
def write_json_results(results):
    with open(STYLE_SPREAD_JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

# Write CSV results
def write_csv(filename, header, rows):
    with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)

# Convert results to CSV format
def convert_results_to_csv():
    json_results = generate_all_sheets()

    # Sheet1: 风格轧差
    sheet1_header = ['日期', '中证红利涨跌幅%', '科创50涨跌幅%', '中证红利-科创50轧差%', '中证红利-科创50净值', '微盘股涨跌幅%', '中证全指涨跌幅%', '微盘股-中证全指轧差%', '微盘股-中证全指净值', '中证2000涨跌幅%', '沪深300涨跌幅%', '中证2000-沪深300轧差%', '中证2000-沪深300净值']
    sheet1_rows = []
    for pair_name, data in json_results['style_spread']['data'].items():
        rows = zip(*[data['dates'], data['spreads'], data['navs']])
        sheet1_rows.extend([[d, *values] for d, *values in rows])
    write_csv(SHEET1_CSV_PATH, sheet1_header, sheet1_rows)

    # Sheet2: 双创等权
    sheet2_header = ['日期', '创业板指涨跌幅%', '科创50涨跌幅%', '等权平均涨跌幅%', '归1净值']
    sheet2_data = json_results['dual_innovation']
    sheet2_rows = zip(sheet2_data['dates'], sheet2_data['cyb_chg'], sheet2_data['kc50_chg'], sheet2_data['navs'])
    write_csv(SHEET2_CSV_PATH, sheet2_header, list(sheet2_rows))

    # Sheet3: 经济敏感轧差
    sheet3_header = ['日期', '有色金属%', '煤炭%', '钢铁%', '周期等权%', '食品饮料%', '医药生物%', '防御等权%', '周期-防御轧差%', '轧差净值']
    sheet3_data = json_results['eco_sensitive']
    sheet3_rows = zip(sheet3_data['dates'], sheet3_data['cycle_chg'], sheet3_data['defense_chg'], sheet3_data['spreads'], sheet3_data['navs'])
    write_csv(SHEET3_CSV_PATH, sheet3_header, list(sheet3_rows))

    # Sheet4: 拥挤-反身性轧差
    sheet4_header = ['日期', '高拥挤Top6等权%', '低拥挤Bot6等权%', '高-低轧差%', '轧差净值', 'Top6行业', 'Bottom6行业']
    sheet4_data = json_results['crowding']
    sheet4_rows = zip(
        sheet4_data['dates'],
        sheet4_data['top_chg'],
        sheet4_data['bot_chg'],
        sheet4_data['spreads'],
        sheet4_data['navs'],
        [', '.join(names) for names in sheet4_data['top_names']],
        [', '.join(names) for names in sheet4_data['bot_names']]
    )
    write_csv(SHEET4_CSV_PATH, sheet4_header, list(sheet4_rows))

if __name__ == "__main__":
    results = generate_all_sheets()
    write_json_results(results)
    convert_results_to_csv()

    # Print output summary
    for path in [STYLE_SPREAD_JSON_PATH, SHEET1_CSV_PATH, SHEET2_CSV_PATH, SHEET3_CSV_PATH, SHEET4_CSV_PATH]:
        if os.path.exists(path):
            size_kb = os.path.getsize(path) / 1024
            print(f"Generated {os.path.basename(path)}: {size_kb:.2f} KB")

    # Verification of reasonable row count and nav range can be added to enhance testing

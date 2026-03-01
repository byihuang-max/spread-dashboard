#!/usr/bin/env python3
"""计算全A成交额波动率指标"""
import json, statistics, os
from datetime import datetime

DIR = os.path.dirname(os.path.abspath(__file__))

def calc():
    with open(os.path.join(DIR, 'quant_stock_data.json')) as f:
        data = json.load(f)
    records = sorted(data['total_amount'], key=lambda x: x['date'])
    amounts = [r['amount_yi'] for r in records]

    def level(v):
        if v < 8000: return '枯竭'
        if v < 10000: return '偏低'
        if v < 15000: return '正常'
        if v < 20000: return '充裕'
        return '过热'

    history = []
    for i in range(len(records)):
        r = records[i]
        amt = r['amount_yi']
        row = {'date': r['date'], 'amount_yi': amt, 'level': level(amt)}

        if i >= 4:
            row['ma5'] = round(statistics.mean(amounts[i-4:i+1]), 2)
            row['vol_5d'] = round(statistics.pstdev(amounts[i-4:i+1]), 2)
        if i >= 19:
            w20 = amounts[i-19:i+1]
            ma20 = statistics.mean(w20)
            std20 = statistics.pstdev(w20)
            row['ma20'] = round(ma20, 2)
            row['vol_20d'] = round(std20, 2)
            row['cv_20d'] = round(std20 / ma20, 4) if ma20 else None
            row['pulse'] = abs(amt - ma20) > 2 * std20
            if 'ma5' in row:
                diff = row['ma5'] / ma20 - 1
                row['trend'] = '放量' if diff > 0.05 else ('缩量' if diff < -0.05 else '平稳')

        history.append(row)

    recent = history[-60:]
    latest = recent[-1]
    out = {
        'update_time': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'latest': latest,
        'history': recent
    }
    out_path = os.path.join(DIR, 'amount_vol.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return out

if __name__ == '__main__':
    result = calc()
    print(json.dumps(result['latest'], ensure_ascii=False, indent=2))

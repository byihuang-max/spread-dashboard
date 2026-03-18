"""
更新择时研究index.html中的IC值表格
从factor_system的factor_ic.json读取最新数据
"""
import json
import re

# 读取IC数据
with open('data/factor_ic.json', 'r') as f:
    ic_data = json.load(f)

# 因子信息
factor_info = {
    'down_count': '跌停家数',
    'up_count': '涨停家数', 
    'sentiment': '综合情绪',
    'seal_diff': '封单额轧差',
    'promotion_rate': '晋级率',
    'zha_rate': '炸板率',
    'max_height': '连板高度',
    'seal_quality': '封板质量',
    'rate_1to2': '一进二率',
    'ud_ratio': '涨跌停比'
}

# 按20日IC排序
factor_order = sorted(
    factor_info.keys(),
    key=lambda f: ic_data.get(f, {}).get('20d', {}).get('ic', 0),
    reverse=True
)

# 生成表格HTML
rows = []
for factor in factor_order:
    name = factor_info[factor]
    ic_5d = ic_data.get(factor, {}).get('5d', {}).get('ic', 0)
    ic_10d = ic_data.get(factor, {}).get('10d', {}).get('ic', 0)
    ic_20d = ic_data.get(factor, {}).get('20d', {}).get('ic', 0)
    icir_20d = ic_data.get(factor, {}).get('20d', {}).get('icir', 0)
    
    # 方向判断
    if ic_20d > 0.03:
        direction = '✅ 趋势'
        color_class = 'green'
    elif ic_20d < -0.03:
        direction = '⚠️ 反向'
        color_class = 'style="color:#ff7b72"'
    else:
        direction = '—'
        color_class = ''
    
    row = f'      <tr><td style="text-align:left">{name}</td>'
    row += f'<td class="{"green" if ic_5d > 0 else ""}" style="{"color:#ff7b72" if ic_5d < 0 else ""}">{ic_5d:+.4f}</td>'
    row += f'<td class="{"green" if ic_10d > 0 else ""}" style="{"color:#ff7b72" if ic_10d < 0 else ""}">{ic_10d:+.4f}</td>'
    row += f'<td class="{"green" if ic_20d > 0 else ""}" style="{"color:#ff7b72" if ic_20d < 0 else ""}">{ic_20d:+.4f}</td>'
    row += f'<td>{icir_20d:.2f}</td>'
    row += f'<td>{direction}</td></tr>'
    rows.append(row)

table_html = '\n'.join(rows)

# 读取index.html
with open('index.html', 'r') as f:
    html = f.read()

# 替换IC表格
pattern = r'(<h2>🔬 因子 IC 值.*?<table class="tbl">.*?<tr><th.*?</tr>)(.*?)(</table>)'
replacement = r'\1\n' + table_html + r'\n      \3'
html = re.sub(pattern, replacement, html, flags=re.DOTALL)

# 写回
with open('index.html', 'w') as f:
    f.write(html)

print("✅ IC表格已更新")

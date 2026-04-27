# -*- coding: utf-8 -*-
"""
修复JSON格式，重新生成完整HTML
"""
import json
import re

# 读取数据
with open('static_data.json', 'r', encoding='utf-8') as f:
    product_data = json.load(f)

# 读取模板
with open('GAMT_Dashboard_v3_final_20260329.html', 'r', encoding='utf-8') as f:
    template = f.read()

# 找到替换位置
start = template.find('const productData = [')
end = template.find('];', start) + 2

# 生成正确的JSON字符串
json_str = json.dumps(product_data, ensure_ascii=False, indent=4)
new_js = f'const productData = {json_str};'

# 替换
new_content = template[:start] + new_js + template[end:]

# 更新统计区间
old_period = '近一周 <span style="color:#888">(2026.03.06 - 2026.03.13)</span>'
new_period = '近一周 <span style="color:#888">(2026.03.17 - 2026.03.20)</span>'
new_content = new_content.replace(old_period, new_period)

# 修复td文字颜色
old_td_css = '.product-table td {\n            padding: 14px 12px;\n            border-bottom: 1px solid var(--border-color);\n        }'
new_td_css = '.product-table td {\n            padding: 14px 12px;\n            border-bottom: 1px solid var(--border-color);\n            color: var(--text-primary);\n        }'
new_content = new_content.replace(old_td_css, new_td_css)

# 保存
with open('GAMT_Dashboard_final.html', 'w', encoding='utf-8') as f:
    f.write(new_content)

print(f"✅ 重新生成完成，共 {len(product_data)} 只基金，JSON格式正确")

#!/usr/bin/env python3
"""
商品期权双卖环境 — 集成脚本

当前版本：
- mod1_rv_regime.py：MVP，用 RV 极值 + PCA 环境判断双卖窗口

后续预留：
- mod2_iv_spread.py：IV-RV spread
- mod3_skew.py：虚值 skew
"""

import json
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
MODULES = [
    ('mod1_rv_regime.py', 'mod1_rv_regime.json', 'RV 极值环境'),
    ('mod2_iv_spread.py', 'mod2_iv_spread.json', 'IV-RV Spread'),
    ('mod3_skew_term.py', 'mod3_skew_term.json', 'Skew + 期限结构'),
    ('mod9_composite_score.py', 'mod9_composite_score.json', '综合评分'),
]
OUT_JSON = os.path.join(BASE, 'option_vol.json')


def run_module(script, label):
    print(f"\n{'─'*40}")
    print(f"▶ 运行 {label}: {script}")
    print(f"{'─'*40}")
    result = subprocess.run(
        [sys.executable, os.path.join(BASE, script)],
        cwd=BASE,
        capture_output=False,
    )
    if result.returncode != 0:
        print(f"  ⚠️ {label} 退出码 {result.returncode}")
        return False
    return True


def merge():
    merged = {}
    for _, json_file, label in MODULES:
        path = os.path.join(BASE, json_file)
        if os.path.exists(path):
            with open(path, encoding='utf-8') as f:
                merged[json_file.replace('.json', '')] = json.load(f)
            print(f"  ✅ 已合并 {label} ({json_file})")
        else:
            print(f"  ❌ 缺失 {json_file}，跳过")

    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    print(f"\n📦 最终输出: {OUT_JSON}")
    return merged


def print_summary(merged):
    print("\n" + '=' * 50)
    print('📊 商品期权双卖环境 — 汇总')
    print('=' * 50)

    comp = merged.get('mod9_composite_score', {})
    regime = comp.get('regime', {})
    if regime:
        print(f"\n【市场层 Regime】")
        print(f"  标签: {regime.get('label')}")
        print(f"  描述: {regime.get('description')}")
        print(f"  平均分: {regime.get('avg_composite_score')}")
        print(f"  可卖品种数: {regime.get('n_sellable')}")

    symbols = comp.get('symbols', [])
    if symbols:
        print(f"\n【Top 5 品种】")
        for row in symbols[:5]:
            print(f"  {row['symbol']:>4s} {row['signal']} score={row['composite_score']} spread={row.get('iv_rv_spread')} {row.get('label')}")


def main():
    mode = 'merge-only'
    if '--run' in sys.argv:
        mode = 'full'

    if mode == 'full':
        print('🚀 完整运行：执行模块 + 合并')
        for script, _, label in MODULES:
            ok = run_module(script, label)
            if not ok:
                print(f'⚠️ {label} 失败，继续下一个...')
    else:
        print('📦 合并模式：直接合并已有 JSON（加 --run 可完整运行）')

    merged = merge()
    print_summary(merged)


if __name__ == '__main__':
    main()

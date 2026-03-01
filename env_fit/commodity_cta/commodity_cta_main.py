#!/usr/bin/env python3
"""
CTA策略环境 — 集成脚本
依次运行模块1/1b/2/2b/3，合并输出到 commodity_cta.json
也可单独运行各模块后，只跑本脚本做合并。

模块1b依赖模块1的数据(fut_daily.csv)，模块2b依赖模块1b的输出。
"""

import json, os, subprocess, sys

BASE = os.path.dirname(os.path.abspath(__file__))

MODULES = [
    ("mod1_cta_env.py",      "mod1_cta_env.json",      "CTA整体环境"),
    ("mod1b_pca_engine.py",  "mod1b_pca_engine.json",  "PCA核心引擎"),
    ("mod2_trend_scan.py",   "mod2_trend_scan.json",   "品种趋势扫描"),
    ("mod2b_pca_loading.py", "mod2b_pca_loading.json", "PCA Loading增强"),
    ("mod3_macro_ratio.py",  "mod3_macro_ratio.json",  "宏观比价"),
]


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
    for script, json_file, label in MODULES:
        path = os.path.join(BASE, json_file)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                merged[json_file.replace(".json", "")] = json.load(f)
            print(f"  ✅ 已合并 {label} ({json_file})")
        else:
            print(f"  ❌ 缺失 {json_file}，跳过")

    out = os.path.join(BASE, "commodity_cta.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    print(f"\n📦 最终输出: {out}")
    print(f"   大小: {os.path.getsize(out)/1024:.1f} KB")
    return merged


def print_summary(merged):
    print("\n" + "=" * 50)
    print("📊 CTA策略环境 — 汇总")
    print("=" * 50)

    # 模块一
    env = merged.get("mod1_cta_env", {}).get("summary", {})
    if env:
        print(f"\n【整体环境（传统）】")
        print(f"  CTA友好度: {env.get('cta_friendly', '?')}/100")
        print(f"  活跃品种: {env.get('n_active', '?')}")
        print(f"  趋势占比: {env.get('trend_pct', 0):.1%}")

    # 模块1b
    pca = merged.get("mod1b_pca_engine", {})
    rolling = pca.get("rolling", [])
    if rolling:
        latest = rolling[-1]
        print(f"\n【PCA环境引擎】")
        print(f"  PC1解释比: {latest['pc1_ratio']:.1%}")
        print(f"  PC2解释比: {latest['pc2_ratio']:.1%}")
        print(f"  环境类型: {latest['env_type']}")
        print(f"  动量信号: {latest['momentum_signal']}")
        print(f"  PCA友好度: {latest['pca_friendly']}")

    # 模块二
    scan = merged.get("mod2_trend_scan", {})
    symbols = scan.get("symbols", [])
    if symbols:
        print(f"\n【趋势扫描 Top 5】")
        for s in symbols[:5]:
            name = s.get("symbol", "?")
            score = s.get("trend_score", 0)
            chg = s.get("chg_20d", s.get("chg_pct", 0))
            td = s.get("trend_dir", "?")
            sig = s.get("signal_count", 0)
            print(f"  {name:>4s}  score={score:.3f}  chg={chg:+.1f}%  {td}  signals={sig}")

    # 模块2b
    pca_loading = merged.get("mod2b_pca_loading", {})
    pca_syms = pca_loading.get("symbols", [])
    if pca_syms:
        print(f"\n【PCA Loading Top 5】")
        print(f"  分化轴: {pca_loading.get('divergence_axis', '?')}")
        for s in pca_syms[:5]:
            print(f"  {s['symbol']:>4s} ({s['sector']})  PC1={s['pc1_loading']:+.3f}  [{s['combined_role']}]")

    # 模块三
    macro = merged.get("mod3_macro_ratio", {})
    if macro:
        print(f"\n【宏观比价】")
        for key in ["cu_au", "sc_au", "ind_agri"]:
            r = macro.get(key)
            if r:
                print(f"  {r['name']}: {r['latest']:.4f} | 20日: {r['chg_20d_pct']:+.2f}% | 分位: {r['pctile_60d']:.0%} | {r['trend']}")


def main():
    mode = "merge-only"
    if "--run" in sys.argv:
        mode = "full"

    if mode == "full":
        print("🚀 完整运行：依次执行五个模块 + 合并")
        for script, _, label in MODULES:
            ok = run_module(script, label)
            if not ok:
                print(f"⚠️ {label} 失败，继续下一个...")
    else:
        print("📦 合并模式：直接合并已有 JSON（加 --run 可完整运行）")

    merged = merge()
    print_summary(merged)


if __name__ == "__main__":
    main()

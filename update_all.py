#!/usr/bin/env python3
"""
GAMT 投研看板 — 一键更新脚本
跑一次完成：数据拉取(CSV+JSON) → 指标计算 → 注入HTML → git push

用法：
  cd ~/Desktop/gamt-dashboard
  python3 update_all.py          # 更新所有模块
  python3 update_all.py --no-push  # 只更新数据，不推送
  python3 update_all.py --module quant_stock  # 只更新某个模块
"""

import subprocess, sys, os, time, argparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

# ═══ 模块定义 ═══
# 每个模块：(名称, 数据脚本列表, 注入脚本)
MODULES = {
    'style_spread': {
        'name': '风格轧差',
        'data_scripts': [
            ('size_spread', 'style_spread.py'),
        ],
        'inject_script': ('', 'inject_style_spread.py'),  # 在根目录
    },
    'quant_stock': {
        'name': '宽基量化股票',
        'data_scripts': [
            ('quant_stock', 'quant_stock_data.py'),
        ],
        'inject_script': ('quant_stock', 'inject_quant_stock.py'),
    },
    'momentum_stock': {
        'name': '强势股情绪',
        'data_scripts': [
            ('momentum_stock', 'momentum_data.py'),
        ],
        'inject_script': ('momentum_stock', 'inject_momentum.py'),
    },
    'commodity_cta': {
        'name': '商品CTA',
        'data_scripts': [
            ('commodity_cta', 'commodity_data.py'),           # 拉数据
            ('commodity_cta', 'mod1_cta_env.py'),             # 计算 mod1
            ('commodity_cta', 'mod2_trend_scan.py'),          # 计算 mod2
            ('commodity_cta', 'mod3_macro_ratio.py'),         # 计算 mod3
            ('commodity_cta', 'commodity_cta_main.py'),       # 合并 JSON
        ],
        'inject_script': ('commodity_cta', 'inject_commodity_cta.py'),
    },
    'cb_env': {
        'name': '转债指增',
        'data_scripts': [
            ('cb_env', 'cb_data.py'),    # 拉数据 → CSV + JSON
            ('cb_env', 'cb_calc.py'),    # 计算指标 → cb_env.json
        ],
        'inject_script': ('cb_env', 'inject_cb_env.py'),
    },
}

def log(msg, level='INFO'):
    ts = time.strftime('%H:%M:%S')
    prefix = {'INFO': '📋', 'OK': '✅', 'ERR': '❌', 'RUN': '🔄'}
    print(f"[{ts}] {prefix.get(level, '  ')} {msg}", flush=True)

def run_script(subdir, script):
    """运行一个 Python 脚本，返回 (成功, 耗时秒)"""
    if subdir:
        path = os.path.join(BASE_DIR, subdir, script)
        cwd = os.path.join(BASE_DIR, subdir)
    else:
        path = os.path.join(BASE_DIR, script)
        cwd = BASE_DIR

    if not os.path.exists(path):
        log(f"脚本不存在: {path}", 'ERR')
        return False, 0

    log(f"运行 {subdir}/{script}" if subdir else f"运行 {script}", 'RUN')
    t0 = time.time()
    try:
        result = subprocess.run(
            [sys.executable, path],
            cwd=cwd,
            capture_output=True, text=True, timeout=300
        )
        elapsed = time.time() - t0
        if result.returncode != 0:
            log(f"  失败 ({elapsed:.1f}s): {result.stderr[-200:]}", 'ERR')
            return False, elapsed
        log(f"  完成 ({elapsed:.1f}s)", 'OK')
        return True, elapsed
    except subprocess.TimeoutExpired:
        log(f"  超时 (>300s)", 'ERR')
        return False, 300
    except Exception as e:
        log(f"  异常: {e}", 'ERR')
        return False, 0

def update_module(mod_key):
    """更新单个模块：数据脚本 → 注入脚本"""
    mod = MODULES[mod_key]
    log(f"═══ {mod['name']} ({mod_key}) ═══")

    all_ok = True
    total_time = 0

    # 1. 数据脚本
    for subdir, script in mod['data_scripts']:
        ok, t = run_script(subdir, script)
        total_time += t
        if not ok:
            all_ok = False
            log(f"  数据脚本失败，跳过注入", 'ERR')
            return False, total_time

    # 2. 注入脚本
    if mod.get('inject_script'):
        subdir, script = mod['inject_script']
        ok, t = run_script(subdir, script)
        total_time += t
        if not ok:
            all_ok = False

    return all_ok, total_time

def git_push(msg='auto: update data'):
    """git add + commit + push"""
    log("═══ Git Push ═══")
    try:
        subprocess.run(['git', 'add', '-A'], cwd=BASE_DIR, check=True)
        # 检查是否有变更
        result = subprocess.run(['git', 'diff', '--cached', '--quiet'], cwd=BASE_DIR)
        if result.returncode == 0:
            log("没有变更，跳过 push", 'OK')
            return True
        subprocess.run(['git', 'commit', '-m', msg], cwd=BASE_DIR, check=True)
        subprocess.run(['git', 'push', 'origin', 'main'], cwd=BASE_DIR, check=True, timeout=30)
        log("推送成功", 'OK')
        return True
    except Exception as e:
        log(f"Git 失败: {e}", 'ERR')
        return False

def main():
    parser = argparse.ArgumentParser(description='GAMT 投研看板一键更新')
    parser.add_argument('--no-push', action='store_true', help='只更新数据，不推送')
    parser.add_argument('--module', '-m', type=str, help='只更新指定模块')
    parser.add_argument('--list', action='store_true', help='列出所有模块')
    args = parser.parse_args()

    if args.list:
        for k, v in MODULES.items():
            print(f"  {k:20s} — {v['name']}")
        return

    log("GAMT 投研看板 — 一键更新开始")
    t0 = time.time()

    modules_to_run = [args.module] if args.module else list(MODULES.keys())
    results = {}

    for mod_key in modules_to_run:
        if mod_key not in MODULES:
            log(f"未知模块: {mod_key}", 'ERR')
            continue
        ok, t = update_module(mod_key)
        results[mod_key] = (ok, t)
        print()

    # 汇总
    log("═══ 汇总 ═══")
    total_time = time.time() - t0
    for k, (ok, t) in results.items():
        status = '✅' if ok else '❌'
        log(f"  {status} {MODULES[k]['name']:12s} ({t:.1f}s)")
    log(f"总耗时: {total_time:.1f}s")

    # Git push
    if not args.no_push:
        ok_count = sum(1 for ok, _ in results.values() if ok)
        total = len(results)
        msg = f"auto: update {ok_count}/{total} modules"
        git_push(msg)
    else:
        log("跳过 git push (--no-push)", 'INFO')

    log("完成！", 'OK')

if __name__ == '__main__':
    main()

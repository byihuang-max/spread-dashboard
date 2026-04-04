#!/usr/bin/env python3
"""
GAMT 投研看板 — 一键更新脚本
跑一次完成：数据拉取(CSV+JSON) → 指标计算 → 注入HTML → git push

用法：
  python3 update_all.py              # 主更新（自动跳过晚到数据模块）
  python3 update_all.py --late-only  # 只跑晚到数据（强势股+耐心资本）
  python3 update_all.py --module quant_stock  # 只更新某个模块（不受分层影响）
  python3 update_all.py --no-push    # 只更新数据，不推送

分层逻辑：
  - 默认模式：跳过 late_data=True 的模块（涨跌停/15min等晚到数据）
  - --late-only：只跑 late_data=True 的模块
  - --module：指定模块，不受分层影响
"""

import subprocess, sys, os, time, argparse, json
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE_DIR)

sys.path.insert(0, os.path.join(BASE_DIR, 'server'))
from module_registry import build_update_all_modules

MODULES = build_update_all_modules()

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
            capture_output=True, text=True, timeout=600
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

    # 1. 外部脚本（如果有）
    if mod.get('external_script'):
        external_path = mod['external_script']
        if not os.path.exists(external_path):
            log(f"外部脚本不存在: {external_path}", 'ERR')
            return False, 0
        
        log(f"运行外部脚本: {external_path}", 'RUN')
        t0 = time.time()
        try:
            result = subprocess.run(
                [sys.executable, external_path],
                cwd=os.path.dirname(external_path),
                capture_output=True, text=True, timeout=600
            )
            elapsed = time.time() - t0
            if result.returncode != 0:
                log(f"  失败 ({elapsed:.1f}s): {result.stderr[-200:]}", 'ERR')
                return False, elapsed
            log(f"  完成 ({elapsed:.1f}s)", 'OK')
            total_time += elapsed
        except subprocess.TimeoutExpired:
            log(f"  超时 (>600s)", 'ERR')
            return False, 600
        except Exception as e:
            log(f"  异常: {e}", 'ERR')
            return False, 0

    # 2. 数据脚本
    for subdir, script in mod['data_scripts']:
        ok, t = run_script(subdir, script)
        total_time += t
        if not ok:
            all_ok = False
            log(f"  数据脚本失败，跳过注入", 'ERR')
            return False, total_time

    # 3. 注入脚本
    if mod.get('inject_script'):
        subdir, script = mod['inject_script']
        ok, t = run_script(subdir, script)
        total_time += t
        if not ok:
            all_ok = False

    # 4. 后置注入脚本（可选）
    if mod.get('post_inject'):
        for subdir, script in mod['post_inject']:
            ok, t = run_script(subdir, script)
            total_time += t
            if not ok:
                all_ok = False

    return all_ok, total_time

def update_timing_exposure_page():
    """更新量化择时研究里的 ML 敞口页"""
    log("═══ 择时敞口评分页 ═══")
    base = os.path.expanduser('~/Desktop/quant-backtest/timing_model')
    scripts = ['ml_exposure_score.py', 'generate_ml_exposure_page.py',
               'live_exposure_nav.py', 'generate_live_exposure_page.py']
    total = 0
    ok_all = True
    for script in scripts:
        path = os.path.join(base, script)
        log(f"运行 {script}", 'RUN')
        t0 = time.time()
        try:
            result = subprocess.run(
                [sys.executable, path],
                cwd=base,
                capture_output=True, text=True, timeout=600
            )
            elapsed = time.time() - t0
            total += elapsed
            if result.returncode != 0:
                ok_all = False
                log(f"  失败 ({elapsed:.1f}s): {result.stderr[-200:]}", 'ERR')
            else:
                log(f"  完成 ({elapsed:.1f}s)", 'OK')
        except Exception as e:
            ok_all = False
            log(f"  异常: {e}", 'ERR')
    return ok_all, total

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
    parser.add_argument('--late-only', action='store_true', help='只更新晚到数据模块（momentum_stock + patient_capital）')
    parser.add_argument('--list', action='store_true', help='列出所有模块')
    args = parser.parse_args()

    if args.list:
        for k, v in MODULES.items():
            print(f"  {k:20s} — {v['name']}")
        return

    log("GAMT 投研看板 — 一键更新开始")
    t0 = time.time()

    # 决定要跑哪些模块
    if args.module:
        modules_to_run = [args.module]
    elif args.late_only:
        # 只跑标记了 late_data=True 的模块
        from module_registry import MODULE_REGISTRY
        modules_to_run = [k for k, v in MODULE_REGISTRY.items() if v.get('late_data') and v.get('include_in_update_all')]
        log(f"晚到数据模式：只更新 {', '.join(modules_to_run)}")
    else:
        # 默认跑所有模块，但跳过 late_data=True 的
        from module_registry import MODULE_REGISTRY
        modules_to_run = [k for k in MODULES.keys() if not MODULE_REGISTRY.get(k, {}).get('late_data')]
        log(f"主更新模式：跳过晚到数据模块")
    
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

    # 更新 update_log.json（与 refresh_server 格式一致）
    update_log_path = os.path.join(BASE_DIR, 'server', 'update_log.json')
    try:
        with open(update_log_path, 'r', encoding='utf-8') as f:
            logs = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        logs = []
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    date_str = datetime.now().strftime('%Y-%m-%d')
    for k, (ok, t) in results.items():
        entry = {
            'module': k,
            'name': MODULES[k]['name'],
            'ok': ok,
            'elapsed': round(t, 1),
            'time': now_str,
            'date': date_str,
            'user': 'cron'
        }
        # 替换同模块旧记录
        logs = [l for l in logs if l.get('module') != k]
        logs.append(entry)
    with open(update_log_path, 'w', encoding='utf-8') as f:
        json.dump(logs, f, indent=1, ensure_ascii=False)
    log("已更新 update_log.json")

    # 更新择时敞口评分页
    ok_exp, t_exp = update_timing_exposure_page()
    results['timing_exposure'] = (ok_exp, t_exp)
    print()

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

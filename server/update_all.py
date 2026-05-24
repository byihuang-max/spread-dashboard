#!/usr/bin/env python3
"""
GAMT 投研看板 — 一键更新脚本
跑一次完成：数据拉取(CSV+JSON) → 指标计算 → 注入HTML → git push

用法：
  python3 update_all.py                     # 盘前模式（默认，只跑海外/宏观等 am_early 模块）
  python3 update_all.py --phase am          # 同上：盘前模式
  python3 update_all.py --phase close       # 收盘后模式（跑全部常规模块）
  python3 update_all.py --phase pm          # 全量模式（常规+晚到数据）
  python3 update_all.py --late-only         # 只跑晚到数据（耐心资本→强势股→择时因子→并购）
  python3 update_all.py --module quant_stock  # 只更新某个模块（不受分层影响）
  python3 update_all.py --no-push           # 只更新数据，不推送

分层逻辑：
  - --phase am（默认）：只跑 am_early=True 的模块（海外/宏观/日历/叙事，7个）
  - --phase close：跑全部常规模块（收盘后 A 股数据已入库）
  - --phase pm：先跑常规模块，再顺序跑晚到数据模块
  - --late-only：只跑 late_data=True 的模块
  - --module：指定模块，不受分层影响
"""

import subprocess, sys, os, time, argparse, json
from datetime import datetime
from pathlib import Path

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE_DIR)

sys.path.insert(0, os.path.join(BASE_DIR, 'server'))
from module_registry import build_update_all_modules

MODULES = build_update_all_modules()

def log(msg, level='INFO'):
    ts = time.strftime('%H:%M:%S')
    prefix = {'INFO': '', 'OK': '', 'ERR': '', 'RUN': ''}
    print(f"[{ts}] {prefix.get(level, '  ')} {msg}", flush=True)

def run_script(subdir, script):
    """运行一个 Python 脚本，返回 (成功, 耗时秒)。支持 'script.py --arg' 格式"""
    # 分离脚本名和参数
    parts = script.split()
    script_name = parts[0]
    script_args = parts[1:]

    if subdir:
        path = os.path.join(BASE_DIR, subdir, script_name)
        cwd = os.path.join(BASE_DIR, subdir)
    else:
        path = os.path.join(BASE_DIR, script_name)
        cwd = BASE_DIR

    if not os.path.exists(path):
        log(f"脚本不存在: {path}", 'ERR')
        return False, 0

    log(f"运行 {subdir}/{script}" if subdir else f"运行 {script}", 'RUN')
    t0 = time.time()
    try:
        result = subprocess.run(
            [sys.executable, path] + script_args,
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
    # 先跑 factor_system/daily_update.py（因子计算上游），再跑敞口评分和净值
    scripts = ['factor_system/daily_update.py',
               'fetch_full_a_amount.py', 'ml_exposure_score.py', 'generate_ml_exposure_page.py',
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
        # 获取已配置的 remote 列表
        configured_remotes = set()
        try:
            r = subprocess.run(['git', 'remote'], cwd=BASE_DIR, capture_output=True, text=True)
            configured_remotes = set(r.stdout.strip().split('\n')) if r.stdout.strip() else set()
        except Exception:
            configured_remotes = {'origin'}
        # 优先推 Gitee（国内直连），再尝试 GitHub；跳过不存在的 remote
        pushed = False
        for remote in ['gitee', 'origin']:
            if remote not in configured_remotes:
                continue
            try:
                subprocess.run(['git', 'push', remote, 'main'], cwd=BASE_DIR, check=True, timeout=30)
                log(f"推送 {remote} 成功", 'OK')
                pushed = True
                break
            except Exception as e:
                log(f"推送 {remote} 失败: {e}", 'WARN')
        # 判断是否在腾讯云上运行（避免 SSH 自己同步自己）
        import socket
        is_cloud = socket.gethostname() == 'localhost' or Path('/home/ubuntu/gamt-dashboard').exists()
        if not is_cloud:
            try:
                subprocess.run(['ssh', '-o', 'ConnectTimeout=5', 'ubuntu@111.229.129.146',
                              'cd /home/ubuntu/gamt-dashboard && git fetch origin && git reset --hard origin/main'],
                              check=True, timeout=30)
                log("腾讯云同步成功", 'OK')
            except Exception:
                log("腾讯云同步失败（非致命）", 'WARN')
        return pushed
    except Exception as e:
        log(f"Git 失败: {e}", 'ERR')
        return False

def resolve_modules(args):
    from module_registry import MODULE_REGISTRY

    normal_modules = [k for k in MODULES.keys() if not MODULE_REGISTRY.get(k, {}).get('late_data')]
    late_modules = [k for k, v in MODULE_REGISTRY.items() if v.get('late_data') and v.get('include_in_update_all')]
    am_early_modules = [k for k in normal_modules if MODULE_REGISTRY.get(k, {}).get('am_early')]

    if args.module:
        log(f"单模块模式：只更新 {args.module}")
        return [args.module], 'single'

    if args.late_only:
        log(f"晚到数据模式：只更新 {', '.join(late_modules)}")
        return late_modules, 'late_only'

    phase = args.phase or 'am'
    if phase == 'pm':
        modules_to_run = normal_modules + late_modules
        log(f"晚间全量模式：先常规后晚到，共 {len(modules_to_run)} 个模块")
        return modules_to_run, 'pm'

    if phase == 'am':
        log(f"盘前模式：只跑海外/宏观等盘前模块（{len(am_early_modules)} 个）")
        return am_early_modules, 'am'

    # phase == 'close': 收盘后跑全部常规模块
    log(f"收盘后模式：跑全部常规模块（{len(normal_modules)} 个）")
    return normal_modules, 'close'

def main():
    parser = argparse.ArgumentParser(description='GAMT 投研看板一键更新')
    parser.add_argument('--no-push', action='store_true', help='只更新数据，不推送')
    parser.add_argument('--module', '-m', type=str, help='只更新指定模块')
    parser.add_argument('--late-only', action='store_true', help='只更新晚到数据模块（momentum_stock + patient_capital + timing_factors）')
    parser.add_argument('--phase', choices=['am', 'close', 'pm'], default='am', help='am=盘前（海外/宏观），close=收盘后（全部常规），pm=全量（常规+晚到）')
    parser.add_argument('--list', action='store_true', help='列出所有模块')
    args = parser.parse_args()

    if args.list:
        for k, v in MODULES.items():
            print(f"  {k:20s} — {v['name']}")
        return

    log("GAMT 投研看板 — 一键更新开始")
    t0 = time.time()

    modules_to_run, run_mode = resolve_modules(args)
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
        status = '' if ok else ''
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
            'user': f'cron:{run_mode}'
        }
        # 替换同模块旧记录
        logs = [l for l in logs if l.get('module') != k]
        logs.append(entry)
    with open(update_log_path, 'w', encoding='utf-8') as f:
        json.dump(logs, f, indent=1, ensure_ascii=False)
    log("已更新 update_log.json")

    # 仅在本轮未包含 timing_factors 时，才额外更新择时敞口评分页
    if 'timing_factors' not in results:
        ok_exp, t_exp = update_timing_exposure_page()
        results['timing_exposure'] = (ok_exp, t_exp)
        print()

    # Git push
    if not args.no_push:
        ok_count = sum(1 for ok, _ in results.values() if ok)
        total = len(results)
        msg = f"auto: update {run_mode} {ok_count}/{total} modules"
        git_push(msg)
    else:
        log("跳过 git push (--no-push)", 'INFO')

    log("完成！", 'OK')

if __name__ == '__main__':
    main()

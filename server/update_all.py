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

import subprocess, sys, os, time, argparse, json
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE_DIR)

# ═══ 模块定义 ═══
# 每个模块：(名称, 数据脚本列表, 注入脚本)
MODULES = {
    'fund_nav': {
        'name': '产品净值',
        'data_scripts': [
            ('size_spread/fund_nav', 'fund_nav_data.py'),    # 拉取产品净值数据
        ],
        'inject_script': None,
    },
    'style_spread': {
        'name': '风格轧差',
        'data_scripts': [
            ('size_spread', 'fetch_incremental.py'),   # 增量拉取 → CSV + JSON cache
            ('size_spread', 'compute_spreads.py'),      # 计算轧差 → JSON + CSV
            ('size_spread', 'render_html.py'),          # 生成静态 HTML 看板
        ],
        'inject_script': None,  # 不再用注入脚本，iframe 加载独立 HTML
    },
    'quant_stock': {
        'name': '宽基量化股票',
        'data_scripts': [
            ('env_fit/quant_stock', 'quant_stock_data.py'),
            ('env_fit/quant_stock', 'excess_attribution.py'),    # 超额归因（依赖fund_nav）
        ],
        'inject_script': ('env_fit/quant_stock', 'inject_quant_stock.py'),
    },
    'momentum_stock': {
        'name': '强势股情绪',
        'data_scripts': [
            ('env_fit/momentum_stock', 'momentum_data.py'),
        ],
        'inject_script': ('env_fit/momentum_stock', 'inject_momentum.py'),
    },
    'commodity_cta': {
        'name': '商品CTA',
        'data_scripts': [
            ('env_fit/commodity_cta', 'commodity_data.py'),           # 拉数据
            ('env_fit/commodity_cta', 'mod1_cta_env.py'),             # 计算 mod1
            ('env_fit/commodity_cta', 'mod2_trend_scan.py'),          # 计算 mod2
            ('env_fit/commodity_cta', 'mod3_macro_ratio.py'),         # 计算 mod3
            ('env_fit/commodity_cta', 'commodity_cta_main.py'),       # 合并 JSON
        ],
        'inject_script': ('env_fit/commodity_cta', 'inject_commodity_cta.py'),
    },
    'cb_env': {
        'name': '转债指增',
        'data_scripts': [
            ('env_fit/cb_env', 'cb_data.py'),    # 拉数据 → CSV + JSON
            ('env_fit/cb_env', 'cb_calc.py'),    # 计算指标 → cb_env.json
        ],
        'inject_script': ('env_fit/cb_env', 'inject_cb_env.py'),
        'post_inject': [('env_fit/cb_env', 'inject_cb_nav.py')],  # 注入产品净值
    },
    'alerts': {
        'name': '红灯预警（A股）',
        'data_scripts': [
            ('alerts', 'alerts_data.py'),    # 拉取估值/涨跌停/成交额数据
            ('alerts', 'alerts_calc.py'),    # 计算5维度风险评分
        ],
        'inject_script': None,  # 独立HTML页面
    },
    'us_alerts': {
        'name': '美股风险监控',
        'data_scripts': [
            ('alerts', 'us_alerts_data.py'),    # 拉取美股数据（VIX/标普/纳指等）
            ('alerts', 'us_alerts_calc.py'),    # 计算趋势+风险等级
        ],
        'inject_script': None,  # 与A股共用alerts.html
    },
    'crowding': {
        'name': '资金流拥挤度',
        'data_scripts': [
            ('micro_flow/crowding', 'crowding_data.py'),    # 北向/ETF/两融/申万/行业ETF
            ('micro_flow/crowding', 'crowding_calc.py'),    # 计算拥挤度指标
        ],
        'inject_script': None,
    },
    'option_sentiment': {
        'name': '期权情绪',
        'data_scripts': [
            ('micro_flow/option_sentiment', 'option_data.py'),    # 期权数据
            ('micro_flow/option_sentiment', 'option_calc.py'),    # PCR/IV等指标
        ],
        'inject_script': None,
    },
    'patient_capital': {
        'name': '耐心资本',
        'data_scripts': [
            ('micro_flow/patient_capital', 'patient_data.py'),    # 机构持仓数据
            ('micro_flow/patient_capital', 'patient_calc.py'),    # 计算耐心资本指标
        ],
        'inject_script': None,
    },
    'macro_liquidity': {
        'name': '宏观流动性',
        'data_scripts': [
            ('macro/liquidity', 'liquidity_data.py'),    # DR007/Shibor/M1M2等
            ('macro/liquidity', 'liquidity_calc.py'),    # 流动性指标计算
        ],
        'inject_script': None,
    },
    'macro_rates': {
        'name': '利率数据',
        'data_scripts': [
            ('macro/rates', 'rates_data.py'),    # 中美利率数据
            ('macro/rates', 'rates_calc.py'),    # 利差计算
        ],
        'inject_script': None,
    },
    'macro_fundamentals': {
        'name': '基本面数据',
        'data_scripts': [
            ('macro/fundamentals', 'fundamentals_data.py'),    # CPI/PPI/PMI等
            ('macro/fundamentals', 'fundamentals_calc.py'),    # 基本面指标
        ],
        'inject_script': None,
    },
    'antifragile': {
        'name': '反脆弱看板',
        'data_scripts': [
            ('meme/antifragile', 'fetch_data.py'),    # 拉取海外资产价格（yfinance）
            ('meme/antifragile', 'calc_corr.py'),     # 30日滚动相关性矩阵
            ('meme/antifragile', 'calc_meme.py'),     # Meme反身性信号
            ('meme/antifragile', 'render_html.py'),   # 渲染 antifragile.html
        ],
        'inject_script': None,
    },
    'narrative_lifecycle': {
        'name': '叙事生命周期',
        'data_scripts': [
            ('meme', 'macro_lifecycle.py'),    # 宏观Meme叙事生命周期判断
        ],
        'inject_script': None,
    },
    'macro_score': {
        'name': '宏观打分+策略适配',
        'data_scripts': [
            ('macro/score', 'macro_score.py'),   # 读取所有模块JSON → 综合打分
        ],
        'inject_script': None,
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

    # 3. 后置注入脚本（可选）
    if mod.get('post_inject'):
        for subdir, script in mod['post_inject']:
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

#!/usr/bin/env python3
"""
GAMT 看板刷新 API 服务
- 前端点"刷新"→ POST /api/refresh/<module>
- 后端依次跑数据脚本 + 注入脚本
- 全局锁：同一时间只跑一个模块，防高并发
- GET /api/status 查看当前状态

启动：python3 refresh_server.py
端口：9876
"""

import subprocess, sys, os, time, json, threading
from http.server import HTTPServer, BaseHTTPRequestHandler

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ═══ 模块配置（和 update_all.py 保持一致）═══
MODULES = {
    'style_spread': {
        'name': '风格轧差',
        'scripts': [
            ('size_spread', 'fetch_incremental.py'),
            ('size_spread', 'compute_spreads.py'),
            ('size_spread', 'render_html.py'),
        ],
    },
    'quant_stock': {
        'name': '宽基量化股票',
        'scripts': [
            ('quant_stock', 'quant_stock_data.py'),
            ('quant_stock', 'inject_quant_stock.py'),
        ],
    },
    'momentum_stock': {
        'name': '强势股',
        'scripts': [
            ('momentum_stock', 'momentum_data.py'),
            ('momentum_stock', 'inject_momentum.py'),
        ],
    },
    'commodity_cta': {
        'name': '商品CTA',
        'scripts': [
            ('commodity_cta', 'commodity_data.py'),
            ('commodity_cta', 'mod1_cta_env.py'),
            ('commodity_cta', 'mod2_trend_scan.py'),
            ('commodity_cta', 'mod3_macro_ratio.py'),
            ('commodity_cta', 'commodity_cta_main.py'),
            ('commodity_cta', 'inject_commodity_cta.py'),
        ],
    },
    'cb_env': {
        'name': '转债',
        'scripts': [
            ('cb_env', 'cb_data.py'),
            ('cb_env', 'cb_calc.py'),
            ('cb_env', 'inject_cb_env.py'),
        ],
    },
    'arbitrage': {
        'name': '套利',
        'scripts': [
            ('arbitrage', 'fetch_incremental.py'),
            ('arbitrage', 'mod1_index_arb.py'),
            ('arbitrage', 'mod2_commodity_arb.py'),
            ('arbitrage', 'mod3_option_arb.py'),
        ],
    },
}

# Tab 名 → 模块名映射（前端 data-strat 到后端 module key）
TAB_MAP = {
    'style-spread': 'style_spread',
    'quant-stock': 'quant_stock',
    'momentum-stock': 'momentum_stock',
    'cta': 'commodity_cta',
    'convertible': 'cb_env',
    'arbitrage': 'arbitrage',
}

# ═══ 全局状态 ═══
lock = threading.Lock()
state = {
    'running': False,
    'module': None,
    'step': None,
    'started': None,
    'last_result': None,
}


def run_module(mod_key):
    """跑一个模块的全部脚本，返回 (ok, logs)"""
    mod = MODULES[mod_key]
    logs = []
    t0 = time.time()

    for subdir, script in mod['scripts']:
        path = os.path.join(BASE_DIR, subdir, script)
        cwd = os.path.join(BASE_DIR, subdir)

        if not os.path.exists(path):
            logs.append(f"⚠️ 跳过不存在: {subdir}/{script}")
            continue

        state['step'] = f"{subdir}/{script}"
        logs.append(f"🔄 {subdir}/{script}")

        try:
            result = subprocess.run(
                [sys.executable, path],
                cwd=cwd,
                capture_output=True, text=True, timeout=600
            )
            elapsed = time.time() - t0
            if result.returncode != 0:
                err = result.stderr[-300:] if result.stderr else result.stdout[-300:]
                logs.append(f"❌ 失败 ({elapsed:.1f}s): {err}")
                return False, logs
            logs.append(f"✅ 完成 ({elapsed:.0f}s)")
        except subprocess.TimeoutExpired:
            logs.append(f"❌ 超时 (>600s)")
            return False, logs
        except Exception as e:
            logs.append(f"❌ 异常: {e}")
            return False, logs

    total = time.time() - t0
    logs.append(f"🎉 全部完成 ({total:.1f}s)")
    return True, logs


class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def _json(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path == '/api/status':
            self._json(200, {
                'running': state['running'],
                'module': state['module'],
                'step': state['step'],
                'started': state['started'],
                'last_result': state['last_result'],
                'modules': {k: v['name'] for k, v in MODULES.items()},
            })
        else:
            self._json(404, {'error': 'not found'})

    def _check_market_hours(self):
        """15:00 之前禁止刷新（A股数据收盘后才完整）"""
        from datetime import datetime
        now = datetime.now()
        if now.hour < 15:
            self._json(403, {'error': f'收盘前({now.strftime("%H:%M")})不可刷新，请15:00后再试'})
            return False
        return True

    def do_POST(self):
        # POST /api/refresh/<tab-name>
        parts = self.path.strip('/').split('/')
        if len(parts) == 3 and parts[0] == 'api' and parts[1] == 'refresh':
            tab = parts[2]
            mod_key = TAB_MAP.get(tab, tab.replace('-', '_'))

            if mod_key not in MODULES:
                self._json(400, {'error': f'未知模块: {tab}', 'available': list(TAB_MAP.keys())})
                return

            if not self._check_market_hours():
                return

            # 尝试获取锁
            acquired = lock.acquire(blocking=False)
            if not acquired:
                self._json(429, {
                    'error': '有任务正在运行，请稍后再试',
                    'running_module': state['module'],
                    'step': state['step'],
                })
                return

            try:
                state['running'] = True
                state['module'] = mod_key
                state['step'] = 'starting'
                state['started'] = time.strftime('%H:%M:%S')

                ok, logs = run_module(mod_key)

                state['last_result'] = {
                    'module': mod_key,
                    'name': MODULES[mod_key]['name'],
                    'ok': ok,
                    'logs': logs,
                    'time': time.strftime('%H:%M:%S'),
                }
                self._json(200, {'ok': ok, 'module': mod_key, 'logs': logs})
            finally:
                state['running'] = False
                state['module'] = None
                state['step'] = None
                lock.release()

        # POST /api/refresh-all
        elif self.path == '/api/refresh-all':
            if not self._check_market_hours():
                return
            acquired = lock.acquire(blocking=False)
            if not acquired:
                self._json(429, {'error': '有任务正在运行', 'running_module': state['module']})
                return
            try:
                state['running'] = True
                state['started'] = time.strftime('%H:%M:%S')
                results = {}
                for mod_key in MODULES:
                    state['module'] = mod_key
                    ok, logs = run_module(mod_key)
                    results[mod_key] = {'ok': ok, 'logs': logs}
                state['last_result'] = {'all': results, 'time': time.strftime('%H:%M:%S')}
                self._json(200, results)
            finally:
                state['running'] = False
                state['module'] = None
                state['step'] = None
                lock.release()
        else:
            self._json(404, {'error': 'not found'})

    def log_message(self, fmt, *args):
        ts = time.strftime('%H:%M:%S')
        print(f"[{ts}] {args[0]}", flush=True)


def main():
    port = 9876
    server = HTTPServer(('0.0.0.0', port), Handler)
    print(f"🚀 GAMT 刷新服务启动: http://localhost:{port}")
    print(f"   POST /api/refresh/<tab>  — 刷新单个模块")
    print(f"   POST /api/refresh-all    — 刷新全部")
    print(f"   GET  /api/status         — 查看状态")
    print(f"   可用 tab: {', '.join(TAB_MAP.keys())}")
    print(flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()

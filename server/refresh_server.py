#!/usr/bin/env python3
"""
GAMT 看板刷新 API 服务
- 前端点"刷新"→ POST /api/refresh/<module>
- 后端依次跑数据脚本 + 注入脚本
- 全局锁：同一时间只跑一个模块，防高并发
- GET /api/status 查看当前状态
- 异步模式：POST 立即返回 202，后台线程执行

启动：python3 refresh_server.py
端口：9876
"""

import subprocess, sys, os, time, json, threading, gzip, io
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ═══ 认证模块 ═══
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import auth

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
            ('env_fit/quant_stock', 'quant_stock_data.py'),
            ('env_fit/quant_stock', 'inject_quant_stock.py'),
        ],
    },
    'momentum_stock': {
        'name': '强势股',
        'scripts': [
            ('env_fit/momentum_stock', 'momentum_data.py'),
            ('env_fit/momentum_stock', 'inject_momentum.py'),
        ],
    },
    'commodity_cta': {
        'name': '商品CTA',
        'scripts': [
            ('env_fit/commodity_cta', 'commodity_data.py'),
            ('env_fit/commodity_cta', 'mod1_cta_env.py'),
            ('env_fit/commodity_cta', 'mod2_trend_scan.py'),
            ('env_fit/commodity_cta', 'mod3_macro_ratio.py'),
            ('env_fit/commodity_cta', 'commodity_cta_main.py'),
            ('env_fit/commodity_cta', 'inject_commodity_cta.py'),
        ],
    },
    'cb_env': {
        'name': '转债',
        'scripts': [
            ('env_fit/cb_env', 'cb_data.py'),
            ('env_fit/cb_env', 'cb_calc.py'),
            ('env_fit/cb_env', 'inject_cb_env.py'),
        ],
    },
    'arbitrage': {
        'name': '套利',
        'scripts': [
            ('env_fit/arbitrage', 'fetch_incremental.py'),
            ('env_fit/arbitrage', 'mod1_index_arb.py'),
            ('env_fit/arbitrage', 'mod2_commodity_arb.py'),
            ('env_fit/arbitrage', 'mod3_option_arb.py'),
        ],
    },
    'patient_capital': {
        'name': '耐心资本持筹',
        'scripts': [
            ('micro_flow/patient_capital', 'patient_data.py'),
            ('micro_flow/patient_capital', 'patient_calc.py'),
        ],
    },
    'crowding': {
        'name': '拥挤度监控',
        'scripts': [
            ('micro_flow/crowding', 'crowding_data.py'),
            ('micro_flow/crowding', 'crowding_calc.py'),
        ],
    },
    'option_sentiment': {
        'name': '期权异常值监控',
        'scripts': [
            ('micro_flow/option_sentiment', 'option_data.py'),
            ('micro_flow/option_sentiment', 'option_calc.py'),
        ],
    },
    'liquidity': {
        'name': '境内流动性',
        'scripts': [
            ('macro/liquidity', 'liquidity_data.py'),
            ('macro/liquidity', 'liquidity_calc.py'),
        ],
    },
    'rates': {
        'name': '全球利率与汇率',
        'scripts': [
            ('macro/rates', 'rates_data.py'),
            ('macro/rates', 'rates_calc.py'),
        ],
    },
    'fundamentals': {
        'name': '经济基本面',
        'scripts': [
            ('macro/fundamentals', 'fundamentals_data.py'),
            ('macro/fundamentals', 'fundamentals_calc.py'),
        ],
    },
    'chain-prosperity': {
        'name': '产业链景气',
        'scripts': [
            ('meso/chain_prosperity', 'chain_data.py'),
            ('meso/chain_prosperity', 'chain_calc.py'),
        ],
    },
    'alerts': {
        'name': '红灯预警',
        'scripts': [
            ('alerts', 'alerts_data.py'),
            ('alerts', 'alerts_calc.py'),
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
    'patient-capital': 'patient_capital',
    'crowding': 'crowding',
    'option-sentiment': 'option_sentiment',
    'liquidity': 'liquidity',
    'rates': 'rates',
    'fundamentals': 'fundamentals',
    'chain-prosperity': 'chain-prosperity',
    'alerts': 'alerts',
}

# ═══ 全局状态 ═══
lock = threading.Lock()
_cancel_flag = threading.Event()

def _make_progress():
    return {
        'total_modules': 0,
        'completed_modules': 0,
        'current_module_index': 0,
        'total_scripts': 0,
        'completed_scripts': 0,
        'current_script': None,
        'elapsed': 0,
        'logs': [],
        'results': {},
    }

state = {
    'running': False,
    'mode': None,
    'module': None,
    'module_name': None,
    'step': None,
    'started': None,
    'last_result': None,
    'progress': _make_progress(),
}

MAX_LOGS = 100

def _append_log(msg):
    logs = state['progress']['logs']
    logs.append(msg)
    if len(logs) > MAX_LOGS:
        del logs[:len(logs) - MAX_LOGS]


def run_module(mod_key):
    """跑一个模块的全部脚本，返回 (ok, logs)"""
    mod = MODULES[mod_key]
    logs = []
    t0 = time.time()
    scripts = mod['scripts']

    for j, (subdir, script) in enumerate(scripts):
        # 检查取消
        if _cancel_flag.is_set():
            logs.append("⛔ 任务已取消")
            _append_log("⛔ 任务已取消")
            return False, logs

        # 更新进度
        state['progress']['current_script'] = script
        state['progress']['completed_scripts'] = j
        state['step'] = f"{subdir}/{script}"

        path = os.path.join(BASE_DIR, subdir, script)
        cwd = os.path.join(BASE_DIR, subdir)

        if not os.path.exists(path):
            logs.append(f"⚠️ 跳过不存在: {subdir}/{script}")
            _append_log(f"⚠️ 跳过: {script}")
            continue

        _append_log(f"🔄 {mod['name']} → {script}")
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
                _append_log(f"❌ {script} 失败 ({elapsed:.0f}s)")
                state['progress']['completed_scripts'] = j + 1
                return False, logs
            logs.append(f"✅ 完成 ({elapsed:.0f}s)")
            _append_log(f"✅ {script} ({elapsed:.0f}s)")
        except subprocess.TimeoutExpired:
            logs.append(f"❌ 超时 (>600s)")
            _append_log(f"❌ {script} 超时")
            state['progress']['completed_scripts'] = j + 1
            return False, logs
        except Exception as e:
            logs.append(f"❌ 异常: {e}")
            _append_log(f"❌ {script} 异常: {e}")
            state['progress']['completed_scripts'] = j + 1
            return False, logs

        state['progress']['completed_scripts'] = j + 1

    total = time.time() - t0
    logs.append(f"🎉 全部完成 ({total:.1f}s)")
    return True, logs


def _run_in_background(mod_keys):
    """后台线程：依次跑 mod_keys 列表中的模块"""
    try:
        _cancel_flag.clear()
        state['progress'] = _make_progress()
        state['progress']['total_modules'] = len(mod_keys)
        t0 = time.time()

        for i, mod_key in enumerate(mod_keys):
            if _cancel_flag.is_set():
                _append_log("⛔ 任务已取消")
                break

            mod = MODULES[mod_key]
            state['module'] = mod_key
            state['module_name'] = mod['name']
            state['progress']['current_module_index'] = i
            state['progress']['total_scripts'] = len(mod['scripts'])
            state['progress']['completed_scripts'] = 0
            state['progress']['current_script'] = None

            ok, logs = run_module(mod_key)

            state['progress']['completed_modules'] = i + 1
            state['progress']['results'][mod_key] = {
                'ok': ok,
                'name': mod['name'],
                'elapsed': round(time.time() - t0, 1),
            }
            state['progress']['elapsed'] = round(time.time() - t0, 1)

        state['progress']['elapsed'] = round(time.time() - t0, 1)
        state['last_result'] = {
            'ok': all(r['ok'] for r in state['progress']['results'].values()),
            'results': state['progress']['results'],
            'time': time.strftime('%H:%M:%S'),
            'elapsed': state['progress']['elapsed'],
        }
    finally:
        state['running'] = False
        state['module'] = None
        state['module_name'] = None
        state['step'] = None
        lock.release()


class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')

    def _json(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        accept_enc = self.headers.get('Accept-Encoding', '')
        if 'gzip' in accept_enc and len(body) > 256:
            body = gzip.compress(body)
            self.send_header('Content-Encoding', 'gzip')
        self.send_header('Content-Length', str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def _read_body(self):
        length = int(self.headers.get('Content-Length', 0))
        if length == 0:
            return {}
        try:
            return json.loads(self.rfile.read(length))
        except:
            return {}

    def _get_token(self):
        h = self.headers.get('Authorization', '')
        if h.startswith('Bearer '):
            return h[7:]
        return None

    def _get_user(self):
        return auth.verify_token(self._get_token())

    def _require_admin(self):
        user = self._get_user()
        if not user:
            self._json(401, {'error': '未登录'})
            return None
        if not user['is_admin']:
            self._json(403, {'error': '无管理员权限'})
            return None
        return user

    def _client_ip(self):
        return self.headers.get('X-Forwarded-For', self.client_address[0]).split(',')[0].strip()

    # ═══ MIME 类型 ═══
    MIME_MAP = {
        '.html':'text/html','.htm':'text/html','.css':'text/css','.js':'application/javascript',
        '.json':'application/json','.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg',
        '.gif':'image/gif','.svg':'image/svg+xml','.ico':'image/x-icon','.webp':'image/webp',
        '.woff':'font/woff','.woff2':'font/woff2','.ttf':'font/ttf','.txt':'text/plain',
        '.webmanifest':'application/manifest+json','.map':'application/json',
    }

    # 静态文件 gzip 缓存: {filepath: (mtime, gzipped_data)}
    _gz_cache = {}

    def _serve_static(self, url_path):
        """托管静态文件"""
        # 清理路径，防止目录遍历
        path = url_path.split('?')[0].split('#')[0]
        if path == '/' or path == '':
            path = '/index.html'
        path = path.lstrip('/')
        # 安全检查
        if '..' in path:
            self._json(403, {'error': 'forbidden'})
            return
        filepath = os.path.join(BASE_DIR, path)
        if not os.path.isfile(filepath):
            # 尝试加 index.html
            if os.path.isdir(filepath):
                filepath = os.path.join(filepath, 'index.html')
            if not os.path.isfile(filepath):
                self._json(404, {'error': 'not found'})
                return
        ext = os.path.splitext(filepath)[1].lower()
        content_type = self.MIME_MAP.get(ext, 'application/octet-stream')
        try:
            with open(filepath, 'rb') as f:
                data = f.read()
            self.send_response(200)
            self.send_header('Content-Type', content_type + ('; charset=utf-8' if ext in ('.html','.css','.js','.json','.svg','.txt') else ''))
            accept_enc = self.headers.get('Accept-Encoding', '')
            if 'gzip' in accept_enc and len(data) > 1024 and ext in ('.html','.css','.js','.json','.svg','.txt'):
                mtime = os.path.getmtime(filepath)
                cached = Handler._gz_cache.get(filepath)
                if cached and cached[0] == mtime:
                    data = cached[1]
                else:
                    data = gzip.compress(data, compresslevel=6)
                    Handler._gz_cache[filepath] = (mtime, data)
                self.send_header('Content-Encoding', 'gzip')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate' if ext in ('.html','.json') else 'public, max-age=3600')
            self._cors()
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            self._json(500, {'error': str(e)})

    def do_GET(self):
        if self.path == '/api/status':
            self._json(200, {
                'running': state['running'],
                'mode': state['mode'],
                'module': state['module'],
                'module_name': state['module_name'],
                'step': state['step'],
                'started': state['started'],
                'last_result': state['last_result'],
                'progress': state['progress'],
                'modules': {k: v['name'] for k, v in MODULES.items()},
            })
        elif self.path == '/api/auth/me':
            user = self._get_user()
            if user:
                self._json(200, user)
            else:
                self._json(401, {'error': '未登录或 token 已过期'})
        elif self.path == '/api/admin/users':
            admin = self._require_admin()
            if admin:
                self._json(200, {'users': auth.list_users()})
        elif self.path.startswith('/api/admin/logs'):
            admin = self._require_admin()
            if admin:
                self._json(200, {'logs': auth.list_login_log(200)})
        elif self.path.startswith('/api/'):
            self._json(404, {'error': 'not found'})
        else:
            self._serve_static(self.path)

    def _check_market_hours(self):
        """只允许 15:00 ~ 次日 09:30 刷新（A股数据收盘后才完整）"""
        from datetime import datetime
        now = datetime.now()
        h, m = now.hour, now.minute
        # 允许：15:00~23:59 或 00:00~09:30
        if 15 <= h <= 23 or h < 9 or (h == 9 and m <= 30):
            return True
        self._json(403, {'error': f'当前时间 {now.strftime("%H:%M")}，刷新仅限 15:00~次日09:30'})
        return False

    def do_POST(self):
        # ═══ 认证 API ═══
        if self.path == '/api/auth/register':
            body = self._read_body()
            ok, msg = auth.register(body.get('username',''), body.get('password',''), body.get('display_name',''))
            self._json(200 if ok else 400, {'ok': ok, 'msg': msg})
            return

        if self.path == '/api/auth/login':
            body = self._read_body()
            ok, data = auth.login(body.get('username',''), body.get('password',''), self._client_ip())
            if ok:
                self._json(200, {'ok': True, **data})
            else:
                self._json(401, {'ok': False, 'msg': data})
            return

        if self.path == '/api/auth/logout':
            token = self._get_token()
            if token:
                auth.logout(token)
            self._json(200, {'ok': True})
            return

        if self.path == '/api/admin/toggle-user':
            admin = self._require_admin()
            if not admin: return
            body = self._read_body()
            auth.toggle_user_status(body.get('user_id'), body.get('status', 'disabled'))
            self._json(200, {'ok': True})
            return

        if self.path == '/api/admin/delete-user':
            admin = self._require_admin()
            if not admin: return
            body = self._read_body()
            auth.delete_user(body.get('user_id'))
            self._json(200, {'ok': True})
            return

        if self.path == '/api/admin/reset-password':
            admin = self._require_admin()
            if not admin: return
            body = self._read_body()
            auth.reset_password(body.get('user_id'), body.get('password', ''))
            self._json(200, {'ok': True})
            return

        # ═══ 取消 API（仅管理员）═══
        if self.path == '/api/cancel':
            admin = self._require_admin()
            if not admin: return
            if not state['running']:
                self._json(400, {'error': '当前没有任务在运行'})
                return
            _cancel_flag.set()
            _append_log("⛔ 收到取消请求")
            self._json(200, {'ok': True, 'message': '已发送取消信号'})
            return

        # ═══ 刷新 API（仅管理员，异步模式）═══
        # POST /api/refresh/<tab-name>
        parts = self.path.strip('/').split('/')
        if len(parts) == 3 and parts[0] == 'api' and parts[1] == 'refresh':
            admin = self._require_admin()
            if not admin: return
            tab = parts[2]
            mod_key = TAB_MAP.get(tab, tab.replace('-', '_'))

            if mod_key not in MODULES:
                self._json(400, {'error': f'未知模块: {tab}', 'available': list(TAB_MAP.keys())})
                return

            if not self._check_market_hours():
                return

            acquired = lock.acquire(blocking=False)
            if not acquired:
                self._json(429, {
                    'error': '有任务正在运行，请稍后再试',
                    'running_module': state['module'],
                    'step': state['step'],
                })
                return

            state['running'] = True
            state['mode'] = 'single'
            state['module'] = mod_key
            state['module_name'] = MODULES[mod_key]['name']
            state['step'] = 'starting'
            state['started'] = time.strftime('%H:%M:%S')

            t = threading.Thread(target=_run_in_background, args=([mod_key],), daemon=True)
            t.start()
            self._json(202, {'ok': True, 'message': f'已启动刷新: {MODULES[mod_key]["name"]}'})

        # POST /api/refresh-all
        elif self.path == '/api/refresh-all':
            admin = self._require_admin()
            if not admin: return
            if not self._check_market_hours():
                return
            acquired = lock.acquire(blocking=False)
            if not acquired:
                self._json(429, {'error': '有任务正在运行', 'running_module': state['module']})
                return

            mod_keys = list(MODULES.keys())
            state['running'] = True
            state['mode'] = 'all'
            state['module'] = mod_keys[0]
            state['module_name'] = MODULES[mod_keys[0]]['name']
            state['step'] = 'starting'
            state['started'] = time.strftime('%H:%M:%S')

            t = threading.Thread(target=_run_in_background, args=(mod_keys,), daemon=True)
            t.start()
            self._json(202, {'ok': True, 'message': '已启动全部刷新'})
        else:
            self._json(404, {'error': 'not found'})

    def log_message(self, fmt, *args):
        ts = time.strftime('%H:%M:%S')
        print(f"[{ts}] {args[0]}", flush=True)


def main():
    port = 9876

    # 预热：启动时预压缩大文件
    for name in ('index.html', 'admin.html'):
        fp = os.path.join(BASE_DIR, name)
        if os.path.isfile(fp):
            with open(fp, 'rb') as f:
                data = f.read()
            gz = gzip.compress(data, compresslevel=6)
            Handler._gz_cache[fp] = (os.path.getmtime(fp), gz)
            print(f"   预压缩 {name}: {len(data)//1024}KB → {len(gz)//1024}KB")

    server = ThreadedHTTPServer(('0.0.0.0', port), Handler)
    print(f"🚀 GAMT 刷新服务启动: http://localhost:{port}")
    print(f"   POST /api/refresh/<tab>  — 刷新单个模块（异步）")
    print(f"   POST /api/refresh-all    — 刷新全部（异步）")
    print(f"   POST /api/cancel         — 取消当前任务")
    print(f"   GET  /api/status         — 查看状态+进度")
    print(f"   可用 tab: {', '.join(TAB_MAP.keys())}")
    print(flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()

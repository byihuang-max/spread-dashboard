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
from urllib.parse import urlparse, parse_qs
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from module_registry import build_refresh_modules, build_tab_map, MODULE_REGISTRY

# ═══ 更新日志 ═══
UPDATE_LOG_PATH = os.path.join(BASE_DIR, 'server', 'update_log.json')
UPDATE_LOG_MAX = 500  # 最多保留500条

def _load_update_log():
    if os.path.exists(UPDATE_LOG_PATH):
        try:
            with open(UPDATE_LOG_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []
    return []

def _save_update_log(logs):
    # 只保留最近 MAX 条
    logs = logs[-UPDATE_LOG_MAX:]
    with open(UPDATE_LOG_PATH, 'w', encoding='utf-8') as f:
        json.dump(logs, f, ensure_ascii=False, indent=1)

def _record_update(mod_key, mod_name, ok, elapsed, user=None):
    """记录一次模块更新"""
    logs = _load_update_log()
    logs.append({
        'module': mod_key,
        'name': mod_name,
        'ok': ok,
        'elapsed': round(elapsed, 1),
        'time': time.strftime('%Y-%m-%d %H:%M:%S'),
        'date': time.strftime('%Y-%m-%d'),
        'user': user or 'system',
    })
    _save_update_log(logs)

# ═══ 认证模块 ═══
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# 产品池管理 API
POOL_SCRIPTS_DIR = os.path.join(BASE_DIR, 'fund-asset-recommend', 'scripts')
if POOL_SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, POOL_SCRIPTS_DIR)
# 尽调库 API
DD_DIR = os.path.join(BASE_DIR, 'dd-dashboard')
if DD_DIR not in sys.path:
    sys.path.insert(0, DD_DIR)
import auth

# ═══ 模块配置（单一注册表生成）═══
MODULES = build_refresh_modules()
TAB_MAP = build_tab_map()


def get_refresh_all_modules():
    """refresh-all 统一口径：先常规模块，后晚到模块。"""
    normal = [k for k in MODULES.keys() if not MODULE_REGISTRY.get(k, {}).get('late_data')]
    late = [k for k in MODULES.keys() if MODULE_REGISTRY.get(k, {}).get('late_data')]
    return normal + late

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
            logs.append(" 任务已取消")
            _append_log(" 任务已取消")
            return False, logs

        # 更新进度
        state['progress']['current_script'] = script
        state['progress']['completed_scripts'] = j
        state['step'] = f"{subdir}/{script}"

        path = os.path.join(BASE_DIR, subdir, script)
        cwd = os.path.join(BASE_DIR, subdir)

        if not os.path.exists(path):
            logs.append(f"⚠ 跳过不存在: {subdir}/{script}")
            _append_log(f"⚠ 跳过: {script}")
            continue

        _append_log(f" {mod['name']} → {script}")
        logs.append(f" {subdir}/{script}")

        try:
            result = subprocess.run(
                [sys.executable, path],
                cwd=cwd,
                capture_output=True, text=True, timeout=600
            )
            elapsed = time.time() - t0
            if result.returncode != 0:
                err = result.stderr[-300:] if result.stderr else result.stdout[-300:]
                logs.append(f" 失败 ({elapsed:.1f}s): {err}")
                _append_log(f" {script} 失败 ({elapsed:.0f}s)")
                state['progress']['completed_scripts'] = j + 1
                return False, logs
            logs.append(f" 完成 ({elapsed:.0f}s)")
            _append_log(f" {script} ({elapsed:.0f}s)")
        except subprocess.TimeoutExpired:
            logs.append(f" 超时 (>600s)")
            _append_log(f" {script} 超时")
            state['progress']['completed_scripts'] = j + 1
            return False, logs
        except Exception as e:
            logs.append(f" 异常: {e}")
            _append_log(f" {script} 异常: {e}")
            state['progress']['completed_scripts'] = j + 1
            return False, logs

        state['progress']['completed_scripts'] = j + 1

    total = time.time() - t0
    logs.append(f" 全部完成 ({total:.1f}s)")
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
                _append_log(" 任务已取消")
                break

            mod = MODULES[mod_key]
            state['module'] = mod_key
            state['module_name'] = mod['name']
            state['progress']['current_module_index'] = i
            state['progress']['total_scripts'] = len(mod['scripts'])
            state['progress']['completed_scripts'] = 0
            state['progress']['current_script'] = None

            ok, logs = run_module(mod_key)

            mod_elapsed = time.time() - t0
            state['progress']['completed_modules'] = i + 1
            state['progress']['results'][mod_key] = {
                'ok': ok,
                'name': mod['name'],
                'elapsed': round(mod_elapsed, 1),
            }
            state['progress']['elapsed'] = round(mod_elapsed, 1)

            # 记录更新日志
            _record_update(mod_key, mod['name'], ok, mod_elapsed,
                           user=state.get('triggered_by', 'system'))

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

    def _serve_notes_list(self):
        """返回Smart Notes所有笔记的元数据列表

        扫描范围：smart-notes/ 根下所有笔记（含 concepts/ conversations/
        decisions/ sessions/ notes/ 等 10 类分层目录）。
        排除：intelligence/（智能分类系统代码与索引，不是笔记）
              以 _ 或 . 开头的隐藏目录 / README.md。
        """
        from pathlib import Path
        root_dir = Path(BASE_DIR) / 'smart-notes'
        notes = []

        if not root_dir.exists():
            self._json(200, notes)
            return

        # 不作为笔记扫描的顶层目录
        EXCLUDE_TOPS = {'intelligence', 'node_modules', '.git'}

        for md_file in root_dir.rglob('*.md'):
            try:
                rel = md_file.relative_to(root_dir)
            except ValueError:
                continue
            parts = rel.parts
            if not parts:
                continue

            # 排除顶层目录 / 隐藏目录 / README
            top = parts[0]
            if top in EXCLUDE_TOPS or top.startswith('.') or top.startswith('_'):
                continue
            if md_file.name.lower() in ('readme.md', 'audit.md'):
                continue

            # 推断分类
            if len(parts) == 1:
                # 根目录下的散笔记
                category = 'uncategorized'
            elif top == 'notes' and len(parts) > 2:
                # notes/research/factors/xxx.md → notes/research
                # notes/engineering/xxx.md → notes/engineering
                category = f'notes/{parts[1]}'
            elif top == 'research' and len(parts) > 2:
                # 兼容根目录下的 research/factors/xxx.md
                category = f'research/{parts[1]}'
            else:
                category = top

            try:
                with open(md_file, 'r', encoding='utf-8') as f:
                    content = f.read()
            except Exception:
                content = ''

            notes.append({
                'name': md_file.stem,
                'path': str(rel),
                'category': category,
                'content': content,
            })

        # 固定顺序：按分类 + 文件名，便于前端稳定展示
        notes.sort(key=lambda n: (n['category'], n['path']))
        self._json(200, notes)

    def _serve_narrative_latest(self):
        """返回最新的叙事监控数据"""
        from pathlib import Path
        from datetime import datetime
        
        cache_dir = Path(BASE_DIR) / "daily_report" / "meme交易" / "cache"
        
        # 找到最新的narrative文件
        narrative_files = sorted(cache_dir.glob("narrative_*.json"))
        if not narrative_files:
            self._json(404, {"error": "No data available"})
            return
        
        latest_file = narrative_files[-1]
        
        try:
            with open(latest_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 提取时间戳
            filename = latest_file.stem  # narrative_20260316_2315
            parts = filename.split('_')
            if len(parts) >= 3:
                timestamp = datetime.strptime(parts[1] + parts[2], '%Y%m%d%H%M').strftime('%Y-%m-%d %H:%M')
            else:
                timestamp = "Unknown"
            
            # 格式化数据
            result = {
                "timestamp": timestamp,
                "news_count": data.get("news_count", 0),
                "fixed_analysis": data.get("fixed_analysis", {}),
                "dynamic_themes": data.get("dynamic_themes", [])
            }
            
            self._json(200, result)
        except Exception as e:
            self._json(500, {"error": str(e)})
        return user

    def _serve_chip_query(self):
        """个股筹码分析 API"""
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        code = params.get('code', [''])[0].strip().upper()
        if not code:
            self._json(400, {'success': False, 'error': '缺少 code 参数'})
            return
        try:
            from chip_api import analyze_stock
            result = analyze_stock(code)
            self._json(200, result)
        except Exception as e:
            self._json(500, {'success': False, 'error': str(e)})

    def _serve_stock_search(self):
        """股票名称/代码模糊搜索 API"""
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        keyword = params.get('q', [''])[0].strip()
        if not keyword:
            self._json(400, {'success': False, 'error': '缺少 q 参数'})
            return
        try:
            from chip_api import search_stock
            results = search_stock(keyword)
            self._json(200, {'success': True, 'results': results})
        except Exception as e:
            self._json(500, {'success': False, 'error': str(e)})

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
        elif self.path == '/api/narrative_latest':
            # 叙事监控最新数据
            self._serve_narrative_latest()
        elif self.path == '/api/notes':
            # Smart Notes API - 动态加载笔记
            self._serve_notes_list()
        elif self.path == '/api/auth/me':
            user = self._get_user()
            if user:
                self._json(200, user)
            else:
                self._json(401, {'error': '未登录或 token 已过期'})
        elif self.path == '/api/auth/settings':
            self._json(200, {'invite_mode': auth.get_invite_mode()})
        elif self.path == '/api/auth/invite/validate':
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            code = params.get('code', [''])[0]
            ok, msg, invite = auth.validate_invite_code(code)
            self._json(200 if ok else 400, {
                'ok': ok,
                'msg': msg,
                'invite': {
                    'id': invite['id'],
                    'note': invite.get('note', ''),
                    'max_uses': invite.get('max_uses', 1),
                    'used_count': invite.get('used_count', 0),
                    'expires_at': invite.get('expires_at'),
                } if invite else None
            })
        elif self.path == '/api/admin/users':
            admin = self._require_admin()
            if admin:
                self._json(200, {'users': auth.list_users()})
        elif self.path == '/api/admin/invites':
            admin = self._require_admin()
            if admin:
                self._json(200, {
                    'invite_mode': auth.get_invite_mode(),
                    'invites': auth.list_invite_codes(200)
                })
        elif self.path.startswith('/api/admin/logs'):
            admin = self._require_admin()
            if admin:
                self._json(200, {'logs': auth.list_login_log(200)})
        elif self.path == '/api/admin/users-by-tier':
            admin = self._require_admin()
            if admin:
                self._json(200, auth.list_users_by_tier())
        elif self.path == '/api/admin/module-permissions':
            admin = self._require_admin()
            if admin:
                self._json(200, auth.get_module_permissions())
        elif self.path == '/api/modules/accessible':
            user = self._get_user()
            if not user:
                # 未登录返回全部模块key（向后兼容）
                all_keys = list(MODULE_REGISTRY.keys())
                self._json(200, {'modules': all_keys})
            else:
                perms = auth.get_module_permissions()
                perm_map = {p['module_key']: p['min_tier'] for p in perms}
                user_tier = 99 if user.get('is_admin') else int(user.get('tier', 0))
                accessible = []
                for key in MODULE_REGISTRY.keys():
                    min_tier = perm_map.get(key, 0)
                    if user_tier >= min_tier:
                        accessible.append(key)
                # 也检查非 registry 中的模块（如 fund_analysis, smart-notes 等）
                for key, min_tier in perm_map.items():
                    if key not in accessible and user_tier >= min_tier:
                        accessible.append(key)
                self._json(200, {'modules': accessible})
        elif self.path.startswith('/api/chip_query'):
            self._serve_chip_query()
        elif self.path.startswith('/api/stock_search'):
            self._serve_stock_search()
        elif self.path == '/api/update-log':
            # 更新日志（需要登录）
            user = self._get_user()
            if not user:
                self._json(401, {'error': '未登录'})
            else:
                logs = _load_update_log()
                # 按日期倒序，最近的在前
                logs.reverse()
                self._json(200, {'logs': logs})
        elif self.path == '/api/email-subscribers':
            admin = self._require_admin()
            if not admin: return
            sub_path = os.path.join(BASE_DIR, 'env_fit', 'momentum_stock', 'email_subscribers.json')
            try:
                with open(sub_path, encoding='utf-8') as f:
                    self._json(200, json.load(f))
            except FileNotFoundError:
                self._json(200, {'subscribers': []})

        elif self.path == '/api/admin/fund-asset-pool':
            # 产品池管理 - 查看（团队+可查看，admin 看全部）
            user = self._get_user()
            if not user:
                self._json(401, {'error': '未登录'})
            elif not user.get('is_admin') and int(user.get('tier', 0)) < 2:
                self._json(403, {'error': '需要团队权限'})
            else:
                import pool_api
                pool = pool_api.get_all_pool()
                stats = pool_api.get_pool_stats()
                # 非管理员只能看到自己提交的 + approved 的
                if not user.get('is_admin'):
                    products = pool.get('products', [])
                    pool['products'] = [
                        p for p in products
                        if p.get('status') == 'approved'
                        or p.get('submitted_by') == user.get('display_name', '')
                        or p.get('submitted_by') == user.get('username', '')
                    ]
                self._json(200, {'pool': pool, 'stats': stats})

        # ═══ 尽调库 GET API ═══
        elif self.path == '/api/dd/funds':
            import dd_api
            self._json(200, dd_api.get_all())
        elif self.path == '/api/dd/stats':
            import dd_api
            self._json(200, dd_api.get_stats())
        elif self.path.startswith('/api/dd/funds/'):
            import dd_api
            fund_id = self.path.split('/api/dd/funds/')[1].split('?')[0]
            fund = dd_api.get_by_id(fund_id)
            if fund:
                self._json(200, fund)
            else:
                self._json(404, {'error': '基金不存在'})

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
            ok, msg = auth.register(
                body.get('username',''),
                body.get('password',''),
                body.get('display_name',''),
                body.get('invite_code','')
            )
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

        if self.path == '/api/admin/set-tier':
            admin = self._require_admin()
            if not admin: return
            body = self._read_body()
            tier = body.get('tier', 0)
            if tier not in (0, 1, 2):
                self._json(400, {'error': 'tier 只能是 0, 1 或 2'})
                return
            auth.set_tier(body.get('user_id'), tier)
            self._json(200, {'ok': True})
            return

        if self.path == '/api/admin/set-module-permission':
            admin = self._require_admin()
            if not admin: return
            body = self._read_body()
            try:
                auth.set_module_permission(body.get('module_key', ''), body.get('min_tier', 0))
                self._json(200, {'ok': True})
            except Exception as e:
                self._json(400, {'error': str(e)})
            return

        if self.path == '/api/admin/invite-mode':
            admin = self._require_admin()
            if not admin: return
            body = self._read_body()
            try:
                mode = auth.set_invite_mode(body.get('mode', 'open'))
            except ValueError as e:
                self._json(400, {'error': str(e)})
                return
            self._json(200, {'ok': True, 'invite_mode': mode})
            return

        if self.path == '/api/admin/create-invite':
            admin = self._require_admin()
            if not admin: return
            body = self._read_body()
            try:
                invite = auth.create_invite_code(
                    note=body.get('note', ''),
                    max_uses=body.get('max_uses', 1),
                    expires_at=body.get('expires_at'),
                    created_by=admin['id'],
                    code=body.get('code', '')
                )
                self._json(200, {'ok': True, 'invite': invite})
            except Exception as e:
                self._json(400, {'ok': False, 'error': str(e)})
            return

        if self.path == '/api/admin/toggle-invite':
            admin = self._require_admin()
            if not admin: return
            body = self._read_body()
            auth.toggle_invite_code(body.get('invite_id'), body.get('status', 'disabled'))
            self._json(200, {'ok': True})
            return

        if self.path == '/api/admin/delete-invite':
            admin = self._require_admin()
            if not admin: return
            body = self._read_body()
            auth.delete_invite_code(body.get('invite_id'))
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
            _append_log(" 收到取消请求")
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
            user = self._get_user()
            state['triggered_by'] = user['display_name'] if user else 'system'

            t = threading.Thread(target=_run_in_background, args=([mod_key],), daemon=True)
            t.start()
            self._json(202, {'ok': True, 'message': f'已启动刷新: {MODULES[mod_key]["name"]}'})

        elif self.path == '/api/email-subscribers':
            admin = self._require_admin()
            if not admin: return
            body = self._read_body()
            sub_path = os.path.join(BASE_DIR, 'env_fit', 'momentum_stock', 'email_subscribers.json')
            # 只允许更新 subscribers 列表
            try:
                with open(sub_path, encoding='utf-8') as f:
                    cfg = json.load(f)
            except FileNotFoundError:
                cfg = {'subscribers': [], 'sender': {}, 'settings': {}}
            cfg['subscribers'] = body.get('subscribers', cfg['subscribers'])
            with open(sub_path, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            # git commit + push 保持版本跟踪
            def _git_sync_subscribers():
                import subprocess
                try:
                    subprocess.run(['git', 'add', sub_path], cwd=BASE_DIR, timeout=10)
                    subprocess.run(['git', 'commit', '-m', 'chore: 更新邮件订阅者列表'], cwd=BASE_DIR, timeout=10)
                    # 推送到可用的 remote
                    for remote in ['gitee', 'origin']:
                        try:
                            result = subprocess.run(['git', 'remote'], cwd=BASE_DIR, capture_output=True, text=True, timeout=5)
                            if remote in result.stdout:
                                subprocess.run(['git', 'push', remote, 'main'], cwd=BASE_DIR, timeout=30)
                                break
                        except Exception:
                            continue
                except Exception as e:
                    print(f'[email-subscribers] git sync failed: {e}')
            threading.Thread(target=_git_sync_subscribers, daemon=True).start()
            self._json(200, {'ok': True, 'count': len(cfg['subscribers'])})

        # ═══ 产品池管理 API ═══
        elif self.path == '/api/admin/fund-asset-pool/submit':
            # 团队成员提交产品（tier >= 2）
            user = self._get_user()
            if not user:
                self._json(401, {'error': '未登录'}); return
            if not user.get('is_admin') and int(user.get('tier', 0)) < 2:
                self._json(403, {'error': '需要团队权限'}); return
            body = self._read_body()
            import pool_api
            ok, msg = pool_api.submit_product(
                reg_code=body.get('code', ''),
                name=body.get('name', ''),
                group=body.get('group', ''),
                detail=body.get('detail', ''),
                reason=body.get('reason', ''),
                submitted_by=user.get('display_name') or user.get('username', ''),
                benchmark=body.get('benchmark'),
                benchmark_name=body.get('benchmark_name'),
            )
            self._json(200 if ok else 400, {'ok': ok, 'msg': msg})

        elif self.path == '/api/admin/fund-asset-pool/review':
            # 管理员审核（approve / reject）
            admin = self._require_admin()
            if not admin: return
            body = self._read_body()
            import pool_api
            ok, msg = pool_api.review_product(
                reg_code=body.get('code', ''),
                action=body.get('action', ''),
                reviewed_by=admin.get('display_name') or admin.get('username', ''),
                review_note=body.get('review_note', ''),
            )
            self._json(200 if ok else 400, {'ok': ok, 'msg': msg})

        elif self.path == '/api/admin/fund-asset-pool/remove':
            # 管理员下架
            admin = self._require_admin()
            if not admin: return
            body = self._read_body()
            import pool_api
            ok, msg = pool_api.remove_product(
                reg_code=body.get('code', ''),
                removed_by=admin.get('display_name') or admin.get('username', ''),
            )
            self._json(200 if ok else 400, {'ok': ok, 'msg': msg})

        elif self.path == '/api/admin/fund-asset-pool/restore':
            # 管理员恢复
            admin = self._require_admin()
            if not admin: return
            body = self._read_body()
            import pool_api
            ok, msg = pool_api.restore_product(
                reg_code=body.get('code', ''),
                restored_by=admin.get('display_name') or admin.get('username', ''),
            )
            self._json(200 if ok else 400, {'ok': ok, 'msg': msg})

        elif self.path == '/api/admin/fund-asset-pool/retry':
            # 重新验证失败的产品
            user = self._get_user()
            if not user:
                self._json(401, {'error': '未登录'}); return
            if not user.get('is_admin') and int(user.get('tier', 0)) < 2:
                self._json(403, {'error': '需要团队权限'}); return
            body = self._read_body()
            import pool_api
            ok, msg = pool_api.retry_verify(body.get('code', ''))
            self._json(200 if ok else 400, {'ok': ok, 'msg': msg})

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

            mod_keys = get_refresh_all_modules()
            state['running'] = True
            state['mode'] = 'all'
            state['module'] = mod_keys[0]
            state['module_name'] = MODULES[mod_keys[0]]['name']
            state['step'] = 'starting'
            state['started'] = time.strftime('%H:%M:%S')
            user = self._get_user()
            state['triggered_by'] = user['display_name'] if user else 'system'

            t = threading.Thread(target=_run_in_background, args=(mod_keys,), daemon=True)
            t.start()
            self._json(202, {'ok': True, 'message': '已启动全部刷新'})

        # ═══ 尽调库 POST API ═══
        elif self.path == '/api/dd/funds':
            # 创建新基金
            user = self._get_user()
            if not user:
                self._json(401, {'error': '未登录'}); return
            body = self._read_body()
            import dd_api
            created_by = user.get('display_name') or user.get('username', 'system')
            ok, result = dd_api.create_fund(body, created_by=created_by)
            self._json(200 if ok else 400, {'ok': ok, 'data': result} if ok else {'ok': ok, 'error': result})

        elif self.path.startswith('/api/dd/funds/') and '/stage' in self.path:
            # 阶段变更: POST /api/dd/funds/<id>/stage
            user = self._get_user()
            if not user:
                self._json(401, {'error': '未登录'}); return
            fund_id = self.path.split('/api/dd/funds/')[1].split('/stage')[0]
            body = self._read_body()
            import dd_api
            changed_by = user.get('display_name') or user.get('username', 'system')
            ok, result = dd_api.change_stage(fund_id, body.get('stage', ''), changed_by=changed_by, note=body.get('note', ''))
            if ok:
                self._json(200, {'ok': True, 'data': result})
            else:
                self._json(400, {'ok': False, 'error': result})

        elif self.path.startswith('/api/dd/funds/') and '/rating' in self.path:
            # 评分: POST /api/dd/funds/<id>/rating
            user = self._get_user()
            if not user:
                self._json(401, {'error': '未登录'}); return
            fund_id = self.path.split('/api/dd/funds/')[1].split('/rating')[0]
            body = self._read_body()
            import dd_api
            rated_by = user.get('display_name') or user.get('username', 'system')
            ok, result = dd_api.rate_fund(fund_id, body, rated_by=rated_by)
            if ok:
                self._json(200, {'ok': True, 'data': result})
            else:
                self._json(400, {'ok': False, 'error': result})

        elif self.path.startswith('/api/dd/funds/') and '/update' in self.path:
            # 更新: POST /api/dd/funds/<id>/update
            user = self._get_user()
            if not user:
                self._json(401, {'error': '未登录'}); return
            fund_id = self.path.split('/api/dd/funds/')[1].split('/update')[0]
            body = self._read_body()
            import dd_api
            updated_by = user.get('display_name') or user.get('username', 'system')
            ok, result = dd_api.update_fund(fund_id, body, updated_by=updated_by)
            if ok:
                self._json(200, {'ok': True, 'data': result})
            else:
                self._json(400, {'ok': False, 'error': result})

        elif self.path.startswith('/api/dd/funds/') and '/delete' in self.path:
            # 删除: POST /api/dd/funds/<id>/delete (admin only)
            admin = self._require_admin()
            if not admin: return
            fund_id = self.path.split('/api/dd/funds/')[1].split('/delete')[0]
            import dd_api
            deleted_by = admin.get('display_name') or admin.get('username', 'system')
            ok, result = dd_api.delete_fund(fund_id, deleted_by=deleted_by)
            self._json(200 if ok else 400, {'ok': ok, 'msg': result})

        elif self.path == '/api/dd/upload':
            # 文件上传
            user = self._get_user()
            if not user:
                self._json(401, {'error': '未登录'}); return
            content_type = self.headers.get('Content-Type', '')
            if 'multipart/form-data' not in content_type:
                self._json(400, {'error': '需要 multipart/form-data'})
                return
            import dd_api
            # 简单 multipart 解析
            content_length = int(self.headers.get('Content-Length', 0))
            body_bytes = self.rfile.read(content_length)
            boundary = content_type.split('boundary=')[1].strip() if 'boundary=' in content_type else ''
            if not boundary:
                self._json(400, {'error': '无法解析 boundary'}); return
            parts = body_bytes.split(f'--{boundary}'.encode())
            filename = None
            file_data = None
            fund_id = None
            for part in parts:
                if b'Content-Disposition' not in part:
                    continue
                header_end = part.find(b'\r\n\r\n')
                if header_end < 0:
                    continue
                header = part[:header_end].decode('utf-8', errors='ignore')
                data = part[header_end+4:]
                if data.endswith(b'\r\n'):
                    data = data[:-2]
                if 'name="file"' in header or 'name="attachment"' in header:
                    # Extract filename
                    if 'filename="' in header:
                        fn_start = header.index('filename="') + 10
                        fn_end = header.index('"', fn_start)
                        filename = header[fn_start:fn_end]
                    file_data = data
                elif 'name="fund_id"' in header:
                    fund_id = data.decode('utf-8').strip()
            if not filename or not file_data:
                self._json(400, {'error': '未找到文件'}); return
            filepath = dd_api.save_upload(filename, file_data)
            if fund_id:
                uploaded_by = user.get('display_name') or user.get('username', 'system')
                dd_api.add_attachment(fund_id, filename, filepath, uploaded_by=uploaded_by)
            self._json(200, {'ok': True, 'path': filepath, 'name': filename})

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
    print(f" GAMT 刷新服务启动: http://localhost:{port}")
    print(f"   POST /api/refresh/<tab>  — 刷新单个模块（异步）")
    print(f"   POST /api/refresh-all    — 刷新全部（异步）")
    print(f"   POST /api/cancel         — 取消当前任务")
    print(f"   GET  /api/status         — 查看状态+进度")
    print(f"   可用 tab: {', '.join(TAB_MAP.keys())}")
    print(flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()

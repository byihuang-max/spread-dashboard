#!/usr/bin/env python3
"""
GAMT 用户认证模块
- SQLite 存储用户数据
- bcrypt-like 密码哈希 (hashlib + salt)
- UUID session token
- 邀请码系统（可选启用，不默认拦截开放注册）
"""

import sqlite3, hashlib, uuid, os, time, secrets

MAX_FAILED_LOGINS = 5
LOGIN_LOCK_MINUTES = 10

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'users.db')

INVITE_MODE_OPEN = 'open'
INVITE_MODE_OPTIONAL = 'optional'
INVITE_MODE_REQUIRED = 'required'


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL')
    return c


def init_db():
    """初始化数据库表"""
    c = _conn()
    c.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            display_name TEXT DEFAULT '',
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0,
            tier INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            last_login TEXT,
            login_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active'
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            expires_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS login_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            ip TEXT,
            action TEXT,
            success INTEGER,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS login_locks (
            ip TEXT PRIMARY KEY,
            failed_count INTEGER DEFAULT 0,
            locked_until TEXT,
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS invite_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            note TEXT DEFAULT '',
            max_uses INTEGER DEFAULT 1,
            used_count INTEGER DEFAULT 0,
            created_by INTEGER,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            expires_at TEXT,
            status TEXT DEFAULT 'active'
        );
        CREATE TABLE IF NOT EXISTS invite_code_uses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invite_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            username TEXT,
            used_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (invite_id) REFERENCES invite_codes(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    ''')
    # 自动迁移：给旧表加 tier 列（如果不存在）
    try:
        c.execute('SELECT tier FROM users LIMIT 1')
    except sqlite3.OperationalError:
        c.execute('ALTER TABLE users ADD COLUMN tier INTEGER DEFAULT 0')
        c.commit()
        print('[auth] 已迁移: 添加 tier 列')

    # 默认注册模式：开放注册
    c.execute('''
        INSERT OR IGNORE INTO system_settings (key, value)
        VALUES ('invite_mode', ?)
    ''', (INVITE_MODE_OPEN,))

    # 确保有默认管理员（首次运行）
    row = c.execute('SELECT COUNT(*) FROM users WHERE is_admin=1').fetchone()
    if row[0] == 0:
        _create_user(c, 'admin', 'gamt2026', is_admin=1, display_name='管理员')
        print('[auth] 默认管理员已创建: admin / gamt2026')
    c.commit()
    c.close()


def _hash_pw(password, salt=None):
    if salt is None:
        salt = uuid.uuid4().hex
    h = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return h.hex(), salt


def _create_user(conn, username, password, is_admin=0, display_name=''):
    h, s = _hash_pw(password)
    cur = conn.execute(
        'INSERT INTO users (username, display_name, password_hash, salt, is_admin) VALUES (?,?,?,?,?)',
        (username, display_name, h, s, is_admin)
    )
    conn.commit()
    return cur.lastrowid


def get_invite_mode():
    c = _conn()
    row = c.execute('SELECT value FROM system_settings WHERE key=?', ('invite_mode',)).fetchone()
    c.close()
    if not row:
        return INVITE_MODE_OPEN
    mode = (row['value'] or INVITE_MODE_OPEN).strip().lower()
    if mode not in (INVITE_MODE_OPEN, INVITE_MODE_OPTIONAL, INVITE_MODE_REQUIRED):
        return INVITE_MODE_OPEN
    return mode


def set_invite_mode(mode):
    mode = (mode or '').strip().lower()
    if mode not in (INVITE_MODE_OPEN, INVITE_MODE_OPTIONAL, INVITE_MODE_REQUIRED):
        raise ValueError('mode must be open / optional / required')
    c = _conn()
    c.execute('''
        INSERT INTO system_settings (key, value, updated_at)
        VALUES ('invite_mode', ?, datetime('now','localtime'))
        ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=datetime('now','localtime')
    ''', (mode,))
    c.commit()
    c.close()
    return mode


def _normalize_invite_code(code):
    return (code or '').strip().upper()


def create_invite_code(note='', max_uses=1, expires_at=None, created_by=None, code=None):
    max_uses = int(max_uses or 1)
    if max_uses < 1:
        max_uses = 1
    note = (note or '').strip()
    invite_code = _normalize_invite_code(code)
    if not invite_code:
        invite_code = secrets.token_urlsafe(9).replace('-', '').replace('_', '').upper()[:10]
    c = _conn()
    c.execute(
        '''
        INSERT INTO invite_codes (code, note, max_uses, expires_at, created_by)
        VALUES (?,?,?,?,?)
        ''',
        (invite_code, note, max_uses, expires_at, created_by)
    )
    invite_id = c.execute('SELECT last_insert_rowid()').fetchone()[0]
    c.commit()
    c.close()
    return get_invite_code(invite_id)


def get_invite_code(invite_id):
    c = _conn()
    row = c.execute('SELECT * FROM invite_codes WHERE id=?', (invite_id,)).fetchone()
    c.close()
    return dict(row) if row else None


def list_invite_codes(limit=200):
    c = _conn()
    rows = c.execute('''
        SELECT i.*, u.username AS creator_username, u.display_name AS creator_display_name
        FROM invite_codes i
        LEFT JOIN users u ON i.created_by = u.id
        ORDER BY i.created_at DESC, i.id DESC
        LIMIT ?
    ''', (limit,)).fetchall()
    c.close()
    return [dict(r) for r in rows]


def toggle_invite_code(invite_id, status):
    status = 'active' if status == 'active' else 'disabled'
    c = _conn()
    c.execute('UPDATE invite_codes SET status=? WHERE id=?', (status, invite_id))
    c.commit()
    c.close()


def delete_invite_code(invite_id):
    c = _conn()
    c.execute('DELETE FROM invite_code_uses WHERE invite_id=?', (invite_id,))
    c.execute('DELETE FROM invite_codes WHERE id=?', (invite_id,))
    c.commit()
    c.close()


def validate_invite_code(code):
    invite_code = _normalize_invite_code(code)
    if not invite_code:
        return False, '邀请码不能为空', None
    c = _conn()
    row = c.execute('SELECT * FROM invite_codes WHERE code=?', (invite_code,)).fetchone()
    c.close()
    if not row:
        return False, '邀请码不存在', None
    if row['status'] != 'active':
        return False, '邀请码已停用', None
    if row['expires_at']:
        now_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
        if row['expires_at'] <= now_str:
            return False, '邀请码已过期', None
    if int(row['used_count'] or 0) >= int(row['max_uses'] or 1):
        return False, '邀请码已用完', None
    return True, '邀请码有效', dict(row)


def _consume_invite_code(conn, invite_id, user_id, username):
    row = conn.execute('SELECT * FROM invite_codes WHERE id=?', (invite_id,)).fetchone()
    if not row:
        return False, '邀请码不存在'
    if row['status'] != 'active':
        return False, '邀请码已停用'
    if row['expires_at']:
        now_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
        if row['expires_at'] <= now_str:
            return False, '邀请码已过期'
    if int(row['used_count'] or 0) >= int(row['max_uses'] or 1):
        return False, '邀请码已用完'

    conn.execute(
        'UPDATE invite_codes SET used_count=used_count+1 WHERE id=?',
        (invite_id,)
    )
    conn.execute(
        'INSERT INTO invite_code_uses (invite_id, user_id, username) VALUES (?,?,?)',
        (invite_id, user_id, username)
    )
    return True, '邀请码已使用'


def register(username, password, display_name='', invite_code=''):
    """注册新用户，返回 (ok, msg)"""
    username = username.strip().lower()
    display_name = display_name.strip()
    mode = get_invite_mode()
    invite = None

    if not username or not password:
        return False, '用户名和密码不能为空'
    if not display_name:
        return False, '请填写姓名'
    if len(username) < 2 or len(username) > 30:
        return False, '用户名长度 2-30 字符'
    if len(password) < 6:
        return False, '密码至少 6 位'

    invite_code = _normalize_invite_code(invite_code)
    if invite_code:
        ok, msg, invite = validate_invite_code(invite_code)
        if not ok:
            return False, msg
    elif mode == INVITE_MODE_REQUIRED:
        return False, '当前注册需要邀请码'

    c = _conn()
    try:
        user_id = _create_user(c, username, password, display_name=display_name)
        if invite:
            ok, msg = _consume_invite_code(c, invite['id'], user_id, username)
            if not ok:
                c.execute('DELETE FROM users WHERE id=?', (user_id,))
                c.commit()
                c.close()
                return False, msg
        c.close()
        return True, '注册成功'
    except sqlite3.IntegrityError:
        c.close()
        return False, '用户名已存在'


def _get_login_lock(conn, ip):
    if not ip:
        return None
    return conn.execute('SELECT * FROM login_locks WHERE ip=?', (ip,)).fetchone()


def _clear_login_lock(conn, ip):
    if not ip:
        return
    conn.execute('DELETE FROM login_locks WHERE ip=?', (ip,))


def _register_failed_login(conn, ip):
    if not ip:
        return None
    row = _get_login_lock(conn, ip)
    if row:
        failed = int(row['failed_count'] or 0) + 1
    else:
        failed = 1
    locked_until = None
    if failed >= MAX_FAILED_LOGINS:
        locked_until = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time() + LOGIN_LOCK_MINUTES * 60))
    conn.execute('''
        INSERT INTO login_locks (ip, failed_count, locked_until, updated_at)
        VALUES (?, ?, ?, datetime('now','localtime'))
        ON CONFLICT(ip) DO UPDATE SET
            failed_count=excluded.failed_count,
            locked_until=excluded.locked_until,
            updated_at=datetime('now','localtime')
    ''', (ip, failed, locked_until))
    return {'failed_count': failed, 'locked_until': locked_until}


def _check_login_locked(conn, ip):
    if not ip:
        return False, None
    row = _get_login_lock(conn, ip)
    if not row:
        return False, None
    locked_until = row['locked_until']
    now_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
    if locked_until and locked_until > now_str:
        return True, locked_until
    if locked_until and locked_until <= now_str:
        _clear_login_lock(conn, ip)
    return False, None


def login(username, password, ip=''):
    """登录，支持用户名或姓名登录，返回 (ok, data)"""
    login_input = username.strip()
    login_lower = login_input.lower()
    c = _conn()

    locked, locked_until = _check_login_locked(c, ip)
    if locked:
        c.execute('INSERT INTO login_log (username, ip, action, success) VALUES (?,?,?,?)',
                  (login_input, ip, 'login_locked', 0))
        c.commit(); c.close()
        return False, f'登录失败次数过多，请 {LOGIN_LOCK_MINUTES} 分钟后再试'

    # 先按用户名精确匹配（小写）
    row = c.execute('SELECT * FROM users WHERE username=?', (login_lower,)).fetchone()
    # 没找到则按姓名匹配（原始大小写）
    if not row:
        row = c.execute('SELECT * FROM users WHERE display_name=?', (login_input,)).fetchone()

    if not row:
        _register_failed_login(c, ip)
        c.execute('INSERT INTO login_log (username, ip, action, success) VALUES (?,?,?,?)',
                  (login_input, ip, 'login', 0))
        c.commit(); c.close()
        return False, '用户名或密码错误'

    if row['status'] != 'active':
        c.close()
        return False, '账号已被禁用'

    h, _ = _hash_pw(password, row['salt'])
    if h != row['password_hash']:
        _register_failed_login(c, ip)
        c.execute('INSERT INTO login_log (user_id, username, ip, action, success) VALUES (?,?,?,?,?)',
                  (row['id'], login_input, ip, 'login', 0))
        c.commit(); c.close()
        return False, '用户名或密码错误'

    _clear_login_lock(c, ip)

    # 登录成功，创建 session token (7天有效)
    token = uuid.uuid4().hex
    expires = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time() + 7*86400))
    c.execute('INSERT INTO sessions (token, user_id, expires_at) VALUES (?,?,?)',
              (token, row['id'], expires))
    c.execute('UPDATE users SET last_login=datetime("now","localtime"), login_count=login_count+1 WHERE id=?',
              (row['id'],))
    c.execute('INSERT INTO login_log (user_id, username, ip, action, success) VALUES (?,?,?,?,?)',
              (row['id'], login_input, ip, 'login', 1))
    c.commit(); c.close()

    return True, {
        'token': token,
        'username': row['username'],
        'display_name': row['display_name'] or row['username'],
        'is_admin': bool(row['is_admin']),
        'tier': row['tier'] if 'tier' in row.keys() else 0,
    }


def verify_token(token):
    """验证 token，返回 user dict 或 None"""
    if not token:
        return None
    c = _conn()
    row = c.execute('''
        SELECT u.* FROM sessions s JOIN users u ON s.user_id=u.id
        WHERE s.token=? AND s.expires_at > datetime('now','localtime')
    ''', (token,)).fetchone()
    c.close()
    if not row:
        return None
    return {
        'id': row['id'],
        'username': row['username'],
        'display_name': row['display_name'] or row['username'],
        'is_admin': bool(row['is_admin']),
        'tier': row['tier'] if 'tier' in row.keys() else 0,
    }


def logout(token):
    c = _conn()
    c.execute('DELETE FROM sessions WHERE token=?', (token,))
    c.commit(); c.close()


def list_users():
    """管理后台：列出所有用户"""
    c = _conn()
    rows = c.execute('''
        SELECT id, username, display_name, is_admin, tier, created_at, last_login, login_count, status
        FROM users ORDER BY created_at DESC
    ''').fetchall()
    c.close()
    return [dict(r) for r in rows]


def list_login_log(limit=100):
    """管理后台：登录日志"""
    c = _conn()
    rows = c.execute('''
        SELECT * FROM login_log ORDER BY created_at DESC LIMIT ?
    ''', (limit,)).fetchall()
    c.close()
    return [dict(r) for r in rows]


def toggle_user_status(user_id, status):
    """启用/禁用用户"""
    c = _conn()
    c.execute('UPDATE users SET status=? WHERE id=? AND is_admin=0', (status, user_id))
    c.commit(); c.close()


def delete_user(user_id):
    """删除用户（不能删管理员）"""
    c = _conn()
    c.execute('DELETE FROM sessions WHERE user_id=?', (user_id,))
    c.execute('DELETE FROM users WHERE id=? AND is_admin=0', (user_id,))
    c.commit(); c.close()


def reset_password(user_id, new_password):
    """重置密码"""
    h, s = _hash_pw(new_password)
    c = _conn()
    c.execute('UPDATE users SET password_hash=?, salt=? WHERE id=?', (h, s, user_id))
    c.execute('DELETE FROM sessions WHERE user_id=?', (user_id,))
    c.commit(); c.close()


def set_tier(user_id, tier):
    """设置用户等级: 0=普通, 1=高级"""
    c = _conn()
    c.execute('UPDATE users SET tier=? WHERE id=? AND is_admin=0', (int(tier), user_id))
    c.commit(); c.close()


# 初始化
init_db()

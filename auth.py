#!/usr/bin/env python3
"""
GAMT 用户认证模块
- SQLite 存储用户数据
- bcrypt-like 密码哈希 (hashlib + salt)
- UUID session token
"""

import sqlite3, hashlib, uuid, os, time, json

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'users.db')

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
    ''')
    # 确保有默认管理员（首次运行）
    row = c.execute('SELECT COUNT(*) FROM users WHERE is_admin=1').fetchone()
    if row[0] == 0:
        _create_user(c, 'admin', 'gamt2026', is_admin=1, display_name='管理员')
        print('[auth] 默认管理员已创建: admin / gamt2026')
    c.close()

def _hash_pw(password, salt=None):
    if salt is None:
        salt = uuid.uuid4().hex
    h = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return h.hex(), salt

def _create_user(conn, username, password, is_admin=0, display_name=''):
    h, s = _hash_pw(password)
    conn.execute(
        'INSERT INTO users (username, display_name, password_hash, salt, is_admin) VALUES (?,?,?,?,?)',
        (username, display_name, h, s, is_admin)
    )
    conn.commit()

def register(username, password, display_name=''):
    """注册新用户，返回 (ok, msg)"""
    username = username.strip().lower()
    if not username or not password:
        return False, '用户名和密码不能为空'
    if len(username) < 2 or len(username) > 30:
        return False, '用户名长度 2-30 字符'
    if len(password) < 6:
        return False, '密码至少 6 位'

    c = _conn()
    try:
        _create_user(c, username, password, display_name=display_name)
        c.close()
        return True, '注册成功'
    except sqlite3.IntegrityError:
        c.close()
        return False, '用户名已存在'

def login(username, password, ip=''):
    """登录，返回 (ok, data)"""
    username = username.strip().lower()
    c = _conn()
    row = c.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()

    if not row:
        c.execute('INSERT INTO login_log (username, ip, action, success) VALUES (?,?,?,?)',
                  (username, ip, 'login', 0))
        c.commit(); c.close()
        return False, '用户名或密码错误'

    if row['status'] != 'active':
        c.close()
        return False, '账号已被禁用'

    h, _ = _hash_pw(password, row['salt'])
    if h != row['password_hash']:
        c.execute('INSERT INTO login_log (user_id, username, ip, action, success) VALUES (?,?,?,?,?)',
                  (row['id'], username, ip, 'login', 0))
        c.commit(); c.close()
        return False, '用户名或密码错误'

    # 登录成功，创建 session token (7天有效)
    token = uuid.uuid4().hex
    expires = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time() + 7*86400))
    c.execute('INSERT INTO sessions (token, user_id, expires_at) VALUES (?,?,?)',
              (token, row['id'], expires))
    c.execute('UPDATE users SET last_login=datetime("now","localtime"), login_count=login_count+1 WHERE id=?',
              (row['id'],))
    c.execute('INSERT INTO login_log (user_id, username, ip, action, success) VALUES (?,?,?,?,?)',
              (row['id'], username, ip, 'login', 1))
    c.commit(); c.close()

    return True, {
        'token': token,
        'username': username,
        'display_name': row['display_name'] or username,
        'is_admin': bool(row['is_admin']),
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
    }

def logout(token):
    c = _conn()
    c.execute('DELETE FROM sessions WHERE token=?', (token,))
    c.commit(); c.close()

def list_users():
    """管理后台：列出所有用户"""
    c = _conn()
    rows = c.execute('''
        SELECT id, username, display_name, is_admin, created_at, last_login, login_count, status
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

# 初始化
init_db()

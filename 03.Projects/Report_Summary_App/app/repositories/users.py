import sqlite3

from app.db import utcnow

PUBLIC_COLS = 'id, username, full_name, role, is_active, must_change_password, created_at, updated_at, last_login_at'


def to_public(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    d = {k: row[k] for k in row.keys() if k != 'password_hash'}
    d['is_active'] = bool(d['is_active'])
    d['must_change_password'] = bool(d['must_change_password'])
    return d


def get_by_id(conn, user_id: int):
    return conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()


def get_by_username(conn, username: str):
    return conn.execute('SELECT * FROM users WHERE username = ?', (username.strip(),)).fetchone()


def list_all(conn) -> list:
    return conn.execute(f'SELECT {PUBLIC_COLS} FROM users ORDER BY role, username').fetchall()


def count(conn) -> int:
    return conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]


def count_active_admins(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM users WHERE role = 'admin' AND is_active = 1").fetchone()[0]


def create(conn, username: str, full_name: str, password_hash: str, role: str, must_change_password: bool = True) -> int:
    now = utcnow()
    cur = conn.execute(
        'INSERT INTO users (username, full_name, password_hash, role, is_active, must_change_password, created_at, updated_at) '
        'VALUES (?, ?, ?, ?, 1, ?, ?, ?)',
        (username.strip(), full_name.strip(), password_hash, role, int(must_change_password), now, now))
    return cur.lastrowid


def update_fields(conn, user_id: int, **fields) -> None:
    allowed = {'full_name', 'role', 'is_active', 'must_change_password', 'password_hash'}
    sets = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not sets:
        return
    sets['updated_at'] = utcnow()
    cols = ', '.join(f'{k} = ?' for k in sets)
    conn.execute(f'UPDATE users SET {cols} WHERE id = ?', (*sets.values(), user_id))


def touch_login(conn, user_id: int) -> None:
    conn.execute('UPDATE users SET last_login_at = ? WHERE id = ?', (utcnow(), user_id))

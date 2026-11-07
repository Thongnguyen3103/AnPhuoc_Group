from app.db import utcnow


def log(conn, action: str, user: dict | None = None, detail: str = '', ip: str = '',
        username: str | None = None) -> None:
    conn.execute(
        'INSERT INTO audit_log (at, user_id, username, action, detail, ip) VALUES (?, ?, ?, ?, ?, ?)',
        (utcnow(), user['id'] if user else None, username or (user['username'] if user else None),
         action, (detail or '')[:500], ip))


def recent(conn, limit: int) -> list:
    return conn.execute(
        'SELECT id, at, user_id, username, action, detail, ip FROM audit_log ORDER BY id DESC LIMIT ?',
        (limit,)).fetchall()

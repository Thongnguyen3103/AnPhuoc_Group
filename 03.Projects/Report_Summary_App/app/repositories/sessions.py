from datetime import datetime, timedelta, timezone

from app.db import utcnow

_FMT = '%Y-%m-%dT%H:%M:%SZ'


def _in(hours: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).strftime(_FMT)


def create(conn, token_hash: str, user_id: int, hours: int, ip: str, user_agent: str) -> None:
    now = utcnow()
    conn.execute(
        'INSERT INTO sessions (token_hash, user_id, created_at, expires_at, last_seen_at, ip, user_agent) '
        'VALUES (?, ?, ?, ?, ?, ?, ?)',
        (token_hash, user_id, now, _in(hours), now, ip, (user_agent or '')[:300]))


def get_valid(conn, token_hash: str):
    """Phiên còn hạn + user đang hoạt động (JOIN để 1 câu SQL / request)."""
    return conn.execute(
        'SELECT s.token_hash, s.expires_at, s.last_seen_at, u.* FROM sessions s '
        'JOIN users u ON u.id = s.user_id '
        'WHERE s.token_hash = ? AND s.expires_at > ? AND u.is_active = 1',
        (token_hash, utcnow())).fetchone()


def extend(conn, token_hash: str, hours: int) -> None:
    conn.execute('UPDATE sessions SET last_seen_at = ?, expires_at = ? WHERE token_hash = ?',
                 (utcnow(), _in(hours), token_hash))


def needs_refresh(last_seen_at: str, minutes: int = 5) -> bool:
    seen = datetime.strptime(last_seen_at, _FMT).replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - seen > timedelta(minutes=minutes)


def delete(conn, token_hash: str) -> None:
    conn.execute('DELETE FROM sessions WHERE token_hash = ?', (token_hash,))


def delete_for_user(conn, user_id: int, except_token_hash: str | None = None) -> None:
    if except_token_hash:
        conn.execute('DELETE FROM sessions WHERE user_id = ? AND token_hash <> ?', (user_id, except_token_hash))
    else:
        conn.execute('DELETE FROM sessions WHERE user_id = ?', (user_id,))


def purge_expired(conn) -> int:
    return conn.execute('DELETE FROM sessions WHERE expires_at <= ?', (utcnow(),)).rowcount

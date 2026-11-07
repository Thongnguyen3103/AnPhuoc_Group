"""Kết nối SQLite và chạy migration. Toàn bộ SQL nằm trong app/repositories (SQL thuần)."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent / 'migrations'


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def connect(db_path: Path) -> sqlite3.Connection:
    # autocommit (giao dịch mở bằng transaction()). check_same_thread=False: FastAPI chạy các dependency
    # đồng bộ của CÙNG 1 request trên các luồng threadpool khác nhau; mỗi request có kết nối riêng, dùng tuần tự.
    conn = sqlite3.connect(db_path, timeout=10, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    conn.execute('PRAGMA busy_timeout = 10000')
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection):
    conn.execute('BEGIN IMMEDIATE')
    try:
        yield conn
    except BaseException:
        conn.execute('ROLLBACK')
        raise
    else:
        conn.execute('COMMIT')


def migrate(db_path: Path) -> list:
    """Áp các file NNN_*.sql chưa chạy, theo thứ tự. Trả về danh sách version vừa áp."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        conn.execute('PRAGMA journal_mode = WAL')
        conn.execute('CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)')
        done = {r['version'] for r in conn.execute('SELECT version FROM schema_migrations')}
        applied = []
        for f in sorted(MIGRATIONS_DIR.glob('[0-9][0-9][0-9]_*.sql')):
            version = f.stem
            if version in done:
                continue
            conn.executescript('BEGIN;\n' + f.read_text(encoding='utf-8') +
                               f"\nINSERT INTO schema_migrations VALUES ('{version}', '{utcnow()}');\nCOMMIT;")
            applied.append(version)
        return applied
    finally:
        conn.close()

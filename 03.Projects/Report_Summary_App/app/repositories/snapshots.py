from app.db import utcnow

COLS = ('id, sha256, ref_label, ref_year, ref_month, built_at, file_name, size_bytes, sku_count, '
        'imported_at, imported_by, is_active')


def get_active(conn):
    return conn.execute(f'SELECT {COLS} FROM snapshots WHERE is_active = 1').fetchone()


def get_by_id(conn, snapshot_id: int):
    return conn.execute(f'SELECT {COLS} FROM snapshots WHERE id = ?', (snapshot_id,)).fetchone()


def get_by_sha(conn, sha256: str):
    return conn.execute(f'SELECT {COLS} FROM snapshots WHERE sha256 = ?', (sha256,)).fetchone()


def list_all(conn) -> list:
    return conn.execute(f'SELECT {COLS} FROM snapshots ORDER BY id DESC').fetchall()


def create(conn, sha256: str, ref: dict, built_at: str, file_name: str, size_bytes: int,
           sku_count: int, imported_by: int | None) -> int:
    cur = conn.execute(
        'INSERT INTO snapshots (sha256, ref_label, ref_year, ref_month, built_at, file_name, size_bytes, '
        'sku_count, imported_at, imported_by, is_active) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)',
        (sha256, ref.get('label'), ref.get('year'), ref.get('month'), built_at, file_name, size_bytes,
         sku_count, utcnow(), imported_by))
    return cur.lastrowid


def activate(conn, snapshot_id: int) -> None:
    conn.execute('UPDATE snapshots SET is_active = 0 WHERE is_active = 1')
    conn.execute('UPDATE snapshots SET is_active = 1 WHERE id = ?', (snapshot_id,))


def list_prunable(conn, keep: int) -> list:
    """Snapshot không active, cũ hơn `keep` bản mới nhất."""
    return conn.execute(
        f'SELECT {COLS} FROM snapshots WHERE is_active = 0 AND id NOT IN '
        '(SELECT id FROM snapshots ORDER BY id DESC LIMIT ?)', (keep,)).fetchall()


def delete(conn, snapshot_id: int) -> None:
    conn.execute('DELETE FROM snapshots WHERE id = ?', (snapshot_id,))

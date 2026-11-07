"""Nạp snapshot dữ liệu do pipeline build (Core/Export_App_Snapshot.py) xuất ra.

Thư mục nguồn chứa payload.json.gz, sku_track.json.gz và meta.json (ghi cuối cùng).
Bản nạp được chép sang data/snapshots/<sha>.json.gz, kiểm tra SHA-256 khớp meta
(tránh đọc phải file đang ghi dở), rồi kích hoạt trong 1 giao dịch.
"""
import gzip
import hashlib
import json
import logging
import shutil
import threading
from pathlib import Path

from app import db
from app.config import Settings
from app.repositories import audit, skus, snapshots

log = logging.getLogger('app.snapshots')


class SnapshotError(Exception):
    pass


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


class SnapshotService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._lock = threading.Lock()

    # ---------- nguồn ----------
    def source_meta(self) -> dict | None:
        meta_path = self.settings.snapshot_source_dir / 'meta.json'
        if not meta_path.is_file():
            return None
        try:
            return json.loads(meta_path.read_text(encoding='utf-8'))
        except (OSError, ValueError) as e:
            raise SnapshotError(f'Không đọc được meta.json: {e}') from e

    def payload_path(self, row) -> Path:
        return self.settings.snapshots_dir / row['file_name']

    # ---------- nạp ----------
    def import_latest(self, conn, user: dict | None = None, ip: str = '') -> tuple:
        """Nạp bản build mới nhất. Trả về (snapshot_row, created). Đã có (cùng SHA) thì không đổi bản đang dùng."""
        with self._lock:
            meta = self.source_meta()
            if not meta:
                raise SnapshotError(f'Chưa có bản build tại {self.settings.snapshot_source_dir}')
            sha = meta['payload_sha256']
            existing = snapshots.get_by_sha(conn, sha)
            if existing:
                return existing, False

            src_dir = self.settings.snapshot_source_dir
            self.settings.snapshots_dir.mkdir(parents=True, exist_ok=True)
            file_name = f'{sha[:16]}.json.gz'
            dst = self.settings.snapshots_dir / file_name
            tmp = dst.with_suffix('.tmp')
            shutil.copyfile(src_dir / 'payload.json.gz', tmp)
            if _sha256_file(tmp) != sha:
                tmp.unlink(missing_ok=True)
                raise SnapshotError('Bản build đang được ghi (SHA chưa khớp meta) — thử lại sau.')
            tmp.replace(dst)

            with gzip.open(src_dir / 'sku_track.json.gz', 'rt', encoding='utf-8') as f:
                sku_rows = json.load(f)

            with db.transaction(conn):
                sid = snapshots.create(conn, sha, meta.get('ref') or {}, meta.get('built'), file_name,
                                       dst.stat().st_size, len(sku_rows), user['id'] if user else None)
                skus.insert_many(conn, sid, sku_rows)
                snapshots.activate(conn, sid)
                audit.log(conn, 'snapshot.import', user, f"#{sid} {(meta.get('ref') or {}).get('label')} "
                          f"build {meta.get('built')}", ip, username=None if user else 'system')
            log.info('Đã nạp snapshot #%s (%s, %s SKU)', sid, meta.get('built'), len(sku_rows))
            self.prune(conn)
            return snapshots.get_by_id(conn, sid), True

    def activate(self, conn, snapshot_id: int, user: dict, ip: str = ''):
        row = snapshots.get_by_id(conn, snapshot_id)
        if not row:
            raise SnapshotError('Không tìm thấy snapshot.')
        if not self.payload_path(row).is_file():
            raise SnapshotError('File dữ liệu của snapshot này không còn trên máy chủ.')
        with db.transaction(conn):
            snapshots.activate(conn, snapshot_id)
            audit.log(conn, 'snapshot.activate', user, f"#{snapshot_id} {row['ref_label']} build {row['built_at']}", ip)
        return snapshots.get_by_id(conn, snapshot_id)

    def prune(self, conn) -> int:
        old = snapshots.list_prunable(conn, self.settings.snapshot_keep)
        for row in old:
            with db.transaction(conn):
                snapshots.delete(conn, row['id'])
            self.payload_path(row).unlink(missing_ok=True)
        return len(old)


class SnapshotWatcher(threading.Thread):
    """Định kỳ kiểm tra meta.json; thấy bản build mới thì tự nạp."""

    def __init__(self, service: SnapshotService):
        super().__init__(name='snapshot-watcher', daemon=True)
        self.service = service
        self._stop_event = threading.Event()
        self._last_mtime = None

    def check_once(self) -> bool:
        meta_path = self.service.settings.snapshot_source_dir / 'meta.json'
        try:
            mtime = meta_path.stat().st_mtime
        except FileNotFoundError:
            return False
        if mtime == self._last_mtime:
            return False
        conn = db.connect(self.service.settings.db_path)
        try:
            _, created = self.service.import_latest(conn)
            self._last_mtime = mtime
            return created
        except SnapshotError as e:
            log.warning('Watcher: %s', e)
            return False
        finally:
            conn.close()

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.check_once()
            except Exception:                       # watcher không được chết vì 1 lỗi lẻ
                log.exception('Watcher lỗi')
            self._stop_event.wait(self.service.settings.watch_interval_sec)

    def stop(self) -> None:
        self._stop_event.set()

import gzip
import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import db  # noqa: E402
from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.repositories import users  # noqa: E402
from app.security import hash_password  # noqa: E402

TEMPLATE_DIR = ROOT / 'Template'
PASSWORD = 'Test1234pw'

SKU_ROWS = [
    {'mh': 'ADTL0400', 'op': '20/000', 'brand': 'Hiệu An Phước', 'cat_group': 'Nhóm chủ đạo', 'group_report': 'Chemise',
     'item': 'Chemise Nam Dài AP', 'status': 'Thanh lý', 'price': 400000, 'prod_ym': 202001, 'age_months': 81,
     'ton_ch': 2302, 'ton_kho': 14738, 'ban_1m': 325, 'ban_3m': 1021, 'ban_6m': 1337, 'ban_ytd': 3023,
     'ban_all': 24395, 'months_since_sale': 0},
    {'mh': 'PSD002014', 'op': '26/022', 'brand': 'Hiệu Pierre Cardin', 'cat_group': 'Nhóm chủ đạo', 'group_report': 'Chemise',
     'item': 'Chemise Nam Dài PIE', 'status': 'Nguyên giá', 'price': 4508000, 'prod_ym': 202605, 'age_months': 5,
     'ton_ch': 1500, 'ton_kho': 371, 'ban_1m': 80, 'ban_3m': 228, 'ban_6m': 300, 'ban_ytd': 300,
     'ban_all': 300, 'months_since_sale': 0},
    {'mh': 'BJQ_%01', 'op': '25/001', 'brand': 'Hiệu Bonjour', 'cat_group': 'Nhóm Anamai / Bonjour', 'group_report': 'Đồ lót',
     'item': 'Áo Lót Bonjour', 'status': 'Nguyên giá', 'price': 150000, 'prod_ym': 0, 'age_months': -1,
     'ton_ch': 10, 'ton_kho': 0, 'ban_1m': 0, 'ban_3m': 0, 'ban_6m': 2, 'ban_ytd': 5,
     'ban_all': 9, 'months_since_sale': 5},
]


def write_snapshot(src: Path, label: str = 'T10/2026', built: str = '03/11/2026 09:41', marker: str = 'a') -> str:
    src.mkdir(parents=True, exist_ok=True)
    payload = gzip.compress(json.dumps({'v': 3, 'built': built, 'ref': {'label': label}, 'marker': marker}).encode())
    sha = hashlib.sha256(payload).hexdigest()
    (src / 'payload.json.gz').write_bytes(payload)
    (src / 'sku_track.json.gz').write_bytes(gzip.compress(json.dumps(SKU_ROWS, ensure_ascii=False).encode()))
    (src / 'meta.json').write_text(json.dumps({
        'format': 1, 'built': built, 'ref': {'year': 2026, 'month': 10, 'label': label},
        'payload_sha256': sha, 'payload_size': len(payload), 'sku_count': len(SKU_ROWS)}), encoding='utf-8')
    return sha


@pytest.fixture
def settings(tmp_path) -> Settings:
    s = Settings(data_dir=tmp_path / 'data', snapshot_source_dir=tmp_path / 'src', template_dir=TEMPLATE_DIR)
    write_snapshot(s.snapshot_source_dir)
    return s


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings, start_watcher=False)) as c:
        yield c


@pytest.fixture
def make_user(settings, client):
    def _make(username, role='viewer', must_change=False, active=True):
        conn = db.connect(settings.db_path)
        try:
            uid = users.create(conn, username, username.title(), hash_password(PASSWORD), role, must_change)
            if not active:
                users.update_fields(conn, uid, is_active=0)
            return uid
        finally:
            conn.close()
    return _make


def login(client, username, password=PASSWORD):
    return client.post('/api/auth/login', json={'username': username, 'password': password})


@pytest.fixture
def viewer(client, make_user):
    make_user('viewer1')
    assert login(client, 'viewer1').status_code == 200
    return client


@pytest.fixture
def admin(client, make_user):
    make_user('admin1', role='admin')
    assert login(client, 'admin1').status_code == 200
    return client


@pytest.fixture
def replace_settings():
    return replace

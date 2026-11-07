from conftest import login, write_snapshot

from app.services.snapshots import SnapshotWatcher


def test_viewer_cannot_use_admin_api(viewer):
    assert viewer.get('/api/admin/users').status_code == 403
    assert viewer.post('/api/admin/users', json={'username': 'x12'}).status_code == 403
    assert viewer.get('/admin', follow_redirects=False).headers['location'] == '/'


def test_create_user_returns_temp_password_and_forces_change(admin):
    r = admin.post('/api/admin/users', json={'username': 'hoa.tran', 'full_name': 'Trần Hoa', 'role': 'viewer'})
    assert r.status_code == 201
    temp = r.json()['temp_password']
    assert r.json()['user']['must_change_password'] is True
    assert admin.post('/api/admin/users', json={'username': 'HOA.TRAN'}).status_code == 409
    assert admin.post('/api/admin/users', json={'username': 'a b'}).status_code == 422

    admin.post('/api/auth/logout')
    assert login(admin, 'hoa.tran', temp).status_code == 200


def test_cannot_lock_or_demote_self_or_last_admin(admin):
    me = admin.get('/api/auth/me').json()['user']
    assert admin.patch(f"/api/admin/users/{me['id']}", json={'is_active': False}).status_code == 400
    assert admin.patch(f"/api/admin/users/{me['id']}", json={'role': 'viewer'}).status_code == 400


def test_lock_user_kills_sessions(admin, client, make_user, settings):
    from fastapi.testclient import TestClient
    from app.main import create_app
    uid = make_user('nv1')
    with TestClient(create_app(settings, start_watcher=False)) as other:
        assert login(other, 'nv1').status_code == 200
        assert admin.patch(f'/api/admin/users/{uid}', json={'is_active': False}).status_code == 200
        assert other.get('/api/auth/me').status_code == 401


def test_reset_password(admin, make_user):
    uid = make_user('nv2')
    r = admin.post(f'/api/admin/users/{uid}/reset-password')
    assert r.status_code == 200 and len(r.json()['temp_password']) >= 8
    assert r.json()['user']['must_change_password'] is True


def test_snapshot_import_activate_and_dedupe(admin, settings):
    assert admin.post('/api/admin/snapshots/import').json()['created'] is False      # đã nạp lúc khởi động
    write_snapshot(settings.snapshot_source_dir, label='T11/2026', marker='b')
    r = admin.post('/api/admin/snapshots/import').json()
    assert r['created'] is True and r['snapshot']['ref_label'] == 'T11/2026'
    snaps = admin.get('/api/admin/snapshots').json()['snapshots']
    assert [s['is_active'] for s in snaps] == [True, False]
    old_id = snaps[1]['id']
    assert admin.post(f'/api/admin/snapshots/{old_id}/activate').status_code == 200
    assert admin.get('/api/report/meta').json()['snapshot']['ref_label'] == 'T10/2026'
    actions = [a['action'] for a in admin.get('/api/admin/audit').json()['items']]
    assert 'snapshot.activate' in actions and 'snapshot.import' in actions


def test_snapshot_rejects_half_written_payload(admin, settings):
    write_snapshot(settings.snapshot_source_dir, label='T11/2026', marker='c')
    (settings.snapshot_source_dir / 'payload.json.gz').write_bytes(b'dang ghi do')
    assert admin.post('/api/admin/snapshots/import').status_code == 409


def test_watcher_picks_up_new_build(client, settings):
    watcher = SnapshotWatcher(client.app.state.snapshot_service)
    watcher.check_once()                                   # bản đã có -> không tạo mới
    write_snapshot(settings.snapshot_source_dir, label='T12/2026', marker='d')
    assert watcher.check_once() is True
    assert client.get('/api/health').json()['snapshot']['ref_label'] == 'T12/2026'


def test_snapshot_prune_keeps_n(admin, settings, client):
    svc = client.app.state.snapshot_service
    object.__setattr__(svc.settings, 'snapshot_keep', 2)
    for i in range(4):
        write_snapshot(settings.snapshot_source_dir, label=f'K{i}', marker=f'p{i}')
        admin.post('/api/admin/snapshots/import')
    snaps = admin.get('/api/admin/snapshots').json()['snapshots']
    assert len(snaps) == 2
    assert len(list(settings.snapshots_dir.glob('*.json.gz'))) == 2

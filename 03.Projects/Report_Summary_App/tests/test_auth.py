from conftest import PASSWORD, login

from app.security import hash_password, verify_password


def test_password_hash_roundtrip():
    h = hash_password('Abc12345')
    assert h.startswith('pbkdf2_sha256$')
    assert verify_password('Abc12345', h)
    assert not verify_password('abc12345', h)
    assert not verify_password('x', 'garbage')


def test_login_success_sets_httponly_cookie(client, make_user):
    make_user('lan')
    r = login(client, 'LAN')                      # username không phân biệt hoa thường
    assert r.status_code == 200
    assert r.json()['user']['username'] == 'lan'
    cookie = r.headers['set-cookie']
    assert 'ap_session=' in cookie and 'HttpOnly' in cookie and 'SameSite=strict' in cookie
    assert client.get('/api/auth/me').json()['user']['username'] == 'lan'


def test_login_wrong_password_and_unknown_user_same_message(client, make_user):
    make_user('lan')
    a = login(client, 'lan', 'sai-mat-khau1')
    b = login(client, 'khong-co', 'sai-mat-khau1')
    assert a.status_code == b.status_code == 401
    assert a.json()['detail'] == b.json()['detail']


def test_inactive_user_cannot_login(client, make_user):
    make_user('khoa', active=False)
    assert login(client, 'khoa').status_code == 401


def test_login_rate_limited_after_failures(client, make_user):
    make_user('lan')
    for _ in range(5):
        assert login(client, 'lan', 'sai12345').status_code == 401
    r = login(client, 'lan')                       # đúng mật khẩu nhưng đang bị khóa tạm
    assert r.status_code == 429


def test_protected_api_requires_login(client):
    assert client.get('/api/auth/me').status_code == 401
    assert client.get('/api/report/payload').status_code == 401
    assert client.get('/api/skus').status_code == 401


def test_logout_invalidates_session(viewer):
    assert viewer.post('/api/auth/logout').status_code == 200
    assert viewer.get('/api/auth/me').status_code == 401


def test_change_password(viewer):
    bad = viewer.post('/api/auth/change-password', json={'current_password': 'sai', 'new_password': 'Moi12345'})
    assert bad.status_code == 400
    weak = viewer.post('/api/auth/change-password', json={'current_password': PASSWORD, 'new_password': '12345678'})
    assert weak.status_code == 400
    ok = viewer.post('/api/auth/change-password', json={'current_password': PASSWORD, 'new_password': 'Moi12345'})
    assert ok.status_code == 200
    assert ok.json()['user']['must_change_password'] is False
    viewer.post('/api/auth/logout')
    assert login(viewer, 'viewer1', PASSWORD).status_code == 401
    assert login(viewer, 'viewer1', 'Moi12345').status_code == 200


def test_cross_origin_post_rejected(client, make_user):
    make_user('lan')
    r = client.post('/api/auth/login', json={'username': 'lan', 'password': PASSWORD},
                    headers={'Origin': 'http://evil.example'})
    assert r.status_code == 403


def test_security_headers_present(client):
    r = client.get('/login')
    assert r.headers['x-frame-options'] == 'DENY'
    assert "default-src 'self'" in r.headers['content-security-policy']

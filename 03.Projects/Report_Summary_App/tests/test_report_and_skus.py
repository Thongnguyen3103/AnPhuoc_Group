import gzip
import json

from conftest import login


def test_startup_imports_snapshot(client):
    h = client.get('/api/health').json()
    assert h['status'] == 'ok'
    assert h['snapshot']['ref_label'] == 'T10/2026'


def test_payload_served_raw_gzip_with_etag(viewer):
    r = viewer.get('/api/report/payload')
    assert r.status_code == 200
    assert r.headers['content-encoding'] == 'identity'       # không bị middleware nén lần 2
    body = json.loads(gzip.decompress(r.content))
    assert body['ref']['label'] == 'T10/2026'
    r2 = viewer.get('/api/report/payload', headers={'If-None-Match': r.headers['etag']})
    assert r2.status_code == 304


def test_report_page_redirects_when_logged_out(client):
    r = client.get('/', follow_redirects=False)
    assert r.status_code == 303 and r.headers['location'] == '/login'


def test_report_page_in_server_mode(viewer):
    r = viewer.get('/')
    assert r.status_code == 200
    html = r.text
    assert '/static/report_boot.js' in html and '/static/app_shell.js' in html
    assert 'src="/assets/Report_Engine.js?v=' in html
    assert viewer.get('/assets/Report_Engine.js').status_code == 200


def test_report_assets_versioned_so_browser_reloads_new_js(viewer):
    # Trang có ?v= theo mtime của JS/CSS -> sửa Report_Engine.js là link đổi, trình duyệt tải bản mới.
    import re
    html = viewer.get('/').text
    versions = set(re.findall(r'(?:Report_Engine\.js|Report_Style\.css|app_shell\.js)\?v=(\d+)', html))
    assert len(versions) == 1
    assert viewer.get('/assets/Report_Engine.js?v=' + versions.pop()).status_code == 200


def test_first_login_forces_password_change(client, make_user):
    make_user('moi', must_change=True)
    login(client, 'moi')
    r = client.get('/', follow_redirects=False)
    assert r.status_code == 303 and r.headers['location'].startswith('/account')


def test_sku_search_and_filters(viewer):
    r = viewer.get('/api/skus', params={'q': 'adtl'}).json()
    assert r['total'] == 1
    it = r['items'][0]
    assert it['mh'] == 'ADTL0400' and it['ton'] == 17040
    assert it['months_of_supply'] == round(17040 / (1021 / 3), 2)

    r = viewer.get('/api/skus', params={'brand': 'Hiệu Pierre Cardin'}).json()
    assert [i['mh'] for i in r['items']] == ['PSD002014']

    r = viewer.get('/api/skus', params={'sort': 'price', 'order': 'asc'}).json()
    assert [i['price'] for i in r['items']] == sorted(i['price'] for i in r['items'])
    assert r['sums']['ton_ch'] == 2302 + 1500 + 10


def test_sku_search_escapes_like_wildcards(viewer):
    assert viewer.get('/api/skus', params={'q': '_%'}).json()['total'] == 1     # chỉ khớp chữ "_%" thật


def test_sku_sort_whitelist(viewer):
    assert viewer.get('/api/skus', params={'sort': 'mh; DROP TABLE users'}).status_code == 400


def test_sku_no_sale_months_of_supply_is_null(viewer):
    it = viewer.get('/api/skus', params={'q': 'BJQ'}).json()['items'][0]
    assert it['months_of_supply'] is None


def test_sku_by_code_and_404(viewer):
    assert viewer.get('/api/skus/ADTL0400').json()['items'][0]['op'] == '20/000'
    assert viewer.get('/api/skus/KHONGCO').status_code == 404


def test_many_requests_share_threadpool_safely(viewer):
    # Hồi quy: kết nối SQLite tạo ở 1 luồng threadpool, dùng/đóng ở luồng khác -> ProgrammingError ngẫu nhiên
    for _ in range(80):
        assert viewer.get('/api/skus', params={'q': 'ADTL', 'limit': 3}).status_code == 200


def test_facets(viewer):
    f = viewer.get('/api/skus/facets', params={'brand': 'Hiệu An Phước'}).json()
    assert f['item'] == ['Chemise Nam Dài AP']
    assert 'Hiệu Bonjour' in f['brand']

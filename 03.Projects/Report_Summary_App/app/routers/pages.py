"""Trang HTML: /login, / (báo cáo 10 sheet từ Template/), /account, /admin."""
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from app.deps import optional_user

router = APIRouter(include_in_schema=False)
WEB_DIR = Path(__file__).resolve().parent.parent / 'web'

_report_cache: dict = {}


def render_report_html(template_dir: Path) -> str:
    """Template gốc + chế độ máy chủ: asset trỏ /assets, payload tải qua API, gắn app_shell.js."""
    src = template_dir / 'Report_Template.html'
    # Phiên bản = mtime mới nhất của template + JS/CSS -> gắn ?v= để trình duyệt không dùng file cũ
    # (HTML mới + Report_Engine.js cũ trong cache -> lỗi "Cannot set properties of null").
    watched = [src] + [template_dir / n for n in ('Report_Engine.js', 'Report_Segments.js', 'Report_Style.css')] \
        + [WEB_DIR / n for n in ('app.css', 'report_boot.js', 'app_shell.js')]
    mtime = max(p.stat().st_mtime for p in watched if p.exists())
    if _report_cache.get('mtime') == mtime:
        return _report_cache['html']
    v = str(int(mtime))
    html = src.read_text(encoding='utf-8')
    html = (html
            .replace('href="Report_Style.css"', f'href="/assets/Report_Style.css?v={v}"')
            .replace('src="Vendor/plotly-basic.min.js"', 'src="/assets/Vendor/plotly-basic.min.js"')
            .replace('src="Report_Segments.js"', f'src="/assets/Report_Segments.js?v={v}"')
            .replace('src="Report_Engine.js"', f'src="/assets/Report_Engine.js?v={v}"'))
    html = html.replace('</head>', f'  <link rel="stylesheet" href="/static/app.css?v={v}">\n'
                                   f'  <script src="/static/report_boot.js?v={v}"></script>\n</head>', 1)
    html = html.replace('</body>', f'  <script src="/static/app_shell.js?v={v}"></script>\n</body>', 1)
    _report_cache.update(mtime=mtime, html=html)
    return html


def _page(name: str) -> FileResponse:
    return FileResponse(WEB_DIR / name, media_type='text/html', headers={'Cache-Control': 'no-cache'})


@router.api_route('/', methods=['GET', 'HEAD'])
def report_page(request: Request, user: dict | None = Depends(optional_user)):
    if not user:
        return RedirectResponse('/login', status_code=303)
    if user['must_change_password']:
        return RedirectResponse('/account?first=1', status_code=303)
    return HTMLResponse(render_report_html(request.app.state.settings.template_dir),
                        headers={'Cache-Control': 'no-cache'})


@router.get('/login')
def login_page(user: dict | None = Depends(optional_user)):
    if user:
        return RedirectResponse('/', status_code=303)
    return _page('login.html')


@router.get('/account')
def account_page(user: dict | None = Depends(optional_user)):
    if not user:
        return RedirectResponse('/login', status_code=303)
    return _page('account.html')


@router.get('/admin')
def admin_page(user: dict | None = Depends(optional_user)):
    if not user:
        return RedirectResponse('/login', status_code=303)
    if user['role'] != 'admin':
        return RedirectResponse('/', status_code=303)
    return _page('admin.html')

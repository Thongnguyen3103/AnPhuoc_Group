"""Khởi tạo ứng dụng FastAPI."""
import logging
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import __version__, db
from app.config import Settings, get_settings
from app.repositories import sessions, users
from app.routers import admin, auth, health, pages, report, skus
from app.security import LoginRateLimiter
from app.services.snapshots import SnapshotError, SnapshotService, SnapshotWatcher

log = logging.getLogger('app')

SECURITY_HEADERS = {
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'DENY',
    'Referrer-Policy': 'same-origin',
    # Template báo cáo dùng onclick/style inline -> cần 'unsafe-inline'; mọi nguồn khác chỉ 'self'
    'Content-Security-Policy': ("default-src 'self'; script-src 'self' 'unsafe-inline'; "
                                "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
                                "connect-src 'self'; font-src 'self' data:; frame-ancestors 'none'; "
                                "base-uri 'self'; form-action 'self'"),
}
UNSAFE_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}


def setup_logging(settings: Settings) -> None:
    root = logging.getLogger('app')
    if root.handlers:
        return
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s')
    fh = RotatingFileHandler(settings.logs_dir / 'app.log', maxBytes=5_000_000, backupCount=5, encoding='utf-8')
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(fh)
    root.addHandler(sh)
    root.setLevel(logging.INFO)


def create_app(settings: Settings | None = None, start_watcher: bool = True) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        setup_logging(settings)
        settings.snapshots_dir.mkdir(parents=True, exist_ok=True)
        applied = db.migrate(settings.db_path)
        if applied:
            log.info('Đã áp migration: %s', ', '.join(applied))
        conn = db.connect(settings.db_path)
        try:
            sessions.purge_expired(conn)
            if users.count(conn) == 0:
                log.warning('Chưa có người dùng. Tạo quản trị: python manage.py create-user <ten> --role admin')
            try:
                app.state.snapshot_service.import_latest(conn)
            except SnapshotError as e:
                log.warning('Chưa nạp được snapshot: %s', e)
        finally:
            conn.close()
        watcher = None
        if start_watcher:
            watcher = SnapshotWatcher(app.state.snapshot_service)
            watcher.start()
        log.info('Report_Summary_App %s sẵn sàng (dữ liệu: %s)', __version__, settings.data_dir)
        yield
        if watcher:
            watcher.stop()
            watcher.join(timeout=5)

    app = FastAPI(title='Báo cáo Tổng hợp An Phước', version=__version__, lifespan=lifespan,
                  docs_url='/api/docs', redoc_url=None, openapi_url='/api/openapi.json')
    app.state.settings = settings
    app.state.snapshot_service = SnapshotService(settings)
    app.state.login_limiter = LoginRateLimiter(settings.login_max_failures, settings.login_window_min * 60)

    @app.middleware('http')
    async def guard(request: Request, call_next):
        # CSRF: yêu cầu thay đổi dữ liệu phải đến từ chính trang này (Origin/Referer khớp)
        if request.method in UNSAFE_METHODS and request.url.path.startswith('/api/'):
            origin = request.headers.get('origin') or ''
            if not origin and request.headers.get('referer'):
                ref = urlsplit(request.headers['referer'])
                origin = f'{ref.scheme}://{ref.netloc}'
            own = f'{request.url.scheme}://{request.headers.get("host", "")}'
            if origin and origin.rstrip('/') != own and origin.rstrip('/') not in settings.trusted_origins:
                return JSONResponse({'detail': 'Yêu cầu không hợp lệ (sai nguồn gốc).'}, status_code=403)
        response = await call_next(request)
        for k, v in SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        return response

    app.add_middleware(GZipMiddleware, minimum_size=1024)

    for r in (auth.router, report.router, skus.router, admin.router, health.router, pages.router):
        app.include_router(r)
    app.mount('/assets', StaticFiles(directory=settings.template_dir), name='assets')
    app.mount('/static', StaticFiles(directory=pages.WEB_DIR), name='static')
    return app

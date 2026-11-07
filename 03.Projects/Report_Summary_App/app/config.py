"""Cấu hình đọc từ biến môi trường, có thể đặt trong file .env cạnh run_server.py."""
import os
from dataclasses import dataclass, field
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent            # .../Report_Summary_App
PROJECTS_DIR = APP_ROOT.parent                                # .../03.Projects
PYTHON_PROJECTS_DIR = PROJECTS_DIR.parent                     # .../01.Python_Projects


def load_dotenv(path: Path) -> None:
    """Nạp file .env đơn giản (KEY=VALUE); biến môi trường có sẵn được ưu tiên."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, value = line.partition('=')
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    return default if v is None else v.strip().lower() in ('1', 'true', 'yes', 'on')


def _int(name: str, default: int) -> int:
    v = os.environ.get(name)
    return default if v in (None, '') else int(v)


def _path(name: str, default: Path) -> Path:
    v = os.environ.get(name)
    return Path(v).expanduser().resolve() if v else default


@dataclass(frozen=True)
class Settings:
    host: str = '0.0.0.0'
    port: int = 8780
    data_dir: Path = APP_ROOT / 'data'
    snapshot_source_dir: Path = PYTHON_PROJECTS_DIR / '04.Output' / 'Report_Summary' / 'app_snapshot'
    template_dir: Path = APP_ROOT / 'Template'
    session_hours: int = 12
    cookie_secure: bool = False
    snapshot_keep: int = 12
    watch_interval_sec: int = 60
    login_max_failures: int = 5
    login_window_min: int = 15
    trusted_origins: tuple = field(default_factory=tuple)

    @property
    def db_path(self) -> Path:
        return self.data_dir / 'app.db'

    @property
    def snapshots_dir(self) -> Path:
        return self.data_dir / 'snapshots'

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / 'logs'


def get_settings() -> Settings:
    load_dotenv(APP_ROOT / '.env')
    d = Settings()
    origins = tuple(o.strip().rstrip('/') for o in os.environ.get('TRUSTED_ORIGINS', '').split(',') if o.strip())
    return Settings(
        host=os.environ.get('APP_HOST', d.host),
        port=_int('APP_PORT', d.port),
        data_dir=_path('DATA_DIR', d.data_dir),
        snapshot_source_dir=_path('SNAPSHOT_SOURCE_DIR', d.snapshot_source_dir),
        template_dir=_path('TEMPLATE_DIR', d.template_dir),
        session_hours=_int('SESSION_HOURS', d.session_hours),
        cookie_secure=_bool('COOKIE_SECURE', d.cookie_secure),
        snapshot_keep=_int('SNAPSHOT_KEEP', d.snapshot_keep),
        watch_interval_sec=_int('WATCH_INTERVAL_SEC', d.watch_interval_sec),
        login_max_failures=_int('LOGIN_MAX_FAILURES', d.login_max_failures),
        login_window_min=_int('LOGIN_WINDOW_MIN', d.login_window_min),
        trusted_origins=origins,
    )

"""Băm mật khẩu, token phiên, giới hạn đăng nhập sai."""
import base64
import hashlib
import hmac
import secrets
import threading
import time
from collections import defaultdict, deque

PBKDF2_ITERATIONS = 390_000
MIN_PASSWORD_LEN = 8
_TEMP_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789'


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, PBKDF2_ITERATIONS)
    return 'pbkdf2_sha256${}${}${}'.format(
        PBKDF2_ITERATIONS, base64.b64encode(salt).decode(), base64.b64encode(dk).decode())


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_b64, hash_b64 = stored.split('$')
        if algo != 'pbkdf2_sha256':
            return False
        dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), base64.b64decode(salt_b64), int(iters))
        return hmac.compare_digest(dk, base64.b64decode(hash_b64))
    except (ValueError, TypeError):
        return False


# Băm giả để thời gian phản hồi giống nhau khi username không tồn tại
DUMMY_HASH = hash_password(secrets.token_urlsafe(12))


def validate_new_password(password: str) -> str | None:
    """Trả về thông báo lỗi (tiếng Việt) hoặc None nếu hợp lệ."""
    if len(password) < MIN_PASSWORD_LEN:
        return f'Mật khẩu phải có ít nhất {MIN_PASSWORD_LEN} ký tự.'
    if password.isdigit() or password.isalpha():
        return 'Mật khẩu cần có cả chữ và số.'
    return None


def generate_temp_password(length: int = 12) -> str:
    while True:
        pw = ''.join(secrets.choice(_TEMP_ALPHABET) for _ in range(length))
        if validate_new_password(pw) is None:
            return pw


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


class LoginRateLimiter:
    """Chặn sau N lần đăng nhập sai trong cửa sổ thời gian, theo (IP, username). Bộ nhớ trong tiến trình."""

    def __init__(self, max_failures: int, window_sec: int):
        self.max_failures = max_failures
        self.window_sec = window_sec
        self._fails = defaultdict(deque)
        self._lock = threading.Lock()

    def _key(self, ip: str, username: str) -> tuple:
        return (ip or '', (username or '').strip().lower())

    def _prune(self, q: deque, now: float) -> None:
        while q and now - q[0] > self.window_sec:
            q.popleft()

    def is_blocked(self, ip: str, username: str) -> bool:
        with self._lock:
            q = self._fails[self._key(ip, username)]
            self._prune(q, time.monotonic())
            return len(q) >= self.max_failures

    def record_failure(self, ip: str, username: str) -> None:
        with self._lock:
            q = self._fails[self._key(ip, username)]
            now = time.monotonic()
            self._prune(q, now)
            q.append(now)

    def reset(self, ip: str, username: str) -> None:
        with self._lock:
            self._fails.pop(self._key(ip, username), None)

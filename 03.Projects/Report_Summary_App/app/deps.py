"""Dependency dùng chung cho router: kết nối DB, người dùng hiện tại, quyền admin."""
from typing import Iterator

from fastapi import Depends, HTTPException, Request, status

from app import db
from app.repositories import sessions, users
from app.security import hash_token

COOKIE_NAME = 'ap_session'


def get_conn(request: Request) -> Iterator:
    conn = db.connect(request.app.state.settings.db_path)
    try:
        yield conn
    finally:
        conn.close()


def client_ip(request: Request) -> str:
    return request.client.host if request.client else ''


def optional_user(request: Request, conn=Depends(get_conn)) -> dict | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    th = hash_token(token)
    row = sessions.get_valid(conn, th)
    if not row:
        return None
    if sessions.needs_refresh(row['last_seen_at']):
        sessions.extend(conn, th, request.app.state.settings.session_hours)
    request.state.token_hash = th
    return users.to_public(row)


def current_user(user: dict | None = Depends(optional_user)) -> dict:
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, 'Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại.')
    return user


def require_admin(user: dict = Depends(current_user)) -> dict:
    if user['role'] != 'admin':
        raise HTTPException(status.HTTP_403_FORBIDDEN, 'Chỉ quản trị viên được thực hiện thao tác này.')
    return user

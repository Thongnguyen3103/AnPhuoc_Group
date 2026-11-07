from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app import db
from app.deps import COOKIE_NAME, client_ip, current_user, get_conn
from app.repositories import audit, sessions, users
from app.security import (DUMMY_HASH, hash_password, new_session_token, hash_token,
                          validate_new_password, verify_password)

router = APIRouter(prefix='/api/auth', tags=['auth'])


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


@router.post('/login')
def login(body: LoginIn, request: Request, response: Response, conn=Depends(get_conn)):
    settings = request.app.state.settings
    limiter = request.app.state.login_limiter
    ip = client_ip(request)
    if limiter.is_blocked(ip, body.username):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            f'Đăng nhập sai quá nhiều lần. Vui lòng thử lại sau {settings.login_window_min} phút.')

    row = users.get_by_username(conn, body.username)
    ok = verify_password(body.password, row['password_hash'] if row else DUMMY_HASH)
    if not row or not ok or not row['is_active']:
        limiter.record_failure(ip, body.username)
        audit.log(conn, 'login_failed', None, 'tài khoản bị khóa' if row and ok else '', ip, username=body.username[:64])
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, 'Sai tên đăng nhập hoặc mật khẩu.')

    limiter.reset(ip, body.username)
    token = new_session_token()
    with db.transaction(conn):
        sessions.create(conn, hash_token(token), row['id'], settings.session_hours, ip,
                        request.headers.get('user-agent', ''))
        users.touch_login(conn, row['id'])
        audit.log(conn, 'login', users.to_public(row), '', ip)
    response.set_cookie(COOKIE_NAME, token, max_age=settings.session_hours * 3600, httponly=True,
                        samesite='strict', secure=settings.cookie_secure, path='/')
    return {'user': users.to_public(users.get_by_id(conn, row['id']))}


@router.post('/logout')
def logout(request: Request, response: Response, user: dict = Depends(current_user), conn=Depends(get_conn)):
    with db.transaction(conn):
        sessions.delete(conn, request.state.token_hash)
        audit.log(conn, 'logout', user, '', client_ip(request))
    response.delete_cookie(COOKIE_NAME, path='/')
    return {'ok': True}


@router.get('/me')
def me(user: dict = Depends(current_user)):
    return {'user': user}


@router.post('/change-password')
def change_password(body: ChangePasswordIn, request: Request, user: dict = Depends(current_user),
                    conn=Depends(get_conn)):
    row = users.get_by_id(conn, user['id'])
    if not verify_password(body.current_password, row['password_hash']):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, 'Mật khẩu hiện tại không đúng.')
    err = validate_new_password(body.new_password)
    if err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, err)
    if body.new_password == body.current_password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, 'Mật khẩu mới phải khác mật khẩu hiện tại.')
    with db.transaction(conn):
        users.update_fields(conn, user['id'], password_hash=hash_password(body.new_password), must_change_password=0)
        sessions.delete_for_user(conn, user['id'], except_token_hash=request.state.token_hash)
        audit.log(conn, 'password.change', user, '', client_ip(request))
    return {'user': users.to_public(users.get_by_id(conn, user['id']))}

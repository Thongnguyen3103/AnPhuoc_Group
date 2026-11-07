from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from app import db
from app.deps import client_ip, get_conn, require_admin
from app.repositories import audit, sessions, snapshots, users
from app.routers.report import snapshot_public
from app.security import generate_temp_password, hash_password
from app.services.snapshots import SnapshotError

router = APIRouter(prefix='/api/admin', tags=['admin'])

Role = Literal['admin', 'viewer']


class UserCreate(BaseModel):
    username: str = Field(pattern=r'^[A-Za-z0-9._-]{3,32}$')
    full_name: str = Field(default='', max_length=100)
    role: Role = 'viewer'


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=100)
    role: Role | None = None
    is_active: bool | None = None


def _get_user_or_404(conn, user_id: int):
    row = users.get_by_id(conn, user_id)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, 'Không tìm thấy người dùng.')
    return row


# ---------------- Người dùng ----------------
@router.get('/users')
def list_users(admin: dict = Depends(require_admin), conn=Depends(get_conn)):
    return {'users': [users.to_public(r) for r in users.list_all(conn)]}


@router.post('/users', status_code=status.HTTP_201_CREATED)
def create_user(body: UserCreate, request: Request, admin: dict = Depends(require_admin), conn=Depends(get_conn)):
    if users.get_by_username(conn, body.username):
        raise HTTPException(status.HTTP_409_CONFLICT, f'Tên đăng nhập "{body.username}" đã tồn tại.')
    temp = generate_temp_password()
    with db.transaction(conn):
        uid = users.create(conn, body.username, body.full_name, hash_password(temp), body.role, True)
        audit.log(conn, 'user.create', admin, f'{body.username} ({body.role})', client_ip(request))
    return {'user': users.to_public(users.get_by_id(conn, uid)), 'temp_password': temp}


@router.patch('/users/{user_id}')
def update_user(user_id: int, body: UserUpdate, request: Request, admin: dict = Depends(require_admin),
                conn=Depends(get_conn)):
    row = _get_user_or_404(conn, user_id)
    demote = body.role is not None and body.role != 'admin' and row['role'] == 'admin'
    disable = body.is_active is False and row['is_active']
    if user_id == admin['id'] and (demote or disable):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, 'Không thể tự khóa hoặc hạ quyền chính mình.')
    if (demote or disable) and row['role'] == 'admin' and users.count_active_admins(conn) <= 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, 'Phải còn ít nhất 1 quản trị viên đang hoạt động.')
    changes = body.model_dump(exclude_none=True)
    with db.transaction(conn):
        users.update_fields(conn, user_id, full_name=body.full_name, role=body.role,
                            is_active=None if body.is_active is None else int(body.is_active))
        if disable:
            sessions.delete_for_user(conn, user_id)
        audit.log(conn, 'user.update', admin, f"{row['username']}: {changes}", client_ip(request))
    return {'user': users.to_public(users.get_by_id(conn, user_id))}


@router.post('/users/{user_id}/reset-password')
def reset_password(user_id: int, request: Request, admin: dict = Depends(require_admin), conn=Depends(get_conn)):
    row = _get_user_or_404(conn, user_id)
    temp = generate_temp_password()
    with db.transaction(conn):
        users.update_fields(conn, user_id, password_hash=hash_password(temp), must_change_password=1)
        sessions.delete_for_user(conn, user_id)
        audit.log(conn, 'user.reset_password', admin, row['username'], client_ip(request))
    return {'user': users.to_public(users.get_by_id(conn, user_id)), 'temp_password': temp}


# ---------------- Dữ liệu (snapshot) ----------------
@router.get('/snapshots')
def list_snapshots(request: Request, admin: dict = Depends(require_admin), conn=Depends(get_conn)):
    try:
        source = request.app.state.snapshot_service.source_meta()
    except SnapshotError as e:
        source = {'error': str(e)}
    return {'snapshots': [snapshot_public(r) for r in snapshots.list_all(conn)], 'source': source}


@router.post('/snapshots/import')
def import_snapshot(request: Request, admin: dict = Depends(require_admin), conn=Depends(get_conn)):
    try:
        row, created = request.app.state.snapshot_service.import_latest(conn, admin, client_ip(request))
    except SnapshotError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    return {'snapshot': snapshot_public(row), 'created': created}


@router.post('/snapshots/{snapshot_id}/activate')
def activate_snapshot(snapshot_id: int, request: Request, admin: dict = Depends(require_admin),
                      conn=Depends(get_conn)):
    try:
        row = request.app.state.snapshot_service.activate(conn, snapshot_id, admin, client_ip(request))
    except SnapshotError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))
    return {'snapshot': snapshot_public(row)}


# ---------------- Nhật ký ----------------
@router.get('/audit')
def audit_log(limit: int = Query(200, ge=1, le=1000), admin: dict = Depends(require_admin), conn=Depends(get_conn)):
    return {'items': [dict(r) for r in audit.recent(conn, limit)]}

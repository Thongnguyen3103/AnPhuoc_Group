from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse, Response

from app.deps import client_ip, current_user, get_conn
from app.repositories import audit, snapshots

router = APIRouter(prefix='/api/report', tags=['report'])


def snapshot_public(row) -> dict | None:
    if row is None:
        return None
    return {k: row[k] for k in ('id', 'ref_label', 'ref_year', 'ref_month', 'built_at', 'size_bytes',
                                'sku_count', 'imported_at')} | {'is_active': bool(row['is_active'])}


def active_or_503(conn):
    row = snapshots.get_active(conn)
    if not row:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            'Chưa có dữ liệu báo cáo trên máy chủ. Liên hệ quản trị để nạp bản build.')
    return row


@router.get('/meta')
def meta(user: dict = Depends(current_user), conn=Depends(get_conn)):
    return {'snapshot': snapshot_public(active_or_503(conn))}


@router.get('/payload')
def payload(request: Request, user: dict = Depends(current_user), conn=Depends(get_conn)):
    row = active_or_503(conn)
    path = request.app.state.snapshot_service.payload_path(row)
    if not path.is_file():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, 'File dữ liệu của snapshot đang dùng bị thiếu.')
    etag = f'"{row["sha256"][:32]}"'
    # identity: payload đã gzip sẵn, client tự giải nén (DecompressionStream) — không để middleware nén lại
    headers = {'ETag': etag, 'Cache-Control': 'private, no-cache', 'Content-Encoding': 'identity'}
    if request.headers.get('if-none-match') == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    audit.log(conn, 'view_report', user, row['ref_label'] or '', client_ip(request))
    return FileResponse(path, media_type='application/octet-stream', headers=headers)

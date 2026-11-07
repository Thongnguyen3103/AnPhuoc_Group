from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.deps import current_user, get_conn
from app.repositories import skus
from app.routers.report import active_or_503, snapshot_public

router = APIRouter(prefix='/api/skus', tags=['skus'])


def _item(row) -> dict:
    d = dict(row)
    d['ton'] = d['ton_ch'] + d['ton_kho']
    avg3 = d['ban_3m'] / 3
    d['months_of_supply'] = (round(d['ton'] / avg3, 2) if avg3 > 0 else None) if d['ton'] > 0 else 0
    return d


@router.get('')
def search(q: str | None = Query(None, max_length=64),
           brand: str | None = None, cat_group: str | None = None, group_report: str | None = None,
           item: str | None = None, status_: str | None = Query(None, alias='status'),
           sort: str = 'ton', order: Literal['asc', 'desc'] = 'desc',
           limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
           user: dict = Depends(current_user), conn=Depends(get_conn)):
    if sort not in skus.SORTABLE:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f'Không sắp xếp được theo "{sort}".')
    snap = active_or_503(conn)
    filters = {'brand': brand, 'cat_group': cat_group, 'group_report': group_report, 'item': item, 'status': status_}
    total, sums, rows = skus.search(conn, snap['id'], (q or '').strip() or None, filters, sort, order == 'desc',
                                    limit, offset)
    return {'snapshot': snapshot_public(snap), 'total': total, 'sums': sums,
            'items': [_item(r) for r in rows], 'limit': limit, 'offset': offset}


@router.get('/facets')
def facets(brand: str | None = None, user: dict = Depends(current_user), conn=Depends(get_conn)):
    snap = active_or_503(conn)
    return {'snapshot_id': snap['id'], **skus.facets(conn, snap['id'], brand)}


@router.get('/{ma_hang}')
def by_code(ma_hang: str, user: dict = Depends(current_user), conn=Depends(get_conn)):
    snap = active_or_503(conn)
    rows = skus.by_code(conn, snap['id'], ma_hang.strip())
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f'Không tìm thấy mã hàng {ma_hang}.')
    return {'snapshot': snapshot_public(snap), 'items': [_item(r) for r in rows]}

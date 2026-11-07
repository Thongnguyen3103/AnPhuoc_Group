from fastapi import APIRouter, Depends

from app import __version__
from app.deps import get_conn
from app.repositories import snapshots

router = APIRouter(tags=['health'])


@router.get('/api/health')
def health(conn=Depends(get_conn)):
    conn.execute('SELECT 1').fetchone()
    snap = snapshots.get_active(conn)
    return {
        'status': 'ok' if snap else 'no_data',
        'version': __version__,
        'snapshot': {'ref_label': snap['ref_label'], 'built_at': snap['built_at']} if snap else None,
    }

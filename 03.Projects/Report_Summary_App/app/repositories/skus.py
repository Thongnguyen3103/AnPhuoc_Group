FIELDS = ('mh', 'op', 'brand', 'cat_group', 'group_report', 'item', 'status', 'price', 'prod_ym', 'age_months',
          'ton_ch', 'ton_kho', 'ban_1m', 'ban_3m', 'ban_6m', 'ban_ytd', 'ban_all', 'months_since_sale')

# Cột được phép sắp xếp (whitelist — không bao giờ ghép chuỗi sort từ request vào SQL)
SORTABLE = {f: f for f in FIELDS}
SORTABLE['ton'] = '(ton_ch + ton_kho)'
FILTERS = ('brand', 'cat_group', 'group_report', 'item', 'status')


def insert_many(conn, snapshot_id: int, rows: list) -> None:
    placeholders = ', '.join('?' * (len(FIELDS) + 1))
    conn.executemany(
        f'INSERT INTO sku_track (snapshot_id, {", ".join(FIELDS)}) VALUES ({placeholders})',
        ((snapshot_id, *(r.get(f) for f in FIELDS)) for r in rows))


def _where(snapshot_id: int, q: str | None, filters: dict) -> tuple:
    clauses, params = ['snapshot_id = ?'], [snapshot_id]
    if q:
        clauses.append("(mh LIKE ? ESCAPE '\\' OR (mh || ' ' || op) LIKE ? ESCAPE '\\')")
        like = '%' + q.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        params += [like, like]
    for f in FILTERS:
        if filters.get(f):
            clauses.append(f'{f} = ?')
            params.append(filters[f])
    return ' AND '.join(clauses), params


def search(conn, snapshot_id: int, q: str | None, filters: dict, sort: str, desc: bool,
           limit: int, offset: int) -> tuple:
    where, params = _where(snapshot_id, q, filters)
    order = SORTABLE.get(sort, SORTABLE['ton'])
    total = conn.execute(f'SELECT COUNT(*) FROM sku_track WHERE {where}', params).fetchone()[0]
    sums = conn.execute(
        'SELECT COALESCE(SUM(ton_ch), 0) AS ton_ch, COALESCE(SUM(ton_kho), 0) AS ton_kho, '
        'COALESCE(SUM(ban_1m), 0) AS ban_1m, COALESCE(SUM(ban_3m), 0) AS ban_3m, '
        'COALESCE(SUM(ban_6m), 0) AS ban_6m, COALESCE(SUM(ban_ytd), 0) AS ban_ytd, '
        f'COALESCE(SUM(ban_all), 0) AS ban_all FROM sku_track WHERE {where}', params).fetchone()
    rows = conn.execute(
        f'SELECT {", ".join(FIELDS)} FROM sku_track WHERE {where} '
        f'ORDER BY {order} {"DESC" if desc else "ASC"}, mh, op LIMIT ? OFFSET ?',
        (*params, limit, offset)).fetchall()
    return total, dict(sums), rows


def by_code(conn, snapshot_id: int, mh: str) -> list:
    return conn.execute(
        f'SELECT {", ".join(FIELDS)} FROM sku_track WHERE snapshot_id = ? AND mh = ? ORDER BY op',
        (snapshot_id, mh)).fetchall()


def facets(conn, snapshot_id: int, brand: str | None = None) -> dict:
    out = {}
    for f in ('brand', 'cat_group', 'group_report', 'item', 'status'):
        sql = f"SELECT DISTINCT {f} FROM sku_track WHERE snapshot_id = ? AND COALESCE({f}, '') <> ''"
        params = [snapshot_id]
        if brand and f != 'brand':
            sql += ' AND brand = ?'
            params.append(brand)
        out[f] = sorted(r[0] for r in conn.execute(sql, params))
    return out

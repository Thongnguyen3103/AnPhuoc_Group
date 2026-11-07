#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Export_App_Snapshot.py — Xuất dữ liệu cho Web app nội bộ (Report_Summary_App)
Ghi vào 04.Output/Report_Summary/app_snapshot/:
- payload.json.gz   : payload báo cáo (cùng bytes GZIP nhúng trong HTML)
- sku_track.json.gz : bảng theo dõi Mã hàng đã giải mã dict (cho API /api/skus)
- meta.json         : thông tin bản build — GHI CUỐI CÙNG (app thấy meta mới = bản build đã đủ file)
Mọi file ghi qua .tmp rồi os.replace để app không bao giờ đọc file dở dang.
"""
import os
import json
import gzip
import hashlib

SKU_FIELDS = {          # cột sku_track (payload) -> tên trường cho app
    'br': 'brand', 'catg': 'cat_group', 'gr': 'group_report', 'item': 'item', 'status': 'status',
    'price': 'price', 'prod': 'prod_ym', 'age': 'age_months',
    'ton_ch': 'ton_ch', 'ton_kho': 'ton_kho', 'b1': 'ban_1m', 'b3': 'ban_3m', 'b6': 'ban_6m',
    'bytd': 'ban_ytd', 'ball': 'ban_all', 'nosale': 'months_since_sale',
}
DICT_COLS = {'key', 'br', 'catg', 'gr', 'item', 'status'}
PM_SEP = '§'


def _write_atomic(path, data):
    tmp = path + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(data)
    os.replace(tmp, path)


def _sku_rows(full_payload):
    st = (full_payload.get('ton') or {}).get('sku_track')
    if not st:
        return []
    words = full_payload['dict']
    cols = {name: st['data'][i] for i, name in enumerate(st['cols'])}
    rows = []
    for i in range(len(cols['key'])):
        mh, _, op = words[cols['key'][i]].partition(PM_SEP)
        row = {'mh': mh, 'op': op}
        for src, dst in SKU_FIELDS.items():
            v = cols[src][i]
            row[dst] = words[v] if src in DICT_COLS else v
        rows.append(row)
    return rows


def run(full_payload, gz_bytes, out_dir):
    snap_dir = os.path.join(out_dir, 'app_snapshot')
    os.makedirs(snap_dir, exist_ok=True)

    sha = hashlib.sha256(gz_bytes).hexdigest()
    _write_atomic(os.path.join(snap_dir, 'payload.json.gz'), gz_bytes)

    rows = _sku_rows(full_payload)
    sku_bytes = gzip.compress(json.dumps(rows, ensure_ascii=False, separators=(',', ':')).encode('utf-8'), 6)
    _write_atomic(os.path.join(snap_dir, 'sku_track.json.gz'), sku_bytes)

    meta = {
        'format': 1,
        'built': full_payload.get('built'),
        'ref': full_payload.get('ref'),
        'payload_sha256': sha,
        'payload_size': len(gz_bytes),
        'sku_count': len(rows),
    }
    _write_atomic(os.path.join(snap_dir, 'meta.json'), json.dumps(meta, ensure_ascii=False, indent=2).encode('utf-8'))
    print(f'   Snapshot Web app: {snap_dir} ({len(gz_bytes)/1024/1024:.2f} MB, {len(rows):,} SKU)')
    return snap_dir

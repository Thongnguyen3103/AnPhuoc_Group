#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Aggregate_Stock_Tracking.py — Stage 2b: Bảng theo dõi Mã hàng (SKU) cho Tồn Sheet 5 & 6
1 dòng / SKU (MaHang + Operation) đang có tồn HOẶC có bán lẻ trong 6 tháng gần nhất:
- Tồn hiện tại tách CH / Kho (cùng bộ lọc với Aggregate_Inventory: bỏ Bao bì, Đồng phục)
- Bán lẻ (SalesSource = Retail, Nội dung = 'Bán' — cùng định nghĩa Phần 1 Số Bán): tháng tham chiếu, 3 tháng, 6 tháng,
  lũy kế năm (YTD), lũy kế toàn kỳ cache (3 năm)
- Số tháng kể từ lần bán gần nhất
- Năm/Tháng sản xuất (F_DataTracking) -> tuổi tồn (tháng) tính đến kỳ tham chiếu
Các chỉ số (số tháng đáp ứng, sell-through, vòng quay...) tính ở client.
"""
import os
import sys
import time
import duckdb
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

import Get_Paths
try:
    from Steps.Normalize_Labels import tracking_sql
    from Steps.Aggregate_Inventory import KHO_LIST, classify_cat_group
except ImportError:
    from Normalize_Labels import tracking_sql
    from Aggregate_Inventory import KHO_LIST, classify_cat_group

STAGE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(STAGE_DIR))

INVENTORY_FILE = Get_Paths.ton_kho_size
TRACKING_FILE = Get_Paths.data_tracking
CACHE_FILE = os.path.join(ROOT, 'Cache', 'Sales_Cache.parquet')

PM_SEP = '§'
MAIN_BR = ('Hiệu An Phước', 'Hiệu Pierre Cardin', 'Hiệu An Phước Ladies', 'Hiệu Bonjour', 'Hiệu Anamai')
EXCL_GR = "(LOWER(COALESCE(Group_Report, '')) NOT LIKE '%bao bì%' AND LOWER(COALESCE(Group_Report, '')) NOT LIKE '%đồng phục%')"


def _map_brand(brand_raw, gender):
    b = (brand_raw or '').strip()
    if b == 'Hiệu An Phước' and (gender or '').strip() == 'Nữ':
        return 'Hiệu An Phước Ladies'
    return b if b in MAIN_BR else 'Khác'


def run(shared_dict, ref_year, ref_month):
    t0 = time.time()
    print('=' * 65)
    print('  [STAGE 2b] BẢNG THEO DÕI MÃ HÀNG (TỒN · BÁN · TUỔI TỒN)')
    print('=' * 65)

    def get_dict_idx(s):
        s_val = '' if s is None else str(s).strip()
        if s_val not in shared_dict['map']:
            shared_dict['map'][s_val] = len(shared_dict['list'])
            shared_dict['list'].append(s_val)
        return shared_dict['map'][s_val]

    ref_idx = ref_year * 12 + ref_month
    kho_sql = ', '.join("'" + k.replace("'", "''") + "'" for k in sorted(KHO_LIST))

    sql = f"""
    WITH inv AS (
        SELECT
            Mahang AS mh, Operation AS op,
            SUM(CASE WHEN Region NOT IN ({kho_sql}) THEN CAST(Qty_TonKho AS BIGINT) ELSE 0 END) AS ton_ch,
            SUM(CASE WHEN Region IN ({kho_sql}) THEN CAST(Qty_TonKho AS BIGINT) ELSE 0 END) AS ton_kho,
            ARG_MAX(Status, Qty_TonKho) AS status,
            MAX(Brand) AS brand, MAX(Gender) AS gender, MAX(Report_item_name) AS item,
            MAX(Group_Report) AS gr, MAX(Product_group) AS pg
        FROM read_parquet('{INVENTORY_FILE}')
        WHERE Qty_TonKho > 0 AND {EXCL_GR}
        GROUP BY 1, 2
    ),
    sal AS (
        SELECT
            MaHang AS mh, Operation AS op,
            SUM(CASE WHEN Year * 12 + Month = {ref_idx} THEN Qty_Ban ELSE 0 END) AS b1,
            SUM(CASE WHEN Year * 12 + Month BETWEEN {ref_idx - 2} AND {ref_idx} THEN Qty_Ban ELSE 0 END) AS b3,
            SUM(CASE WHEN Year * 12 + Month BETWEEN {ref_idx - 5} AND {ref_idx} THEN Qty_Ban ELSE 0 END) AS b6,
            SUM(CASE WHEN Year = {ref_year} AND Month <= {ref_month} THEN Qty_Ban ELSE 0 END) AS bytd,
            SUM(Qty_Ban) AS ball,
            MAX(CASE WHEN Qty_Ban > 0 THEN Year * 12 + Month END) AS last_idx,
            MAX(Brand) AS brand, MAX(Gender) AS gender, MAX(Report_item_name) AS item,
            MAX(Group_Report) AS gr, MAX(Product_group) AS pg
        FROM read_parquet('{CACHE_FILE}')
        WHERE SalesSource = 'Retail' AND COALESCE("Nội dung", 'Bán') = 'Bán'
          AND Year * 12 + Month <= {ref_idx} AND {EXCL_GR}
        GROUP BY 1, 2
    ),
    trk AS (
        SELECT item_code, Operation,
               MAX(Production_year) AS py, MAX(Production_month) AS pm, MAX(Price) AS price
        FROM ({tracking_sql(TRACKING_FILE)})
        GROUP BY 1, 2
    )
    SELECT
        COALESCE(i.mh, s.mh) AS mh, COALESCE(i.op, s.op) AS op,
        COALESCE(i.brand, s.brand) AS brand, COALESCE(i.gender, s.gender) AS gender,
        COALESCE(i.item, s.item) AS item, COALESCE(i.gr, s.gr) AS gr, COALESCE(i.pg, s.pg) AS pg,
        COALESCE(i.status, 'Nguyên giá') AS status,
        COALESCE(i.ton_ch, 0) AS ton_ch, COALESCE(i.ton_kho, 0) AS ton_kho,
        COALESCE(s.b1, 0) AS b1, COALESCE(s.b3, 0) AS b3, COALESCE(s.b6, 0) AS b6,
        COALESCE(s.bytd, 0) AS bytd, COALESCE(s.ball, 0) AS ball, s.last_idx,
        t.py, t.pm, COALESCE(t.price, 0) AS price
    FROM inv i
    FULL OUTER JOIN sal s ON i.mh = s.mh AND i.op = s.op
    LEFT JOIN trk t ON COALESCE(i.mh, s.mh) = t.item_code AND COALESCE(i.op, s.op) = t.Operation
    WHERE COALESCE(i.ton_ch, 0) + COALESCE(i.ton_kho, 0) > 0 OR COALESCE(s.b6, 0) <> 0
    """
    con = duckdb.connect(':memory:')
    df = con.execute(sql).fetchdf()

    cols = ['key', 'br', 'catg', 'gr', 'item', 'status', 'price', 'prod', 'age',
            'ton_ch', 'ton_kho', 'b1', 'b3', 'b6', 'bytd', 'ball', 'nosale']
    data = [[] for _ in cols]
    n_unknown = 0
    for r in df.itertuples(index=False):
        brand = _map_brand(r.brand, r.gender)
        item = str(r.item or '').strip()
        # Tuổi tồn: tháng SX thiếu/0 -> lấy giữa năm (T6); chưa có năm SX -> -1 (Chưa rõ)
        py = 0 if pd.isna(r.py) else int(r.py)
        pm = 0 if pd.isna(r.pm) else int(r.pm)
        if py:
            pm_eff = pm if 1 <= pm <= 12 else 6
            prod = py * 100 + pm_eff
            age = max(0, ref_idx - (py * 12 + pm_eff))
        else:
            prod, age = 0, -1
            n_unknown += 1
        last_idx = r.last_idx
        nosale = -1 if pd.isna(last_idx) else int(ref_idx - last_idx)

        data[0].append(get_dict_idx(str(r.mh).strip() + PM_SEP + str(r.op).strip()))
        data[1].append(get_dict_idx(brand))
        data[2].append(get_dict_idx(classify_cat_group(r.gr, r.pg, item, str(r.brand or '').strip())))
        data[3].append(get_dict_idx(str(r.gr or '').strip()))
        data[4].append(get_dict_idx(item))
        data[5].append(get_dict_idx(str(r.status or 'Nguyên giá').strip()))
        data[6].append(int(round(float(r.price or 0))))
        data[7].append(prod)
        data[8].append(age)
        for ci, v in ((9, r.ton_ch), (10, r.ton_kho), (11, r.b1), (12, r.b3), (13, r.b6), (14, r.bytd), (15, r.ball)):
            data[ci].append(int(v))
        data[16].append(nosale)

    tot_ton = sum(data[9]) + sum(data[10])
    print(f'   Số SKU theo dõi: {len(df):,} (chưa rõ năm SX: {n_unknown:,})')
    print(f'   Tổng tồn trong bảng theo dõi: {tot_ton:,} sp  ·  Bán lẻ T{ref_month}: {sum(data[11]):,} sp')
    print(f'   Hoàn thành Stage 2b ({time.time()-t0:.1f}s)')
    return {'cols': cols, 'data': data}, tot_ton

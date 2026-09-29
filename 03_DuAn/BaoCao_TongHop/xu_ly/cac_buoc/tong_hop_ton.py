#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
tong_hop_ton.py — Stage 2: Tổng hợp dữ liệu Báo cáo Số Tồn & Đối soát Size cấp Cửa hàng
- Đọc từ InventorySize.parquet
- LEFT JOIN F_DataTracking.parquet để lấy đầy đủ thuộc tính
- Đọc lệnh HHLC (07.Lenh_HHLC) để gắn cờ luân chuyển
- Tính cờ sold_30/60/90 từ cache_sales
- Phân loại region_kind (Cửa hàng vs 5 Kho chính + Kho khác)
- Phân loại kỳ phân phối (cửa sổ 6 tháng) & gán size_profile
- ĐỐI SOÁT SIZE CẤP CỬA HÀNG: Kết hợp Bán & Tồn (Store_name, Mahang, Size, ban_qty, ton_qty)
- Metadata đầy đủ cho từng Mã hàng (product_meta)
- Xuất dữ liệu Columnar + Dictionary Encoding
"""
import os
import sys
import time
import re
import duckdb

sys.stdout.reconfigure(encoding='utf-8')

from dung_chung import duong_dan

STAGE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(STAGE_DIR)
ROOT = os.path.dirname(BACKEND_DIR)

INVENTORY_FILE = duong_dan.ton_kho_size
TRACKING_FILE = duong_dan.data_tracking
HHLC_GLOB = os.path.join(duong_dan.lenh_hhlc, '*', '*.parquet')
CACHE_FILE = os.path.join(ROOT, 'du_lieu_tam', 'cache_ban_hang.parquet')

KHO_LIST = {
    'Kho Tổng hợp', 'Kho AP', 'Kho PIE', 'Kho CNHN', 'Kho TB3 đồ lót',
    'Kho KDTT', 'Kho Nội Bộ AP', 'Kho Sửa Chữa', 'KDND'
}
KHO_CHINH = {'Kho AP', 'Kho PIE', 'Kho TB3 đồ lót', 'Kho CNHN', 'Kho Tổng hợp'}


def parse_dist_plan(dist_str, ref_year, ref_month):
    """
    Phân loại Dist_plan theo yêu cầu nghiệp vụ:
    - prep: Chuẩn bị PP (KHPP >= tháng hiện tại, ví dụ T9, T10/2026)
    - new_dist: Mới PP (trong vòng 6 tháng gần đây, ví dụ T3..T8/2026)
    - pp_6m: Đã PP 6 tháng (7..12 tháng)
    - pp_1y: Đã PP 1 năm (13..24 tháng)
    - pp_2y: Đã PP 2 năm (25..36 tháng)
    - pp_over_2y: Đã PP > 2 năm (> 36 tháng)
    - special: Chưa có KHPP hoặc đặc biệt
    """
    if not dist_str:
        return 'special', None, None
    s = str(dist_str).strip()
    m = re.search(r'T?(\d{1,2})[\./](\d{4})', s, re.IGNORECASE)
    if not m:
        return 'special', None, None
    try:
        month = int(m.group(1))
        year = int(m.group(2))
        if month < 1 or month > 12 or year < 2010 or year > 2035:
            return 'special', None, None
        
        diff_months = (ref_year - year) * 12 + (ref_month - month)
        if diff_months < 0:
            return 'prep', year, month
        elif 0 <= diff_months <= 5:
            return 'new_dist', year, month
        elif 6 <= diff_months <= 11:
            return 'pp_6m', year, month
        elif 12 <= diff_months <= 23:
            return 'pp_1y', year, month
        elif 24 <= diff_months <= 35:
            return 'pp_2y', year, month
        else:
            return 'pp_over_2y', year, month
    except Exception:
        return 'special', None, None


def determine_size_profile(item_name, sample_sizes):
    """Xác định size_profile để biết khi nào hiển thị Tổng size."""
    name_low = str(item_name).lower()
    sizes_set = {str(s).upper() for s in sample_sizes if str(s).strip()}
    
    if any(x in name_low for x in ['áo ngực', 'ao nguc', 'bra']):
        return 'bra'
    if any(x in name_low for x in ['chemise nam', 'sơ mi nam', 'so mi nam']):
        return 'chemise_men'
    if any(x in name_low for x in ['chemise nữ', 'sơ mi nữ', 'so mi nu', 'váy', 'đầm']):
        return 'women_alpha'
    if any(x in name_low for x in ['quần tây', 'quan tay', 'quần kaki', 'quan kaki', 'quần vest', 'quan vest']):
        return 'pants_numeric'
    if any(s in sizes_set for s in ['37', '38', '39', '40', '41', '42', '43', '44']):
        return 'chemise_men'
    if any(s in sizes_set for s in ['S', 'M', 'L', 'XL', 'XXL', '3XL']):
        return 'alpha'
    if any(s in sizes_set for s in ['28', '29', '30', '31', '32', '33', '34', '35', '36']):
        return 'pants_numeric'
    return 'other'


CAT_GROUP_CORE_GR = {'Chemise', 'Áo Thun', 'Quần Tây', 'Quần Kaki', 'Quần Short', 'Áo Khoác', 'Suit'}


def classify_cat_group(group_report, product_group, item_name, brand):
    """Phân 6 nhóm hàng cho Sheet 4 — KHỚP với CASE cat_group trong tong_hop_ban.attr_sql."""
    gr = (group_report or '').strip()
    grl = gr.lower()
    pgl = (product_group or '').lower()
    itl = (item_name or '').lower()
    if 'golf' in grl or 'golf' in itl:
        return 'Nhóm Golf'
    if 'da' in grl or 'da' in pgl:
        return 'Nhóm Đồ da'
    if any(k in grl for k in ('phụ kiện', 'cà vạt', 'khăn', 'nón', 'tất', 'vớ')):
        return 'Nhóm Phụ kiện khác'
    if brand in ('Hiệu Anamai', 'Hiệu Bonjour') or 'đồ lót' in grl or 'nội y' in grl:
        return 'Nhóm Anamai / Bonjour'
    if gr in CAT_GROUP_CORE_GR:
        return 'Nhóm chủ đạo'
    return 'Nhóm Quần áo khác'


def run(shared_dict=None, ref_year=2026, ref_month=8):
    t0 = time.time()
    print('=' * 65)
    print('  [STAGE 2] AGGREGATE SỐ TỒN & ĐỐI SOÁT SIZE CẤP CỬA HÀNG')
    print('=' * 65)

    if shared_dict is None:
        shared_dict = {'list': [], 'map': {}}

    def get_dict_idx(s):
        s_val = '' if s is None else str(s).strip()
        if s_val not in shared_dict['map']:
            idx = len(shared_dict['list'])
            shared_dict['list'].append(s_val)
            shared_dict['map'][s_val] = idx
        return shared_dict['map'][s_val]

    con = duckdb.connect(':memory:')

    # 1. Đọc lệnh HHLC (lấy mã hàng vừa nhận luân chuyển trong 4 tháng: tháng 6, 7, 8, 9 nếu ref=8)
    print('   Đang đọc thông tin Lệnh luân chuyển (HHLC 4 tháng)...')
    hhlc_items = set()
    try:
        hhlc_df = con.execute(f"""
            SELECT DISTINCT MaHang
            FROM read_parquet('{HHLC_GLOB}')
            WHERE Year = {ref_year} AND Month BETWEEN {ref_month - 2} AND {ref_month + 1}
        """).fetchdf()
        hhlc_items = set(hhlc_df['MaHang'].dropna().tolist())
        print(f'   Có {len(hhlc_items):,} mã hàng vừa luân chuyển trong 4 tháng ({ref_month-2}..{ref_month+1}/{ref_year})')
    except Exception as e:
        print(f'   Lưu ý: Không tải được HHLC ({e}), bỏ qua badge LC')

    # 2. Đọc lịch sử bán để tính cờ sold_30/60/90
    print('   Đang tính cờ bán gần đây (sold_30/60/90) từ cache_sales...')
    sold_flags = {}
    try:
        sold_df = con.execute(f"""
            SELECT
                MaHang,
                MAX(CASE WHEN Year = {ref_year} AND Month = {ref_month} THEN 1 ELSE 0 END) AS s30,
                MAX(CASE WHEN Year = {ref_year} AND Month >= {ref_month - 1} THEN 1 ELSE 0 END) AS s60,
                MAX(CASE WHEN Year = {ref_year} AND Month >= {ref_month - 2} THEN 1 ELSE 0 END) AS s90
            FROM read_parquet('{CACHE_FILE}')
            WHERE Qty_Ban > 0
            GROUP BY MaHang
        """).fetchdf()
        for r in sold_df.itertuples(index=False):
            if r.s30 == 1:
                sold_flags[r.MaHang] = 'sold_30'
            elif r.s60 == 1:
                sold_flags[r.MaHang] = 'sold_60'
            elif r.s90 == 1:
                sold_flags[r.MaHang] = 'sold_90'
            else:
                sold_flags[r.MaHang] = 'not_sold_90'
        print(f'   Đã tính cờ bán cho {len(sold_flags):,} mã hàng')
    except Exception as e:
        print(f'   Lưu ý: Không tải được cờ bán ({e})')

    # 3. Đọc dữ liệu Tồn kho + Join Tracking
    print('   Đang đọc InventorySize & Join F_DataTracking...')
    inv_sql = f"""
    WITH raw_inv AS (
        SELECT
            Store_name, Region, Warehouse, Brand, Report_item_name, Mahang,
            Operation, Size, CAST(Qty_TonKho AS INT) AS Qty_TonKho, Status,
            Product_type, Gender, Product_group, Group_Report
        FROM read_parquet('{INVENTORY_FILE}')
        WHERE Qty_TonKho > 0
          AND (LOWER(COALESCE(Group_Report, '')) NOT LIKE '%bao bì%' AND LOWER(COALESCE(Group_Report, '')) NOT LIKE '%đồng phục%')
    ),
    trk AS (
        SELECT
            item_code, Operation,
            MAX(Color_group) AS Color_group,
            MAX(Color_tone) AS Color_tone,
            MAX(Form) AS Form,
            MAX(Style) AS Style,
            MAX(Attribute) AS Attribute,
            MAX(Dist_plan) AS Dist_plan,
            MAX(Price) AS Price,
            MAX(Sub_Brand) AS Sub_Brand
        FROM read_parquet('{TRACKING_FILE}')
        GROUP BY item_code, Operation
    )
    SELECT
        i.Store_name, i.Region, i.Warehouse, i.Brand, i.Report_item_name, i.Mahang,
        i.Operation, i.Size, i.Qty_TonKho, i.Status, i.Product_type, i.Gender,
        i.Product_group, i.Group_Report,
        COALESCE(t.Color_group, '') AS Color_group,
        COALESCE(t.Color_tone, '') AS Color_tone,
        COALESCE(t.Form, '') AS Form,
        COALESCE(t.Style, '') AS Style,
        COALESCE(t.Attribute, '') AS Attribute,
        COALESCE(t.Dist_plan, '') AS Dist_plan,
        COALESCE(t.Price, 0) AS Price,
        COALESCE(t.Sub_Brand, '') AS Sub_Brand
    FROM raw_inv i
    LEFT JOIN trk t ON i.Mahang = t.item_code AND i.Operation = t.Operation
    """
    inv_df = con.execute(inv_sql).fetchdf()
    print(f'   Đã nạp {len(inv_df):,} dòng tồn chi tiết')

    # 4. Gom nhóm kích cỡ (Size Matrix) + metadata cấp SKU
    #    1 SKU = MaHang + Operation. product_meta key = "MaHang§Operation".
    print('   Đang xử lý phân bổ Size và gán size_profile...')
    PM_SEP = '§'
    MAIN_BR = ('Hiệu An Phước', 'Hiệu Pierre Cardin', 'Hiệu An Phước Ladies', 'Hiệu Bonjour', 'Hiệu Anamai')

    def _map_brand(brand_raw, gender):
        b = (brand_raw or '').strip()
        if b == 'Hiệu An Phước' and (gender or '').strip() == 'Nữ':
            return 'Hiệu An Phước Ladies'
        return b if b in MAIN_BR else 'Khác'

    item_sizes = {}
    item_sample_sizes = {}
    item_attributes = {}
    product_meta = {}

    for r in inv_df.itertuples(index=False):
        it = r.Report_item_name
        sz = str(r.Size).strip()
        qty = int(r.Qty_TonKho)
        mh = str(r.Mahang).strip()
        op = str(r.Operation).strip()

        if it not in item_sizes:
            item_sizes[it] = {}
            item_sample_sizes[it] = set()
            item_attributes[it] = {'forms': {}, 'styles': {}, 'colors': {}, 'sub_brands': {}}
        item_sizes[it][sz] = item_sizes[it].get(sz, 0) + qty
        item_sample_sizes[it].add(sz)

        f = str(r.Form).strip() or 'Khác'
        st = str(r.Style).strip() or 'Khác'
        c = str(r.Color_group).strip() or 'Khác'
        sb = str(r.Sub_Brand).strip() or 'Khác'

        item_attributes[it]['forms'][f] = item_attributes[it]['forms'].get(f, 0) + qty
        item_attributes[it]['styles'][st] = item_attributes[it]['styles'].get(st, 0) + qty
        item_attributes[it]['colors'][c] = item_attributes[it]['colors'].get(c, 0) + qty
        item_attributes[it]['sub_brands'][sb] = item_attributes[it]['sub_brands'].get(sb, 0) + qty

        pmk = mh + PM_SEP + op
        if pmk not in product_meta:
            d_cat, _, _ = parse_dist_plan(r.Dist_plan, ref_year, ref_month)
            product_meta[pmk] = [
                get_dict_idx(str(it or '').strip()),                       # 0 tên hàng
                get_dict_idx(str(r.Group_Report or '').strip()),          # 1 nhóm BC
                get_dict_idx(_map_brand(r.Brand, r.Gender)),              # 2 brand
                get_dict_idx(f),                                           # 3 form
                get_dict_idx(st),                                          # 4 style
                get_dict_idx(c),                                           # 5 màu
                float(r.Price or 0),                                       # 6 đơn giá
                get_dict_idx(sold_flags.get(mh, 'not_sold_90')),          # 7 cờ bán (theo MaHang)
                get_dict_idx(str(r.Dist_plan or '').strip()),             # 8 Dist_plan gốc
                get_dict_idx(d_cat),                                       # 9 nhóm tuổi PP
                1 if mh in hhlc_items else 0,                              # 10 cờ LC (theo MaHang)
                get_dict_idx(str(r.Status or 'Nguyên giá').strip()),      # 11 trạng thái
                get_dict_idx(classify_cat_group(r.Group_Report, r.Product_group, it, str(r.Brand).strip())),  # 12 nhóm hàng
                get_dict_idx(op),                                          # 13 Operation
            ]

    item_profiles = {it: determine_size_profile(it, szs) for it, szs in item_sample_sizes.items()}

    # 5. Tổng hợp Overview Tồn theo các chiều nghiệp vụ
    print('   Đang tổng hợp dữ liệu Tồn theo các chiều phân tích...')
    ton_grouped = {}
    for r in inv_df.itertuples(index=False):
        rg_val = str(r.Region).strip()
        rk = 'KHO' if rg_val in KHO_LIST else 'CH'
        if rk == 'KHO':
            wh = rg_val if rg_val in KHO_CHINH else 'Kho khác'
        else:
            wh = 'Cửa hàng'

        br_val = str(r.Brand).strip()
        if br_val == 'Hiệu An Phước' and str(r.Gender).strip() == 'Nữ':
            br = 'Hiệu An Phước Ladies'
        elif br_val in ['Hiệu An Phước', 'Hiệu Pierre Cardin', 'Hiệu An Phước Ladies', 'Hiệu Bonjour', 'Hiệu Anamai']:
            br = br_val
        else:
            br = 'Khác'

        dist_cat, _, _ = parse_dist_plan(r.Dist_plan, ref_year, ref_month)
        sold_cat = sold_flags.get(r.Mahang, 'not_sold_90')
        status_val = str(r.Status).strip() or 'Nguyên giá'
        has_lc = 1 if r.Mahang in hhlc_items else 0
        size_prof = item_profiles.get(r.Report_item_name, 'OTHER')
        cat_grp = classify_cat_group(r.Group_Report, r.Product_group, r.Report_item_name, str(r.Brand).strip())

        key = (
            rk, rg_val, wh, br, str(r.Product_group).strip(), str(r.Group_Report).strip(),
            str(r.Report_item_name).strip(), str(r.Color_group).strip(), str(r.Form).strip(),
            str(r.Style).strip(), str(r.Attribute).strip(), dist_cat, sold_cat, has_lc, size_prof, status_val,
            cat_grp
        )
        ton_grouped[key] = ton_grouped.get(key, 0) + int(r.Qty_TonKho)

    print(f'   Tổng hợp Overview Tồn: {len(ton_grouped):,} tổ hợp')

    # Giữ nguyên vị trí qty = index 16 (engine phụ thuộc); catg thêm ở CUỐI = index 17
    cols = ['rk', 'rg', 'wh', 'br', 'pg', 'gr', 'item', 'cg', 'form', 'style', 'attr', 'dist_cat', 'sold_cat', 'has_lc', 'size_prof', 'status', 'qty', 'catg']
    data = [[] for _ in cols]

    for k, qty in ton_grouped.items():
        data[0].append(get_dict_idx(k[0]))   # rk
        data[1].append(get_dict_idx(k[1]))   # rg
        data[2].append(get_dict_idx(k[2]))   # wh
        data[3].append(get_dict_idx(k[3]))   # br
        data[4].append(get_dict_idx(k[4]))   # pg
        data[5].append(get_dict_idx(k[5]))   # gr
        data[6].append(get_dict_idx(k[6]))   # item
        data[7].append(get_dict_idx(k[7]))   # cg
        data[8].append(get_dict_idx(k[8]))   # form
        data[9].append(get_dict_idx(k[9]))   # style
        data[10].append(get_dict_idx(k[10])) # attr
        data[11].append(get_dict_idx(k[11])) # dist_cat
        data[12].append(get_dict_idx(k[12])) # sold_cat
        data[13].append(int(k[13]))          # has_lc
        data[14].append(get_dict_idx(k[14])) # size_prof
        data[15].append(get_dict_idx(k[15])) # status
        data[16].append(int(qty))            # qty
        data[17].append(get_dict_idx(k[16])) # catg (nhóm hàng Sheet 4)

    # 6. ĐỐI SOÁT SIZE CẤP CỬA HÀNG (store_product_sizes)
    # Kết hợp Bán (2026) và Tồn kho theo cặp (Store_name, Mahang, Size)
    print('   Đang tính toán ma trận Đối soát Bán & Tồn đến từng Size của từng Cửa hàng...')
    st_size_sql = f"""
    WITH st_sales AS (
        SELECT
            Store_name, MaHang, Operation, Size,
            CAST(SUM(Qty_Ban) AS INT) AS ban_qty
        FROM read_parquet('{CACHE_FILE}')
        WHERE Year = {ref_year}
          AND Store_name NOT IN ('Kho Tổng hợp', 'Kho AP', 'Kho PIE', 'Kho CNHN', 'Kho TB3 đồ lót', 'Kho KDTT', 'Kho Nội Bộ AP', 'Kho Sửa Chữa', 'KDND')
          AND (LOWER(COALESCE(Group_Report, '')) NOT LIKE '%bao bì%' AND LOWER(COALESCE(Group_Report, '')) NOT LIKE '%đồng phục%')
        GROUP BY 1, 2, 3, 4
    ),
    st_inv AS (
        SELECT
            Store_name, Mahang, Operation, Size,
            CAST(SUM(CAST(Qty_TonKho AS INT)) AS INT) AS ton_qty
        FROM read_parquet('{INVENTORY_FILE}')
        WHERE Qty_TonKho > 0
          AND Store_name NOT IN ('Kho Tổng hợp', 'Kho AP', 'Kho PIE', 'Kho CNHN', 'Kho TB3 đồ lót', 'Kho KDTT', 'Kho Nội Bộ AP', 'Kho Sửa Chữa', 'KDND')
          AND (LOWER(COALESCE(Group_Report, '')) NOT LIKE '%bao bì%' AND LOWER(COALESCE(Group_Report, '')) NOT LIKE '%đồng phục%')
        GROUP BY 1, 2, 3, 4
    )
    SELECT
        COALESCE(s.Store_name, i.Store_name) AS st,
        COALESCE(s.MaHang, i.Mahang) || '{PM_SEP}' || COALESCE(s.Operation, i.Operation) AS sku,
        COALESCE(s.Size, i.Size) AS sz,
        COALESCE(s.ban_qty, 0) AS ban_qty,
        COALESCE(i.ton_qty, 0) AS ton_qty
    FROM st_sales s
    FULL OUTER JOIN st_inv i
      ON s.Store_name = i.Store_name AND s.MaHang = i.Mahang AND s.Operation = i.Operation AND s.Size = i.Size
    WHERE (COALESCE(s.ban_qty, 0) > 0 OR COALESCE(i.ton_qty, 0) > 0)
    """
    st_size_df = con.execute(st_size_sql).fetchdf()
    print(f'   Tổng số bản ghi đối soát size cửa hàng (SKU = MaHang+Operation): {len(st_size_df):,} dòng')

    # cột 'sku' = "MaHang§Operation" (gộp 1 cột thay vì 2 -> nhẹ payload)
    st_size_cols = ['st', 'sku', 'sz', 'ban', 'ton']
    st_size_data = [[] for _ in st_size_cols]
    for r in st_size_df.itertuples(index=False):
        st_size_data[0].append(get_dict_idx(r.st))
        st_size_data[1].append(get_dict_idx(r.sku))
        st_size_data[2].append(get_dict_idx(r.sz))
        st_size_data[3].append(int(r.ban_qty))
        st_size_data[4].append(int(r.ton_qty))

    sizes_payload = {}
    for it, sz_map in item_sizes.items():
        it_idx = get_dict_idx(it)
        sizes_payload[it_idx] = [[get_dict_idx(sz), qty] for sz, qty in sz_map.items()]

    # 7. Thống kê số Tên hàng vs số Mã hàng (SKU) thực tế theo từng Brand
    brand_items_set = {}
    brand_skus_set = {}
    wh_skus_dict = {}

    for r in inv_df.itertuples(index=False):
        br_val = str(r.Brand).strip()
        if br_val == 'Hiệu An Phước' and str(r.Gender).strip() == 'Nữ':
            br = 'Hiệu An Phước Ladies'
        elif br_val in ['Hiệu An Phước', 'Hiệu Pierre Cardin', 'Hiệu An Phước Ladies', 'Hiệu Bonjour', 'Hiệu Anamai']:
            br = br_val
        else:
            br = 'Khác'

        if br not in brand_items_set:
            brand_items_set[br] = set()
            brand_skus_set[br] = set()
        brand_items_set[br].add(r.Report_item_name)
        brand_skus_set[br].add((r.Mahang, r.Operation))   # 1 SKU = MaHang + Operation

        # SKU detail cho 5 kho tổng — key = MaHang§Operation; thuộc tính đọc từ product_meta[key]
        rg_val = str(r.Region).strip()
        if rg_val in KHO_CHINH:
            it = str(r.Report_item_name).strip()
            mh = str(r.Mahang).strip()
            op = str(r.Operation).strip()
            sk_key = mh + PM_SEP + op
            sz = str(r.Size).strip()
            qty = int(r.Qty_TonKho)

            if rg_val not in wh_skus_dict:
                wh_skus_dict[rg_val] = {}
            if it not in wh_skus_dict[rg_val]:
                wh_skus_dict[rg_val][it] = {}
            if sk_key not in wh_skus_dict[rg_val][it]:
                wh_skus_dict[rg_val][it][sk_key] = {'mh': mh, 'op': op, 'key': sk_key, 'qty': 0, 'sizes': {}}
            wh_skus_dict[rg_val][it][sk_key]['qty'] += qty
            wh_skus_dict[rg_val][it][sk_key]['sizes'][sz] = wh_skus_dict[rg_val][it][sk_key]['sizes'].get(sz, 0) + qty

    brand_counts = {
        br: {
            'item_count': len(brand_items_set[br]),   # số Tên hàng (Report_item_name)
            'sku_count': len(brand_skus_set[br])       # số SKU = (MaHang, Operation)
        }
        for br in brand_items_set
    }

    warehouse_skus = {}
    for wh, it_map in wh_skus_dict.items():
        warehouse_skus[wh] = {}
        for it, mh_map in it_map.items():
            warehouse_skus[wh][it] = sorted(mh_map.values(), key=lambda x: x['qty'], reverse=True)

    ton_payload = {
        'cols': cols,
        'data': data,
        'sizes': sizes_payload,
        'item_attributes': item_attributes,
        'product_meta': product_meta,
        'brand_counts': brand_counts,
        'warehouse_skus': warehouse_skus,
        'store_product_sizes': {
            'cols': st_size_cols,
            'data': st_size_data
        }
    }

    print(f'   Hoàn thành Stage 2: Ton payload ready ({time.time()-t0:.1f}s)')
    return ton_payload, shared_dict


if __name__ == '__main__':
    ton_pl, s_dict = run()
    print(f"Sample test OK: Dict={len(s_dict['list'])} words, Rows={len(ton_pl['data'][0])}")

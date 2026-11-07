#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Aggregate_Sales.py — Stage 3: Tổng hợp dữ liệu Báo cáo Số Bán
- Đọc từ Cache/Sales_Cache.parquet
- Tổng hợp Overview (ov) gồm cả chiều Giao dịch (Nội dung: Bán / Đổi / Tặng / HĐ)
- Bảng phụ active_stores (số cửa hàng có Qty > 0 theo kỳ & khu vực)
- Chi tiết Top 2.000 mã hàng (prod) + metadata (meta)
- Top 5 mã hàng bán chạy Nguyên giá theo từng loại hàng (top_fullprice)
- Lát cắt thuộc tính bán (attr_sales: Color, Form, Style, Attribute)
- Phân tích chuyên biệt Giao dịch Đổi trả (return_analysis)
- Xuất dữ liệu cấu trúc Columnar + Dictionary Encoding
"""
import os
import sys
import time
import duckdb

sys.stdout.reconfigure(encoding='utf-8')

STAGE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(STAGE_DIR)
ROOT = os.path.dirname(BACKEND_DIR)

CACHE_FILE = os.path.join(ROOT, 'Cache', 'Sales_Cache.parquet')


def run(shared_dict=None):
    t0 = time.time()
    print('=' * 65)
    print('  [STAGE 3] AGGREGATE SỐ BÁN & GIAO DỊCH ĐỔI TRẢ')
    print('=' * 65)

    if not os.path.exists(CACHE_FILE):
        raise FileNotFoundError(f'Không tìm thấy {CACHE_FILE}. Cần chạy Refresh_Sales_Cache trước!')

    con = duckdb.connect(':memory:')
    con.execute(f"CREATE VIEW cache AS SELECT * FROM read_parquet('{CACHE_FILE}')")

    # 1. Xác định kỳ tham chiếu mới nhất
    ref_row = con.execute("""
        SELECT Year, Month
        FROM cache
        ORDER BY Year DESC, Month DESC
        LIMIT 1
    """).fetchone()

    ref_year, ref_month = int(ref_row[0]), int(ref_row[1])
    ref_label = f"T{ref_month}/{ref_year}"
    print(f'   Kỳ tham chiếu mới nhất: {ref_label}')

    # 2. Shared dictionary helper
    if shared_dict is None:
        shared_dict = {'list': [], 'map': {}}

    def get_dict_idx(s):
        s_val = '' if s is None else str(s).strip()
        if s_val not in shared_dict['map']:
            idx = len(shared_dict['list'])
            shared_dict['list'].append(s_val)
            shared_dict['map'][s_val] = idx
        return shared_dict['map'][s_val]

    # 3. Tính active_stores: [year][month][region] -> số CH có Qty > 0
    print('   Đang tính toán active_stores...')
    active_rows = con.execute("""
        SELECT
            CAST(Year AS INT) AS y,
            CAST(Month AS INT) AS m,
            Region AS rg,
            COUNT(DISTINCT Store_name) AS active_count
        FROM cache
        WHERE Qty_Ban > 0
          AND (LOWER(COALESCE(Group_Report, '')) NOT LIKE '%bao bì%' AND LOWER(COALESCE(Group_Report, '')) NOT LIKE '%đồng phục%')
        GROUP BY 1, 2, 3
    """).fetchall()

    active_stores = {}
    for y, m, rg, count in active_rows:
        y_str = str(y)
        m_str = str(m)
        if y_str not in active_stores:
            active_stores[y_str] = {}
        if m_str not in active_stores[y_str]:
            active_stores[y_str][m_str] = {}
        active_stores[y_str][m_str][rg] = int(count)

    # 4. Tổng hợp Overview (ov) — Bổ sung txn_type (Nội dung: Bán / Đổi / Tặng / HĐ)
    print('   Đang tổng hợp Overview (ov) kèm Giao dịch...')
    # Overview gọn: engine chỉ cần y/m/src/txn/price/st/rg/br/qty
    # (bỏ rk/pg/gr/item -> ít cột + ít tổ hợp hơn nhiều -> payload nhỏ hẳn)
    ov_sql = """
    SELECT
        CAST(Year AS INT) AS y,
        CAST(Month AS INT) AS m,
        CASE WHEN SalesSource = 'Contract' THEN 'HĐ' ELSE 'Lẻ' END AS src,
        COALESCE("Nội dung", 'Bán') AS txn_type,
        CASE WHEN SalesSource = 'Contract' THEN 'Hợp đồng'
             WHEN Status = 'Sale' THEN 'Sale'
             WHEN Status = 'Thanh lý' THEN 'Thanh lý'
             ELSE 'Nguyên giá' END AS price_type,
        Store_name AS st,
        Region AS rg,
        CASE WHEN Brand = 'Hiệu An Phước' AND Gender = 'Nữ' THEN 'Hiệu An Phước Ladies'
             WHEN Brand IN ('Hiệu An Phước', 'Hiệu Pierre Cardin', 'Hiệu An Phước Ladies', 'Hiệu Bonjour', 'Hiệu Anamai') THEN Brand
             ELSE 'Khác' END AS br,
        CAST(SUM(Qty_Ban) AS INT) AS qty
    FROM cache
    WHERE (LOWER(COALESCE(Group_Report, '')) NOT LIKE '%bao bì%' AND LOWER(COALESCE(Group_Report, '')) NOT LIKE '%đồng phục%')
    GROUP BY 1, 2, 3, 4, 5, 6, 7, 8
    """

    ov_df = con.execute(ov_sql).fetchdf()
    print(f'   Tổng hợp xong Overview: {len(ov_df):,} dòng')

    ov_cols = ['y', 'm', 'src', 'txn_type', 'price_type', 'st', 'rg', 'br', 'qty']
    ov_data = [[] for _ in ov_cols]

    for r in ov_df.itertuples(index=False):
        ov_data[0].append(int(r.y))
        ov_data[1].append(int(r.m))
        ov_data[2].append(get_dict_idx(r.src))
        ov_data[3].append(get_dict_idx(r.txn_type))
        ov_data[4].append(get_dict_idx(r.price_type))
        ov_data[5].append(get_dict_idx(r.st))
        ov_data[6].append(get_dict_idx(r.rg))
        ov_data[7].append(get_dict_idx(r.br))
        ov_data[8].append(int(r.qty))

    # 5. Top 5 mã hàng bán chạy Nguyên giá theo từng loại hàng trong tháng (top_fullprice)
    print('   Đang tính Top 5 mã hàng bán chạy Nguyên giá theo từng loại hàng...')
    top_fp_sql = f"""
    WITH ranked AS (
        SELECT
            COALESCE(Report_item_name, '') AS item,
            COALESCE(Group_Report, '') AS gr,
            MaHang,
            COALESCE(Form, '') AS form,
            COALESCE(Style, '') AS style,
            COALESCE(Color_group, '') AS cg,
            COALESCE(Price, 0) AS price,
            CAST(SUM(Qty_Ban) AS INT) AS qty,
            ROW_NUMBER() OVER (PARTITION BY COALESCE(Report_item_name, '') ORDER BY SUM(Qty_Ban) DESC) as rank
        FROM cache
        WHERE Year = {ref_year} AND Month = {ref_month}
          AND SalesSource = 'Retail'
          AND Status = 'Nguyên giá'
          AND COALESCE("Nội dung", 'Bán') = 'Bán'
          AND Region != 'Event'
          AND (LOWER(COALESCE(Group_Report, '')) NOT LIKE '%bao bì%' AND LOWER(COALESCE(Group_Report, '')) NOT LIKE '%đồng phục%')
        GROUP BY COALESCE(Report_item_name, ''), COALESCE(Group_Report, ''), MaHang, COALESCE(Form, ''), COALESCE(Style, ''), COALESCE(Color_group, ''), COALESCE(Price, 0)
    )
    SELECT item, gr, MaHang, form, style, cg, price, qty
    FROM ranked
    WHERE rank <= 5
    ORDER BY gr, item, qty DESC
    """
    top_fp_df = con.execute(top_fp_sql).fetchdf()
    top_fullprice = {}
    for r in top_fp_df.itertuples(index=False):
        it = r.item
        if it not in top_fullprice:
            top_fullprice[it] = []
        top_fullprice[it].append({
            'mahang': r.MaHang,
            'form': r.form,
            'style': r.style,
            'cg': r.cg,
            'price': float(r.price or 0),
            'qty': int(r.qty)
        })
    # 5b. Xếp hạng Cửa hàng bán chạy Nguyên giá (Top & Bottom 20, loại trừ Event)
    #     - Gom theo Store_name (KHÔNG kèm Region) để mỗi cửa hàng chỉ xuất hiện đúng 1 lần
    #     - Khu vực hiển thị = khu vực đóng góp nhiều Qty nhất của cửa hàng đó (arg_max)
    #     - Chỉ tính giao dịch "Bán" (bỏ Đổi/Tặng), hàng Nguyên giá, bỏ Event
    print('   Đang xếp hạng Cửa hàng bán Nguyên giá (gom theo CH, loại trừ Event)...')
    prev_m = ref_month - 1 if ref_month > 1 else 12
    prev_y = ref_year if ref_month > 1 else ref_year - 1
    top_stores_fp_sql = f"""
    WITH by_store_region AS (
        SELECT
            Store_name AS st,
            Region AS rg,
            CAST(SUM(CASE WHEN Year = {ref_year} AND Month = {ref_month} THEN Qty_Ban ELSE 0 END) AS INT) AS cur_m_qty,
            CAST(SUM(CASE WHEN Year = {prev_y} AND Month = {prev_m} THEN Qty_Ban ELSE 0 END) AS INT) AS prev_m_qty,
            CAST(SUM(CASE WHEN Year = {ref_year - 1} AND Month = {ref_month} THEN Qty_Ban ELSE 0 END) AS INT) AS yoy_qty,
            CAST(SUM(CASE WHEN Year = {ref_year} THEN Qty_Ban ELSE 0 END) AS INT) AS total_fp
        FROM cache
        WHERE SalesSource = 'Retail'
          AND Status = 'Nguyên giá'
          AND COALESCE("Nội dung", 'Bán') = 'Bán'
          AND Region != 'Event'
          AND (LOWER(COALESCE(Group_Report, '')) NOT LIKE '%bao bì%' AND LOWER(COALESCE(Group_Report, '')) NOT LIKE '%đồng phục%')
        GROUP BY 1, 2
    )
    SELECT
        st,
        arg_max(rg, total_fp) AS rg,
        CAST(SUM(cur_m_qty) AS INT) AS cur_m_qty,
        CAST(SUM(prev_m_qty) AS INT) AS prev_m_qty,
        CAST(SUM(yoy_qty) AS INT) AS yoy_qty,
        CAST(SUM(total_fp) AS INT) AS total_fp
    FROM by_store_region
    GROUP BY st
    ORDER BY total_fp DESC
    """
    top_stores_fp_df = con.execute(top_stores_fp_sql).fetchdf()
    top_stores_fullprice = []
    for r in top_stores_fp_df.itertuples(index=False):
        mom = round((r.cur_m_qty - r.prev_m_qty) / r.prev_m_qty * 100, 1) if r.prev_m_qty > 0 else None
        yoy = round((r.cur_m_qty - r.yoy_qty) / r.yoy_qty * 100, 1) if r.yoy_qty > 0 else None
        top_stores_fullprice.append({
            'st': r.st,
            'rg': r.rg,
            'qty': int(r.total_fp),
            'cur': int(r.cur_m_qty),   # Qty tháng hiện tại — để loại CH đóng cửa (§13.0b)
            'mom': mom,
            'yoy': yoy
        })

    # 5c. Top 5 Cửa hàng theo từng Khu vực của từng Brand (Nguyên giá, loại trừ Event)
    print('   Đang tính Top 5 Cửa hàng theo từng Khu vực của từng Brand (Nguyên giá, loại trừ Event)...')
    top_st_rg_br_sql = f"""
    WITH ranked AS (
        SELECT
            CASE WHEN Brand = 'Hiệu An Phước' AND Gender = 'Nữ' THEN 'Hiệu An Phước Ladies'
                 WHEN Brand IN ('Hiệu An Phước', 'Hiệu Pierre Cardin', 'Hiệu An Phước Ladies', 'Hiệu Bonjour', 'Hiệu Anamai') THEN Brand
                 ELSE 'Khác' END AS br,
            Region AS rg,
            Store_name AS st,
            CAST(SUM(Qty_Ban) AS INT) AS qty,
            ROW_NUMBER() OVER (PARTITION BY (
                CASE WHEN Brand = 'Hiệu An Phước' AND Gender = 'Nữ' THEN 'Hiệu An Phước Ladies'
                     WHEN Brand IN ('Hiệu An Phước', 'Hiệu Pierre Cardin', 'Hiệu An Phước Ladies', 'Hiệu Bonjour', 'Hiệu Anamai') THEN Brand
                     ELSE 'Khác' END
            ), Region ORDER BY SUM(Qty_Ban) DESC) as rank
        FROM cache
        WHERE Year = {ref_year}
          AND SalesSource = 'Retail'
          AND Status = 'Nguyên giá'
          AND COALESCE("Nội dung", 'Bán') = 'Bán'
          AND Region != 'Event'
          AND (LOWER(COALESCE(Group_Report, '')) NOT LIKE '%bao bì%' AND LOWER(COALESCE(Group_Report, '')) NOT LIKE '%đồng phục%')
        GROUP BY 1, 2, 3
    )
    SELECT br, rg, st, qty
    FROM ranked
    WHERE rank <= 5
    ORDER BY br, rg, qty DESC
    """
    top_st_rg_br_df = con.execute(top_st_rg_br_sql).fetchdf()
    top_stores_region_brand = {}
    for r in top_st_rg_br_df.itertuples(index=False):
        if r.br not in top_stores_region_brand:
            top_stores_region_brand[r.br] = {}
        if r.rg not in top_stores_region_brand[r.br]:
            top_stores_region_brand[r.br][r.rg] = []
        top_stores_region_brand[r.br][r.rg].append({
            'st': r.st,
            'qty': int(r.qty)
        })

    # 5d. Chỉ số chi tiết & Thứ hạng Cửa hàng trong Khu vực và Toàn Hệ thống (loại trừ Event)
    print('   Đang tính Thứ hạng & Chi tiết Giá của từng Cửa hàng...')
    st_ranks_sql = f"""
    WITH st_region AS (
        SELECT
            Store_name AS st,
            Region AS rg,
            CAST(SUM(CASE WHEN Status = 'Nguyên giá' AND COALESCE("Nội dung", 'Bán') = 'Bán' THEN Qty_Ban ELSE 0 END) AS INT) AS fp_qty,
            CAST(SUM(CASE WHEN Status = 'Sale' AND COALESCE("Nội dung", 'Bán') = 'Bán' THEN Qty_Ban ELSE 0 END) AS INT) AS sale_qty,
            CAST(SUM(CASE WHEN Status = 'Thanh lý' AND COALESCE("Nội dung", 'Bán') = 'Bán' THEN Qty_Ban ELSE 0 END) AS INT) AS tl_qty,
            CAST(SUM(CASE WHEN SalesSource = 'Contract' AND COALESCE("Nội dung", 'Bán') = 'Bán' THEN Qty_Ban ELSE 0 END) AS INT) AS hd_qty,
            CAST(SUM(CASE WHEN COALESCE("Nội dung", 'Bán') = 'Bán' THEN Qty_Ban ELSE 0 END) AS INT) AS total_qty,
            CAST(SUM(CASE WHEN "Nội dung" = 'Đổi' THEN ABS(Qty_Ban) ELSE 0 END) AS INT) AS ret_qty
        FROM cache
        WHERE Year = {ref_year}
          AND Region != 'Event'
          AND (LOWER(COALESCE(Group_Report, '')) NOT LIKE '%bao bì%' AND LOWER(COALESCE(Group_Report, '')) NOT LIKE '%đồng phục%')
        GROUP BY 1, 2
    ),
    st_totals AS (
        SELECT
            st,
            arg_max(rg, total_qty) AS rg,
            CAST(SUM(fp_qty) AS INT) AS fp_qty,
            CAST(SUM(sale_qty) AS INT) AS sale_qty,
            CAST(SUM(tl_qty) AS INT) AS tl_qty,
            CAST(SUM(hd_qty) AS INT) AS hd_qty,
            CAST(SUM(total_qty) AS INT) AS total_qty,
            CAST(SUM(ret_qty) AS INT) AS ret_qty
        FROM st_region
        GROUP BY st
    ),
    st_with_ranks AS (
        SELECT
            st, rg, fp_qty, sale_qty, tl_qty, hd_qty, total_qty, ret_qty,
            DENSE_RANK() OVER (PARTITION BY rg ORDER BY total_qty DESC) AS rank_rg,
            COUNT(*) OVER (PARTITION BY rg) AS total_stores_rg,
            DENSE_RANK() OVER (ORDER BY total_qty DESC) AS rank_sys,
            COUNT(*) OVER () AS total_stores_sys
        FROM st_totals
    )
    SELECT * FROM st_with_ranks
    """
    st_ranks_df = con.execute(st_ranks_sql).fetchdf()
    store_metrics = {}
    for r in st_ranks_df.itertuples(index=False):
        store_metrics[r.st] = {
            'rg': r.rg,
            'fp': int(r.fp_qty),
            'sale': int(r.sale_qty),
            'tl': int(r.tl_qty),
            'hd': int(r.hd_qty),
            'total': int(r.total_qty),
            'ret': int(r.ret_qty),
            'rank_rg': int(r.rank_rg),
            'total_rg': int(r.total_stores_rg),
            'rank_sys': int(r.rank_sys),
            'total_sys': int(r.total_stores_sys)
        }

    # 5d. Top 5 mã hàng bán chạy Nguyên giá cho từng Brand theo từng Tên hàng (toàn hệ thống & cấp cửa hàng)
    print('   Đang tính Top 5 mã bán chạy Nguyên giá theo Brand x Tên hàng...')
    top_fp_bi_sql = f"""
    WITH ranked AS (
        SELECT
            CASE WHEN Brand = 'Hiệu An Phước' AND Gender = 'Nữ' THEN 'Hiệu An Phước Ladies'
                 WHEN Brand IN ('Hiệu An Phước', 'Hiệu Pierre Cardin', 'Hiệu An Phước Ladies', 'Hiệu Bonjour', 'Hiệu Anamai') THEN Brand
                 ELSE 'Khác' END AS br,
            COALESCE(Report_item_name, '') AS item,
            MaHang,
            COALESCE(Form, '') AS form,
            COALESCE(Style, '') AS style,
            COALESCE(Color_group, '') AS cg,
            COALESCE(Price, 0) AS price,
            CAST(SUM(Qty_Ban) AS INT) AS qty,
            ROW_NUMBER() OVER (PARTITION BY (
                CASE WHEN Brand = 'Hiệu An Phước' AND Gender = 'Nữ' THEN 'Hiệu An Phước Ladies'
                     WHEN Brand IN ('Hiệu An Phước', 'Hiệu Pierre Cardin', 'Hiệu An Phước Ladies', 'Hiệu Bonjour', 'Hiệu Anamai') THEN Brand
                     ELSE 'Khác' END
            ), COALESCE(Report_item_name, '') ORDER BY SUM(Qty_Ban) DESC) as rank
        FROM cache
        WHERE Year = {ref_year}
          AND SalesSource = 'Retail'
          AND Status = 'Nguyên giá'
          AND COALESCE("Nội dung", 'Bán') = 'Bán'
          AND Region != 'Event'
          AND (LOWER(COALESCE(Group_Report, '')) NOT LIKE '%bao bì%' AND LOWER(COALESCE(Group_Report, '')) NOT LIKE '%đồng phục%')
        GROUP BY 1, 2, 3, 4, 5, 6, 7
    )
    SELECT br, item, MaHang, form, style, cg, price, qty
    FROM ranked
    WHERE rank <= 5
    ORDER BY br, item, qty DESC
    """
    top_fp_bi_df = con.execute(top_fp_bi_sql).fetchdf()

    # Bản theo TỪNG THÁNG (cho control "Kỳ xem" ở Sheet 2)
    top_fp_bi_m_sql = f"""
    WITH ranked AS (
        SELECT
            CAST(Month AS INT) AS m,
            CASE WHEN Brand = 'Hiệu An Phước' AND Gender = 'Nữ' THEN 'Hiệu An Phước Ladies'
                 WHEN Brand IN ('Hiệu An Phước', 'Hiệu Pierre Cardin', 'Hiệu An Phước Ladies', 'Hiệu Bonjour', 'Hiệu Anamai') THEN Brand
                 ELSE 'Khác' END AS br,
            COALESCE(Report_item_name, '') AS item,
            MaHang,
            COALESCE(Form, '') AS form,
            COALESCE(Style, '') AS style,
            COALESCE(Color_group, '') AS cg,
            COALESCE(Price, 0) AS price,
            CAST(SUM(Qty_Ban) AS INT) AS qty,
            ROW_NUMBER() OVER (PARTITION BY CAST(Month AS INT), (
                CASE WHEN Brand = 'Hiệu An Phước' AND Gender = 'Nữ' THEN 'Hiệu An Phước Ladies'
                     WHEN Brand IN ('Hiệu An Phước', 'Hiệu Pierre Cardin', 'Hiệu An Phước Ladies', 'Hiệu Bonjour', 'Hiệu Anamai') THEN Brand
                     ELSE 'Khác' END
            ), COALESCE(Report_item_name, '') ORDER BY SUM(Qty_Ban) DESC) as rank
        FROM cache
        WHERE Year = {ref_year}
          AND SalesSource = 'Retail'
          AND Status = 'Nguyên giá'
          AND COALESCE("Nội dung", 'Bán') = 'Bán'
          AND Region != 'Event'
          AND (LOWER(COALESCE(Group_Report, '')) NOT LIKE '%bao bì%' AND LOWER(COALESCE(Group_Report, '')) NOT LIKE '%đồng phục%')
        GROUP BY 1, 2, 3, 4, 5, 6, 7, 8
    )
    SELECT m, br, item, MaHang, form, style, cg, price, qty
    FROM ranked
    WHERE rank <= 5
    ORDER BY m, br, item, qty DESC
    """
    top_fp_bi_m_df = con.execute(top_fp_bi_m_sql).fetchdf()

    def _collect_bi(df, month_col):
        out = {}
        for r in df.itertuples(index=False):
            pk = str(int(getattr(r, month_col))) if month_col else 'ytd'
            out.setdefault(pk, {}).setdefault(r.br, {}).setdefault(r.item, []).append({
                'mahang': r.MaHang,
                'form': r.form,
                'style': r.style,
                'cg': r.cg,
                'price': float(r.price or 0),
                'qty': int(r.qty)
            })
        return out

    # top_fullprice_brand_item = { 'ytd': {br:{item:[...]}}, '1':{...}, ..., '{ref_month}':{...} }
    top_fullprice_brand_item = _collect_bi(top_fp_bi_df, None)
    top_fullprice_brand_item.update(_collect_bi(top_fp_bi_m_df, 'm'))

    # 5e. Top 5 mã hàng bán chạy Nguyên giá theo từng Cửa hàng x Brand x Tên hàng
    print('   Đang tính Top 5 mã bán chạy Nguyên giá theo Store x Brand x Tên hàng...')
    top_fp_sbi_sql = f"""
    WITH ranked AS (
        SELECT
            Store_name,
            CASE WHEN Brand = 'Hiệu An Phước' AND Gender = 'Nữ' THEN 'Hiệu An Phước Ladies'
                 WHEN Brand IN ('Hiệu An Phước', 'Hiệu Pierre Cardin', 'Hiệu An Phước Ladies', 'Hiệu Bonjour', 'Hiệu Anamai') THEN Brand
                 ELSE 'Khác' END AS br,
            COALESCE(Report_item_name, '') AS item,
            MaHang,
            COALESCE(Form, '') AS form,
            COALESCE(Style, '') AS style,
            COALESCE(Color_group, '') AS cg,
            COALESCE(Price, 0) AS price,
            CAST(SUM(Qty_Ban) AS INT) AS qty,
            ROW_NUMBER() OVER (PARTITION BY Store_name, (
                CASE WHEN Brand = 'Hiệu An Phước' AND Gender = 'Nữ' THEN 'Hiệu An Phước Ladies'
                     WHEN Brand IN ('Hiệu An Phước', 'Hiệu Pierre Cardin', 'Hiệu An Phước Ladies', 'Hiệu Bonjour', 'Hiệu Anamai') THEN Brand
                     ELSE 'Khác' END
            ), COALESCE(Report_item_name, '') ORDER BY SUM(Qty_Ban) DESC) as rank
        FROM cache
        WHERE Year = {ref_year}
          AND SalesSource = 'Retail'
          AND Status = 'Nguyên giá'
          AND COALESCE("Nội dung", 'Bán') = 'Bán'
          AND (LOWER(COALESCE(Group_Report, '')) NOT LIKE '%bao bì%' AND LOWER(COALESCE(Group_Report, '')) NOT LIKE '%đồng phục%')
        GROUP BY 1, 2, 3, 4, 5, 6, 7, 8
    )
    SELECT Store_name, br, item, MaHang, form, style, cg, price, qty
    FROM ranked
    WHERE rank <= 5
    ORDER BY Store_name, br, item, qty DESC
    """
    top_fp_sbi_df = con.execute(top_fp_sbi_sql).fetchdf()
    top_fullprice_store_brand_item = {}
    for r in top_fp_sbi_df.itertuples(index=False):
        st = r.Store_name
        b = r.br
        it = r.item
        if st not in top_fullprice_store_brand_item:
            top_fullprice_store_brand_item[st] = {}
        if b not in top_fullprice_store_brand_item[st]:
            top_fullprice_store_brand_item[st][b] = {}
        if it not in top_fullprice_store_brand_item[st][b]:
            top_fullprice_store_brand_item[st][b][it] = []
        top_fullprice_store_brand_item[st][b][it].append({
            'mahang': r.MaHang,
            'form': r.form,
            'style': r.style,
            'cg': r.cg,
            'price': float(r.price or 0),
            'qty': int(r.qty)
        })

    # 6. Lát cắt Thuộc tính Bán (attr_sales: CatGroup, Brand, Form, Style, Color qua các năm 2024-2026)
    print('   Đang tổng hợp Lát cắt Thuộc tính Bán đa năm (attr_sales)...')
    attr_sql = f"""
    SELECT
        CAST(Year AS INT) AS y,
        CAST(Month AS INT) AS m,
        Region AS rg,
        CASE WHEN Brand = 'Hiệu An Phước' AND Gender = 'Nữ' THEN 'Hiệu An Phước Ladies'
             WHEN Brand IN ('Hiệu An Phước', 'Hiệu Pierre Cardin', 'Hiệu An Phước Ladies', 'Hiệu Bonjour', 'Hiệu Anamai') THEN Brand
             ELSE 'Khác' END AS br,
        COALESCE(Group_Report, '') AS gr,
        COALESCE(Report_item_name, '') AS item,
        COALESCE(Color_group, '') AS cg,
        COALESCE(Form, '') AS form,
        COALESCE(Style, '') AS style,
        CASE
            WHEN LOWER(COALESCE(Group_Report, '')) LIKE '%golf%' OR LOWER(COALESCE(Report_item_name, '')) LIKE '%golf%' THEN 'Nhóm Golf'
            WHEN LOWER(COALESCE(Group_Report, '')) LIKE '%da%' OR LOWER(COALESCE(Product_group, '')) LIKE '%da%' THEN 'Nhóm Đồ da'
            WHEN LOWER(COALESCE(Group_Report, '')) LIKE '%phụ kiện%' OR LOWER(COALESCE(Group_Report, '')) LIKE '%cà vạt%' OR LOWER(COALESCE(Group_Report, '')) LIKE '%khăn%' OR LOWER(COALESCE(Group_Report, '')) LIKE '%nón%' OR LOWER(COALESCE(Group_Report, '')) LIKE '%tất%' OR LOWER(COALESCE(Group_Report, '')) LIKE '%vớ%' THEN 'Nhóm Phụ kiện khác'
            WHEN Brand IN ('Hiệu Anamai', 'Hiệu Bonjour') OR LOWER(COALESCE(Group_Report, '')) LIKE '%đồ lót%' OR LOWER(COALESCE(Group_Report, '')) LIKE '%nội y%' THEN 'Nhóm Anamai / Bonjour'
            WHEN COALESCE(Group_Report, '') IN ('Chemise', 'Áo Thun', 'Quần Tây', 'Quần Kaki', 'Quần Short', 'Áo Khoác', 'Suit') THEN 'Nhóm chủ đạo'
            ELSE 'Nhóm Quần áo khác'
        END AS cat_group,
        CAST(SUM(Qty_Ban) AS INT) AS qty
    FROM cache
    WHERE SalesSource = 'Retail'
      AND "Nội dung" = 'Bán'
      AND (LOWER(COALESCE(Group_Report, '')) NOT LIKE '%bao bì%' AND LOWER(COALESCE(Group_Report, '')) NOT LIKE '%đồng phục%')
    GROUP BY 1, 2, 3, 4, 5, 6, 7, 8, 9, 10
    """
    attr_df = con.execute(attr_sql).fetchdf()
    # 'm' thêm ở CUỐI để giữ nguyên index 0..9 mà engine đang đọc
    attr_cols = ['y', 'rg', 'br', 'gr', 'item', 'cg', 'form', 'style', 'cat_group', 'qty', 'm']
    attr_data = [[] for _ in attr_cols]
    for r in attr_df.itertuples(index=False):
        attr_data[0].append(int(r.y))
        attr_data[1].append(get_dict_idx(r.rg))
        attr_data[2].append(get_dict_idx(r.br))
        attr_data[3].append(get_dict_idx(r.gr))
        attr_data[4].append(get_dict_idx(r.item))
        attr_data[5].append(get_dict_idx(r.cg))
        attr_data[6].append(get_dict_idx(r.form))
        attr_data[7].append(get_dict_idx(r.style))
        attr_data[8].append(get_dict_idx(r.cat_group))
        attr_data[9].append(int(r.qty))
        attr_data[10].append(int(r.m))
    print(f'   Tổng hợp xong Lát cắt Thuộc tính đa năm: {len(attr_df):,} dòng')

    # 7. Phân tích Chuyên biệt Giao dịch Đổi trả (return_analysis)
    print('   Đang phân tích Giao dịch Đổi trả...')
    # 7a. Tỷ lệ đổi trả theo Brand
    ret_brand_sql = f"""
    SELECT
        CASE WHEN Brand = 'Hiệu An Phước' AND Gender = 'Nữ' THEN 'Hiệu An Phước Ladies'
             WHEN Brand IN ('Hiệu An Phước', 'Hiệu Pierre Cardin', 'Hiệu An Phước Ladies', 'Hiệu Bonjour', 'Hiệu Anamai') THEN Brand
             ELSE 'Khác' END AS br,
        CAST(SUM(CASE WHEN "Nội dung" = 'Bán' THEN Qty_Ban ELSE 0 END) AS INT) AS ban_qty,
        CAST(SUM(CASE WHEN "Nội dung" = 'Đổi' THEN ABS(Qty_Ban) ELSE 0 END) AS INT) AS doi_qty
    FROM cache
    WHERE Year = {ref_year}
      AND (LOWER(COALESCE(Group_Report, '')) NOT LIKE '%bao bì%' AND LOWER(COALESCE(Group_Report, '')) NOT LIKE '%đồng phục%')
    GROUP BY 1
    """
    ret_brand_df = con.execute(ret_brand_sql).fetchdf()
    ret_brand = {}
    for r in ret_brand_df.itertuples(index=False):
        rate = (r.doi_qty / r.ban_qty * 100) if r.ban_qty > 0 else 0
        ret_brand[r.br] = {'ban': r.ban_qty, 'doi': r.doi_qty, 'rate': round(rate, 2)}

    # 7b. Tỷ lệ đổi trả theo Group_Report
    ret_gr_sql = f"""
    SELECT
        COALESCE(Group_Report, '') AS gr,
        CAST(SUM(CASE WHEN "Nội dung" = 'Bán' THEN Qty_Ban ELSE 0 END) AS INT) AS ban_qty,
        CAST(SUM(CASE WHEN "Nội dung" = 'Đổi' THEN ABS(Qty_Ban) ELSE 0 END) AS INT) AS doi_qty
    FROM cache
    WHERE Year = {ref_year}
      AND (LOWER(COALESCE(Group_Report, '')) NOT LIKE '%bao bì%' AND LOWER(COALESCE(Group_Report, '')) NOT LIKE '%đồng phục%')
    GROUP BY 1
    HAVING SUM(CASE WHEN "Nội dung" = 'Bán' THEN Qty_Ban ELSE 0 END) > 500
    ORDER BY (SUM(CASE WHEN "Nội dung" = 'Đổi' THEN ABS(Qty_Ban) ELSE 0 END) * 1.0 / NULLIF(SUM(CASE WHEN "Nội dung" = 'Bán' THEN Qty_Ban ELSE 0 END), 0)) DESC
    LIMIT 15
    """
    ret_gr_df = con.execute(ret_gr_sql).fetchdf()
    ret_gr = []
    for r in ret_gr_df.itertuples(index=False):
        rate = (r.doi_qty / r.ban_qty * 100) if r.ban_qty > 0 else 0
        ret_gr.append({'gr': r.gr, 'ban': r.ban_qty, 'doi': r.doi_qty, 'rate': round(rate, 2)})

    # 7c. Top 20 Cửa hàng có Tỷ lệ đổi trả cao nhất (xét CH có bán > 1000 sp)
    ret_st_sql = f"""
    SELECT
        Store_name, Region,
        CAST(SUM(CASE WHEN "Nội dung" = 'Bán' THEN Qty_Ban ELSE 0 END) AS INT) AS ban_qty,
        CAST(SUM(CASE WHEN "Nội dung" = 'Đổi' THEN ABS(Qty_Ban) ELSE 0 END) AS INT) AS doi_qty
    FROM cache
    WHERE Year = {ref_year}
      AND (LOWER(COALESCE(Group_Report, '')) NOT LIKE '%bao bì%' AND LOWER(COALESCE(Group_Report, '')) NOT LIKE '%đồng phục%')
    GROUP BY 1, 2
    HAVING SUM(CASE WHEN "Nội dung" = 'Bán' THEN Qty_Ban ELSE 0 END) >= 1000
    ORDER BY (SUM(CASE WHEN "Nội dung" = 'Đổi' THEN ABS(Qty_Ban) ELSE 0 END) * 1.0 / SUM(CASE WHEN "Nội dung" = 'Bán' THEN Qty_Ban ELSE 0 END)) DESC
    LIMIT 20
    """
    ret_st_df = con.execute(ret_st_sql).fetchdf()
    ret_stores = []
    for r in ret_st_df.itertuples(index=False):
        rate = (r.doi_qty / r.ban_qty * 100) if r.ban_qty > 0 else 0
        ret_stores.append({'st': r.Store_name, 'rg': r.Region, 'ban': r.ban_qty, 'doi': r.doi_qty, 'rate': round(rate, 2)})

    # 7d. Top 20 Mã hàng bị Đổi trả nhiều nhất
    ret_mh_sql = f"""
    SELECT
        MaHang,
        COALESCE(Report_item_name, '') AS item,
        COALESCE(Color_group, '') AS cg,
        COALESCE(Form, '') AS form,
        CAST(SUM(CASE WHEN "Nội dung" = 'Bán' THEN Qty_Ban ELSE 0 END) AS INT) AS ban_qty,
        CAST(SUM(CASE WHEN "Nội dung" = 'Đổi' THEN ABS(Qty_Ban) ELSE 0 END) AS INT) AS doi_qty
    FROM cache
    WHERE Year = {ref_year}
      AND (LOWER(COALESCE(Group_Report, '')) NOT LIKE '%bao bì%' AND LOWER(COALESCE(Group_Report, '')) NOT LIKE '%đồng phục%')
    GROUP BY 1, 2, 3, 4
    ORDER BY doi_qty DESC
    LIMIT 20
    """
    ret_mh_df = con.execute(ret_mh_sql).fetchdf()
    ret_items = []
    for r in ret_mh_df.itertuples(index=False):
        rate = (r.doi_qty / r.ban_qty * 100) if r.ban_qty > 0 else 0
        ret_items.append({'mahang': r.MaHang, 'item': r.item, 'cg': r.cg, 'form': r.form, 'ban': r.ban_qty, 'doi': r.doi_qty, 'rate': round(rate, 2)})

    return_analysis = {
        'brand': ret_brand,
        'group_report': ret_gr,
        'top_stores': ret_stores,
        'top_items': ret_items
    }

    # 8. Top 2000 Mã hàng & Metadata
    ban_payload = {
        'ref': {
            'year': ref_year,
            'month': ref_month,
            'label': ref_label
        },
        'active_stores': active_stores,
        'ov': {
            'cols': ov_cols,
            'data': ov_data
        },
        # Sheet 2 & 3 nay tinh lai truc tiep tu 'ov' theo "Ky xem" -> bo cac ban pre-agg
        # (top_stores_fullprice / top_stores_region_brand / store_metrics)
        'top_fullprice_brand_item': top_fullprice_brand_item,
        'top_fullprice_store_brand_item': top_fullprice_store_brand_item,
        'attr_sales': {
            'cols': attr_cols,
            'data': attr_data
        },
        'return_analysis': return_analysis
    }

    print(f'   Hoàn thành Stage 3: Ban payload ready ({time.time()-t0:.1f}s)')
    return ban_payload, shared_dict, ref_year, ref_month


if __name__ == '__main__':
    payload, s_dict, y, m = run()
    print(f"Test OK: Year={y}, Month={m}, Dict={len(s_dict['list'])} words")

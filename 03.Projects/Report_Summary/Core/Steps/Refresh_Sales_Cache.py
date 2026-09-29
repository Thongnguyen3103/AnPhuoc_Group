#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Refresh_Sales_Cache.py — Stage 1: Làm mới Sales_Cache.parquet từ dữ liệu gốc
Đọc System_sales + Contract_sales (3 năm gần nhất) + F_DataTracking + A_Region.

TỰ PHÁT HIỆN: khi chạy KHÔNG có --force-cache, so kỳ mới nhất (Year*100+Month)
và tổng số dòng của nguồn với cache. Nếu nguồn có kỳ mới hơn HOẶC số dòng khác
(thêm/sửa file bán) -> tự động nạp lại cache. Ngược lại -> bỏ qua.
--force-cache = ép nạp lại bất kể.
"""
import os
import sys
import time
import duckdb

sys.stdout.reconfigure(encoding='utf-8')

import Get_Paths

STAGE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(STAGE_DIR)
ROOT = os.path.dirname(BACKEND_DIR)

SYSTEM_SALES_GLOB = os.path.join(Get_Paths.ban_le, '*', '*.parquet')
CONTRACT_SALES_GLOB = os.path.join(Get_Paths.ban_hop_dong, '*', '*.parquet')
TRACKING_FILE = Get_Paths.data_tracking
REGION_FILE = Get_Paths.region

OUT_FILE = os.path.join(ROOT, 'Cache', 'Sales_Cache.parquet')
YEARS_BACK = 3


def run(force=False):
    t0 = time.time()
    print('=' * 65)
    print('  [STAGE 1] REFRESH CACHE (Sales_Cache.parquet)')
    print('=' * 65)

    con = duckdb.connect(':memory:')

    # --- Tự phát hiện dữ liệu bán mới: nếu nguồn có kỳ mới hơn / số dòng khác cache -> nạp lại ---
    if not force and os.path.exists(OUT_FILE):
        def _q(sql, default=None):
            try:
                v = con.execute(sql).fetchone()[0]
                return v if v is not None else default
            except Exception:
                return default

        src_ym = max(
            _q(f"SELECT MAX(Year*100 + Month) FROM '{SYSTEM_SALES_GLOB}'", 0),
            _q(f"SELECT MAX(Year*100 + Month) FROM '{CONTRACT_SALES_GLOB}'", 0),
        )
        cch_ym = _q(f"SELECT MAX(Year*100 + Month) FROM '{OUT_FILE}'", 0)

        src_year = src_ym // 100
        min_y = src_year - (YEARS_BACK - 1)
        src_rows = (_q(f"SELECT COUNT(*) FROM '{SYSTEM_SALES_GLOB}' WHERE Year >= {min_y}", 0)
                    + _q(f"SELECT COUNT(*) FROM '{CONTRACT_SALES_GLOB}' WHERE Year >= {min_y}", 0))
        cch_rows = _q(f"SELECT COUNT(*) FROM '{OUT_FILE}'", 0)

        up_to_date = (src_ym <= cch_ym) and (src_rows == cch_rows)
        if up_to_date:
            mb = os.path.getsize(OUT_FILE) / (1024 * 1024)
            print(f'   Cache đã mới nhất (kỳ {cch_ym // 100}/{cch_ym % 100:02d}, {cch_rows:,} dòng) — bỏ qua refresh.')
            print('   (--force-cache để ép tạo lại toàn bộ)')
            con.close()
            return OUT_FILE
        print(f'   Phát hiện dữ liệu bán thay đổi → tự động nạp lại cache:')
        print(f'      kỳ mới nhất: nguồn {src_ym // 100}/{src_ym % 100:02d}  vs  cache {cch_ym // 100}/{cch_ym % 100:02d}')
        print(f'      số dòng    : nguồn {src_rows:,}  vs  cache {cch_rows:,}')

    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)

    ref_year = con.execute(f"SELECT MAX(Year) FROM '{SYSTEM_SALES_GLOB}'").fetchone()[0]
    min_year = ref_year - (YEARS_BACK - 1)
    print(f'   Năm tham chiếu: {ref_year} -> Lấy dữ liệu từ {min_year} đến {ref_year}')

    sql = f"""
    COPY (
        WITH sales AS (
            SELECT
                Store_name, Region, Warehouse, CAST(Month AS BIGINT) AS Month, Quarter,
                CAST(Year AS BIGINT) AS Year, Brand, Report_item_name, MaHang, Operation, Size,
                CAST(Qty_Ban AS BIGINT) AS Qty_Ban, "Nội dung", Status, Product_type, Gender,
                Product_group, Group_Report, "Sales _Type" AS Sales_Type, 'Retail' AS SalesSource
            FROM '{SYSTEM_SALES_GLOB}'
            WHERE Year >= {min_year}

            UNION ALL

            SELECT
                Store_name, Region, Warehouse, CAST(Month AS BIGINT) AS Month, Quarter,
                CAST(Year AS BIGINT) AS Year, Brand, Report_item_name, MaHang, Operation, Size,
                CAST(Qty_Ban AS BIGINT) AS Qty_Ban, NULL AS "Nội dung", Status, Product_type, Gender,
                Product_group, Group_Report, "Sales _Type" AS Sales_Type, 'Contract' AS SalesSource
            FROM '{CONTRACT_SALES_GLOB}'
            WHERE Year >= {min_year}
        )
        SELECT
            s.Store_name, s.Region, s.Warehouse, s.Month, s.Quarter, s.Year, s.Brand,
            s.Report_item_name, s.MaHang, s.Operation, s.Size, s.Qty_Ban, s."Nội dung",
            s.Status, s.Product_type, s.Gender, s.Product_group, s.Group_Report, s.Sales_Type,
            s.SalesSource,
            r.Store_rank, r.FLD,
            t.Combined_PK, t.Color_code, t.Composition, t.Color_tone, t.Color_group, t.Form,
            t.Style, t.Attribute, t.Description, t.Price, t.Dist_plan,
            CAST(t.Production_month AS DOUBLE) AS Production_month,
            CAST(t.Production_year AS DOUBLE) AS Production_year, t.Sub_Brand, t.System_item_name
        FROM sales s
        LEFT JOIN '{TRACKING_FILE}' t ON s.MaHang = t.item_code AND s.Operation = t.Operation
        LEFT JOIN (
            SELECT 
                Store_name,
                MAX(Store_rank) AS Store_rank,
                MAX(FLD) AS FLD
            FROM '{REGION_FILE}'
            GROUP BY Store_name
        ) r ON s.Store_name = r.Store_name
    ) TO '{OUT_FILE}' (FORMAT PARQUET)
    """

    print('   Đang trích xuất và lưu Sales_Cache.parquet...')
    con.execute(sql)
    n = con.execute(f"SELECT COUNT(*) FROM '{OUT_FILE}'").fetchone()[0]
    mb = os.path.getsize(OUT_FILE) / (1024 * 1024)
    print(f'   Hoàn thành: {n:,} dòng ({mb:.1f} MB, {time.time()-t0:.1f}s)')
    return OUT_FILE


if __name__ == '__main__':
    force_run = '--force' in sys.argv
    run(force=force_run)

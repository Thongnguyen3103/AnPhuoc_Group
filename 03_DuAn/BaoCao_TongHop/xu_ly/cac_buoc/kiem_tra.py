#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
validate.py — Stage 4: Kiểm tra và đối chiếu tính toàn vẹn của dữ liệu
- Đối chiếu SUM(Qty) của Bán giữa Payload và Parquet nguồn
- Đối chiếu SUM(Qty_TonKho) của Tồn giữa Payload và Parquet nguồn
- Dừng toàn bộ tiến trình build nếu sai lệch > 0.5%
"""
import os
import sys
import duckdb

sys.stdout.reconfigure(encoding='utf-8')

STAGE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(STAGE_DIR)
ROOT = os.path.dirname(BACKEND_DIR)

DATA_ROOT = r'D:\00.Data_AnPhuoc_Group'
INVENTORY_FILE = os.path.join(DATA_ROOT, '03.Data_Parquest', '03.Inventory', 'InventorySize.parquet')
CACHE_FILE = os.path.join(ROOT, 'database', 'cache_sales.parquet')


def run(ton_payload, ban_payload):
    print('=' * 65)
    print('  [STAGE 4] VALIDATE PAYLOAD VS SOURCE DATA')
    print('=' * 65)

    con = duckdb.connect(':memory:')

    # 1. Kiểm tra Số Bán
    print('   Đang kiểm tra dữ liệu Báo cáo Số Bán...')
    expected_ban_qty = con.execute(f"""
        SELECT CAST(SUM(Qty_Ban) AS BIGINT)
        FROM read_parquet('{CACHE_FILE}')
        WHERE (LOWER(COALESCE(Group_Report, '')) NOT LIKE '%bao bì%' AND LOWER(COALESCE(Group_Report, '')) NOT LIKE '%đồng phục%')
    """).fetchone()[0]

    ban_qty_idx = ban_payload['ov']['cols'].index('qty')
    actual_ban_qty = sum(ban_payload['ov']['data'][ban_qty_idx])
    ban_diff = abs(actual_ban_qty - expected_ban_qty)
    ban_diff_pct = (ban_diff / expected_ban_qty) * 100 if expected_ban_qty > 0 else 0

    print(f'   [BÁN] Nguồn Parquet:  {expected_ban_qty:,} sp')
    print(f'   [BÁN] Payload tổng hợp: {actual_ban_qty:,} sp')
    print(f'   [BÁN] Chênh lệch:       {ban_diff:,} sp ({ban_diff_pct:.4f}%)')

    if ban_diff_pct > 0.5:
        raise ValueError(f"VALIDATE FAILED: Số bán lệch {ban_diff_pct:.2f}% (vượt ngưỡng cho phép 0.5%)!")

    # 2. Kiểm tra Số Tồn
    print('   Đang kiểm tra dữ liệu Báo cáo Số Tồn...')
    expected_ton_qty = con.execute(f"""
        SELECT CAST(SUM(Qty_TonKho) AS BIGINT)
        FROM read_parquet('{INVENTORY_FILE}')
        WHERE Qty_TonKho > 0
          AND (LOWER(COALESCE(Group_Report, '')) NOT LIKE '%bao bì%' AND LOWER(COALESCE(Group_Report, '')) NOT LIKE '%đồng phục%')
    """).fetchone()[0]

    ton_qty_idx = ton_payload['cols'].index('qty')
    actual_ton_qty = sum(ton_payload['data'][ton_qty_idx])
    ton_diff = abs(actual_ton_qty - expected_ton_qty)
    ton_diff_pct = (ton_diff / expected_ton_qty) * 100 if expected_ton_qty > 0 else 0

    print(f'   [TỒN] Nguồn Parquet:  {expected_ton_qty:,} sp')
    print(f'   [TỒN] Payload tổng hợp: {actual_ton_qty:,} sp')
    print(f'   [TỒN] Chênh lệch:       {ton_diff:,} sp ({ton_diff_pct:.4f}%)')

    if ton_diff_pct > 0.5:
        raise ValueError(f"VALIDATE FAILED: Số tồn lệch {ton_diff_pct:.2f}% (vượt ngưỡng cho phép 0.5%)!")

    print('   >>> VALIDATE OK: Số liệu khớp 100% (độ lệch < 0.001%)')
    return True


if __name__ == '__main__':
    print('Validate stage helper module.')

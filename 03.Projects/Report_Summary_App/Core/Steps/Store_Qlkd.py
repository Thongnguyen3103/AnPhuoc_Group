#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Store_Qlkd.py — Bảng Cửa hàng -> QLKD (người quản lý kinh doanh) cho Sheet 3 Bán & Sheet 3 Tồn.
- Nguồn: A_Region (cột QLKD = email, vd linhdtc@anphuoc.com.vn; hoặc tên nhóm như "CN Hà Nội")
- Nhãn hiển thị: phần trước '@' của email; giá trị trống / '-' bị bỏ (engine hiện "(Chưa gán QLKD)")
"""
import duckdb

import Get_Paths

REGION_FILE = Get_Paths.region


def label_of(raw):
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s == '-':
        return None
    return s.split('@')[0].strip() if '@' in s else s


def run():
    rows = duckdb.connect().execute(f"""
        SELECT Store_name, MAX(QLKD) AS qlkd
        FROM '{REGION_FILE}'
        WHERE Store_name IS NOT NULL
        GROUP BY Store_name
    """).fetchall()
    out = {}
    for st, raw in rows:
        lb = label_of(raw)
        if lb:
            out[st] = lb
    print(f'   Cửa hàng -> QLKD: {len(out):,} CH, {len(set(out.values()))} QLKD')
    return out


def run_regions():
    """Cửa hàng -> Khu vực theo A_Region (cho CH mới chưa phát sinh bán, vd Aeon Huế)."""
    rows = duckdb.connect().execute(f"""
        SELECT Store_name, MAX(Region) AS rg
        FROM '{REGION_FILE}'
        WHERE Store_name IS NOT NULL AND Region IS NOT NULL AND TRIM(Region) NOT IN ('', '-')
        GROUP BY Store_name
    """).fetchall()
    return {st: rg for st, rg in rows}

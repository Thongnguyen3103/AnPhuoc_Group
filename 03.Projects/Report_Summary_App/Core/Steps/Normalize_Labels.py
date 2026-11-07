#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Normalize_Labels.py — Chuẩn hoá nhãn thuộc tính trong F_DataTracking
F_DataTracking nhập tay nên cùng 1 nhãn có nhiều cách viết hoa/thường
(VD: 'Cổ Bo' / 'Cổ bo', 'Bông/Họa tiết' / 'Bông/Họa Tiết', 'Sọc' / 'SỌc')
-> báo cáo tách thành nhiều dòng trùng. Gom về cách viết phổ biến nhất
(nhiều mã hàng dùng nhất) cho mỗi nhãn (so khớp LOWER + TRIM).
"""

NORMALIZED_COLS = ('Form', 'Style', 'Color_group', 'Color_tone', 'Attribute')


def tracking_sql(tracking_file):
    """Trả về câu SELECT (dùng làm subquery) thay cho read_parquet(tracking_file),
    giữ nguyên mọi cột nhưng các cột NORMALIZED_COLS đã gom cách viết."""
    maps = []
    joins = []
    replaces = []
    for i, col in enumerate(NORMALIZED_COLS):
        maps.append(f"""
        m{i} AS (
            SELECT k, v AS canon FROM (
                SELECT k, v, ROW_NUMBER() OVER (PARTITION BY k ORDER BY n DESC, v) AS rn
                FROM (
                    SELECT LOWER(TRIM({col})) AS k, TRIM({col}) AS v, COUNT(*) AS n
                    FROM trk_raw WHERE {col} IS NOT NULL AND TRIM({col}) <> ''
                    GROUP BY 1, 2
                )
            ) WHERE rn = 1
        )""")
        joins.append(f"LEFT JOIN m{i} ON LOWER(TRIM(trk_raw.{col})) = m{i}.k")
        replaces.append(f"COALESCE(m{i}.canon, trk_raw.{col}) AS {col}")
    return f"""
    WITH trk_raw AS (SELECT * FROM read_parquet('{tracking_file}')),
    {','.join(maps)}
    SELECT trk_raw.* REPLACE ({', '.join(replaces)})
    FROM trk_raw
    {' '.join(joins)}
    """

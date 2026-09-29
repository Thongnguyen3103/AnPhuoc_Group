# -*- coding: utf-8 -*-
"""I/O dùng chung cho lớp Parquet: đọc bảng lookup Master, xuất Parquet phân
mảnh theo năm/tháng."""
import os
import duckdb
import pandas as pd

from .paths import Paths

MASTER_DIR = Paths.MASTER_DIR
PARQUET_ROOT = Paths.PARQUET_ROOT


def load_master_table(name: str) -> pd.DataFrame:
    """Đọc 1 bảng lookup/danh mục từ 02.Master/<name>.parquet."""
    return pd.read_parquet(os.path.join(MASTER_DIR, f"{name}.parquet")).fillna("").astype(str)


def export_parquet_partitioned(df: pd.DataFrame, dir_name: str, file_prefix: str) -> None:
    """Xuất df ra Parquet: thư mục = dir_name -> năm (vd 2026), mỗi tháng 1 file tên
    <file_prefix>_<MM>.parquet. Chỉ ghi đè đúng file tháng có trong df, giữ nguyên các tháng khác."""
    base_dir = os.path.join(PARQUET_ROOT, dir_name)
    periods = df[["Year", "Month"]].dropna().drop_duplicates().astype(int)

    con = duckdb.connect()
    con.register("_data", df)
    for row in periods.itertuples():
        year_dir = os.path.join(base_dir, str(row.Year))
        os.makedirs(year_dir, exist_ok=True)
        file_path = os.path.join(year_dir, f"{file_prefix}_{row.Month:02d}.parquet")
        con.execute(
            f"""
            COPY (SELECT * FROM _data WHERE "Year" = {row.Year} AND "Month" = {row.Month})
            TO '{file_path}' (FORMAT PARQUET)
            """
        )
    con.unregister("_data")
    con.close()
    print(f"  Đã xuất Parquet ({file_prefix}_MM.parquet) -> {base_dir}")

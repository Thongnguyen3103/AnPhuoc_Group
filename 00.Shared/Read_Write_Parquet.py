# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import duckdb
import pandas as pd

import Get_Paths

MASTER_DIR = Get_Paths.master
PARQUET_ROOT = Get_Paths.parquet

# Tên bảng -> (key đường dẫn trong Config_Paths.yaml, file/glob bên trong).
# Bảng phân mảnh theo năm/tháng dùng glob "*/*.parquet".
PARQUET_TABLES = {
    "A_Region":          ("master", "A_Region.parquet"),
    "B_Size":            ("master", "B_Size.parquet"),
    "C_BasicSizeChart":  ("master", "C_BasicSizeChart.parquet"),
    "D_Category":        ("master", "D_Category.parquet"),
    "E_T-Shirt":         ("master", "E_T-Shirt.parquet"),
    "F_DataTracking":    ("master", "F_DataTracking.parquet"),
    "HDD_QLKD_Tong_hop": ("master", "HDD_QLKD_Tong_hop.parquet"),
    "System_sales":      ("ban_le", "*/*.parquet"),
    "Contract_sales":    ("ban_hop_dong", "*/*.parquet"),
    "Inventory":         ("ton_kho_parquet", "Inventory.parquet"),
    "InventorySize":     ("ton_kho_parquet", "InventorySize.parquet"),
    "NhapTuSX":          ("nhap_sx_parquet", "*/*.parquet"),
    "NhapTrungChuyen_CHNHN": ("nhap_trung_chuyen_hn_parquet", "*/*.parquet"),
    "KhoXuat_CH":        ("kho_xuat_ch_parquet", "*/*.parquet"),
    "HH_LuanChuyen":     ("lenh_hhlc", "*/*.parquet"),
    "History_LC":        ("lich_su_lc", "*/*.parquet"),
    "TraKho":            ("tra_kho", "*/*.parquet"),
    "Revenue":           ("doanh_thu_parquet", "Revenue.parquet"),
    "Target":            ("doanh_thu_parquet", "Target.parquet"),
    "Bill_sales":        ("doanh_thu_parquet", "Bill_sales.parquet"),
}


def table_path(name: str, data_root: str | None = None) -> str:
    """Đường dẫn (có thể là glob) tới file parquet của bảng `name`.
    data_root: gốc kho dữ liệu khác mặc định (00.Data_AnPhuoc_Group) — None = theo Config_Paths.yaml."""
    key, pattern = PARQUET_TABLES[name]
    base = Get_Paths.lay(key)
    if data_root and os.path.normcase(os.path.normpath(data_root)) != os.path.normcase(Get_Paths.DATA_ROOT):
        base = os.path.join(os.path.normpath(data_root), os.path.relpath(base, Get_Paths.DATA_ROOT))
    return os.path.join(base, pattern)


def connect_parquet_views(tables=None, data_root: str | None = None) -> duckdb.DuckDBPyConnection:
    """Kết nối DuckDB trong RAM, tạo sẵn VIEW cho từng bảng trỏ thẳng tới file parquet
    (union_by_name: các file tháng lệch cột vẫn gộp được). Bảng thiếu file thì bỏ qua."""
    con = duckdb.connect()
    for name in (tables or PARQUET_TABLES):
        path = table_path(name, data_root)
        if "*" not in path and not os.path.exists(path):
            continue
        src = path.replace("'", "''")
        try:
            con.execute(f"""CREATE VIEW "{name}" AS SELECT * FROM read_parquet('{src}', union_by_name=true)""")
        except duckdb.IOException:
            pass  # glob không khớp file nào
    return con


def read_table(name: str, data_root: str | None = None) -> pd.DataFrame:
    """Đọc trọn 1 bảng parquet ra DataFrame."""
    con = connect_parquet_views([name], data_root)
    try:
        return con.execute(f'SELECT * FROM "{name}"').fetchdf()
    finally:
        con.close()


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

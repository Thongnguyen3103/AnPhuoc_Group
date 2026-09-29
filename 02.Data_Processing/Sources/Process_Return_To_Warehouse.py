# -*- coding: utf-8 -*-
"""Trả Kho (TraKho)."""
import csv
import os
import sys
import io

import numpy as np
import pandas as pd

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # 02.Data_Processing
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "00.Shared"))  # 00.Shared (Get_Paths...)
from Process_Monthly_Base import MonthlySourceProcessor
from Parse_Date import parse_date
from Read_Write_Parquet import load_master_table
import Get_Paths
from Convert_Size import actual_size

RAW_COLS = [
    "LyDo", "NgayChungTu", "MaHang", "Size", "SoLuong",
    "TacNghiep", "MaCH_XUAT", "MaCH_NHAP",
]


def _read_csv_fixing_ragged_tail(path: str, encoding: str):
    """Đọc CSV bằng csv.reader (không qua pandas parser). Cột cuối (Noidung) hay
    chứa dấu ',' không escape -> dòng bị dư field so với header. Vì dấu ',' dư
    luôn nằm trong cột CUỐI, gộp các field dư trở lại đúng cột cuối thay vì bỏ
    dòng. Trả về (DataFrame, số dòng đã gộp)."""
    with open(path, encoding=encoding, newline="") as f:
        rows = list(csv.reader(f))
    if not rows:
        return pd.DataFrame(), 0

    header = [str(h).replace("\ufeff", "").strip() for h in rows[0]]
    n_cols = len(header)
    n_fixed = 0
    fixed_rows = []
    for row in rows[1:]:
        if not row or all(c.strip() == "" for c in row):
            continue
        if len(row) > n_cols:
            row = row[: n_cols - 1] + [",".join(row[n_cols - 1:])]
            n_fixed += 1
        elif len(row) < n_cols:
            row = row + [""] * (n_cols - len(row))
        fixed_rows.append(row)

    df = pd.DataFrame(fixed_rows, columns=header, dtype=str)
    return df, n_fixed


def robust_read_csv(path: str, progress_label: str = "") -> pd.DataFrame:
    """Đọc 1 file TraKho (.csv), tự dò encoding (ưu tiên utf-16)."""
    encodings_try = ["utf-16", "utf-16-le", "utf-16-be", "utf-8-sig", "utf-8", "cp1258", "latin1"]
    last_err = None
    for enc in encodings_try:
        try:
            df, n_fixed = _read_csv_fixing_ragged_tail(path, enc)
            missing = [c for c in RAW_COLS if c not in df.columns]
            if missing:
                print(f"  [WARN] {os.path.basename(path)} thiếu cột: {missing}")
                for c in missing:
                    df[c] = np.nan
            df = df[RAW_COLS]

            fname = os.path.basename(path)
            prefix = f"Đang đọc file {progress_label}: " if progress_label else ""
            if n_fixed:
                print(f"  [WARN] {fname}: đã gộp {n_fixed} dòng bị tách cột cuối (dấu ',' không escape trong Nội dung).")
            print(f"  {prefix}{fname} ({enc}) | Tổng dòng file: {len(df):,}")
            return df
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"Could not read {path}. Last error: {last_err}")


class TraKhoProcessor(MonthlySourceProcessor):
    source_dir = Get_Paths.nguon_tra_kho
    output_dir_name = "09.TraKho"
    file_prefix = "TraKho"
    label = "TraKho"

    def load_lookups(self):
        return {
            "a_region": load_master_table("A_Region"),
            "e_tshirt": load_master_table("E_T-Shirt"),
            "d_category": load_master_table("D_Category"),
        }

    def read_files(self, files: list[str]) -> pd.DataFrame:
        total_files = len(files)
        dfs = [robust_read_csv(f, progress_label=f"{i}/{total_files}") for i, f in enumerate(files, 1)]
        df = pd.concat(dfs, ignore_index=True)
        print(f"\n  >>> Tổng số dòng đọc được từ {total_files} file: {len(df):,}")
        return df

    def transform(self, df: pd.DataFrame, lookups) -> pd.DataFrame:
        a_region, e_tshirt, d_category = lookups["a_region"], lookups["e_tshirt"], lookups["d_category"]

        # Chỉ giữ đúng nghiệp vụ CH trả hàng nhập kho (mỗi file Kho*.csv ứng với 1 kho
        # nhập khác nhau qua MaCH_NHAP: KHOAP/KHOTB/KHOSALETL/... — không lọc cứng theo kho)
        df = df[df['LyDo'].astype(str).str.strip() == 'Nhập cửa hàng trả kho'].copy()

        # Cast numbers
        df['SoLuong'] = pd.to_numeric(df['SoLuong'].astype(str).str.replace(r'[^\d\-\.]', '', regex=True), errors='coerce')

        # NgayChungTu: DD/MM/YYYY -> Year/Month/Quarter
        df['NgayChungTu_dt'] = parse_date(df['NgayChungTu'], '%d/%m/%Y')
        df['Month'] = df['NgayChungTu_dt'].dt.month
        df['Year'] = df['NgayChungTu_dt'].dt.year
        df = df.dropna(subset=['Year', 'Month']).copy()
        df['Year'] = df['Year'].astype(int)
        df['Month'] = df['Month'].astype(int)
        df['Quarter'] = "Q" + np.ceil(df['Month'] / 3).astype(int).astype(str) + "." + df['Year'].astype(str)

        # MaHang -> Short_name (để tra D_Category)
        mahang_str = df["MaHang"].astype(str).str.strip()
        df["Short_name"] = mahang_str.apply(lambda x: x[:-4] if len(x) >= 4 else x)

        df = df.merge(
            d_category[['Short_name', 'Brand', 'Report_item_name', 'Product_type', 'Gender', 'Product_group', 'Group_Report']],
            on='Short_name', how='left',
        )
        df = df.merge(e_tshirt[['item_code', 'T-shirt_name']], left_on='MaHang', right_on='item_code', how='left')
        tshirt = df['T-shirt_name'].fillna("").astype(str).str.strip()
        df['Report_item_name'] = np.where(tshirt != "", tshirt, df['Report_item_name'])
        df = df.drop(columns=['Short_name', 'item_code', 'T-shirt_name'], errors='ignore')

        # Filter product/brand không phải hàng hóa thực (giống Xử lý Bán)
        cond_product = ~df["Product_type"].isin(["Bao Bì", "Đồng Phục"])
        df = df[cond_product]
        df = df[~df['Brand'].isin(["Dv In Theu", "Khác"])].copy()

        # Chuẩn hóa Size theo SIZE_MAP
        df['Size'] = [actual_size(sz, name) for sz, name in zip(df['Size'], df['Report_item_name'])]

        # Cửa hàng trả — MaCH_XUAT chứa tên hiển thị CH (khớp A_Region.Store_name)
        df['Mã CH'] = df['MaCH_XUAT'].astype(str).str.strip()
        df = df.merge(a_region[['Store_name', 'Region', 'Warehouse']], left_on='Mã CH', right_on='Store_name', how='left')

        df = df.rename(columns={
            "TacNghiep": "Operation",
            "SoLuong": "Qty_Tra",
        })
        # File nguồn không có cột Trangthai như báo cáo cũ; Kho_Nhan lấy trực tiếp
        # mã kho thô MaCH_NHAP (giữ đúng quy ước đang dùng ở bảng KhoXuat_CH)
        df['Kho_Nhan'] = df['MaCH_NHAP'].astype(str).str.strip()
        df['TrangThai'] = np.nan

        group_cols = [
            "Store_name", "Region", "Warehouse", "NgayChungTu_dt", "Month", "Quarter", "Year", "Brand", "Report_item_name",
            "MaHang", "Operation", "Size", "TrangThai", "Kho_Nhan", "Product_type", "Gender",
            "Product_group", "Group_Report",
        ]
        for c in group_cols:
            if c not in df.columns:
                df[c] = np.nan

        df_grouped = df.groupby(group_cols, dropna=False).agg(Qty_Tra=('Qty_Tra', 'sum')).reset_index()

        final_cols = [
            "Store_name", "Region", "Warehouse", "NgayChungTu_dt", "Month", "Quarter", "Year", "Brand", "Report_item_name",
            "MaHang", "Operation", "Size", "Qty_Tra", "TrangThai", "Kho_Nhan", "Product_type", "Gender",
            "Product_group", "Group_Report",
        ]
        df_grouped = df_grouped[final_cols]

        print(f"TraKho — {len(df_grouped):,} dòng nhóm | Tổng Qty_Tra: {df_grouped['Qty_Tra'].sum():,.0f}")
        return df_grouped

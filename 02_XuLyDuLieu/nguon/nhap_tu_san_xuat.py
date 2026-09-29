# -*- coding: utf-8 -*-
"""Nhập từ SX (NhapTuSX)."""
import csv
import os
import sys
import io

import numpy as np
import pandas as pd

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # 02_XuLyDuLieu
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # 01.Python_Projects (dung_chung)
from xu_ly_theo_thang import MonthlySourceProcessor
from dung_chung.ngay_thang import parse_date
from dung_chung.doc_ghi_parquet import load_master_table
from dung_chung import duong_dan
from dung_chung.quy_doi_size import actual_size


def robust_read_csv(path: str, progress_label: str = "") -> pd.DataFrame:
    """Đọc tệp CSV với mã hóa utf-16 và tự động xử lý các dòng bị chia tách do unescaped commas trong Noidung."""
    encodings_try = ["utf-16", "utf-8-sig", "utf-8", "cp1258", "latin1"]
    last_err = None
    for enc in encodings_try:
        try:
            with open(path, "r", encoding=enc, newline="") as f:
                reader = csv.reader(f)
                header = [" ".join(str(c).replace("\ufeff", "").strip().split()) for c in next(reader)]
                ncols = len(header)

                rows, n_ok, n_recovered, n_dropped = [], 0, 0, 0
                for row in reader:
                    if len(row) == ncols:
                        rows.append(row)
                        n_ok += 1
                    elif len(row) > ncols:
                        # Gộp các trường bị phân tách từ cột Noidung (index 17)
                        # Cột Noidung bắt đầu tại chỉ mục 17
                        # Các cột phía sau Noidung: có (ncols - 18) cột
                        merged_noidung = ",".join(row[17: len(row) - (ncols - 18)])
                        new_row = row[:17] + [merged_noidung] + row[-(ncols - 18):]
                        rows.append(new_row)
                        n_recovered += 1
                    else:
                        n_dropped += 1

            df = pd.DataFrame(rows, columns=header)
            fname = os.path.basename(path)
            prefix = f"Đang đọc file {progress_label}: " if progress_label else ""
            print(f"  {prefix}{fname} ({enc}) | Tổng dòng: {len(df):,} | Khôi phục: {n_recovered:,} | Bỏ qua: {n_dropped:,}")
            return df
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"Could not read {path}. Last error: {last_err}")


class NhapTuSXProcessor(MonthlySourceProcessor):
    source_dir = duong_dan.nguon_nhap_sx
    output_dir_name = "05.NhapSX"
    file_prefix = "NhapTuSX"
    label = "NhapTuSX"

    def load_lookups(self):
        return {
            "a_region": load_master_table("A_Region"),
            "d_category": load_master_table("D_Category"),
        }

    def read_files(self, files: list[str]) -> pd.DataFrame:
        total_files = len(files)
        dfs = [robust_read_csv(f, progress_label=f"{i}/{total_files}") for i, f in enumerate(files, 1)]
        df = pd.concat(dfs, ignore_index=True)
        print(f"\n  >>> Tổng số dòng đọc được từ {total_files} file: {len(df):,}")
        return df

    def transform(self, df: pd.DataFrame, lookups) -> pd.DataFrame:
        a_region, d_category = lookups["a_region"], lookups["d_category"]

        # Chuyển đổi định dạng số cho SoLuong và Sale
        for col in ["SoLuong", "Sale"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col].astype(str).str.replace(r'[^\d\-,\.]', '', regex=True).str.replace(',', '.'), errors='coerce').fillna(0)
            else:
                df[col] = 0

        # Tách ngày/tháng/năm từ NgayChungTu
        if "NgayChungTu" in df.columns:
            df['NgayChungTu_parsed'] = parse_date(df['NgayChungTu'], '%d/%m/%Y')
            df['Month'] = df['NgayChungTu_parsed'].dt.month
            df['Year'] = df['NgayChungTu_parsed'].dt.year

            # Loại bỏ dòng không có thông tin ngày tháng hợp lệ để làm khóa upsert
            df = df.dropna(subset=['Month', 'Year']).copy()
            df['Month'] = df['Month'].astype(int)
            df['Year'] = df['Year'].astype(int)

            valid_dates = df['Month'].notna() & df['Year'].notna()
            df['Quarter'] = pd.Series(dtype=object)
            df.loc[valid_dates, 'Quarter'] = (
                "Q" + np.ceil(df.loc[valid_dates, 'Month'] / 3).astype(int).astype(str)
                + "." + df.loc[valid_dates, 'Year'].astype(int).astype(str)
            )
        else:
            df['Month'] = np.nan
            df['Year'] = np.nan
            df['Quarter'] = np.nan

        # Trích xuất Short_name từ MaHang
        if "MaHang" in df.columns:
            mahang_str = df["MaHang"].astype(str).str.strip()
            df["Short_name"] = mahang_str.apply(lambda x: x[:-4] if len(x) >= 4 else x)
        else:
            df["Short_name"] = ""

        # 1. D_Category
        df = df.merge(
            d_category[['Short_name', 'Brand', 'Report_item_name', 'Product_type', 'Gender', 'Product_group', 'Group_Report']],
            on='Short_name',
            how='left',
        )

        # 2. A_Region dựa trên mã kho nhận MaCH_NHAP khớp với Store_code trong A_Region
        if "MaCH_NHAP" in df.columns:
            df['MaCH_NHAP'] = df['MaCH_NHAP'].astype(str).str.strip()
            df = df.merge(
                a_region[['Store_code', 'Store_name', 'Region', 'Warehouse']],
                left_on='MaCH_NHAP',
                right_on='Store_code',
                how='left',
            )
            df = df.drop(columns=['Store_code'], errors='ignore')
        else:
            df['Store_name'] = np.nan
            df['Region'] = np.nan
            df['Warehouse'] = np.nan

        # 3. Chuẩn hóa Size theo SIZE_MAP
        if 'Report_item_name' not in df.columns:
            df['Report_item_name'] = np.nan
        if 'Size' not in df.columns:
            df['Size'] = np.nan

        df['Size'] = [actual_size(sz, name) for sz, name in zip(df['Size'], df['Report_item_name'])]

        # Xử lý cột trạng thái (Status)
        mask_thanhly = df['Product_type'].astype(str).str.contains("Thanh lý", case=False, na=False)
        mask_sale = df['Sale'].isin([30, 50])
        df['Status'] = np.where(mask_thanhly, "Thanh lý", np.where(mask_sale, "Sale", "Nguyên giá"))

        # Rename TacNghiep thành Operation
        if 'TacNghiep' in df.columns:
            df = df.rename(columns={'TacNghiep': 'Operation'})
        else:
            df['Operation'] = np.nan

        group_cols = [
            "LyDo", "MaCH_XUAT", "MaCH_NHAP", "Store_name", "Region", "Warehouse",
            "Month", "Quarter", "Year", "Brand", "Report_item_name", "MaHang",
            "Operation", "Size", "Sale", "Status", "Product_type", "Gender",
            "Product_group", "Group_Report",
        ]
        for c in group_cols:
            if c not in df.columns:
                df[c] = np.nan

        df_grouped = df.groupby(group_cols, dropna=False).agg(SoLuong=('SoLuong', 'sum')).reset_index()

        final_cols = [
            "LyDo", "MaCH_XUAT", "MaCH_NHAP", "Store_name", "Region", "Warehouse",
            "Month", "Quarter", "Year", "Brand", "Report_item_name", "MaHang",
            "Operation", "Size", "SoLuong", "Sale", "Status", "Product_type",
            "Gender", "Product_group", "Group_Report",
        ]
        df_grouped = df_grouped[final_cols]

        print(f"NhapTuSX — {len(df_grouped):,} dòng nhóm | Tổng SoLuong: {df_grouped['SoLuong'].sum():,.0f}")
        return df_grouped

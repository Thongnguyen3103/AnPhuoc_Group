# -*- coding: utf-8 -*-
"""Lịch sử Luân chuyển (History_LC)."""
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
    "SoCT", "Ngay", "mahang", "GiaTri", "Mau", "Size", "SoLuong",
    "CH", "CH_N", "MaCH", "MaCH_N", "Trangthainhap", "Tacnghiep", "salesoff",
]


def robust_read_csv(path: str, progress_label: str = "") -> pd.DataFrame:
    """Đọc 1 file History_LC (.csv), tự dò encoding (ưu tiên utf-16)."""
    encodings_try = ["utf-16", "utf-16-le", "utf-16-be", "utf-8-sig", "utf-8", "cp1258", "latin1"]
    last_err = None
    for enc in encodings_try:
        try:
            df = pd.read_csv(path, encoding=enc, dtype=str, low_memory=False)
            df.columns = [" ".join(str(c).replace("\ufeff", "").strip().split()) for c in df.columns]
            missing = [c for c in RAW_COLS if c not in df.columns]
            if missing:
                print(f"  [WARN] {os.path.basename(path)} thiếu cột: {missing}")
                for c in missing:
                    df[c] = np.nan
            df = df[RAW_COLS]

            fname = os.path.basename(path)
            prefix = f"Đang đọc file {progress_label}: " if progress_label else ""
            print(f"  {prefix}{fname} ({enc}) | Tổng dòng file: {len(df):,}")
            return df
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"Could not read {path}. Last error: {last_err}")


class HistoryLCProcessor(MonthlySourceProcessor):
    source_dir = Get_Paths.nguon_lich_su_lc
    output_dir_name = "08.History_LC"
    file_prefix = "History_LC"
    label = "History_LC"

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

        # Cast numbers
        for c in ["GiaTri", "SoLuong", "salesoff"]:
            df[c] = pd.to_numeric(df[c].astype(str).str.replace(r'[^\d\-,\.]', '', regex=True).str.replace(',', '.'), errors='coerce')

        # Ngay: MM/DD/YYYY HH:MM:SS AM/PM -> Year/Month/Quarter
        df['NgayChungTu'] = parse_date(df['Ngay'], '%m/%d/%Y')
        df['Month'] = df['NgayChungTu'].dt.month
        df['Year'] = df['NgayChungTu'].dt.year
        df = df.dropna(subset=['Year', 'Month']).copy()
        df['Year'] = df['Year'].astype(int)
        df['Month'] = df['Month'].astype(int)
        df['Quarter'] = "Q" + np.ceil(df['Month'] / 3).astype(int).astype(str) + "." + df['Year'].astype(str)

        # MaHang -> Short_name (để tra D_Category)
        mahang_str = df["mahang"].astype(str).str.strip()
        df = df.rename(columns={"mahang": "MaHang"})
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

        # Store nguồn (MaCH) và store nhận (MaCH_N) — tra A_Region
        a_region_lookup = a_region[['Store_code', 'Store_name', 'Region', 'Warehouse']].drop_duplicates('Store_code')
        df = df.merge(
            a_region_lookup.rename(columns={"Store_code": "MaCH", "Store_name": "Store_from", "Region": "Region_from", "Warehouse": "Warehouse_from"}),
            on='MaCH', how='left',
        )
        df = df.merge(
            a_region_lookup.rename(columns={"Store_code": "MaCH_N", "Store_name": "Store_to", "Region": "Region_to", "Warehouse": "Warehouse_to"}),
            on='MaCH_N', how='left',
        )

        # Status: Thanh lý theo Product_type, Sale theo salesoff (giống Xử lý Bán)
        mask_thanhly = df['Product_type'].astype(str).str.contains("Thanh lý", case=False, na=False)
        mask_sale = df['salesoff'].isin([30, 50])
        df['Status'] = np.where(mask_thanhly, "Thanh lý", np.where(mask_sale, "Sale", "Nguyên giá"))

        df = df.rename(columns={
            "Tacnghiep": "Operation",
            "SoLuong": "Qty_Chuyen",
            "Trangthainhap": "TrangThaiNhap",
        })

        group_cols = [
            "Store_from", "Region_from", "Warehouse_from", "Store_to", "Region_to", "Warehouse_to",
            "NgayChungTu", "Month", "Quarter", "Year", "Brand", "Report_item_name", "MaHang", "Operation", "Size",
            "Status", "TrangThaiNhap", "Product_type", "Gender", "Product_group", "Group_Report",
        ]
        for c in group_cols:
            if c not in df.columns:
                df[c] = np.nan

        df_grouped = df.groupby(group_cols, dropna=False).agg(Qty_Chuyen=('Qty_Chuyen', 'sum')).reset_index()

        final_cols = [
            "Store_from", "Region_from", "Warehouse_from", "Store_to", "Region_to", "Warehouse_to",
            "NgayChungTu", "Month", "Quarter", "Year", "Brand", "Report_item_name", "MaHang", "Operation", "Size",
            "Qty_Chuyen", "Status", "TrangThaiNhap", "Product_type", "Gender", "Product_group", "Group_Report",
        ]
        df_grouped = df_grouped[final_cols]

        print(f"History_LC — {len(df_grouped):,} dòng nhóm | Tổng Qty_Chuyen: {df_grouped['Qty_Chuyen'].sum():,.0f}")
        return df_grouped


if __name__ == "__main__":
    # Chay doc lap file nay (vd bam Run trong VS Code)
    HistoryLCProcessor().run()

# -*- coding: utf-8 -*-
"""Bán lẻ (System_sales) và Bán Hợp Đồng (Contract_sales)."""
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

# Mã cửa hàng cũ (xuất hiện trong SoChungTu các năm trước) -> mã hiện hành trong A_Region
STORE_CODE_ALIAS = {
    "VINCOMLX": "LONGXUYEN2",  # Long Xuyên 2
    "HN27": "HP4",             # Hải Phòng 4
}


def extract_ma_ch(x):
    """Trích mã cửa hàng nằm giữa '/' và '-' trong SoChungTu (vd '6900/NGA6-PT' -> 'NGA6').
    Mã cũ (đã đổi tên/không còn dùng trong A_Region) được quy về mã mới qua STORE_CODE_ALIAS."""
    x = str(x)
    if "/" in x and "-" in x:
        start = x.find("/") + 1
        end = x.find("-", start)
        if end != -1:
            code = x[start:end]
            return STORE_CODE_ALIAS.get(code, code)
    return np.nan


def robust_read_csv(path: str, progress_label: str = "") -> pd.DataFrame:
    """Đọc CSV, tự dò encoding/delimiter, và tự PHỤC HỒI các dòng bị dư đúng 1 field do dấu
    phẩy không escape trong cột ghi chú tự do (vd cột 'Kieu' của báo cáo System Sales, mặt
    hàng Áo Ngực hay có ghi chú kiểu 'C13 - SG coque 2.3, h.push' làm dòng bị tách dư field).
    Trước đây các dòng này bị pandas.read_csv(on_bad_lines='skip') âm thầm loại bỏ, gây lệch
    số liệu. Dòng lệch nhiều hơn 1 field (không đủ tin cậy để tự sửa) sẽ bị bỏ qua và cảnh báo."""
    encodings_try = ["utf-8-sig", "utf-8", "cp1258", "cp1252", "latin1", "utf-16", "utf-16-le", "utf-16-be"]
    with open(path, "rb") as fb:
        raw = fb.read(200_000)
    prefer_utf16 = raw.count(b"\x00") > 100
    encodings = (["utf-16", "utf-16-le", "utf-16-be"] + encodings_try) if prefer_utf16 else encodings_try

    last_err = None
    for enc in encodings:
        try:
            with open(path, "r", encoding=enc, newline="") as f:
                sample = f.read(200_000)
            if not sample:
                raise RuntimeError("Empty file")
            try:
                delimiter = csv.Sniffer().sniff(sample, delimiters=[",", ";", "\t", "|"]).delimiter
            except Exception:
                delimiter = ","

            with open(path, "r", encoding=enc, newline="") as f:
                reader = csv.reader(f, delimiter=delimiter)
                header = [" ".join(str(c).replace("\ufeff", "").strip().split()) for c in next(reader)]
                ncols = len(header)
                # Cột ghi chú tự do dễ bị dính dấu phẩy chưa escape (nếu file có cột này)
                merge_idx = next((i for i, c in enumerate(header) if c == "Kieu"), None)

                rows, n_ok, n_recovered, n_dropped = [], 0, 0, 0
                for row in reader:
                    if len(row) == ncols:
                        rows.append(row)
                        n_ok += 1
                    elif len(row) == ncols + 1 and merge_idx is not None:
                        rows.append(row[:merge_idx] + [row[merge_idx] + delimiter + row[merge_idx + 1]] + row[merge_idx + 2:])
                        n_recovered += 1
                    else:
                        n_dropped += 1

            total = n_ok + n_recovered + n_dropped
            fname = os.path.basename(path)
            prefix = f"Đang đọc file {progress_label}: " if progress_label else ""
            print(f"  {prefix}{fname} | Tổng dòng file: {total:,} | Không đọc được: {n_dropped:,}")

            return pd.DataFrame(rows, columns=header)
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"Could not read {path}. Last error: {last_err}")


class SystemSalesProcessor(MonthlySourceProcessor):
    source_dir = Get_Paths.nguon_ban_le
    output_dir_name = "01.System_sales"
    file_prefix = "System_sales"
    label = "System_sales"

    def load_lookups(self):
        return {
            "a_region": load_master_table("A_Region"),
            "e_tshirt": load_master_table("E_T-Shirt"),
            "d_category": load_master_table("D_Category"),
        }

    def read_files(self, files: list[str]) -> pd.DataFrame:
        total_files = len(files)
        dfs = [robust_read_csv(f, progress_label=f"{i}/{total_files}") for i, f in enumerate(files, 1)]
        return pd.concat(dfs, ignore_index=True)

    def transform(self, df: pd.DataFrame, lookups) -> pd.DataFrame:
        a_region, e_tshirt, d_category = lookups["a_region"], lookups["e_tshirt"], lookups["d_category"]

        num_cols = ["SoLuong", "DonGia", "ThueVat", "ThanhTien", "Sales"]
        for c in num_cols:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c].astype(str).str.replace(r'[^\d\-,\.]', '', regex=True).str.replace(',', '.'), errors='coerce')

        if "NgayChungTu" in df.columns:
            # System sales: MM/DD/YYYY HH:MM:SS
            df['NgayChungTu'] = parse_date(df['NgayChungTu'], '%m/%d/%Y')
            df['Month'] = df['NgayChungTu'].dt.month
            df['Year'] = df['NgayChungTu'].dt.year
            valid_dates = df['Month'].notna() & df['Year'].notna()
            df['Quarter'] = pd.Series(dtype=object)
            df.loc[valid_dates, 'Quarter'] = (
                "Q" + np.ceil(df.loc[valid_dates, 'Month'] / 3).astype(int).astype(str)
                + "." + df.loc[valid_dates, 'Year'].astype(int).astype(str)
            )

        if "DienGiai" in df.columns:
            df["Nội dung"] = df["DienGiai"].astype(str).str.split(":", n=1).str[0].str.strip()
        else:
            df["Nội dung"] = ""

        if "MaHang" in df.columns:
            mahang_str = df["MaHang"].astype(str).str.strip()
            df["Short_name"] = mahang_str.apply(lambda x: x[:-4] if len(x) >= 4 else x)
            df["Code_color"] = mahang_str.apply(lambda x: x[-4:] if len(x) >= 4 else "")
        else:
            df["Short_name"] = ""
            df["Code_color"] = ""

        if "SoChungTu" in df.columns:
            df['Mã CH'] = df['SoChungTu'].apply(extract_ma_ch)
        else:
            df['Mã CH'] = np.nan

        df = df.merge(a_region[['Store_code', 'Store_name', 'Region', 'Warehouse']], left_on='Mã CH', right_on='Store_code', how='left')
        df = df.merge(e_tshirt[['item_code', 'T-shirt_name']], left_on='MaHang', right_on='item_code', how='left')
        df = df.merge(d_category[['Short_name', 'Brand', 'System_item_name', 'Report_item_name', 'Product_type', 'Gender', 'Product_group', 'Group_Report']], on='Short_name', how='left')

        if 'T-shirt_name' in df.columns and 'Report_item_name' in df.columns:
            df['Report_item_name'] = np.where(df['T-shirt_name'].notna() & (df['T-shirt_name'] != ""), df['T-shirt_name'], df['Report_item_name'])
        df = df.drop(columns=['T-shirt_name', 'item_code'], errors='ignore')

        # Filter rows
        cond_noidung = df["Nội dung"].str.strip().isin(["Bán", "Tặng", "Đổi"])
        # Casing phải khớp đúng với D_Category ("Bao Bì", "Đồng Phục"); trước đây viết sai
        # ("Bao bì", "Đồng phục") khiến filter này không loại được dòng nào.
        cond_product = ~df["Product_type"].isin(["Bao Bì", "Đồng Phục"])
        df = df[cond_noidung & cond_product].copy()

        # Status
        mask_thanhly = df['Product_type'].astype(str).str.contains("Thanh lý", case=False, na=False)
        mask_sale = df['Sales'].isin([30, 50])
        df['Status'] = np.where(mask_thanhly, "Thanh lý", np.where(mask_sale, "Sale", "Nguyên giá"))

        # Size logic
        if 'Report_item_name' not in df.columns:
            df['Report_item_name'] = np.nan
        if 'Size' not in df.columns:
            df['Size'] = np.nan

        df['Size'] = [actual_size(sz, name) for sz, name in zip(df['Size'], df['Report_item_name'])]

        df = df.drop(columns=['SoChungTu', 'DienGiai', 'ThueVat', 'ThanhTien'], errors='ignore')

        if 'TacNghiep' in df.columns:
            df = df.rename(columns={'TacNghiep': 'Operation'})
        else:
            df['Operation'] = np.nan

        df = df.rename(columns={'SoLuong': 'Slg_Ban'})
        df['Sales _Type'] = pd.Series(dtype=object)
        df.loc[df['MaHang'].notna() & (df['MaHang'] != ""), 'Sales _Type'] = "Retail"

        # Filter Brand
        df = df[~df['Brand'].isin(["Dv In Theu", "Khác"])]

        group_cols = [
            "Store_name", "NgayChungTu", "Month", "Quarter", "Year", "MaHang", "Operation", "Region", "Warehouse",
            "Brand", "Product_type", "Gender", "Product_group", "Report_item_name", "Status",
            "Size", "Group_Report", "Nội dung", "Sales _Type",
        ]
        for c in group_cols:
            if c not in df.columns:
                df[c] = np.nan

        df_grouped = df.groupby(group_cols, dropna=False).agg(Qty_Ban=('Slg_Ban', 'sum')).reset_index()

        final_cols = [
            "Store_name", "Region", "Warehouse", "NgayChungTu", "Month", "Quarter", "Year", "Brand", "Report_item_name",
            "MaHang", "Operation", "Size", "Qty_Ban", "Nội dung", "Status", "Product_type", "Gender", "Product_group",
            "Group_Report", "Sales _Type",
        ]
        for c in final_cols:
            if c not in df_grouped.columns:
                df_grouped[c] = np.nan
        df_grouped = df_grouped[final_cols]

        print(f"System_sales — {len(df_grouped):,} dòng nhóm | Tổng Qty_Ban: {df_grouped['Qty_Ban'].sum():,.0f}")
        return df_grouped


class ContractSalesProcessor(MonthlySourceProcessor):
    source_dir = Get_Paths.nguon_ban_hop_dong
    output_dir_name = "02.Contract_sales"
    file_prefix = "Contract_sales"
    label = "Contract_sales"

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
        a_region, d_category = lookups["a_region"], lookups["d_category"]

        if "SoLuong" in df.columns:
            df["SoLuong"] = pd.to_numeric(df["SoLuong"].astype(str).str.replace(r'[^\d\-,\.]', '', regex=True).str.replace(',', '.'), errors='coerce')
        if "Sale" in df.columns:
            df["Sale"] = pd.to_numeric(df["Sale"].astype(str).str.replace(r'[^\d\-,\.]', '', regex=True).str.replace(',', '.'), errors='coerce')

        if "NgayChungTu" in df.columns:
            # Contract sales: DD/MM/YYYY
            df['NgayChungTu'] = parse_date(df['NgayChungTu'], '%d/%m/%Y')
            df['Month'] = df['NgayChungTu'].dt.month
            df['Year'] = df['NgayChungTu'].dt.year
            valid_dates = df['Month'].notna() & df['Year'].notna()
            df['Quarter'] = pd.Series(dtype=object)
            df.loc[valid_dates, 'Quarter'] = (
                "Q" + np.ceil(df.loc[valid_dates, 'Month'] / 3).astype(int).astype(str)
                + "." + df.loc[valid_dates, 'Year'].astype(int).astype(str)
            )

        if "SoChungTu" in df.columns:
            df['Mã CH'] = df['SoChungTu'].apply(extract_ma_ch)
        else:
            df['Mã CH'] = np.nan

        df = df.merge(a_region[['Store_code', 'Store_name', 'Region', 'Warehouse']], left_on='Mã CH', right_on='Store_code', how='left')

        if "MaHang" in df.columns:
            df['Short_name'] = df['MaHang'].astype(str).apply(lambda x: x[:-4] if len(x) >= 4 else x)
        else:
            df['Short_name'] = ""

        df = df.merge(d_category[['Short_name', 'Brand', 'System_item_name', 'Report_item_name', 'Product_type', 'Gender', 'Product_group', 'Group_Report']], on='Short_name', how='left')

        if 'Report_item_name' not in df.columns:
            df['Report_item_name'] = np.nan
        if 'Size' not in df.columns:
            df['Size'] = np.nan

        df['Size'] = [actual_size(sz, name) for sz, name in zip(df['Size'], df['Report_item_name'])]

        mask_sale = df['Sale'].isin([30, 50])
        df['Status'] = np.where(mask_sale, "Sale", "Nguyên giá")

        if 'TacNghiep' in df.columns:
            df = df.rename(columns={'TacNghiep': 'Operation'})
        else:
            df['Operation'] = np.nan

        df['Sales _Type'] = pd.Series(dtype=object)
        df.loc[df['MaHang'].notna() & (df['MaHang'] != ""), 'Sales _Type'] = "Contract"

        group_cols = [
            "MaHang", "Operation", "NgayChungTu", "Month", "Quarter", "Year", "Store_name", "Region", "Warehouse",
            "Brand", "Report_item_name", "Product_type", "Gender", "Product_group", "Group_Report",
            "Size", "Status", "Sales _Type",
        ]
        for c in group_cols:
            if c not in df.columns:
                df[c] = np.nan

        df_grouped = df.groupby(group_cols, dropna=False).agg(Qty_Ban=('SoLuong', 'sum')).reset_index()

        final_cols = [
            "Store_name", "Region", "Warehouse", "NgayChungTu", "Month", "Quarter", "Year", "Brand", "Report_item_name",
            "MaHang", "Operation", "Size", "Qty_Ban", "Status", "Product_type", "Gender", "Product_group",
            "Group_Report", "Sales _Type",
        ]
        for c in final_cols:
            if c not in df_grouped.columns:
                df_grouped[c] = np.nan
        df_grouped = df_grouped[final_cols]

        print(f"  >>> Không có filter loại dòng (Contract Sales) | Tổng SoLuong đưa vào nhóm: {df['SoLuong'].sum():,.0f}")
        print(f"Contract_sales — {len(df_grouped):,} dòng nhóm | Tổng Qty_Ban: {df_grouped['Qty_Ban'].sum():,.0f}")
        return df_grouped


if __name__ == "__main__":
    # Chay doc lap file nay (vd bam Run trong VS Code)
    # Chay ca Ban le + Ban hop dong, dung chung lookups (doc Master 1 lan) — giong Run_All_Processing.py
    _lookups = SystemSalesProcessor().load_lookups()
    SystemSalesProcessor().run(lookups=_lookups)
    ContractSalesProcessor().run(lookups=_lookups)

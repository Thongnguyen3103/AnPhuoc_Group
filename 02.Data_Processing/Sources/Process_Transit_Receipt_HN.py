# -*- coding: utf-8 -*-
"""Nhập kho trung chuyển — Kho Chi nhánh Hà Nội (NhapTrungChuyen_CHNHN).

Nguồn : 01.Source/07.NhapTrungChuyen_CHNHN/NTC_<kho>_<MM-YYYY>.xls
        (tải bằng 01.Data_Download, job qlkd_ntc — BaoCaoNhapXuatKho.aspx, chi tiết có mã hàng)
        Cột: STT, Ngày, Số chứng từ, Mã hàng, Tên hàng, Số lượng, Đơn giá, Sale, Trị giá, Ghi chú
        - "Ghi chú"     = tên kho XUẤT hàng đi (Kho An Phước, Kho PIE, Kho Tổng hợp (NG-S-TL)...)
        - "Số chứng từ" = 3241/KHOHN-26-NK -> mã kho NHẬN = KHOHN
Đích  : 03.Data_Parquest/04.NhapTrungChuyen_CHNHN/<năm>/NhapTrungChuyen_CHNHN_<MM>.parquet
        (gộp theo tháng, giống các nguồn khác; báo cáo không có Size / Operation)
"""
import os
import sys
import io

import numpy as np
import pandas as pd

if isinstance(sys.stdout, io.TextIOWrapper) and sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # 02.Data_Processing
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "00.Shared"))  # 00.Shared (Get_Paths...)
from Process_Monthly_Base import MonthlySourceProcessor
from Parse_Date import parse_date
from Read_Write_Parquet import load_master_table
import Get_Paths

# Tên cột trong file nguồn -> tên cột chuẩn của pipeline
RENAME_MAP = {
    "Ngày": "NgayChungTu",
    "Số chứng từ": "SoChungTu",
    "Mã hàng": "MaHang",
    "Tên hàng": "TenHang",
    "Số lượng": "SoLuong",
    "Đơn giá": "Don_gia",
    "Sale": "Sale",
    "Trị giá": "Tri_gia",
    "Ghi chú": "Kho_Xuat",
}


def read_ntc_excel(path: str, progress_label: str = "") -> pd.DataFrame:
    """Đọc 1 file NTC (.xls/.xlsx) — sheet đầu tiên, dòng 1 là tiêu đề. Bỏ dòng trống/dòng tổng (không có mã hàng)."""
    df = pd.read_excel(path, sheet_name=0, engine="calamine", dtype=str)
    df.columns = [" ".join(str(c).replace("﻿", "").split()) for c in df.columns]
    missing = [c for c in RENAME_MAP if c not in df.columns]
    if missing:
        raise ValueError(f"{os.path.basename(path)}: thiếu cột {missing}. Cột hiện có: {list(df.columns)}")
    df = df.rename(columns=RENAME_MAP)
    df = df[df["MaHang"].notna() & (df["MaHang"].astype(str).str.strip() != "")].copy()
    df["Source_file"] = os.path.basename(path)
    prefix = f"Đang đọc file {progress_label}: " if progress_label else ""
    print(f"  {prefix}{os.path.basename(path)} | Tổng dòng: {len(df):,}")
    return df


class NhapTrungChuyenCHNHNProcessor(MonthlySourceProcessor):
    source_dir = Get_Paths.nguon_nhap_trung_chuyen_hn
    file_glob = "*.xls*"                     # .xls (tải từ QLKD) hoặc .xlsx
    output_dir_name = "04.NhapTrungChuyen_CHNHN"
    file_prefix = "NhapTrungChuyen_CHNHN"
    label = "NhapTrungChuyen_CHNHN"

    def _files(self) -> list[str]:
        # bỏ file tạm của Excel (~$...)
        return [f for f in super()._files() if not os.path.basename(f).startswith("~$")]

    def load_lookups(self):
        return {
            "a_region": load_master_table("A_Region"),
            "d_category": load_master_table("D_Category"),
        }

    def read_files(self, files: list[str]) -> pd.DataFrame:
        total_files = len(files)
        dfs = [read_ntc_excel(f, progress_label=f"{i}/{total_files}") for i, f in enumerate(sorted(files), 1)]
        df = pd.concat(dfs, ignore_index=True)
        print(f"\n  >>> Tổng số dòng đọc được từ {total_files} file: {len(df):,}")
        return df

    def transform(self, df: pd.DataFrame, lookups) -> pd.DataFrame:
        a_region, d_category = lookups["a_region"], lookups["d_category"]

        # Số
        for col in ["SoLuong", "Don_gia", "Sale", "Tri_gia"]:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(r"[^\d\-,\.]", "", regex=True).str.replace(",", "."),
                errors="coerce").fillna(0)

        # Ngày -> Month / Year / Quarter
        df["NgayChungTu_parsed"] = parse_date(df["NgayChungTu"], "%d/%m/%Y")
        df = df.dropna(subset=["NgayChungTu_parsed"]).copy()
        df["Month"] = df["NgayChungTu_parsed"].dt.month.astype(int)
        df["Year"] = df["NgayChungTu_parsed"].dt.year.astype(int)
        df["Quarter"] = "Q" + np.ceil(df["Month"] / 3).astype(int).astype(str) + "." + df["Year"].astype(str)

        # Kho NHẬN: "3241/KHOHN-26-NK" -> "KHOHN"
        df["MaCH_NHAP"] = df["SoChungTu"].astype(str).str.extract(r"/([A-Za-z0-9]+)-", expand=False).str.strip()
        # Kho XUẤT: tên kho trong "Ghi chú" -> mã kho theo A_Region (kho không có mã thì để trống, giữ tên)
        df["Kho_Xuat"] = df["Kho_Xuat"].astype(str).str.strip()
        a_region_norm = a_region.assign(_name=a_region["Store_name"].astype(str).str.strip())
        name_to_code = (a_region_norm[a_region_norm["Store_code"].astype(str).str.strip() != ""]
                        .drop_duplicates("_name").set_index("_name")["Store_code"])
        df["MaCH_XUAT"] = df["Kho_Xuat"].map(name_to_code)

        # D_Category theo Short_name (Mã hàng bỏ 4 ký tự cuối)
        mahang_str = df["MaHang"].astype(str).str.strip()
        df["MaHang"] = mahang_str
        df["Short_name"] = mahang_str.apply(lambda x: x[:-4] if len(x) >= 4 else x)
        df = df.merge(
            d_category[["Short_name", "Brand", "Report_item_name", "Product_type", "Gender", "Product_group", "Group_Report"]],
            on="Short_name", how="left")
        n_miss = df["Brand"].isna().sum()
        if n_miss:
            print(f"  [WARN] {n_miss} dòng không khớp D_Category: {sorted(df.loc[df['Brand'].isna(), 'MaHang'].unique())[:10]}")

        # A_Region theo kho NHẬN
        df = df.merge(a_region[["Store_code", "Store_name", "Region", "Warehouse"]],
                      left_on="MaCH_NHAP", right_on="Store_code", how="left").drop(columns=["Store_code"])

        # Trạng thái (cùng quy tắc với NhapTuSX)
        mask_thanhly = df["Product_type"].astype(str).str.contains("Thanh lý", case=False, na=False)
        mask_sale = df["Sale"].isin([30, 50])
        df["Status"] = np.where(mask_thanhly, "Thanh lý", np.where(mask_sale, "Sale", "Nguyên giá"))

        group_cols = [
            "Kho_Xuat", "MaCH_XUAT", "MaCH_NHAP", "Store_name", "Region", "Warehouse",
            "Month", "Quarter", "Year", "Brand", "Report_item_name", "MaHang",
            "Don_gia", "Sale", "Status", "Product_type", "Gender", "Product_group", "Group_Report",
        ]
        df_grouped = (df.groupby(group_cols, dropna=False)
                        .agg(SoLuong=("SoLuong", "sum"), Tri_gia=("Tri_gia", "sum"))
                        .reset_index())
        df_grouped = df_grouped[group_cols[:12] + ["SoLuong", "Don_gia", "Tri_gia"] + group_cols[13:]]

        print(f"NhapTrungChuyen_CHNHN — {len(df_grouped):,} dòng nhóm | Tổng SoLuong: {df_grouped['SoLuong'].sum():,.0f}"
              f" | Tổng Trị giá: {df_grouped['Tri_gia'].sum():,.0f}")
        return df_grouped


if __name__ == "__main__":
    # Chay doc lap file nay (vd bam Run trong VS Code)
    NhapTrungChuyenCHNHNProcessor().run()

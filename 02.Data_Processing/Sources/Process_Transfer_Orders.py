# -*- coding: utf-8 -*-
"""Lệnh Điều chuyển hàng hóa (HH_LuanChuyen)."""
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
from Read_Write_Parquet import load_master_table
import Get_Paths
from Convert_Size import actual_size

RAW_COLS = [
    "Ngày", "Cửa hàng chuyển", "Mahang", "Tenhang", "MaMau",
    "tac_nghiep", "Size", "SL_chuyển", "Cửa hàng nhận", "Note",
]

# Chuẩn hóa tên cột tiếng Việt sang tiếng Anh, đồng bộ với các script khác
# (NgayChungTu, MaHang, TenHang, Operation, Store_name...)
RENAME_MAP = {
    "Ngày": "NgayChungTu",
    "Cửa hàng chuyển": "Store_from",
    "Cửa hàng nhận": "Store_to",
    "Mahang": "MaHang",
    "Tenhang": "TenHang",
    "tac_nghiep": "Operation",
    "SL_chuyển": "Qty_Chuyen",
}


def robust_read_excel(path: str, progress_label: str = "") -> pd.DataFrame:
    """Đọc 1 file điều chuyển (.xlsx), giữ Mahang/MaMau/Size/tac_nghiep dạng chuỗi
    để không mất số 0 đứng đầu."""
    df = pd.read_excel(
        path,
        sheet_name=0,
        engine="openpyxl",
        dtype={"Mahang": str, "MaMau": str, "Size": str, "tac_nghiep": str},
    )
    df.columns = [" ".join(str(c).strip().split()) for c in df.columns]
    missing = [c for c in RAW_COLS if c not in df.columns]
    if missing:
        print(f"  [WARN] {os.path.basename(path)} thiếu cột: {missing}")
        for c in missing:
            df[c] = np.nan
    df = df[RAW_COLS]

    fname = os.path.basename(path)
    prefix = f"Đang đọc file {progress_label}: " if progress_label else ""
    print(f"  {prefix}{fname} | Tổng dòng file: {len(df):,}")
    return df


class LenhLuanChuyenProcessor(MonthlySourceProcessor):
    source_dir = Get_Paths.hhlc_o_mang
    file_glob = os.path.join("**", "*.xlsx")
    output_dir_name = "07.Lenh_HHLC"
    file_prefix = "KQ_HHLC"
    label = "HH_LuanChuyen"

    def _files(self) -> list[str]:
        return [f for f in super()._files() if not os.path.basename(f).startswith("~$")]

    def load_lookups(self):
        return {"d_category": load_master_table("D_Category")}

    def read_files(self, files: list[str]) -> pd.DataFrame:
        total_files = len(files)
        dfs = [robust_read_excel(f, progress_label=f"{i}/{total_files}") for i, f in enumerate(files, 1)]
        df = pd.concat(dfs, ignore_index=True)
        df = df.rename(columns=RENAME_MAP)
        print(f"\n  >>> Tổng số dòng đọc được từ {total_files} file: {len(df):,}")
        return df

    def transform(self, df: pd.DataFrame, lookups) -> pd.DataFrame:
        d_category = lookups["d_category"]

        # NgayChungTu -> Year/Month/Quarter (phân theo ngày thực tế trong dữ liệu, không theo tên thư mục nguồn)
        df["NgayChungTu"] = pd.to_datetime(df["NgayChungTu"], errors="coerce")
        df["Month"] = df["NgayChungTu"].dt.month
        df["Year"] = df["NgayChungTu"].dt.year
        df = df.dropna(subset=["Year", "Month"]).copy()
        df["Year"] = df["Year"].astype(int)
        df["Month"] = df["Month"].astype(int)
        df["Quarter"] = "Q" + np.ceil(df["Month"] / 3).astype(int).astype(str) + "." + df["Year"].astype(str)

        # Qty_Chuyen -> số
        df["Qty_Chuyen"] = pd.to_numeric(df["Qty_Chuyen"], errors="coerce").fillna(0)

        # Report_item_name — tra theo Short_name (MaHang bỏ 4 ký tự cuối)
        mahang_str = df["MaHang"].astype(str).str.strip()
        df["Short_name"] = mahang_str.apply(lambda x: x[:-4] if len(x) >= 4 else x)
        df = df.merge(
            d_category[["Short_name", "Report_item_name"]].drop_duplicates("Short_name"),
            on="Short_name", how="left",
        )
        df = df.drop(columns=["Short_name"], errors="ignore")

        # Chuẩn hóa Size theo SIZE_MAP (Report_item_name phải có trước để biết hàng Nữ/Jupe/Váy)
        df["Size"] = [actual_size(sz, name) for sz, name in zip(df["Size"], df["Report_item_name"])]

        final_cols = [
            "NgayChungTu", "Year", "Month", "Quarter", "Store_from", "Store_to",
            "MaHang", "Report_item_name", "Operation", "Size", "Qty_Chuyen", "Note",
        ]
        df = df[final_cols]

        print(f"HH_LuanChuyen — {len(df):,} dòng | Tổng Qty_Chuyen: {df['Qty_Chuyen'].sum():,.0f}")
        return df


if __name__ == "__main__":
    # Chay doc lap file nay (vd bam Run trong VS Code)
    LenhLuanChuyenProcessor().run()

# -*- coding: utf-8 -*-
"""Kho Xuất CH (KhoXuat_CH)."""
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


def _read_csv_tolerant(path: str, enc: str):
    """Đọc thủ công từng dòng theo dấu phẩy. Từ cột Noidung trở đi không cần
    escape dấu phẩy nữa — toàn bộ phần còn lại của dòng (kể cả dấu phẩy dư)
    được gộp nguyên vào cột Noidung, không tách và không có cột nào sau nó."""
    with open(path, encoding=enc) as fh:
        lines = fh.read().splitlines()
    if not lines:
        return pd.DataFrame(), 0

    header = [h.strip() for h in lines[0].split(",")]
    idx_noidung = header.index("Noidung") if "Noidung" in header else len(header) - 1
    header = header[: idx_noidung + 1]

    rows = []
    n_short = 0
    for line in lines[1:]:
        if line == "":
            continue
        fields = line.split(",", idx_noidung)
        if len(fields) <= idx_noidung:
            n_short += 1
            fields += [""] * (idx_noidung + 1 - len(fields))
        rows.append(fields)

    df = pd.DataFrame(rows, columns=header)
    return df, n_short


def robust_read_csv(path: str, progress_label: str = "") -> pd.DataFrame:
    """Đọc tệp CSV với các bảng mã hóa khác nhau (ưu tiên utf-16 cho định dạng xuất kho)."""
    encodings_try = ["utf-16", "utf-8-sig", "utf-8", "cp1258", "latin1"]
    last_err = None
    for enc in encodings_try:
        try:
            n_bad = 0
            try:
                df = pd.read_csv(path, encoding=enc, low_memory=False, index_col=False)
            except pd.errors.ParserError:
                df, n_bad = _read_csv_tolerant(path, enc)
            # Clean column names (bỏ khoảng trắng thừa và BOM)
            df.columns = [" ".join(str(c).replace("\ufeff", "").strip().split()) for c in df.columns]
            # Bỏ các cột thừa nằm sau cột Noidung (rác từ dấu phẩy dư/cột không tên)
            if "Noidung" in df.columns:
                df = df.iloc[:, : df.columns.get_loc("Noidung") + 1]
            fname = os.path.basename(path)
            prefix = f"Đang đọc file {progress_label}: " if progress_label else ""
            print(f"  {prefix}{fname} ({enc}) | Tổng dòng file: {len(df):,}")
            if n_bad:
                print(f"  [WARN] {n_bad} dòng thiếu field (đã bổ sung rỗng) trong {fname}")
            return df
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"Could not read {path}. Last error: {last_err}")


def _extract_kho_xuat(x):
    x = str(x).strip()
    if "/" in x and "-" in x:
        start = x.find("/") + 1
        end = x.find("-", start)
        if end != -1:
            return x[start:end]
    return "UNKNOWN"


class KhoXuatCHProcessor(MonthlySourceProcessor):
    source_dir = Get_Paths.nguon_kho_xuat_ch
    output_dir_name = "06.KhoXuat_CH"
    file_prefix = "KhoXuat_CH"
    label = "KhoXuat_CH"

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

        # Trích xuất mã KhoXuat từ SoChungTu (lấy phần nằm giữa '/' và '-')
        if "SoChungTu" in df.columns:
            df['KhoXuat'] = df['SoChungTu'].apply(_extract_kho_xuat)
        else:
            df['KhoXuat'] = "UNKNOWN"

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

        # 2. A_Region dựa trên cửa hàng nhận TenCH_NHAP khớp với Store_name trong A_Region
        if "TenCH_NHAP" in df.columns:
            df = df.merge(
                a_region[['Store_name', 'Region', 'Warehouse']],
                left_on='TenCH_NHAP',
                right_on='Store_name',
                how='left',
            )
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

        # Phân nhóm Status theo cột Sale
        df['Status'] = np.where(df['Sale'].isin([30, 50]), "Sale", "Nguyên giá")

        # Rename TacNghiep thành Operation
        if 'TacNghiep' in df.columns:
            df = df.rename(columns={'TacNghiep': 'Operation'})
        else:
            df['Operation'] = np.nan

        group_cols = [
            "LyDo", "KhoXuat", "TenCH_NHAP", "Region", "Warehouse",
            "Month", "Quarter", "Year", "Brand", "Report_item_name", "MaHang",
            "Operation", "Size", "Sale", "Status", "Product_type", "Gender",
            "Product_group", "Group_Report",
        ]
        for c in group_cols:
            if c not in df.columns:
                df[c] = np.nan

        df_grouped = df.groupby(group_cols, dropna=False).agg(SoLuong=('SoLuong', 'sum')).reset_index()

        final_cols = [
            "LyDo", "KhoXuat", "TenCH_NHAP", "Region", "Warehouse",
            "Month", "Quarter", "Year", "Brand", "Report_item_name", "MaHang",
            "Operation", "Size", "SoLuong", "Sale", "Status", "Product_type",
            "Gender", "Product_group", "Group_Report",
        ]
        df_grouped = df_grouped[final_cols]

        print(f"KhoXuat_CH — {len(df_grouped):,} dòng nhóm | Tổng SoLuong: {df_grouped['SoLuong'].sum():,.0f}")
        return df_grouped


if __name__ == "__main__":
    # Chay doc lap file nay (vd bam Run trong VS Code)
    KhoXuatCHProcessor().run()

# -*- coding: utf-8 -*-
"""Dữ liệu cấp BILL cho báo cáo quý (Report_Quarter).

Parquet System_sales (03.Data_Parquest/01.System_sales) đã GỘP theo mặt hàng/ngày nên mất
số chứng từ (SoChungTu), giờ bán và tổng tiền bill -> không đếm được bill / khung giờ.
Module này đọc thẳng file thô Baocao_BanHang_<từ>_<đến>.csv (01.Source/01.System_sales),
dùng lại robust_read_csv + extract_ma_ch của 02.Data_Processing/Sources/Process_Sales.py
(chỉ import, không sửa), rồi rút gọn về 1 dòng / 1 bill và lưu cache theo tháng:

    04.Output/Report_Quarter/Bill_Cache/<YYYY>/Bills_<MM>.parquet

Cache được GỘP (không ghi đè) theo SoChungTu, nên file tải theo nửa tháng / tải lại vẫn đúng.
File thô đã đọc được ghi vào _Processed_Files.csv để lần sau bỏ qua (đổi kích thước/ngày
sửa file thì đọc lại).

Định nghĩa (khớp logic lọc của Process_Sales.py):
  - 1 bill = 1 SoChungTu có ít nhất 1 dòng "Bán" hợp lệ
    (Nội dung = "Bán", Product_type không phải Bao Bì / Đồng Phục, Brand không phải
     Dv In Theu / Khác). "Bán phiếu tặng" (bán voucher, chứng từ -PT) KHÔNG tính là bill.
  - Giá trị bill = Tongtien (tổng tiền khách trả của cả chứng từ, đã trừ Sale % và CK VIP;
    cột này lặp lại giống nhau trên mọi dòng của 1 chứng từ).
  - Giờ bill = giờ trong NgayChungTu (M/D/YYYY h:mm:ss AM/PM).
  - Nhãn hàng trong bill (SL_* = số lượng, TT_* = tổng ThanhTien dòng Bán, sau Sale % trước CK VIP):
      FLD = Anamai + Bonjour, PIE = Pierre Cardin (đều kể cả HTT), AP = các hiệu còn lại
      (An Phước, An Phước Ladies, Gerb Weis, Tomiya...).
  - Từng hiệu (HTT gộp vào hiệu chính cùng tên): SLH_<mã> / TTH_<mã>, mã theo HIEU
    (APN = An Phước, APL = An Phước Ladies, PIE, ANA = Anamai, BON = Bonjour, KHAC).
"""
from __future__ import annotations

import glob
import io
import os
import sys

import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))                    # Report_Quarter
PROJECTS_ROOT = os.path.dirname(os.path.dirname(PROJECT_DIR))                # 01.Python_Projects
for _p in (
    os.path.join(PROJECTS_ROOT, "00.Shared"),
    os.path.join(PROJECTS_ROOT, "02.Data_Processing"),
    os.path.join(PROJECTS_ROOT, "02.Data_Processing", "Sources"),
):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import Get_Paths  # noqa: E402
from Read_Write_Parquet import load_master_table  # noqa: E402


def _import_process_sales():
    """Process_Sales.py bọc lại sys.stdout khi encoding != 'utf-8' (Jupyter báo 'UTF-8' và
    OutStream không có .buffer) -> tạm thay stdout bằng 1 stream utf-8 giả khi import."""
    real_stdout = sys.stdout
    sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    try:
        import Process_Sales
    finally:
        sys.stdout = real_stdout
    return Process_Sales


_ps = _import_process_sales()
robust_read_csv = _ps.robust_read_csv
extract_ma_ch = _ps.extract_ma_ch

OUTPUT_DIR = Get_Paths.thu_muc_ket_qua("Report_Quarter")
CACHE_DIR = os.path.join(OUTPUT_DIR, "Bill_Cache")
MANIFEST = os.path.join(CACHE_DIR, "_Processed_Files.csv")

THU_VN = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "CN"]

# Từng hiệu (Brand trong D_Category bỏ "Hiệu " và " HTT" -> HTT gộp vào hiệu chính cùng tên)
# mã cột -> tên hiệu; hiệu khác (Gerb Weis, Tomiya, Thanh Lý...) vào "KHAC"
HIEU = {"APN": "An Phước", "APL": "An Phước Ladies", "PIE": "Pierre Cardin",
        "ANA": "Anamai", "BON": "Bonjour", "KHAC": "Hiệu khác"}

BILL_COLS = [
    "SoChungTu", "Store_code", "Store_name", "Region", "Warehouse",
    "NgayGio", "Ngay", "Gio", "Thu", "Year", "Month", "Quarter", "Tongtien", "SL_Ban",
    "SL_AP", "SL_PIE", "SL_FLD", "TT_AP", "TT_PIE", "TT_FLD",
] + [f"SLH_{m}" for m in HIEU] + [f"TTH_{m}" for m in HIEU]


def _to_num(s: pd.Series) -> pd.Series:
    """Giống Process_Sales: bỏ ký tự lạ, ',' -> '.'."""
    return pd.to_numeric(
        s.astype(str).str.replace(r"[^\d\-,\.]", "", regex=True).str.replace(",", "."),
        errors="coerce",
    )


def _parse_datetime(s: pd.Series) -> pd.Series:
    raw = s.astype(str).str.strip()
    dt = pd.to_datetime(raw, format="%m/%d/%Y %I:%M:%S %p", errors="coerce")
    miss = dt.isna()
    if miss.any():  # phòng file xuất dạng 24h
        dt.loc[miss] = pd.to_datetime(raw[miss], format="%m/%d/%Y %H:%M:%S", errors="coerce")
    return dt


def raw_to_bills(df: pd.DataFrame, a_region: pd.DataFrame, d_category: pd.DataFrame) -> pd.DataFrame:
    """DataFrame thô (1 dòng / 1 mặt hàng) -> 1 dòng / 1 bill."""
    df = df.copy()
    df["Nội dung"] = df["DienGiai"].astype(str).str.split(":", n=1).str[0].str.strip()
    df["Short_name"] = df["MaHang"].astype(str).str.strip().apply(lambda x: x[:-4] if len(x) >= 4 else x)
    df = df.merge(d_category[["Short_name", "Brand", "Product_type"]].drop_duplicates("Short_name"),
                  on="Short_name", how="left")

    valid_ban = (
        (df["Nội dung"] == "Bán")
        & ~df["Product_type"].isin(["Bao Bì", "Đồng Phục"])
        & ~df["Brand"].isin(["Dv In Theu", "Khác"])
    )
    df["SL_Ban"] = np.where(valid_ban, _to_num(df["SoLuong"]).fillna(0), 0)
    df["Tongtien"] = _to_num(df["Tongtien"])
    df["_valid"] = valid_ban
    # Nhãn hàng: FLD = Anamai + Bonjour; PIE = Pierre Cardin (đều kể cả HTT); AP = các hiệu còn lại
    brand = df["Brand"].astype(str)
    is_fld = brand.str.contains("Anamai|Bonjour", case=False, na=False)
    is_pie = brand.str.contains("Pierre Cardin", case=False, na=False)
    is_ap = ~is_fld & ~is_pie
    tt = _to_num(df["ThanhTien"]).fillna(0)                   # tiền dòng (sau Sale %, trước CK VIP)
    for nhan, mask in (("AP", is_ap), ("PIE", is_pie), ("FLD", is_fld)):
        df[f"SL_{nhan}"] = np.where(valid_ban & mask, df["SL_Ban"], 0)
        df[f"TT_{nhan}"] = np.where(valid_ban & mask, tt, 0)
    # Từng hiệu: SLH_<mã> = số lượng, TTH_<mã> = ThanhTien
    ten_hieu = brand.str.replace("Hiệu ", "", regex=False).str.replace(" HTT", "", regex=False).str.strip()
    ma_hieu = ten_hieu.map({v: k for k, v in HIEU.items()}).fillna("KHAC")
    for m in HIEU:
        df[f"SLH_{m}"] = np.where(valid_ban & (ma_hieu == m), df["SL_Ban"], 0)
        df[f"TTH_{m}"] = np.where(valid_ban & (ma_hieu == m), tt, 0)

    bills = df.groupby("SoChungTu", sort=False).agg(
        **{c: (c, "sum") for c in [f"SLH_{m}" for m in HIEU] + [f"TTH_{m}" for m in HIEU]},
        NgayChungTu=("NgayChungTu", "first"),
        Tongtien=("Tongtien", "first"),
        SL_Ban=("SL_Ban", "sum"),
        SL_AP=("SL_AP", "sum"),
        SL_PIE=("SL_PIE", "sum"),
        SL_FLD=("SL_FLD", "sum"),
        TT_AP=("TT_AP", "sum"),
        TT_PIE=("TT_PIE", "sum"),
        TT_FLD=("TT_FLD", "sum"),
        _valid=("_valid", "any"),
    ).reset_index()
    bills = bills[bills["_valid"]].drop(columns="_valid")

    bills["NgayGio"] = _parse_datetime(bills["NgayChungTu"])
    n_bad = int(bills["NgayGio"].isna().sum())
    if n_bad:
        print(f"  [WARN] {n_bad:,} bill không parse được ngày giờ -> bỏ.")
    bills = bills[bills["NgayGio"].notna()].drop(columns="NgayChungTu")

    bills["Store_code"] = bills["SoChungTu"].apply(extract_ma_ch)
    bills = bills.merge(a_region[["Store_code", "Store_name", "Region", "Warehouse"]].drop_duplicates("Store_code"),
                        on="Store_code", how="left")
    bills["Region"] = bills["Region"].fillna("Không xác định")
    bills["Store_name"] = bills["Store_name"].fillna(bills["Store_code"])

    bills["Ngay"] = bills["NgayGio"].dt.normalize()
    bills["Gio"] = bills["NgayGio"].dt.hour
    bills["Thu"] = bills["NgayGio"].dt.dayofweek          # 0 = Thứ 2 ... 6 = CN
    bills["Year"] = bills["NgayGio"].dt.year
    bills["Month"] = bills["NgayGio"].dt.month
    bills["Quarter"] = "Q" + ((bills["Month"] - 1) // 3 + 1).astype(str) + "." + bills["Year"].astype(str)
    return bills[BILL_COLS]


def _cache_path(year: int, month: int) -> str:
    return os.path.join(CACHE_DIR, str(year), f"Bills_{month:02d}.parquet")


def _save_month(df_month: pd.DataFrame, year: int, month: int) -> int:
    path = _cache_path(year, month)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        df_month = pd.concat([pd.read_parquet(path), df_month], ignore_index=True)
    df_month = df_month.drop_duplicates("SoChungTu", keep="last").sort_values("NgayGio")
    df_month.to_parquet(path, index=False)
    return len(df_month)


def _load_manifest() -> pd.DataFrame:
    if os.path.exists(MANIFEST):
        return pd.read_csv(MANIFEST, encoding="utf-8-sig")
    return pd.DataFrame(columns=["file", "size", "mtime"])


def update_bill_cache(raw_dirs: list[str], force: bool = False) -> None:
    """Đọc các file Baocao_BanHang_*.csv mới trong raw_dirs -> cập nhật cache bill theo tháng."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    manifest = _load_manifest()
    seen = set(zip(manifest["file"], manifest["size"].astype("int64"), manifest["mtime"].astype(float).round(0)))

    files = []
    for d in raw_dirs:
        files += glob.glob(os.path.join(d, "*.csv"))   # Baocao_BanHang_*.csv, Bao cao chi tiet ban hang*.csv...
    todo = []
    for f in sorted(set(files)):
        st = os.stat(f)
        key = (os.path.basename(f), int(st.st_size), round(st.st_mtime, 0))
        if force or key not in seen:
            todo.append((f, key))

    print(f"Tìm thấy {len(files)} file thô, cần đọc mới: {len(todo)}")
    if not todo:
        return

    a_region = load_master_table("A_Region")
    d_category = load_master_table("D_Category")
    new_rows = []
    for i, (f, key) in enumerate(todo, 1):
        raw = robust_read_csv(f, progress_label=f"{i}/{len(todo)}")
        bills = raw_to_bills(raw, a_region, d_category)
        for (y, m), g in bills.groupby(["Year", "Month"]):
            n = _save_month(g, int(y), int(m))
            print(f"    -> cache {y}-{m:02d}: +{len(g):,} bill (tổng tháng sau gộp: {n:,})")
        new_rows.append({"file": key[0], "size": key[1], "mtime": key[2]})

    new_df = pd.DataFrame(new_rows)
    manifest = new_df if manifest.empty else pd.concat([manifest, new_df], ignore_index=True)
    manifest = manifest.drop_duplicates("file", keep="last")
    manifest.to_csv(MANIFEST, index=False, encoding="utf-8-sig")


def quarter_months(quarter: str) -> list[tuple[int, int]]:
    """'Q3.2026' -> [(2026, 7), (2026, 8), (2026, 9)]"""
    q, y = quarter.upper().lstrip("Q").split(".")
    q, y = int(q), int(y)
    return [(y, 3 * (q - 1) + i) for i in (1, 2, 3)]


def previous_quarter(quarter: str) -> str:
    q, y = quarter.upper().lstrip("Q").split(".")
    q, y = int(q), int(y)
    return f"Q4.{y - 1}" if q == 1 else f"Q{q - 1}.{y}"


def same_quarter_last_year(quarter: str) -> str:
    q, y = quarter.upper().lstrip("Q").split(".")
    return f"Q{int(q)}.{int(y) - 1}"


def load_quarters(quarters: list[str]) -> pd.DataFrame:
    """Đọc cache bill của các quý; in cảnh báo tháng thiếu / thiếu ngày."""
    parts = []
    for qtr in quarters:
        for y, m in quarter_months(qtr):
            path = _cache_path(y, m)
            if not os.path.exists(path):
                print(f"  [THIẾU] {qtr}: chưa có dữ liệu bill tháng {m:02d}/{y}")
                continue
            df = pd.read_parquet(path)
            n_days = df["Ngay"].nunique()
            days_in_month = pd.Period(f"{y}-{m:02d}").days_in_month
            flag = "" if n_days >= days_in_month else f"  [CHƯA ĐỦ: {n_days}/{days_in_month} ngày]"
            print(f"  {qtr} | {m:02d}/{y}: {len(df):>9,} bill | {df['Ngay'].min():%d/%m} -> {df['Ngay'].max():%d/%m}{flag}")
            parts.append(df)
    if not parts:
        return pd.DataFrame(columns=BILL_COLS)
    return pd.concat(parts, ignore_index=True)

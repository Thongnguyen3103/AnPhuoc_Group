# -*- coding: utf-8 -*-
import os
import glob
import pandas as pd
import numpy as np
import csv
import sys
import io
import duckdb

# Set stdout encoding to UTF-8
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

SYSTEM_SALES_DIR = r"\\hovmfs01\PKD\PhanPhoi\Thong.Nguyen\Analysis_data\2.System_sales"
CONTRACT_SALES_DIR = r"\\hovmfs01\PKD\PhanPhoi\Thong.Nguyen\Analysis_data\3.Contract_sales"
DB_PATH = r"D:\DataBase\DuckDB\Database_AP.duckdb"

def upsert_by_month(con: duckdb.DuckDBPyConnection, table_name: str, df: pd.DataFrame) -> str:
    """Upsert theo (Year, Month): xóa các tháng có trong df rồi insert lại.
    Nếu bảng chưa tồn tại thì tạo mới."""
    table_exists = con.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?",
        [table_name],
    ).fetchone()[0] > 0

    con.register("_new_data", df)

    if not table_exists:
        con.execute(f'CREATE TABLE "{table_name}" AS SELECT * FROM _new_data')
        msg = "Tạo mới"
    else:
        periods = (
            df[["Year", "Month"]]
            .dropna()
            .drop_duplicates()
            .astype({"Year": int, "Month": int})
        )
        if len(periods) > 0:
            con.register("_periods", periods)
            con.execute(
                f'DELETE FROM "{table_name}" '
                f'WHERE (CAST("Year" AS INTEGER), CAST("Month" AS INTEGER)) '
                f'IN (SELECT "Year", "Month" FROM _periods)'
            )
            con.unregister("_periods")
        con.execute(f'INSERT INTO "{table_name}" SELECT * FROM _new_data')
        period_list = ", ".join(
            f"{int(r.Year)}/{int(r.Month):02d}" for r in periods.itertuples()
        )
        msg = f"Cập nhật {len(periods)} tháng [{period_list}]"

    con.unregister("_new_data")
    return msg


def parse_date(series: pd.Series, fmt: str) -> pd.Series:
    """Parse cột ngày với format tường minh, bỏ qua phần giờ nếu có.
    fmt ví dụ: '%m/%d/%Y' (system sales) hoặc '%d/%m/%Y' (contract sales)."""
    raw = series.astype(str).str.strip()
    date_str = raw.str.extract(r'(\d{1,2}/\d{1,2}/\d{4})', expand=False)
    result = pd.to_datetime(date_str, format=fmt, errors='coerce')
    failed = result.isna() & raw.ne('nan') & raw.ne('')
    n_failed = failed.sum()
    if n_failed:
        print(f"  [WARN] {n_failed} dòng không parse được NgayChungTu.")
    return result


def robust_read_csv(path: str) -> pd.DataFrame:
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
            
            df = pd.read_csv(path, sep=delimiter, encoding=enc, dtype=str, on_bad_lines='skip')
            df.columns = [" ".join(str(c).replace("\ufeff", "").strip().split()) for c in df.columns]
            return df
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"Could not read {path}. Last error: {last_err}")

def load_db():
    print("Loading database...")
    con = duckdb.connect(DB_PATH, read_only=True)
    a_region = con.execute('SELECT * FROM "A_Region"').df().fillna("").astype(str)
    e_tshirt = con.execute('SELECT * FROM "E_T-Shirt"').df().fillna("").astype(str)
    d_category = con.execute('SELECT * FROM "D_Category"').df().fillna("").astype(str)
    b_size = con.execute('SELECT * FROM "B_Size"').df().fillna("").astype(str)
    con.close()
    return a_region, e_tshirt, d_category, b_size

def process_system_sales(a_region, e_tshirt, d_category, b_size):
    print("Processing System Sales...")
    files = glob.glob(os.path.join(SYSTEM_SALES_DIR, "*.csv"))
    if not files:
        print("No System Sales files found.")
        return
    
    dfs = []
    total_files = len(files)
    for i, f in enumerate(files, 1):
        print(f"\r  Đang đọc {i}/{total_files} file ({i/total_files*100:.1f}%)", end="", flush=True)
        df = robust_read_csv(f)
        dfs.append(df)
    print()
    
    if not dfs:
        return
        
    df = pd.concat(dfs, ignore_index=True)
    
    # Cast numbers
    num_cols = ["SoLuong", "DonGia", "ThueVat", "ThanhTien", "Sales"]
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c].astype(str).str.replace(r'[^\d\-,\.]', '', regex=True).str.replace(',', '.'), errors='coerce')
    
    if "NgayChungTu" in df.columns:
        # System sales: MM/DD/YYYY HH:MM:SS
        df['NgayChungTu'] = parse_date(df['NgayChungTu'], '%m/%d/%Y')
        df['Month'] = df['NgayChungTu'].dt.month
        df['Year']  = df['NgayChungTu'].dt.year
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
        
    if "TenCuaHang" in df.columns:
        df = df.rename(columns={'TenCuaHang': 'Store_name'})
    else:
        df['Store_name'] = ""
    df = df.merge(a_region[['Store_name', 'Region', 'Warehouse']], on='Store_name', how='left')
    df = df.merge(e_tshirt[['item_code', 'T-shirt_name']], left_on='MaHang', right_on='item_code', how='left')
    df = df.merge(d_category[['Short_name', 'Brand', 'System_item_name', 'Report_item_name', 'Product_type', 'Gender', 'Product_group', 'Group_Report']], on='Short_name', how='left')
    
    if 'T-shirt_name' in df.columns and 'Report_item_name' in df.columns:
        df['Report_item_name'] = np.where(df['T-shirt_name'].notna() & (df['T-shirt_name'] != ""), df['T-shirt_name'], df['Report_item_name'])
    df = df.drop(columns=['T-shirt_name', 'item_code'], errors='ignore')
    
    # Filter rows
    cond_noidung = df["Nội dung"].str.strip().isin(["Bán", "Tặng", "Đổi"])
    cond_product = ~df["Product_type"].isin(["Bao bì", "Đồng phục"])
    df = df[cond_noidung & cond_product]
    
    # Status
    mask_thanhly = df['Product_type'].astype(str).str.contains("Thanh lý", case=False, na=False)
    mask_sale = df['Sales'].isin([30, 50])
    df['Status'] = np.where(mask_thanhly, "Thanh lý", np.where(mask_sale, "Sale", "Nguyên giá"))
    
    # Size logic
    if 'Report_item_name' not in df.columns:
        df['Report_item_name'] = np.nan
    if 'Size' not in df.columns:
        df['Size'] = np.nan
        
    b_size_lookup = b_size[['System_item_name', 'System_size', 'Actual_size']].drop_duplicates()
    df = df.merge(b_size_lookup, left_on=['Report_item_name', 'Size'], right_on=['System_item_name', 'System_size'], how='left')
    
    df['Size'] = np.where(df['Actual_size'].notna() & (df['Actual_size'] != ""), df['Actual_size'], df['Size'])
    df = df.drop(columns=['System_item_name_y', 'System_size', 'Actual_size'], errors='ignore')
    if 'System_item_name_x' in df.columns:
        df = df.rename(columns={'System_item_name_x': 'System_item_name'})
        
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
    
    # Group By
    group_cols = [
        "Store_name", "Month", "Quarter", "Year", "MaHang", "Operation", "Region", "Warehouse",
        "Brand", "Product_type", "Gender", "Product_group", "Report_item_name", "Status",
        "Size", "Group_Report", "Nội dung", "Sales _Type",
    ]
    # Ensure columns exist
    for c in group_cols:
        if c not in df.columns:
            df[c] = np.nan

    df_grouped = df.groupby(group_cols, dropna=False).agg(Qty_Ban=('Slg_Ban', 'sum')).reset_index()

    final_cols = [
        "Store_name", "Region", "Warehouse", "Month", "Quarter", "Year", "Brand", "Report_item_name",
        "MaHang", "Operation", "Size", "Qty_Ban", "Nội dung", "Status", "Product_type", "Gender", "Product_group",
        "Group_Report", "Sales _Type",
    ]
    
    for c in final_cols:
        if c not in df_grouped.columns:
            df_grouped[c] = np.nan
    df_grouped = df_grouped[final_cols]

    con = duckdb.connect(DB_PATH)
    msg = upsert_by_month(con, "System_sales", df_grouped)
    con.close()
    print(f"System_sales — {msg}: {len(df_grouped):,} dong")

def process_contract_sales(a_region, e_tshirt, d_category, b_size):
    print("Processing Contract Sales...")
    files = glob.glob(os.path.join(CONTRACT_SALES_DIR, "*.csv"))
    if not files:
        print("No Contract Sales files found.")
        return
        
    dfs = []
    total_files = len(files)
    for i, f in enumerate(files, 1):
        print(f"\r  Đang đọc {i}/{total_files} file ({i/total_files*100:.1f}%)", end="", flush=True)
        df = robust_read_csv(f)
        dfs.append(df)
    print()
        
    if not dfs:
        return
        
    df = pd.concat(dfs, ignore_index=True)
    
    if "SoLuong" in df.columns:
        df["SoLuong"] = pd.to_numeric(df["SoLuong"].astype(str).str.replace(r'[^\d\-,\.]', '', regex=True).str.replace(',', '.'), errors='coerce')
    if "Sale" in df.columns:
        df["Sale"] = pd.to_numeric(df["Sale"].astype(str).str.replace(r'[^\d\-,\.]', '', regex=True).str.replace(',', '.'), errors='coerce')
        
    if "NgayChungTu" in df.columns:
        # Contract sales: DD/MM/YYYY
        df['NgayChungTu'] = parse_date(df['NgayChungTu'], '%d/%m/%Y')
        df['Month'] = df['NgayChungTu'].dt.month
        df['Year']  = df['NgayChungTu'].dt.year
        valid_dates = df['Month'].notna() & df['Year'].notna()
        df['Quarter'] = pd.Series(dtype=object)
        df.loc[valid_dates, 'Quarter'] = (
            "Q" + np.ceil(df.loc[valid_dates, 'Month'] / 3).astype(int).astype(str)
            + "." + df.loc[valid_dates, 'Year'].astype(int).astype(str)
        )

    def extract_ma_ch(x):
        x = str(x)
        if "/" in x and "-" in x:
            start = x.find("/") + 1
            end = x.find("-", start)
            if end != -1:
                return x[start:end]
        return np.nan
        
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
        
    b_size_lookup = b_size[['System_item_name', 'System_size', 'Actual_size']].drop_duplicates()
    df = df.merge(b_size_lookup, left_on=['Report_item_name', 'Size'], right_on=['System_item_name', 'System_size'], how='left')
    
    df['Size'] = np.where(df['Actual_size'].notna() & (df['Actual_size'] != ""), df['Actual_size'], df['Size'])
    df = df.drop(columns=['System_item_name_y', 'System_size', 'Actual_size'], errors='ignore')
    if 'System_item_name_x' in df.columns:
        df = df.rename(columns={'System_item_name_x': 'System_item_name'})
        
    mask_sale = df['Sale'].isin([30, 50])
    df['Status'] = np.where(mask_sale, "Sale", "Nguyên giá")
    
    if 'TacNghiep' in df.columns:
        df = df.rename(columns={'TacNghiep': 'Operation'})
    else:
        df['Operation'] = np.nan

    df['Sales _Type'] = pd.Series(dtype=object)
    df.loc[df['MaHang'].notna() & (df['MaHang'] != ""), 'Sales _Type'] = "Contract"
    
    group_cols = [
        "MaHang", "Operation", "Month", "Quarter", "Year", "Store_name", "Region", "Warehouse",
        "Brand", "Report_item_name", "Product_type", "Gender", "Product_group", "Group_Report",
        "Size", "Status", "Sales _Type",
    ]

    for c in group_cols:
        if c not in df.columns:
            df[c] = np.nan

    df_grouped = df.groupby(group_cols, dropna=False).agg(Qty_Ban=('SoLuong', 'sum')).reset_index()

    final_cols = [
        "Store_name", "Region", "Warehouse", "Month", "Quarter", "Year", "Brand", "Report_item_name",
        "MaHang", "Operation", "Size", "Qty_Ban", "Status", "Product_type", "Gender", "Product_group",
        "Group_Report", "Sales _Type",
    ]
    for c in final_cols:
        if c not in df_grouped.columns:
            df_grouped[c] = np.nan
    df_grouped = df_grouped[final_cols]

    con = duckdb.connect(DB_PATH)
    msg = upsert_by_month(con, "Contract_sales", df_grouped)
    con.close()
    print(f"Contract_sales — {msg}: {len(df_grouped):,} dong")

if __name__ == "__main__":
    a_region, e_tshirt, d_category, b_size = load_db()
    process_system_sales(a_region, e_tshirt, d_category, b_size)
    process_contract_sales(a_region, e_tshirt, d_category, b_size)

# -*- coding: utf-8 -*-
import os
import glob
import pandas as pd
import numpy as np
import csv
import sys
import io

# Set stdout encoding to UTF-8
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

SYSTEM_SALES_DIR = r"\\hovmfs01\PKD\PhanPhoi\Thong.Nguyen\Analysis_data\2.System_sales"
CONTRACT_SALES_DIR = r"\\hovmfs01\PKD\PhanPhoi\Thong.Nguyen\Analysis_data\3.Contract_sales"
DB_PATH = r"\\hovmfs01\PKD\PhanPhoi\Thong.Nguyen\Analysis_data\1.Processed_data\1.Data_Tracking.xlsx"
OUTPUT_SYSTEM_DIR = r"D:\DataBase\1.System_sales"
OUTPUT_CONTRACT_DIR = r"D:\DataBase\2.Contract_sales"
OUTPUT_DM_DIR = r"Y:\BẢO TRÂN\DM"

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
    a_region = pd.read_excel(DB_PATH, sheet_name="A_Region", dtype=str)
    e_tshirt = pd.read_excel(DB_PATH, sheet_name="E_T-Shirt", dtype=str)
    d_category = pd.read_excel(DB_PATH, sheet_name="D_Category", dtype=str)
    b_size = pd.read_excel(DB_PATH, sheet_name="B_Size", dtype=str)
    f_datatracking = pd.read_excel(DB_PATH, sheet_name="F_DataTracking", dtype=str)
    return a_region, e_tshirt, d_category, b_size, f_datatracking

def process_system_sales(a_region, e_tshirt, d_category, b_size, f_datatracking):
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
        df['NgayChungTu'] = pd.to_datetime(df['NgayChungTu'], errors='coerce', dayfirst=True)
        df['Month'] = df['NgayChungTu'].dt.month
        df['Year'] = df['NgayChungTu'].dt.year
        
        valid_dates = df['Month'].notna() & df['Year'].notna()
        df['Quarter'] = pd.Series(dtype=object)
        df.loc[valid_dates, 'Quarter'] = "Q" + np.ceil(df.loc[valid_dates, 'Month']/3).astype(int).astype(str) + "." + df.loc[valid_dates, 'Year'].astype(int).astype(str)
        
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
        
    df = df.merge(f_datatracking[['item_code', 'Operation', 'Color_group', 'Dist_plan', 'Form', 'Production_month', 'Production_year', 'Style','Attribute']], 
                  left_on=['MaHang', 'Operation'], right_on=['item_code', 'Operation'], how='left')
    df = df.drop(columns=['item_code'], errors='ignore')
        
    df = df.rename(columns={'SoLuong': 'Slg_Ban'})
    df['Sales _Type'] = pd.Series(dtype=object)
    df.loc[df['MaHang'].notna() & (df['MaHang'] != ""), 'Sales _Type'] = "Retail"
    
    # Filter Brand
    df = df[~df['Brand'].isin(["Dv In Theu", "Khác"])]
    
    # Group By
    group_cols = [
        "Store_name", "Month", "Quarter", "Year", "MaHang", "Operation", "Region", "Warehouse", 
        "Brand", "Product_type", "Gender", "Product_group", "Report_item_name", "Status", 
        "Size", "Dist_plan", "Production_month", "Production_year", "Sales _Type", 
        "Color_group", "Form", "Style","Attribute", "Group_Report", "Nội dung"
    ]
    # Ensure columns exist
    for c in group_cols:
        if c not in df.columns:
            df[c] = np.nan
            
    df_grouped = df.groupby(group_cols, dropna=False).agg(Qty_Ban=('Slg_Ban', 'sum')).reset_index()
    
    final_cols = [
        "Store_name", "Region", "Warehouse", "Month", "Quarter", "Year", "Brand", "Report_item_name",
        "MaHang", "Operation", "Size", "Qty_Ban", "Nội dung", "Status", "Product_type", "Gender", "Product_group",
        "Group_Report", "Color_group", "Form", "Style","Attribute", "Dist_plan", "Production_month", "Production_year", "Sales _Type"
    ]
    
    for c in final_cols:
        if c not in df_grouped.columns:
            df_grouped[c] = np.nan
    df_grouped = df_grouped[final_cols]
    
    os.makedirs(OUTPUT_SYSTEM_DIR, exist_ok=True)
    
    try:
        os.makedirs(OUTPUT_DM_DIR, exist_ok=True)
    except Exception as e:
        print(f"Warning: Could not create {OUTPUT_DM_DIR}: {e}")
        
    df_dm = df_grouped[df_grouped['Brand'].isin(['Hiệu An Phước', 'Hiệu Pierre Cardin'])]
    
    if 'Year' in df_grouped.columns:
        years = df_grouped['Year'].dropna().unique()
        for y in years:
            y_int = int(y)
            out_path = os.path.join(OUTPUT_SYSTEM_DIR, f"System_sales_{y_int}.csv")
            df_grouped[df_grouped['Year'] == y].to_csv(out_path, index=False, encoding='utf-8-sig')
            print(f"Exported System Sales for {y_int} to {out_path}")
            
            try:
                out_path_dm = os.path.join(OUTPUT_DM_DIR, f"System_sales_{y_int}.csv")
                df_dm[df_dm['Year'] == y].to_csv(out_path_dm, index=False, encoding='utf-8-sig')
                print(f"Exported System Sales (DM) for {y_int} to {out_path_dm}")
            except Exception as e:
                print(f"Warning: Could not export to {out_path_dm}: {e}")
    else:
        out_path = os.path.join(OUTPUT_SYSTEM_DIR, "System_sales_All_Years.csv")
        df_grouped.to_csv(out_path, index=False, encoding='utf-8-sig')
        print(f"Exported System Sales to {out_path}")
        
        try:
            out_path_dm = os.path.join(OUTPUT_DM_DIR, "System_sales_All_Years.csv")
            df_dm.to_csv(out_path_dm, index=False, encoding='utf-8-sig')
            print(f"Exported System Sales (DM) to {out_path_dm}")
        except Exception as e:
            print(f"Warning: Could not export to {out_path_dm}: {e}")

def process_contract_sales(a_region, e_tshirt, d_category, b_size, f_datatracking):
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
        df['NgayChungTu'] = pd.to_datetime(df['NgayChungTu'], errors='coerce', dayfirst=True)
        df['Month'] = df['NgayChungTu'].dt.month
        df['Year'] = df['NgayChungTu'].dt.year
        valid_dates = df['Month'].notna() & df['Year'].notna()
        df['Quarter'] = pd.Series(dtype=object)
        df.loc[valid_dates, 'Quarter'] = "Q" + np.ceil(df.loc[valid_dates, 'Month']/3).astype(int).astype(str) + "." + df.loc[valid_dates, 'Year'].astype(int).astype(str)
        
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
        
    df = df.merge(f_datatracking[['item_code', 'Operation', 'Color_group', 'Form', 'Style', 'Attribute', 'Dist_plan', 'Production_month', 'Production_year']], 
                  left_on=['MaHang', 'Operation'], right_on=['item_code', 'Operation'], how='left')
    df = df.drop(columns=['item_code'], errors='ignore')
        
    df['Sales _Type'] = pd.Series(dtype=object)
    df.loc[df['MaHang'].notna() & (df['MaHang'] != ""), 'Sales _Type'] = "Contract"
    
    group_cols = [
        "MaHang", "Operation", "Month", "Quarter", "Year", "Store_name", "Region", "Warehouse", 
        "Brand", "Report_item_name", "Product_type", "Gender", "Product_group", "Group_Report", 
        "Size", "Status", "Color_group", "Form", "Style", "Attribute", "Dist_plan", "Production_month", "Production_year", "Sales _Type"
    ]
    
    for c in group_cols:
        if c not in df.columns:
            df[c] = np.nan
            
    df_grouped = df.groupby(group_cols, dropna=False).agg(Qty_Ban=('SoLuong', 'sum')).reset_index()
    
    final_cols = [
        "Store_name", "Region", "Warehouse", "Month", "Quarter", "Year", "Brand", "Report_item_name", 
        "MaHang", "Operation", "Size", "Qty_Ban", "Status", "Product_type", "Gender", "Product_group", 
        "Group_Report", "Color_group", "Form", "Style", "Attribute","Dist_plan", "Production_month", "Production_year", "Sales _Type"
    ]
    for c in final_cols:
        if c not in df_grouped.columns:
            df_grouped[c] = np.nan
    df_grouped = df_grouped[final_cols]
    
    os.makedirs(OUTPUT_CONTRACT_DIR, exist_ok=True)
    
    try:
        os.makedirs(OUTPUT_DM_DIR, exist_ok=True)
    except Exception as e:
        print(f"Warning: Could not create {OUTPUT_DM_DIR}: {e}")
        
    df_dm = df_grouped[df_grouped['Brand'].isin(['Hiệu An Phước', 'Hiệu Pierre Cardin'])]
    
    if 'Year' in df_grouped.columns:
        years = df_grouped['Year'].dropna().unique()
        for y in years:
            y_int = int(y)
            out_path = os.path.join(OUTPUT_CONTRACT_DIR, f"Contract_sales_{y_int}.csv")
            df_grouped[df_grouped['Year'] == y].to_csv(out_path, index=False, encoding='utf-8-sig')
            print(f"Exported Contract Sales for {y_int} to {out_path}")
            
            try:
                out_path_dm = os.path.join(OUTPUT_DM_DIR, f"Contract_sales_{y_int}.csv")
                df_dm[df_dm['Year'] == y].to_csv(out_path_dm, index=False, encoding='utf-8-sig')
                print(f"Exported Contract Sales (DM) for {y_int} to {out_path_dm}")
            except Exception as e:
                print(f"Warning: Could not export to {out_path_dm}: {e}")
    else:
        out_path = os.path.join(OUTPUT_CONTRACT_DIR, "Contract_sales_All_Years.csv")
        df_grouped.to_csv(out_path, index=False, encoding='utf-8-sig')
        print(f"Exported Contract Sales to {out_path}")
        
        try:
            out_path_dm = os.path.join(OUTPUT_DM_DIR, "Contract_sales_All_Years.csv")
            df_dm.to_csv(out_path_dm, index=False, encoding='utf-8-sig')
            print(f"Exported Contract Sales (DM) to {out_path_dm}")
        except Exception as e:
            print(f"Warning: Could not export to {out_path_dm}: {e}")

if __name__ == "__main__":
    a_region, e_tshirt, d_category, b_size, f_datatracking = load_db()
    process_system_sales(a_region, e_tshirt, d_category, b_size, f_datatracking)
    process_contract_sales(a_region, e_tshirt, d_category, b_size, f_datatracking)

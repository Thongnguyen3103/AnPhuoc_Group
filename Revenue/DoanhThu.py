import os
import re
import sys
import glob
import functools
import csv
import duckdb
import pandas as pd
import numpy as np

sys.stdout.reconfigure(encoding='utf-8')

DATABASE_PATH = r"D:\DataBase\DuckDB\Report_AP.duckdb"

def robust_read_csv(path: str) -> pd.DataFrame:
    encodings_try = ["utf-8-sig", "utf-8", "cp1258", "cp1252", "latin1", "utf-16", "utf-16-le", "utf-16-be"]
    try:
        with open(path, "rb") as fb:
            raw = fb.read(50_000)
    except Exception as e:
        raise RuntimeError(f"Could not read raw file {path}: {e}")
        
    if not raw:
        raise RuntimeError(f"Empty file: {path}")
        
    prefer_utf16 = raw.count(b"\x00") > 100
    encodings = (["utf-16", "utf-16-le", "utf-16-be"] + encodings_try) if prefer_utf16 else encodings_try

    last_err = None
    for enc in encodings:
        try:
            sample = raw.decode(enc)
            if not sample:
                continue
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

@functools.lru_cache(maxsize=1)
def load_a_region_mapper() -> dict:
    db_path = r"\\hovmfs01\PKD\PhanPhoi\Thong.Nguyen\Analysis_data\1.Processed_data\1.Data_Tracking.xlsx"
    if not os.path.exists(db_path):
        print(f"\nWarning: Database file not found at {db_path}")
        return {}
        
    try:
        a_region = pd.read_excel(db_path, sheet_name="A_Region").fillna("").astype(str)
        for col in a_region.columns:
            a_region[col] = a_region[col].str.strip().str.replace(r'\s+', ' ', regex=True)
            
        map_name = {}
        map_code = {}
        val_tuples = list(zip(a_region['Store_RP'], a_region['Store_code'], a_region['Region'], a_region['Warehouse']))
        
        name_cols = [c for c in ['Store_name', 'Store_RP', 'CH_Doanh_thu'] if c in a_region.columns]
        code_cols = [c for c in ['Store_code', 'Store_DT', 'Store_Công'] if c in a_region.columns]
        
        for idx, tpl in enumerate(val_tuples):
            if not tpl[0] or tpl[0] == 'nan':
                continue
            for col in name_cols:
                val = a_region.iloc[idx][col]
                if val and val != 'nan':
                    map_name[val.lower()] = tpl
            for col in code_cols:
                val = a_region.iloc[idx][col]
                if val and val != 'nan':
                    map_code[val.lower()] = tpl
                    
        manual_overrides = {
            'bninh': ('Bắc Ninh', 'BACNINH', 'Hà Nội', 'HTCH'),
            'lcai': ('Lào Cai', 'LAOCAI', 'Hà Nội', 'HTCH'),
            'lqd': ('Nguyên Hồng', 'LQDINH', 'TP. HCM', 'HTCH'),
            'qn': ('Quy Nhơn - Phan Bội Châu', 'QUINHON2', 'Miền Trung - TN', 'HTCH'),
            'st': ('Sóc Trăng', 'STR', 'Miền Tây', 'HTCH'),
            'thisomall': ('Hội Chợ Thiso Mall SaLa', 'HCTHISO', 'Event', 'HTCH'),
            'vcgrdpark': ('Vincom Grand Park', 'VINCOMTD', 'TP. HCM', 'HTCH'),
            'nhong': ('Nguyên Hồng', 'nan', 'TP. HCM', 'HTCH'),
            'qn3': ('Quy Nhơn - Trần Hưng Đạo', 'QUYNHON', 'Miền Trung - TN', 'HTCH'),
            'yb': ('Yên Bái', 'YENBAI', 'Hà Nội', 'HTCH'),
            'hội chợ mega buôn ma thuột': ('Hội Chợ Mega Buôn Mê Thuột', 'METBMT', 'Event', 'HTCH'),
            'hội chợ mega q.6': ('Hội Chợ Mega Q6', 'nan', 'Event', 'HTCH'),
            'hội chợ vstyle đà nẵng': ('Hội Chợ Vstyle Đà Nẵng', 'nan', 'Event', 'HTCH'),
        }
        
        lookup = {}
        lookup.update(map_code)
        lookup.update(map_name)
        lookup.update(manual_overrides)
        return lookup
    except Exception as e:
        print(f"\nError loading A_Region mapper: {e}")
        return {}

def map_regions(df: pd.DataFrame, code_col: str, name_col: str = None, default_rp_from_name: bool = False) -> pd.DataFrame:
    lookup = load_a_region_mapper()
    if not lookup:
        df['Store_RP'] = df[name_col] if (name_col and default_rp_from_name) else "Unknown"
        df['Store_code'] = "Unknown"
        df['Region'] = "Unknown"
        df['Warehouse'] = "Unknown"
        return df

    def clean_key(series):
        if series is None:
            return pd.Series(index=df.index, dtype=str)
        return series.astype(str).str.strip().str.lower().str.replace(r'\s+', ' ', regex=True)
        
    clean_codes = clean_key(df[code_col])
    mapped = clean_codes.map(lookup)
    
    if name_col is not None:
        clean_names = clean_key(df[name_col])
        mapped_names = clean_names.map(lookup)
        mapped = mapped.fillna(mapped_names)
        
    store_rps, store_codes, regions, warehouses = [], [], [], []
    name_source = df[name_col] if name_col is not None else df[code_col]
    
    for val, name_val in zip(mapped, name_source):
        if isinstance(val, tuple):
            store_rps.append(val[0])
            store_codes.append(val[1])
            regions.append(val[2])
            warehouses.append(val[3])
        else:
            store_rps.append(str(name_val).strip() if default_rp_from_name else "Unknown")
            store_codes.append("Unknown")
            regions.append("Unknown")
            warehouses.append("Unknown")
            
    df['Store_RP'] = store_rps
    df['Store_code'] = store_codes
    df['Region'] = regions
    df['Warehouse'] = warehouses
    return df

@functools.lru_cache(maxsize=1)
def load_d_category(db_path: str) -> pd.DataFrame:
    if not os.path.exists(db_path):
        print(f"\nWarning: Database file not found at {db_path}")
        return pd.DataFrame()
    try:
        df = pd.read_excel(db_path, sheet_name="D_Category")
        df['Short_name'] = df['Short_name'].astype(str).str.strip()
        return df[['Short_name', 'Brand', 'Product_type']]
    except Exception as e:
        print(f"\nError reading D_Category sheet from {db_path}: {e}")
        return pd.DataFrame()

def process_sales_data():
    input_dir = r"D:\DataBase\4.Revenue"
    
    file_pattern = re.compile(r"DOANH THU THEO NGAY\s+(\d+)\.(\d+)\.xls$", re.IGNORECASE)
    all_records = []
    
    sales_dirs = [
        r"Z:\DOANH THU THEO NGAY 2026",
        r"Z:\DOANH THU THEO NGAY 2025"
    ]
    
    print("--- 1. Processing Sales Data ---")
    for sales_dir in sales_dirs:
        if not os.path.exists(sales_dir):
            continue
            
        files = [f for f in os.listdir(sales_dir) if f.lower().endswith(".xls")]
        print(f"Found {len(files)} sales files in {sales_dir}")
        
        for f_idx, filename in enumerate(files, 1):
            filepath = os.path.join(sales_dir, filename)
            match = file_pattern.search(filename)
            if not match:
                continue
                
            month = int(match.group(1))
            year = int(match.group(2))
            
            print(f"\r  [{f_idx}/{len(files)}] Reading {filename} ({month:02d}/{year})", end="", flush=True)
            
            try:
                with pd.ExcelFile(filepath) as xls:
                    for sheet_name in xls.sheet_names:
                        if sheet_name.strip().upper() == 'DK' or not sheet_name.strip().isdigit():
                            continue
                            
                        day = int(sheet_name.strip())
                        date_str = f"{year:04d}-{month:02d}-{day:02d}"
                        
                        df = xls.parse(sheet_name, header=None)
                        
                        header_idx = None
                        for idx, row in enumerate(df.values):
                            if any(isinstance(val, str) and "MÃ CH" in val for val in row):
                                header_idx = idx
                                break
                                
                        if header_idx is None:
                            continue
                            
                        col_map = {}
                        for c in range(df.shape[1]):
                            val2 = str(df.iloc[header_idx, c]).strip() if pd.notna(df.iloc[header_idx, c]) else ""
                            val3 = str(df.iloc[header_idx + 1, c]).strip() if pd.notna(df.iloc[header_idx + 1, c]) else ""
                            val2 = " ".join(val2.split())
                            val3 = " ".join(val3.split())
                            
                            if val2 == 'MÃ CH':
                                col_map['Mã CH'] = c
                            elif val2 == 'TÊN CỬA HÀNG':
                                col_map['Tên CH'] = c
                            elif val3 == 'TỔNG DT':
                                col_map['Tổng DT'] = c
                            elif val3 == 'DT AP':
                                col_map['DT AP'] = c
                            elif val3 == 'DT FLD':
                                col_map['DT FLD'] = c
                            elif val3 == 'Số tiền HĐ':
                                col_map['Số tiền HĐ'] = c
                            elif val3 == 'DT AP NAM':
                                col_map['DT AP NAM'] = c
                            elif val3 == 'DT PIE':
                                col_map['DT PIE'] = c
                            elif val3 == 'DT AP LADIES':
                                col_map['DT AP LADIES'] = c
                            elif val3 == 'DT ANAMAI':
                                col_map['DT ANAMAI'] = c
                            elif val3 == 'DT BONJOUR':
                                col_map['DT BONJOUR'] = c
                            elif val3 == 'DT PQT':
                                col_map['DT PQT'] = c

                        is_2026 = 'DT AP NAM' in col_map
                        start_row = header_idx + 3
                        
                        df_day = df.iloc[start_row:].copy()
                        rename_dict = {idx: name for name, idx in col_map.items()}
                        df_day = df_day.rename(columns=rename_dict)
                        
                        if 'Mã CH' not in df_day.columns:
                            continue
                            
                        df_day = df_day[df_day['Mã CH'].notna()]
                        df_day['Mã CH'] = df_day['Mã CH'].astype(str).str.strip()
                        df_day = df_day[(df_day['Mã CH'] != "") & (df_day['Mã CH'].str.upper() != 'MÃ CH')]
                        
                        if df_day.empty:
                            continue
                            
                        if is_2026:
                            cols_to_convert = ['DT AP NAM', 'DT PIE', 'DT AP LADIES', 'DT ANAMAI', 'DT BONJOUR', 'DT PQT', 'Số tiền HĐ']
                            for col in cols_to_convert:
                                if col in df_day.columns:
                                    df_day[col] = pd.to_numeric(df_day[col], errors='coerce').fillna(0.0)
                                else:
                                    df_day[col] = 0.0
                            
                            df_day['Tổng DT'] = df_day['DT AP NAM'] + df_day['DT PIE'] + df_day['DT AP LADIES'] + df_day['DT ANAMAI'] + df_day['DT BONJOUR'] + df_day['DT PQT'] + df_day['Số tiền HĐ']
                            df_day['DT AP'] = df_day['DT AP NAM'] + df_day['DT PIE'] + df_day['DT PQT']
                            df_day['DT FLD'] = df_day['DT ANAMAI'] + df_day['DT BONJOUR']
                        else:
                            cols_to_convert = ['Tổng DT', 'DT AP', 'DT FLD', 'Số tiền HĐ']
                            for col in cols_to_convert:
                                if col in df_day.columns:
                                    df_day[col] = pd.to_numeric(df_day[col], errors='coerce').fillna(0.0)
                                else:
                                    df_day[col] = 0.0
                            
                            for col in ['DT AP NAM', 'DT PIE', 'DT AP LADIES', 'DT ANAMAI', 'DT BONJOUR', 'DT PQT']:
                                df_day[col] = 0.0
                                
                        df_day = df_day[df_day['Tổng DT'] != 0]
                        if df_day.empty:
                            continue
                            
                        cols_to_clean = ['Tổng DT', 'DT AP', 'DT FLD', 'Số tiền HĐ', 'DT AP NAM', 'DT PIE', 'DT AP LADIES', 'DT ANAMAI', 'DT BONJOUR', 'DT PQT']
                        for col in cols_to_clean:
                            df_day[col] = df_day[col].replace(0.0, np.nan)
                            
                        df_day['Ngày'] = date_str
                        df_day['Tên CH'] = df_day['Tên CH'].fillna("").astype(str).str.strip() if 'Tên CH' in df_day.columns else ""
                        
                        df_day = df_day[['Ngày', 'Mã CH', 'Tên CH'] + cols_to_clean]
                        all_records.append(df_day)
            except Exception as e:
                print(f"\n  Error reading file {filename}: {e}")
        print()
        
    if all_records:
        df_out = pd.concat(all_records, ignore_index=True)
        df_out = map_regions(df_out, 'Mã CH', 'Tên CH')
        
        cols_order = [
            'Ngày', 'Store_RP', 'Store_code', 'Region', 'Warehouse', 'Tổng DT', 'DT AP', 'DT FLD', 'Số tiền HĐ',
            'DT AP NAM', 'DT PIE', 'DT AP LADIES', 'DT ANAMAI', 'DT BONJOUR', 'DT PQT'
        ]
        df_out = df_out.reindex(columns=cols_order)
        df_out.sort_values(by=['Ngày', 'Store_code'], inplace=True)
        
        os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
        with duckdb.connect(DATABASE_PATH) as conn:
            conn.execute("CREATE OR REPLACE TABLE revenue AS SELECT * FROM df_out")
        print(f"  Saved daily sales data to database table 'revenue' in: {DATABASE_PATH} (Rows: {len(df_out)})")
    else:
        print("  No daily sales records were processed!")

def process_target_data():
    input_dir = r"D:\DataBase\4.Revenue"
    target_filepath = r"Z:\DOANH THU CUA HANG NAM-2026.xlsx"
    
    if not os.path.exists(target_filepath):
        print(f"\nError: Target file not found at {target_filepath}")
        return
        
    print("\n--- 2. Processing Target Data ---")
    print(f"Reading target file: {target_filepath}")
    
    try:
        with pd.ExcelFile(target_filepath) as xls:
            sheets = [s for s in xls.sheet_names if re.match(r"^THOP\d+$", s)]
            print(f"Found target sheets: {sheets}")
            
            target_records = []
            
            for sheet in sheets:
                month = int(sheet.replace("THOP", ""))
                print(f"  Reading sheet: {sheet} (Tháng {month})")
                
                df = xls.parse(sheet, header=None)
                if len(df) <= 5:
                    continue
                    
                df_sheet = df.iloc[5:].copy()
                if df_sheet.shape[1] <= 267:
                    continue
                    
                df_sheet = df_sheet[[1, 2, 263, 264, 265, 266, 267]]
                df_sheet.columns = ['Tên CH', 'Mã CH', 'Tổng chỉ tiêu AP+FLD', 'Chỉ tiêu AP', 'Chỉ tiêu FLD', 'Số ngày', 'Chỉ tiêu bình quân/Ngày']
                
                df_sheet = df_sheet[df_sheet['Mã CH'].notna()]
                df_sheet['Mã CH'] = df_sheet['Mã CH'].astype(str).str.strip()
                df_sheet = df_sheet[(df_sheet['Mã CH'] != "") & (df_sheet['Mã CH'].str.upper() != 'MÃ CH') & (~df_sheet['Mã CH'].str.startswith('%'))]
                
                if df_sheet.empty:
                    continue
                    
                df_sheet['Tên CH'] = df_sheet['Tên CH'].fillna("").astype(str).str.strip()
                
                num_cols = ['Tổng chỉ tiêu AP+FLD', 'Chỉ tiêu AP', 'Chỉ tiêu FLD', 'Số ngày', 'Chỉ tiêu bình quân/Ngày']
                for col in num_cols:
                    df_sheet[col] = pd.to_numeric(df_sheet[col], errors='coerce').fillna(0.0)
                    
                mask_zero_total = df_sheet['Tổng chỉ tiêu AP+FLD'] == 0.0
                df_sheet.loc[mask_zero_total, 'Tổng chỉ tiêu AP+FLD'] = df_sheet.loc[mask_zero_total, 'Chỉ tiêu AP'] + df_sheet.loc[mask_zero_total, 'Chỉ tiêu FLD']
                
                df_sheet = df_sheet[df_sheet['Tổng chỉ tiêu AP+FLD'] != 0.0]
                if df_sheet.empty:
                    continue
                    
                mask_zero_bq = (df_sheet['Chỉ tiêu bình quân/Ngày'] == 0.0) & (df_sheet['Số ngày'] > 0)
                df_sheet.loc[mask_zero_bq, 'Chỉ tiêu bình quân/Ngày'] = df_sheet.loc[mask_zero_bq, 'Tổng chỉ tiêu AP+FLD'] / df_sheet.loc[mask_zero_bq, 'Số ngày']
                
                for col in num_cols:
                    df_sheet[col] = df_sheet[col].replace(0.0, np.nan)
                    
                df_sheet['Năm'] = 2026
                df_sheet['Tháng'] = month
                
                target_records.append(df_sheet)
    except Exception as e:
        print(f"  Error processing targets: {e}")
        return
        
    if target_records:
        df_target = pd.concat(target_records, ignore_index=True)
        df_target = map_regions(df_target, 'Mã CH', 'Tên CH')
        
        cols = ['Năm', 'Tháng', 'Store_RP', 'Store_code', 'Region', 'Warehouse', 'Tổng chỉ tiêu AP+FLD', 'Chỉ tiêu AP', 'Chỉ tiêu FLD', 'Số ngày', 'Chỉ tiêu bình quân/Ngày']
        df_target = df_target.reindex(columns=cols)
        df_target.sort_values(by=['Tháng', 'Store_code'], inplace=True)
        
        os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
        with duckdb.connect(DATABASE_PATH) as conn:
            conn.execute("CREATE OR REPLACE TABLE target AS SELECT * FROM df_target")
        print(f"  Saved targets data to database table 'target' in: {DATABASE_PATH} (Rows: {len(df_target)})")
    else:
        print("  No target records were processed!")

def process_sales_details():
    input_dir = r"D:\DataBase\4.Revenue"
    system_sales_dir = r"\\hovmfs01\PKD\PhanPhoi\Thong.Nguyen\Analysis_data\2.System_sales"
    db_path = r"\\hovmfs01\PKD\PhanPhoi\Thong.Nguyen\Analysis_data\1.Processed_data\1.Data_Tracking.xlsx"
    
    if not os.path.exists(db_path):
        print(f"\nError: Database file not found at {db_path}")
        return
        
    print("\n--- 3. Processing Sales Details ---")
    
    d_category = load_d_category(db_path)
    if d_category.empty:
        print("  Could not load D_Category. Exiting details processing.")
        return
        
    files = glob.glob(os.path.join(system_sales_dir, "*.csv"))
    if not files:
        print("  No System Sales files found.")
        return
        
    print(f"Found {len(files)} sales CSV files in system sales folder")
    all_dfs = []
    total_files = len(files)
    
    for i, f in enumerate(files, 1):
        print(f"\r  [{i}/{total_files}] Reading sales CSV: {os.path.basename(f)}", end="", flush=True)
        try:
            df = robust_read_csv(f)
            all_dfs.append(df)
        except Exception as e:
            print(f"\n  Error reading {os.path.basename(f)}: {e}")
            
    print()
    
    if not all_dfs:
        print("  No CSV data could be read.")
        return
        
    df_sales = pd.concat(all_dfs, ignore_index=True)
    
    if "SoLuong" not in df_sales.columns or "NgayChungTu" not in df_sales.columns:
        print("  Required columns (SoLuong, NgayChungTu) not found in sales data.")
        return
        
    df_sales["SoLuong"] = pd.to_numeric(df_sales["SoLuong"].astype(str).str.replace(r'[^\d\-,\.]', '', regex=True).str.replace(',', '.'), errors='coerce').fillna(0).astype(int)
    
    df_sales["Nội dung"] = df_sales["DienGiai"].astype(str).str.split(":", n=1).str[0].str.strip()
    df_sales["Short_name"] = df_sales["MaHang"].astype(str).str.strip().apply(lambda x: x[:-4] if len(x) >= 4 else x)
    
    df_sales = df_sales.merge(d_category, on='Short_name', how='left')
    
    cond_noidung = df_sales["Nội dung"].isin(["Bán", "Tặng", "Đổi"])
    cond_product = ~df_sales["Product_type"].astype(str).str.lower().str.strip().isin(["bao bì", "đồng phục"])
    df_filtered = df_sales[cond_noidung & cond_product].copy()
    
    df_filtered['NgayChungTu'] = pd.to_datetime(df_filtered['NgayChungTu'], errors='coerce', dayfirst=True)
    df_filtered['Ngay_Str'] = df_filtered['NgayChungTu'].dt.strftime('%Y-%m-%d')
    
    df_filtered = df_filtered[df_filtered['Ngay_Str'].notna()]
    if 'TenCuaHang' not in df_filtered.columns:
        df_filtered['TenCuaHang'] = ""
    df_filtered['TenCuaHang'] = df_filtered['TenCuaHang'].astype(str).str.strip()
    df_filtered = df_filtered[df_filtered['TenCuaHang'] != ""]
    
    df_filtered['Is_AP_PIE'] = df_filtered['Brand'].str.contains("An Phước|Pierre Cardin|Gerb Weis|Tomiya", case=False, na=False)
    df_filtered['Is_FLD'] = df_filtered['Brand'].str.contains("Anamai|Bonjour", case=False, na=False)
    
    df_filtered['Slg_Ban_Val'] = np.where(df_filtered['Nội dung'] == 'Bán', df_filtered['SoLuong'], 0)
    df_filtered['Slg_Doi_Val'] = np.where(df_filtered['Nội dung'] == 'Đổi', df_filtered['SoLuong'], 0)
    df_filtered['Slg_AP_PIE_Val'] = np.where((df_filtered['Nội dung'] == 'Bán') & df_filtered['Is_AP_PIE'], df_filtered['SoLuong'], 0)
    df_filtered['Slg_FLD_Val'] = np.where((df_filtered['Nội dung'] == 'Bán') & df_filtered['Is_FLD'], df_filtered['SoLuong'], 0)
    
    df_filtered['Bill_AP_PIE_Val'] = np.where((df_filtered['Nội dung'] == 'Bán') & df_filtered['Is_AP_PIE'], df_filtered['SoChungTu'], np.nan)
    df_filtered['Bill_FLD_Val'] = np.where((df_filtered['Nội dung'] == 'Bán') & df_filtered['Is_FLD'], df_filtered['SoChungTu'], np.nan)
    
    print("  Aggregating sales details...")
    grouped = df_filtered.groupby(['Ngay_Str', 'TenCuaHang']).agg(
        Tong_Bill=('SoChungTu', 'nunique'),
        Slg_Ban=('Slg_Ban_Val', 'sum'),
        Slg_Doi=('Slg_Doi_Val', 'sum'),
        Slg_AP_PIE=('Slg_AP_PIE_Val', 'sum'),
        Slg_FLD=('Slg_FLD_Val', 'sum'),
        Bill_AP_PIE=('Bill_AP_PIE_Val', 'nunique'),
        Bill_FLD=('Bill_FLD_Val', 'nunique')
    ).reset_index()
    
    grouped['Slg_Doi'] = grouped['Slg_Doi'].abs()
    
    grouped = grouped.rename(columns={
        'Ngay_Str': 'Ngày',
        'TenCuaHang': 'Tên cửa hàng',
        'Tong_Bill': 'Tổng số bill (số chứng từ)',
        'Slg_Ban': 'Số lượng bán',
        'Slg_Doi': 'Số lượng đổi',
        'Slg_AP_PIE': 'SL bán AP + PIE',
        'Slg_FLD': 'SL bán FLD (Anamai + Bonjour)',
        'Bill_AP_PIE': 'Số bill AP/Pie',
        'Bill_FLD': 'Số bill FLD'
    })
    
    num_cols = [
        'Tổng số bill (số chứng từ)', 'Số lượng bán', 'Số lượng đổi',
        'SL bán AP + PIE', 'SL bán FLD (Anamai + Bonjour)', 'Số bill AP/Pie', 'Số bill FLD'
    ]
    for col in num_cols:
        grouped[col] = grouped[col].replace(0, np.nan).replace(0.0, np.nan)
        
    grouped = map_regions(grouped, 'Tên cửa hàng', default_rp_from_name=True)
    grouped = grouped.drop(columns=['Tên cửa hàng'])
    
    cols = list(grouped.columns)
    for c in ['Store_RP', 'Store_code', 'Region', 'Warehouse']:
        if c in cols:
            cols.remove(c)
    idx_ngay = cols.index('Ngày')
    cols.insert(idx_ngay + 1, 'Store_RP')
    cols.insert(idx_ngay + 2, 'Store_code')
    cols.insert(idx_ngay + 3, 'Region')
    cols.insert(idx_ngay + 4, 'Warehouse')
    grouped = grouped[cols]
        
    grouped.sort_values(by=['Ngày', 'Store_code'], inplace=True)
    
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    with duckdb.connect(DATABASE_PATH) as conn:
        conn.execute("CREATE OR REPLACE TABLE bill_sales AS SELECT * FROM grouped")
    print(f"  Saved consolidated sales details to database table 'bill_sales' in: {DATABASE_PATH} (Rows: {len(grouped)})")

if __name__ == "__main__":
    process_sales_data()
    process_target_data()
    process_sales_details()

import os
import sys
import re
import glob
import math
import pandas as pd
import numpy as np
import duckdb

sys.stdout.reconfigure(encoding='utf-8')

# -------------------------------------------------------------
# Utility functions
# -------------------------------------------------------------
def trim_dataframe(df):
    for col in df.columns:
        if df[col].dtype == "object":
            df[col] = df[col].map(lambda x: x.strip() if isinstance(x, str) else x)
    return df


core_upper_set = {'ap', 'pie', 'htt', 'hd', 'hđ', 'tl', 'hd1', 'dg', 'đg', 'po', 'ht', 'nb'}


def format_cat_word(word, is_after_hyphen=False):
    word = word.strip()
    if not word:
        return ""

    def uppercase_paren(inside):
        return re.sub(r'(?i)\bcm\b', 'cm', inside.upper())

    if '(' in word and ')' in word:
        parts = re.split(r'(\(.*?\))', word)
        new_parts = []
        for p in parts:
            if p.startswith('(') and p.endswith(')'):
                new_parts.append(f"({uppercase_paren(p[1:-1])})")
            else:
                if p:
                    clean_p = re.sub(r'[^a-zA-Z0-9]', '', p).lower()
                    if is_after_hyphen:
                        new_parts.append(p.upper())
                    elif clean_p in core_upper_set:
                        new_parts.append(p.upper())
                    else:
                        new_parts.append(p.capitalize())
                else:
                    new_parts.append("")
        return "".join(new_parts)

    if is_after_hyphen:
        return word.upper()
    clean_word = re.sub(r'[^a-zA-Z0-9]', '', word).lower()
    if clean_word in core_upper_set:
        return word.upper()
    return word.capitalize()


def format_cat_text(text):
    if text is None:
        return ""
    if isinstance(text, float) and math.isnan(text):
        return ""
    text_str = str(text).strip()
    if not text_str:
        return ""
    words = text_str.split()
    formatted_words = []
    for w in words:
        if '-' in w:
            subparts = w.split('-')
            new_subparts = [
                format_cat_word(sp, is_after_hyphen=(i > 0))
                for i, sp in enumerate(subparts)
            ]
            formatted_words.append("-".join(new_subparts))
        else:
            formatted_words.append(format_cat_word(w))
    return " ".join(formatted_words)


def title_case(val):
    if pd.isna(val) or val is None:
        return ""
    return str(val).strip().title()


def clean_str(val):
    if pd.isna(val) or val is None:
        return ""
    return str(val).strip()


def clean_code(val):
    if pd.isna(val) or val is None:
        return ""
    return str(val).strip().upper()


def format_brand(val):
    if pd.isna(val) or val is None:
        return ""
    brand_name = str(val).strip().title()
    return f"Hiệu {brand_name}" if brand_name else ""


def compute_combined_pk(df):
    item_codes = df['item_code'].fillna('').astype(str).str.strip().str.upper()
    operations = df['Operation'].fillna('').astype(str).str.strip()
    combined = item_codes + operations
    combined[(item_codes == '') & (operations == '')] = np.nan
    return combined


def report_duplicates(df, df_name, col_name):
    if col_name not in df.columns:
        return
    s = df[col_name].dropna()
    s = s[s != '']
    dup_mask = s.duplicated(keep=False)
    dup_vals = s[dup_mask].unique()
    if len(dup_vals) > 0:
        print(f"\n[PHÁT HIỆN TRÙNG LẶP] Bảng '{df_name}', Cột '{col_name}':")
        print(f"Có {len(dup_vals)} giá trị bị trùng:")
        for val in dup_vals[:15]:
            rows = df[df[col_name].astype(str).str.strip() == str(val)]
            print(f"  - '{val}' ({len(rows)} dòng):")
            for r_idx, row in rows.iterrows():
                name = row.get('System_item_name') or row.get('Store_name') or row.get('Short_name')
                print(f"    * Dòng {r_idx} | Brand='{row.get('Brand')}', Name='{name}'")
        if len(dup_vals) > 15:
            print(f"    ... và {len(dup_vals) - 15} giá trị trùng khác.")


# -------------------------------------------------------------
# Main
# -------------------------------------------------------------
def main():
    db_dir  = r"D:\DataBase\DuckDB"
    db_path = os.path.join(db_dir, "Database_AP.duckdb")
    old_db_path = os.path.join(db_dir, "Duck_database_AP.duckdb")

    path_processed_tracking = r"\\hovmfs01\PKD\PhanPhoi\Thong.Nguyen\Analysis_data\1.Processed_data\1.Data_Tracking.xlsx"
    path_raw_2025           = r"\\hovmfs01\PKD\PhanPhoi\Thong.Nguyen\Analysis_data\16.Raw_data\Data_Tracking_2025.xlsx"
    path_rank_2026          = r"Y:\Hang Ni\DOANH THU DOI CHIEU NXT\2026\1. DS TONG HOP XEP LOAI CUA HANG 2026.xlsx"
    y_drive_dir             = r"Y:\ANAMAI BONJOUR"

    # Xóa database cũ nếu còn
    if os.path.exists(old_db_path):
        try:
            print(f"Removing old database: {old_db_path}")
            os.remove(old_db_path)
        except Exception as e:
            print(f"Warning: Could not remove old database: {e}")

    # --- Step 1: Folders & Files ---
    print("--- Step 1: Initializing Folders & Finding Files ---")
    os.makedirs(db_dir, exist_ok=True)
    print(f"Database directory: {db_dir}")

    search_pattern = os.path.join(y_drive_dir, "NEW - DU LIEU DATA HH *.xlsx")
    matching_files = glob.glob(search_pattern)
    if not matching_files:
        print(f"Error: No file matching 'NEW - DU LIEU DATA HH *.xlsx' found in {y_drive_dir}")
        return
    matching_files.sort(key=os.path.getmtime, reverse=True)
    path_new_dmhh = matching_files[0]
    print(f"Found latest DMHH file: {os.path.basename(path_new_dmhh)}")

    # --- Step 2: Store Ranks & A_Region ---
    print("\n--- Step 2: Loading & Extracting Store Ranks ---")
    if not os.path.exists(path_rank_2026):
        print(f"Error: Store rank file not found: {path_rank_2026}")
        return

    df_rank_excel = pd.read_excel(path_rank_2026, sheet_name='Xep loai CH', header=None)
    store_ranks = {}
    for idx in range(4, len(df_rank_excel)):
        row_values = df_rank_excel.iloc[idx].tolist()
        stt = row_values[0]
        if pd.isna(stt) or not isinstance(stt, (int, float)):
            continue
        ma_ch  = str(row_values[1]).strip().lower() if pd.notna(row_values[1]) else ""
        ten_ch = str(row_values[3]).strip().lower() if pd.notna(row_values[3]) else ""
        ranks  = row_values[5:16]
        valid_ranks = [str(r).strip() for r in ranks if pd.notna(r) and str(r).strip()]
        latest_rank = valid_ranks[-1] if valid_ranks else ""
        if ma_ch:
            store_ranks[ma_ch] = latest_rank
        if ten_ch:
            store_ranks[ten_ch] = latest_rank

    print("Loading A_Region sheet...")
    df_region = trim_dataframe(pd.read_excel(path_processed_tracking, sheet_name='A_Region'))

    def get_updated_rank(row_region):
        store_name = str(row_region.get('Store_name', '')).strip()
        store_code = str(row_region.get('Store_code', '')).strip()
        store_dt   = str(row_region.get('Store_DT', '')).strip()
        store_cong = str(row_region.get('Store_Công', '')).strip()
        original_rank = str(row_region.get('Store_rank', '')).strip()
        if store_name.lower() in store_ranks:
            return store_ranks[store_name.lower()]
        paren_match = re.search(r'\((.*?)\)', store_name)
        if paren_match and paren_match.group(1).strip().lower() in store_ranks:
            return store_ranks[paren_match.group(1).strip().lower()]
        for key in (store_dt, store_cong, store_code):
            if key and key.lower() in store_ranks:
                return store_ranks[key.lower()]
        for k, v in store_ranks.items():
            if len(k) > 5 and (k in store_name.lower() or store_name.lower() in k):
                return v
        return original_rank if original_rank and original_rank != 'nan' else ""

    old_ranks = df_region['Store_rank'].copy()
    df_region['Store_rank'] = df_region.apply(get_updated_rank, axis=1)
    print(f"Updated Store_rank for {np.sum(old_ranks != df_region['Store_rank'])} rows.")

    print("\n--- Checking duplicates in A_Region ---")
    for col in ['Store_name', 'Store_code', 'Store_DT', 'Store_Công', 'CH_Doanh_thu']:
        if col in df_region.columns:
            s = df_region[col].dropna()
            s = s[s != '']
            dup_vals = s[s.duplicated(keep=False)].unique()
            if len(dup_vals) > 0:
                print(f"  [TRÙNG] Cột '{col}': {len(dup_vals)} giá trị trùng")
            else:
                print(f"  Cột '{col}': OK")

    # --- Step 3: D_Category ---
    print("\n--- Step 3: Loading & Formatting D_Category ---")
    df_cat = trim_dataframe(pd.read_excel(path_processed_tracking, sheet_name='D_Category'))
    for col in df_cat.columns:
        if col == 'Short_name':
            df_cat[col] = df_cat[col].astype(str).str.strip().str.upper()
        else:
            df_cat[col] = df_cat[col].map(format_cat_text)

    # --- Step 4: Other dimension sheets ---
    print("\n--- Step 4: Loading Other Dimension Sheets ---")
    df_size      = trim_dataframe(pd.read_excel(path_processed_tracking, sheet_name='B_Size'))
    df_sizechart = trim_dataframe(pd.read_excel(path_processed_tracking, sheet_name='C_BasicSizeChart'))
    df_tshirt    = trim_dataframe(pd.read_excel(path_processed_tracking, sheet_name='E_T-Shirt'))

    # --- Step 5: F_DataTracking ---
    print("\n--- Step 5: Processing & Merging Tracking Data ---")

    df_hist = trim_dataframe(pd.read_excel(path_processed_tracking, sheet_name='F_DataTracking'))
    df_hist['Combined_PK'] = compute_combined_pk(df_hist)

    df_2025 = trim_dataframe(pd.read_excel(path_raw_2025, sheet_name='DataTracking_2025'))
    df_2025['Combined_PK'] = compute_combined_pk(df_2025)

    print(f"Loading new DMHH data...")
    xl_new = pd.ExcelFile(path_new_dmhh)
    target_sheet = ([s for s in xl_new.sheet_names if "DMHH" in s and "MỚI" in s and "TN" in s]
                    or [s for s in xl_new.sheet_names if "DMHH" in s or "dmhh" in s]
                    or [xl_new.sheet_names[0]])
    df_new_raw = pd.read_excel(path_new_dmhh, sheet_name=target_sheet[0], header=1)
    df_new_raw.columns = [str(c).strip() for c in df_new_raw.columns]

    new_mapped_rows = []
    for _, row in df_new_raw.iterrows():
        time_nk = clean_str(row.get('TIME NK'))
        prod_month = prod_year = np.nan
        if time_nk and '-' in time_nk:
            parts = time_nk.split('-')
            if len(parts) == 2:
                try:
                    p0, p1 = int(parts[0]), int(parts[1])
                    prod_year  = 2000 + p0 if p0 < 100 else p0
                    prod_month = p1
                except ValueError:
                    pass
        new_mapped_rows.append({
            'Brand':            format_brand(row.get('nhãn hiệu')),
            'System_item_name': clean_str(row.get('TenHang')),
            'Operation':        clean_str(row.get('tac_nghiep')),
            'Color_code':       clean_code(row.get('mau_so')),
            'item_code':        clean_code(row.get('Mahang')),
            'Composition':      title_case(row.get('thành phần')),
            'Color_tone':       title_case(row.get('màu - chữ')),
            'Color_group':      "",
            'Form':             title_case(row.get('form')),
            'Style':            title_case(row.get('KIỂU DÁNG')),
            'Attribute':        title_case(row.get('tt khác')),
            'Description':      title_case(row.get('bst')),
            'Price':            (np.nan if pd.isna(row.get('gia')) else
                                 (float(row.get('gia')) if str(row.get('gia')).replace('.','').isdigit()
                                  else row.get('gia'))),
            'Dist_plan':        title_case(row.get('khpp')),
            'Production_month': prod_month,
            'Production_year':  prod_year,
            'Sub_Brand':        "",
            'N/D':              "",
        })

    df_new_mapped = trim_dataframe(pd.DataFrame(new_mapped_rows))
    df_new_mapped['Combined_PK'] = compute_combined_pk(df_new_mapped)

    cols_order = ['Brand', 'System_item_name', 'Operation', 'Color_code', 'item_code',
                  'Composition', 'Color_tone', 'Color_group', 'Form', 'Style',
                  'Attribute', 'Description', 'Price', 'Dist_plan', 'Production_month',
                  'Production_year', 'Combined_PK', 'Sub_Brand', 'N/D']
    df_tracking_all = pd.concat(
        [df_hist[cols_order], df_2025[cols_order], df_new_mapped[cols_order]],
        ignore_index=True,
    )
    df_tracking_all = trim_dataframe(df_tracking_all)

    # --- Step 6: Duplicate checks ---
    print("\n--- Step 6: Duplicate Checks ---")
    report_duplicates(df_cat, 'D_Category', 'Short_name')
    for src_df, src_name in [
        (df_hist,       'Historical Tracking'),
        (df_2025,       '2025 Tracking'),
        (df_new_mapped, 'New DMHH Tracking'),
    ]:
        report_duplicates(src_df, src_name, 'Combined_PK')

    pk_sets = [set(d['Combined_PK'].dropna().unique())
               for d in (df_hist, df_2025, df_new_mapped)]
    names   = ['Historical', '2025', 'New DMHH']
    pairs   = [(0, 1), (0, 2), (1, 2)]
    for a, b in pairs:
        overlap = pk_sets[a] & pk_sets[b]
        if overlap:
            print(f"  Trùng {names[a]} ↔ {names[b]}: {len(overlap)} khóa")
    if not any(pk_sets[a] & pk_sets[b] for a, b in pairs):
        print("  Không phát hiện trùng lặp chéo giữa các nguồn.")

    # --- Step 7: Load into DuckDB ---
    print(f"\n--- Step 7: Loading into DuckDB: {db_path} ---")
    conn = duckdb.connect(db_path)
    for tbl, df_src in [
        ("A_Region",         df_region),
        ("B_Size",           df_size),
        ("D_Category",       df_cat),
        ("C_BasicSizeChart", df_sizechart),
        ("E_T-Shirt",        df_tshirt),
        ("F_DataTracking",   df_tracking_all),
    ]:
        conn.register("_src", df_src)
        conn.execute(f'CREATE OR REPLACE TABLE "{tbl}" AS SELECT * FROM _src')
        conn.unregister("_src")

    tables = conn.execute("SHOW TABLES").fetchall()
    print("Tables in DuckDB:", [t[0] for t in tables])
    for t in tables:
        count = conn.execute(f'SELECT COUNT(*) FROM "{t[0]}"').fetchone()[0]
        print(f"  - {t[0]}: {count:,} rows")
    conn.close()
    print(f"\nDatabase saved to: {db_path}")


if __name__ == "__main__":
    main()

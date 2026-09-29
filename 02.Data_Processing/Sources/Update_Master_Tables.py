# -*- coding: utf-8 -*-
"""Làm mới các bảng danh mục/lookup (Master): A_Region, B_Size, D_Category,
C_BasicSizeChart, E_T-Shirt, F_DataTracking. Đây là nguồn cho load_master_table()
ở mọi processor khác, nên luôn full-refresh (không phân mảnh theo tháng)."""
import glob
import math
import os
import re
import sys

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # 02.Data_Processing
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "00.Shared"))  # 00.Shared (Get_Paths...)
from Read_Write_Parquet import MASTER_DIR
import Get_Paths

PATH_PROCESSED_TRACKING = Get_Paths.data_tracking_excel
PATH_RAW_2025 = Get_Paths.nguon_tracking_2025
PATH_RANK_2026 = Get_Paths.xep_loai_cua_hang
Y_DRIVE_DIR = Get_Paths.danh_muc_hang_hoa


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
    return str(val).strip().capitalize()


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


# Danh sách System_item_name cần xét cặp Ngắn/Dài - Nam/Nữ theo Color_code
ND_TARGET_ITEM_NAMES = [
    'Áo Thun Nam Dài AP', 'Áo Thun Nam Dài PIE', 'Áo Thun Nam Ngắn AP', 'Áo Thun Nam Ngắn PIE',
    'Áo Thun Nữ AP', 'Áo Thun Nữ Dài Tay AP', 'Áo Thun Nữ PIE',
    'Áo T-SHIRT Nam Ngắn AP', 'Áo T-SHIRT Nam Ngắn PIE', 'Áo T-SHIRT Nữ Dài AP', 'Áo T-SHIRT Nữ Ngắn AP',
    'Chemise Nam Dài AP', 'Chemise Nam Dài PIE', 'Chemise Nam Ngắn AP', 'Chemise Nam Ngắn PIE',
    'Chemise Nữ Dài AP', 'Chemise Nữ Dài PIE', 'Chemise Nữ Ngắn AP', 'Chemise Nữ Ngắn PIE',
]


def get_gender_from_name(name):
    if re.search(r'\bNữ\b', name, re.IGNORECASE):
        return 'Nữ'
    if re.search(r'\bNam\b', name, re.IGNORECASE):
        return 'Nam'
    return None


def get_length_from_name(name):
    if re.search(r'\bDài\b', name, re.IGNORECASE):
        return 'Dài'
    if re.search(r'\bNgắn\b', name, re.IGNORECASE):
        return 'Ngắn'
    return None


def get_category_from_name(name):
    """Xác định dòng sản phẩm (Chemise / Áo T-SHIRT / Áo Thun) để chỉ ghép cặp
    trong cùng dòng, không ghép chéo giữa các dòng khác nhau."""
    if re.search(r'T-SHIRT|TSHIRT', name, re.IGNORECASE):
        return 'Áo T-SHIRT'
    if re.search(r'\bChemise\b', name, re.IGNORECASE):
        return 'Chemise'
    if re.search(r'\bThun\b', name, re.IGNORECASE):
        return 'Áo Thun'
    return None


def compute_nd_pairs(df, target_names=ND_TARGET_ITEM_NAMES):
    """Xác định cặp Ngắn/Dài - Nam/Nữ cho các dòng có System_item_name nằm trong
    target_names, cùng Color_code và cùng dòng sản phẩm (Chemise chỉ ghép với
    Chemise, Áo Thun chỉ ghép với Áo Thun, ...)."""
    names_clean = df['System_item_name'].fillna('').astype(str).str.strip()
    codes_clean = df['Color_code'].fillna('').astype(str).str.strip()
    target_set = {t.strip() for t in target_names}
    mask = names_clean.isin(target_set) & (codes_clean != '')

    nd_result = pd.Series('', index=df.index, dtype=object)
    if not mask.any():
        return nd_result

    sub = pd.DataFrame({'name': names_clean[mask], 'code': codes_clean[mask]})
    sub['gender'] = sub['name'].map(get_gender_from_name)
    sub['length'] = sub['name'].map(get_length_from_name)
    sub['category'] = sub['name'].map(get_category_from_name)

    for (code, category), grp in sub.groupby(['code', 'category']):
        genders = {g for g in grp['gender'] if g}
        lengths = {l for l in grp['length'] if l}
        has_gender_diff = len(genders) > 1
        has_length_diff = len(lengths) > 1
        if has_gender_diff and has_length_diff:
            label = 'Cặp N/D-Nam/Nữ'
        elif has_length_diff:
            label = 'Cặp Ngắn/Dài'
        elif has_gender_diff:
            label = 'Cặp Nam/Nữ'
        else:
            label = ''
        if label:
            nd_result.loc[grp.index] = label

    return nd_result


def report_duplicates(df, df_name, col_name):
    if col_name not in df.columns:
        return
    s = df[col_name].dropna()
    s = s[s != '']
    dup_vals = s[s.duplicated(keep=False)].unique()
    if len(dup_vals) > 0:
        preview = ", ".join(f"'{v}'" for v in dup_vals[:5])
        more = f" (+{len(dup_vals) - 5} khác)" if len(dup_vals) > 5 else ""
        print(f"  [TRÙNG] {df_name}.{col_name}: {len(dup_vals)} giá trị — {preview}{more}")


class DataTrackingProcessor:
    """Đọc Data_Tracking.xlsx (+ DMHH mới nhất trên Y:) và xuất các bảng
    danh mục/khu vực/size chuẩn hoá ra 02.Master/*.parquet."""

    def run(self) -> None:
        search_pattern = os.path.join(Y_DRIVE_DIR, "NEW - DU LIEU DATA HH *.xlsx")
        matching_files = glob.glob(search_pattern)
        if not matching_files:
            print(f"[LỖI] Không tìm thấy file 'NEW - DU LIEU DATA HH *.xlsx' trong {Y_DRIVE_DIR}")
            return
        matching_files.sort(key=os.path.getmtime, reverse=True)
        path_new_dmhh = matching_files[0]
        print(f"File DMHH mới nhất: {os.path.basename(path_new_dmhh)}")

        if not os.path.exists(PATH_RANK_2026):
            print(f"[LỖI] Không tìm thấy file xếp loại CH: {PATH_RANK_2026}")
            return

        df_rank_excel = pd.read_excel(PATH_RANK_2026, sheet_name='Xep loai CH', header=None)
        store_ranks = {}
        for idx in range(4, len(df_rank_excel)):
            row_values = df_rank_excel.iloc[idx].tolist()
            stt = row_values[0]
            if pd.isna(stt) or not isinstance(stt, (int, float)):
                continue
            ma_ch = str(row_values[1]).strip().lower() if pd.notna(row_values[1]) else ""
            ten_ch = str(row_values[3]).strip().lower() if pd.notna(row_values[3]) else ""
            ranks = row_values[5:16]
            valid_ranks = [str(r).strip() for r in ranks if pd.notna(r) and str(r).strip()]
            latest_rank = valid_ranks[-1] if valid_ranks else ""
            if ma_ch:
                store_ranks[ma_ch] = latest_rank
            if ten_ch:
                store_ranks[ten_ch] = latest_rank

        df_region = trim_dataframe(pd.read_excel(PATH_PROCESSED_TRACKING, sheet_name='A_Region'))

        def get_updated_rank(row_region):
            store_name = str(row_region.get('Store_name', '')).strip()
            store_code = str(row_region.get('Store_code', '')).strip()
            store_dt = str(row_region.get('Store_DT', '')).strip()
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
        print(f"A_Region: cập nhật Store_rank cho {np.sum(old_ranks != df_region['Store_rank'])} dòng")

        for col in ['Store_name', 'Store_code', 'Store_DT', 'Store_Công', 'CH_Doanh_thu']:
            if col in df_region.columns:
                s = df_region[col].dropna()
                s = s[s != '']
                dup_vals = s[s.duplicated(keep=False)].unique()
                if len(dup_vals) > 0:
                    print(f"  [TRÙNG] A_Region.{col}: {len(dup_vals)} giá trị trùng")

        df_cat = trim_dataframe(pd.read_excel(PATH_PROCESSED_TRACKING, sheet_name='D_Category'))
        for col in df_cat.columns:
            if col == 'Short_name':
                df_cat[col] = df_cat[col].astype(str).str.strip().str.upper()
            else:
                df_cat[col] = df_cat[col].map(format_cat_text)

        df_size = trim_dataframe(pd.read_excel(PATH_PROCESSED_TRACKING, sheet_name='B_Size'))
        df_sizechart = trim_dataframe(pd.read_excel(PATH_PROCESSED_TRACKING, sheet_name='C_BasicSizeChart'))
        df_tshirt = trim_dataframe(pd.read_excel(PATH_PROCESSED_TRACKING, sheet_name='E_T-Shirt'))

        df_hist = trim_dataframe(pd.read_excel(PATH_PROCESSED_TRACKING, sheet_name='F_DataTracking'))
        df_hist['Combined_PK'] = compute_combined_pk(df_hist)

        df_2025 = trim_dataframe(pd.read_excel(PATH_RAW_2025, sheet_name='DataTracking_2025'))
        df_2025['Combined_PK'] = compute_combined_pk(df_2025)

        xl_new = pd.ExcelFile(path_new_dmhh)
        target_sheet = ([s for s in xl_new.sheet_names if "DMHH" in s and "MỚI" in s and "TN" in s]
                        or [s for s in xl_new.sheet_names if "DMHH" in s or "dmhh" in s]
                        or [xl_new.sheet_names[0]])
        df_new_raw = pd.read_excel(path_new_dmhh, sheet_name=target_sheet[0], header=1)
        df_new_raw.columns = [str(c).strip() for c in df_new_raw.columns]

        # Sheet DMHH thường bị định dạng (viền/tô màu...) kéo dài quá phạm vi dữ liệu thật,
        # khiến pandas đọc luôn tới gần giới hạn tối đa của Excel (~1,048,576 dòng) toàn dòng trống.
        # Lọc theo 'Mahang' (khóa chính của dữ liệu tracking) để loại các dòng rác này.
        n_raw_before = len(df_new_raw)
        if 'Mahang' in df_new_raw.columns:
            df_new_raw = df_new_raw[df_new_raw['Mahang'].notna() & (df_new_raw['Mahang'].astype(str).str.strip() != '')]
        print(f"  Sheet '{target_sheet[0]}': đọc {n_raw_before:,} dòng, giữ {len(df_new_raw):,} dòng có Mahang.")

        new_mapped_rows = []
        for _, row in df_new_raw.iterrows():
            time_nk = clean_str(row.get('TIME NK'))
            prod_month = prod_year = np.nan
            if time_nk and '-' in time_nk:
                parts = time_nk.split('-')
                if len(parts) == 2:
                    try:
                        p0, p1 = int(parts[0]), int(parts[1])
                        prod_year = 2000 + p0 if p0 < 100 else p0
                        prod_month = p1
                    except ValueError:
                        pass
            new_mapped_rows.append({
                'Brand': format_brand(row.get('nhãn hiệu')),
                'System_item_name': clean_str(row.get('TenHang')),
                'Operation': clean_str(row.get('tac_nghiep')),
                'Color_code': clean_code(row.get('mau_so')),
                'item_code': clean_code(row.get('Mahang')),
                'Composition': title_case(row.get('thành phần')),
                'Color_tone': title_case(row.get('màu - chữ')),
                'Color_group': title_case(row.get('màu - chữ')),
                'Form': title_case(row.get('form')),
                'Style': title_case(row.get('KIỂU DÁNG')),
                'Attribute': title_case(row.get('tt khác')),
                'Description': title_case(row.get('bst')),
                'Price': (np.nan if pd.isna(row.get('gia')) else
                          (float(row.get('gia')) if str(row.get('gia')).replace('.', '').isdigit()
                           else row.get('gia'))),
                'Dist_plan': title_case(row.get('khpp')),
                'Production_month': prod_month,
                'Production_year': prod_year,
                'Sub_Brand': "",
                'N/D': "",
                'Qty_LSX': title_case(row.get('SL LỆNH SX PM')),
            })

        df_new_mapped = trim_dataframe(pd.DataFrame(new_mapped_rows))
        df_new_mapped['Combined_PK'] = compute_combined_pk(df_new_mapped)

        cols_order = ['Brand', 'System_item_name', 'Operation', 'Color_code', 'item_code',
                      'Composition', 'Color_tone', 'Color_group', 'Form', 'Style',
                      'Attribute', 'Description', 'Price', 'Dist_plan', 'Production_month',
                      'Production_year', 'Combined_PK', 'Sub_Brand', 'N/D', 'Qty_LSX']
        df_tracking_all = pd.concat(
            [df_hist[cols_order], df_2025[cols_order], df_new_mapped[cols_order]],
            ignore_index=True,
        )
        df_tracking_all = trim_dataframe(df_tracking_all)

        df_tracking_all['N/D'] = compute_nd_pairs(df_tracking_all)
        print(f"F_DataTracking: {len(df_tracking_all):,} dòng "
              f"(Historical {len(df_hist):,} + 2025 {len(df_2025):,} + DMHH mới {len(df_new_mapped):,}) | "
              f"{int((df_tracking_all['N/D'] != '').sum())} dòng thuộc cặp Ngắn/Dài-Nam/Nữ")

        report_duplicates(df_cat, 'D_Category', 'Short_name')
        for src_df, src_name in [
            (df_hist, 'Historical Tracking'),
            (df_2025, '2025 Tracking'),
            (df_new_mapped, 'New DMHH Tracking'),
        ]:
            report_duplicates(src_df, src_name, 'Combined_PK')

        pk_sets = [set(d['Combined_PK'].dropna().unique()) for d in (df_hist, df_2025, df_new_mapped)]
        names = ['Historical', '2025', 'New DMHH']
        pairs = [(0, 1), (0, 2), (1, 2)]
        for a, b in pairs:
            overlap = pk_sets[a] & pk_sets[b]
            if overlap:
                print(f"  [TRÙNG] {names[a]} ↔ {names[b]}: {len(overlap)} khóa")

        os.makedirs(MASTER_DIR, exist_ok=True)
        tables_to_export = [
            ("A_Region", df_region),
            ("B_Size", df_size),
            ("D_Category", df_cat),
            ("C_BasicSizeChart", df_sizechart),
            ("E_T-Shirt", df_tshirt),
            ("F_DataTracking", df_tracking_all),
        ]
        conn = duckdb.connect()
        for tbl, df_src in tables_to_export:
            conn.register("_src", df_src)
            conn.execute(f"COPY _src TO '{os.path.join(MASTER_DIR, f'{tbl}.parquet')}' (FORMAT PARQUET)")
            conn.unregister("_src")
        conn.close()
        print(f"Đã xuất {len(tables_to_export)} bảng Parquet -> {MASTER_DIR} "
              f"({', '.join(f'{tbl}: {len(df_src):,}' for tbl, df_src in tables_to_export)})")


def main():
    DataTrackingProcessor().run()


if __name__ == "__main__":
    main()

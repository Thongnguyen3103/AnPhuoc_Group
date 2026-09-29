# -*- coding: utf-8 -*-
"""Xử lý HDD_QLKD + HDD_Report -> HDD_QLKD_Tong_hop.parquet (bảng snapshot, không
phân mảnh theo tháng — khác nhóm MonthlySourceProcessor nên không kế thừa base
class đó, nhưng vẫn cung cấp cùng interface run() để Run_All_Processing.py gọi thống nhất)."""
import csv
import glob
import os
import sys
import warnings

import numpy as np
import pandas as pd
import duckdb

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # 02.Data_Processing
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "00.Shared"))  # 00.Shared (Get_Paths...)
from Read_Write_Parquet import MASTER_DIR, load_master_table
import Get_Paths
from Convert_Size import actual_size

warnings.filterwarnings("ignore", category=UserWarning)


def robust_read_csv(path: str) -> pd.DataFrame:
    """Đọc CSV với xử lý encoding linh hoạt"""
    encodings_try = ["utf-8-sig", "utf-8", "cp1258", "cp1252", "latin1", "iso-8859-1"]
    with open(path, "rb") as fb:
        raw = fb.read(200_000)

    if raw.startswith(b'\xff\xfe') or raw.startswith(b'\xfe\xff'):
        encodings = ["utf-16", "utf-16-le", "utf-16-be"] + encodings_try
    else:
        encodings = encodings_try

    last_err = None
    for enc in encodings:
        try:
            with open(path, "r", encoding=enc, newline="", errors="ignore") as f:
                sample = f.read(200_000)
            if not sample:
                continue
            try:
                delimiter = csv.Sniffer().sniff(sample, delimiters=[",", ";", "\t", "|"]).delimiter
            except Exception:
                delimiter = ","
            rows = []
            with open(path, "r", encoding=enc, newline="", errors="ignore") as f:
                reader = csv.reader(f, delimiter=delimiter, quotechar='"', escapechar="\\", strict=False)
                rows.extend(row for row in reader)
            if not rows or len(rows) < 2:
                continue

            header = [" ".join(h.replace("\ufeff", "").strip().split()) for h in rows[0]]
            if not header or all(not h for h in header):
                continue

            n_cols = len(header)
            fixed = []
            for r in rows[1:]:
                if len(r) < n_cols:
                    r = r + [""] * (n_cols - len(r))
                elif len(r) > n_cols:
                    r = r[:n_cols]
                fixed.append(r)

            df = pd.DataFrame(fixed, columns=header).fillna("").astype(str)
            return df
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"Không thể đọc: {last_err}")


def clean_for_excel(df: pd.DataFrame) -> pd.DataFrame:
    """Làm sạch ký tự cấm trong Excel"""
    string_cols = [
        c for c in df.columns
        if pd.api.types.is_object_dtype(df[c]) or pd.api.types.is_string_dtype(df[c])
    ]
    for c in string_cols:
        df[c] = df[c].astype(str).str.replace(r'[\x00-\x08\x0B-\x0C\x0E-\x1F]', '', regex=True)
    return df


def adjust_output_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Điều chỉnh nhẹ data đầu ra theo format Power Query M."""
    result = df.copy()

    # Đổi tên trước để logic match rõ ràng hơn
    result = result.rename(columns={"Mã hàng": "Mahang"})

    result = result.drop(
        columns=["STT", "Số chứng từ", "Ngày gửi", "Dự kiến", "Tên hàng"],
        errors="ignore",
    )

    if "Size" in result.columns:
        if "Report_item_name" not in result.columns:
            result["Report_item_name"] = ""
        result["Size"] = [
            actual_size(sz, name) for sz, name in zip(result["Size"], result["Report_item_name"])
        ]

    for col in ["Dist_plan", "Production_month"]:
        if col in result.columns:
            result[col] = result[col].fillna("").astype(str)

    result = result.rename(columns={"Nơi nhận": "Store_name", "Số lượng": "Slg_TonKho"})
    result = result.drop(columns=["Đơn giá"], errors="ignore")
    result = result.drop(columns=["Sales", "Short_name", "Code_color"], errors="ignore")

    column_order = [
        "Mahang", "Size", "Slg_TonKho", "Store_name", "Operation", "Brand",
        "System_item_name", "Report_item_name", "Product_type", "Gender",
        "Product_group", "Group_Report", "Region", "Warehouse", "Status",
        "Color_group", "Dist_plan", "Form", "Production_month",
        "Production_year", "Style", "Attribute",
    ]
    existing_order = [c for c in column_order if c in result.columns]
    remaining_cols = [c for c in result.columns if c not in existing_order]
    result = result[existing_order + remaining_cols]
    result = result.rename(columns={"Slg_TonKho": "Qty_TonKho"})
    return result


def _sum_qty(df: pd.DataFrame, candidates: list) -> float:
    """Tìm cột số lượng theo tên (không phân biệt hoa/thường) trong candidates
    rồi cộng tổng (chấp nhận số dạng '1.234,5' hoặc '1234.5')."""
    if df is None or len(df) == 0:
        return 0.0
    lower_candidates = [c.lower() for c in candidates]
    col = next(
        (c for c in df.columns if c.strip() in candidates or c.strip().lower() in lower_candidates),
        None,
    )
    if col is None:
        return 0.0
    return float(pd.to_numeric(df[col].astype(str).str.replace(",", "."), errors="coerce").fillna(0).sum())


def _get_trang_thai(row):
    if "Product_type" in row.index:
        product_type = str(row["Product_type"]).strip()
        if "Thanh lý" in product_type or "thanh lý" in product_type.lower():
            return "Thanh lý"
    if "Sales" in row.index:
        try:
            sales_val = float(row["Sales"])
            if sales_val in [30.0, 50.0]:
                return "Sale"
        except Exception:
            pass
    return "Nguyên giá"


class HDDProcessor:
    """Gộp HDD_QLKD + HDD_Report, tra danh mục/khu vực, xuất
    D:\\...\\02.Master\\HDD_QLKD_Tong_hop.parquet."""

    def _read_folder(self, folder: str, label: str) -> pd.DataFrame:
        csv_files = sorted(glob.glob(os.path.join(folder, "*.csv")))
        excel_files = sorted(glob.glob(os.path.join(folder, "*.xls*")))
        if not csv_files and not excel_files:
            return pd.DataFrame()

        frames = []
        for f in csv_files:
            try:
                frames.append(robust_read_csv(f))
            except Exception as e:
                print(f"  ❌ {os.path.basename(f)}: {str(e)[:60]}")

        for f in excel_files:
            try:
                excel_file = pd.ExcelFile(f)
                for sheet in excel_file.sheet_names[:3]:
                    try:
                        df = pd.read_excel(f, sheet_name=sheet, dtype=str)
                        if len(df) > 0:
                            frames.append(df)
                            break
                    except Exception:
                        continue
            except Exception as e:
                print(f"  ❌ {os.path.basename(f)}: {str(e)[:60]}")

        if not frames:
            return pd.DataFrame()

        data = pd.concat(frames, ignore_index=True)
        print(f"✓ {label}: {len(data):,} dòng")
        data = data.dropna(how='all').fillna("")
        return data

    def run(self) -> pd.DataFrame | None:
        print("-" * 80)
        print("BẮT ĐẦU XỬ LÝ HDD_QLKD + HDD_REPORT")
        print("-" * 80)

        qlkd_data = self._read_folder(Get_Paths.nguon_hdd_qlkd, "QLKD")
        if qlkd_data.empty:
            print(f"❌ Không tìm thấy dữ liệu QLKD trong:\n{Get_Paths.nguon_hdd_qlkd}")
            return None
        for col in ["Size", "Operation", "Sales"]:
            if col not in qlkd_data.columns:
                qlkd_data[col] = ""

        report_data = self._read_folder(Get_Paths.nguon_hdd_report, "Report")

        qty_qlkd_goc = _sum_qty(qlkd_data, ["Số lượng"])
        qty_report_goc = _sum_qty(report_data, ["SoLuong"])
        print(f"📊 Tổng SL nguồn — QLKD: {qty_qlkd_goc:,.0f} | Report: {qty_report_goc:,.0f}")

        qlkd_data_original = qlkd_data.copy()
        soct_qlkd_col = None

        if len(report_data) > 0:
            soct_qlkd_col = next((c for c in qlkd_data.columns if "số chứng từ" in c.lower()), None)
            soct_report_col = next(
                (c for c in report_data.columns if c.strip() == "SoCT" or "soct" in c.lower()), None
            )

            if soct_qlkd_col and soct_report_col:
                soct_qlkd_set = set(qlkd_data[soct_qlkd_col].astype(str).str.strip())
                soct_qlkd_set.discard("")
                soct_report_set = set(report_data[soct_report_col].astype(str).str.strip())
                soct_report_set.discard("")
                soct_overlap = soct_qlkd_set & soct_report_set

                qlkd_data_temp = qlkd_data[soct_qlkd_col].astype(str).str.strip()
                qlkd_data = qlkd_data[~qlkd_data_temp.isin(soct_overlap)]

                report_data_temp = report_data[soct_report_col].astype(str).str.strip()
                report_filtered = report_data[report_data_temp.isin(soct_overlap)].copy()

                column_mapping = {
                    "STT": "STT",
                    "SoCT": "Số chứng từ",
                    "Ngay": "Ngày gửi",
                    "mahang": "Mã hàng",
                    "TenHang": "Tên hàng",
                    "GiaTri": "Đơn giá",
                    "SoLuong": "Số lượng",
                    "": "Dự kiến",
                    "CH_N": "Nơi nhận",
                    "Size": "Size",
                    "Tacnghiep": "Operation",
                    "salesoff": "Sales",
                }

                qlkd_cols = list(qlkd_data.columns)
                report_subset = pd.DataFrame()
                for report_col, qlkd_col in column_mapping.items():
                    if qlkd_col in qlkd_cols:
                        found_col = next(
                            (rc for rc in report_filtered.columns
                             if rc.strip() == report_col or (report_col and rc.strip().lower() == report_col.lower())),
                            None,
                        )
                        if found_col:
                            report_subset[qlkd_col] = report_filtered[found_col].astype(str)
                        elif qlkd_col not in report_subset.columns:
                            report_subset[qlkd_col] = ""
                for col in qlkd_cols:
                    if col not in report_subset.columns:
                        report_subset[col] = ""
                report_subset = report_subset[qlkd_cols]

                final_data = pd.concat([qlkd_data, report_subset], ignore_index=True)
                print(f"✓ Ghép QLKD + Report (SoCT trùng: {len(soct_overlap):,}): {len(final_data):,} dòng")

                # Đối chiếu SL cho đúng các SoCT trùng — cùng 1 chứng từ, QLKD và
                # Report phải khai cùng số lượng; chênh lệch ở đây là dấu hiệu lệch dữ liệu.
                overlap_mask = qlkd_data_original[soct_qlkd_col].astype(str).str.strip().isin(soct_overlap)
                qty_overlap_qlkd = _sum_qty(qlkd_data_original[overlap_mask], ["Số lượng"])
                qty_overlap_report = _sum_qty(report_subset, ["Số lượng"])
                diff = qty_overlap_qlkd - qty_overlap_report
                flag = "  ⚠️ LỆCH" if abs(diff) > 0.01 else "  ✓ khớp"
                print(f"📊 Đối chiếu SL {len(soct_overlap):,} SoCT trùng — QLKD: {qty_overlap_qlkd:,.0f} | "
                      f"Report: {qty_overlap_report:,.0f} | Chênh lệch: {diff:,.0f}{flag}")
            else:
                print("⚠️  Không tìm cột 'Số chứng từ' ở QLKD hoặc 'SoCT' ở Report")
                final_data = qlkd_data
        else:
            print("⚠️  Không có dữ liệu Report, dùng chỉ QLKD")
            final_data = qlkd_data

        danh_muc_df = load_master_table("D_Category")
        khu_vuc_df = load_master_table("A_Region")
        e_tshirt_df = load_master_table("E_T-Shirt")

        for col in ["Đơn giá", "Số lượng", "Sales"]:
            if col in final_data.columns:
                final_data[col] = pd.to_numeric(
                    final_data[col].astype(str).str.replace(",", "."), errors="coerce"
                ).fillna(0).astype(float)

        # Xử lý "Nơi nhận" - nếu trống thì lookup từ QLKD gốc
        if "Nơi nhận" in final_data.columns and soct_qlkd_col and "Nơi nhận" in qlkd_data_original.columns:
            noi_nhan_mapping = {}
            for _, row in qlkd_data_original.iterrows():
                soct_key = str(row[soct_qlkd_col]).strip()
                noi_nhan_val = str(row["Nơi nhận"]).strip()
                if soct_key and noi_nhan_val:
                    noi_nhan_mapping[soct_key] = noi_nhan_val

            for idx, row in final_data.iterrows():
                noi_nhan_current = str(final_data.at[idx, "Nơi nhận"]).strip()
                if not noi_nhan_current:
                    soct_val = str(final_data.at[idx, soct_qlkd_col]).strip() if soct_qlkd_col in final_data.columns else ""
                    if soct_val in noi_nhan_mapping:
                        final_data.at[idx, "Nơi nhận"] = noi_nhan_mapping[soct_val]

        if "Mã hàng" in final_data.columns:
            final_data["Short_name"] = final_data["Mã hàng"].astype(str).apply(lambda x: x[:-4] if len(x) > 4 else "")
            final_data["Code_color"] = final_data["Mã hàng"].astype(str).apply(lambda x: x[-4:] if len(x) >= 4 else x)

        if len(danh_muc_df) > 0 and "Short_name" in final_data.columns:
            lookup_cols = ["Brand", "System_item_name", "Report_item_name", "Product_type", "Gender", "Product_group", "Group_Report"]
            for lookup_col in lookup_cols:
                if lookup_col not in final_data.columns:
                    final_data[lookup_col] = ""
                if lookup_col in danh_muc_df.columns:
                    mapping = dict(zip(danh_muc_df["Short_name"], danh_muc_df[lookup_col]))
                    final_data[lookup_col] = final_data["Short_name"].apply(lambda x: mapping.get(str(x).strip(), ""))

        if len(khu_vuc_df) > 0 and "Nơi nhận" in final_data.columns:
            for khu_vuc_col in ["Region", "Warehouse"]:
                if khu_vuc_col not in final_data.columns:
                    final_data[khu_vuc_col] = ""
                if khu_vuc_col in khu_vuc_df.columns and "Store_name" in khu_vuc_df.columns:
                    mapping = dict(zip(khu_vuc_df["Store_name"], khu_vuc_df[khu_vuc_col]))
                    final_data[khu_vuc_col] = final_data["Nơi nhận"].apply(lambda x: mapping.get(str(x).strip(), ""))

        if len(e_tshirt_df) > 0 and "Mã hàng" in final_data.columns and all(c in e_tshirt_df.columns for c in ["item_code", "T-shirt_name"]):
            e_tshirt_clean = e_tshirt_df[["item_code", "T-shirt_name"]].copy()
            e_tshirt_clean["item_code"] = e_tshirt_clean["item_code"].astype(str).str.strip()
            e_tshirt_clean = e_tshirt_clean.drop_duplicates("item_code")
            final_data["Mã hàng"] = final_data["Mã hàng"].astype(str).str.strip()
            final_data = final_data.merge(e_tshirt_clean, left_on="Mã hàng", right_on="item_code", how="left")
            tshirt = final_data["T-shirt_name"].fillna("").astype(str).str.strip()
            if "Report_item_name" in final_data.columns:
                final_data["Report_item_name"] = np.where(tshirt != "", tshirt, final_data["Report_item_name"])
            else:
                final_data["Report_item_name"] = tshirt
            final_data = final_data.drop(columns=["item_code", "T-shirt_name"], errors="ignore")

        final_data["Status"] = final_data.apply(_get_trang_thai, axis=1)
        final_data = adjust_output_columns(final_data)
        final_data = clean_for_excel(final_data)

        os.makedirs(MASTER_DIR, exist_ok=True)
        out_path = os.path.join(MASTER_DIR, "HDD_QLKD_Tong_hop.parquet")
        con = duckdb.connect()
        con.register("final_data", final_data)
        con.execute(f"COPY final_data TO '{out_path}' (FORMAT PARQUET)")
        con.close()

        output_qty_col = "Qty_TonKho" if "Qty_TonKho" in final_data.columns else "Số lượng"
        tong_sl_output = pd.to_numeric(final_data.get(output_qty_col, 0), errors="coerce").fillna(0).sum()
        print(f"HDD_QLKD_Tong_hop — {len(final_data):,} dòng | Tổng Qty_TonKho: {tong_sl_output:,.0f} -> {out_path}")
        return final_data


def main():
    HDDProcessor().run()


if __name__ == "__main__":
    main()

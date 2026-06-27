
import os, csv, glob, warnings
import pandas as pd
import numpy as np
import duckdb

FOLDER_HDD_QLKD = r"\\hovmfs01\PKD\PhanPhoi\Thong.Nguyen\Analysis_data\5.In_transit_stock_HDD\1.HDD_QLKD"
FOLDER_HDD_REPORT = r"\\hovmfs01\PKD\PhanPhoi\Thong.Nguyen\Analysis_data\5.In_transit_stock_HDD\2.HDD_Report"

warnings.filterwarnings("ignore", category=UserWarning)

def robust_read_csv(path: str) -> pd.DataFrame:
    """Đọc CSV với xử lý encoding linh hoạt"""
    encodings_try = ["utf-8-sig","utf-8","cp1258","cp1252","latin1","iso-8859-1"]
    with open(path, "rb") as fb:
        raw = fb.read(200_000)
    
    if raw.startswith(b'\xff\xfe') or raw.startswith(b'\xfe\xff'):
        encodings = ["utf-16","utf-16-le","utf-16-be"] + encodings_try
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
                delimiter = csv.Sniffer().sniff(sample, delimiters=[",",";","\t","|"]).delimiter
            except Exception:
                delimiter = ","
            rows = []
            with open(path, "r", encoding=enc, newline="", errors="ignore") as f:
                reader = csv.reader(f, delimiter=delimiter, quotechar='"', escapechar="\\", strict=False)
                rows.extend(row for row in reader)
            if not rows or len(rows) < 2:
                continue
            
            header = [" ".join(h.replace("\ufeff","").strip().split()) for h in rows[0]]
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

def read_lookup_sheet(path: str, table_name: str) -> pd.DataFrame:
    try:
        con = duckdb.connect(path, read_only=True)
        df = con.execute(f'SELECT * FROM "{table_name}"').df()
        con.close()
        return df.fillna("").astype(str)
    except Exception as e:
        print(f"  ⚠️ Không đọc được table '{table_name}': {str(e)[:80]}")
        return pd.DataFrame()

def adjust_output_columns(
    df: pd.DataFrame,
    b_size_df: pd.DataFrame,
) -> pd.DataFrame:
    """Điều chỉnh nhẹ data đầu ra theo format Power Query M."""
    result = df.copy()

    # Đổi tên trước để logic match rõ ràng hơn
    result = result.rename(columns={"Mã hàng": "Mahang"})

    result = result.drop(
        columns=["STT", "Số chứng từ", "Ngày gửi", "Dự kiến", "Tên hàng"],
        errors="ignore",
    )

    size_cols = ["System_item_name", "System_size", "Actual_size"]
    if (
        len(b_size_df) > 0
        and all(c in result.columns for c in ["Report_item_name", "Size"])
        and all(c in b_size_df.columns for c in size_cols)
    ):
        result = result.merge(
            b_size_df[size_cols].drop_duplicates(subset=["System_item_name", "System_size"]),
            how="left",
            left_on=["Report_item_name", "Size"],
            right_on=["System_item_name", "System_size"],
            suffixes=("", "_size"),
        )
        result = result.drop(columns=["System_item_name_size", "System_size"], errors="ignore")

    for col in ["Dist_plan", "Production_month"]:
        if col in result.columns:
            result[col] = result[col].fillna("").astype(str)

    result = result.rename(columns={"Nơi nhận": "Store_name", "Số lượng": "Slg_TonKho"})
    result = result.drop(columns=["Đơn giá"], errors="ignore")
    result = result.drop(columns=["Sales", "Short_name", "Code_color"], errors="ignore")

    if "Size" in result.columns and "Actual_size" in result.columns:
        actual_size = result["Actual_size"]
        result["Size"] = actual_size.where(
            actual_size.notna() & (actual_size.astype(str).str.strip() != ""),
            result["Size"],
        )

    result = result.drop(columns=["Actual_size"], errors="ignore")

    column_order = [
        "Mahang", "Size", "Slg_TonKho", "Store_name", "Operation", "Brand",
        "System_item_name", "Report_item_name", "Product_type", "Gender",
        "Product_group", "Group_Report", "Region", "Warehouse", "Status",
        "Color_group", "Dist_plan", "Form", "Production_month",
        "Production_year", "Style","Attribute",
    ]
    existing_order = [c for c in column_order if c in result.columns]
    remaining_cols = [c for c in result.columns if c not in existing_order]
    result = result[existing_order + remaining_cols]
    result = result.rename(columns={"Slg_TonKho": "Qty_TonKho"})
    return result

def main():
    print("-" * 80)
    print("BẮTĐẦU XỬ LÝ HDD_QLKD + HDD_REPORT")
    print("-" * 80)
    
    # ===== BƯỚC 1: ĐỌC DỮ LIỆU TỪ HDD_QLKD =====
    print("\n📁 BƯỚC 1: Đọc dữ liệu từ HDD_QLKD...")
    csv_files_qlkd = sorted(glob.glob(os.path.join(FOLDER_HDD_QLKD, "*.csv")))
    excel_files_qlkd = sorted(glob.glob(os.path.join(FOLDER_HDD_QLKD, "*.xls*")))
    
    all_files_qlkd = csv_files_qlkd + excel_files_qlkd
    if not all_files_qlkd:
        print(f"❌ Không tìm thấy file CSV/Excel trong:\n{FOLDER_HDD_QLKD}")
        return
    
    frames_qlkd = []
    
    # Đọc CSV QLKD
    for i, f in enumerate(csv_files_qlkd, 1):
        try:
            df = robust_read_csv(f)
            frames_qlkd.append(df)
        except Exception as e:
            print(f"  ❌ {os.path.basename(f)}: {str(e)[:60]}")
            continue
    
    # Đọc Excel QLKD
    for i, f in enumerate(excel_files_qlkd, len(csv_files_qlkd) + 1):
        try:
            excel_file = pd.ExcelFile(f)
            for sheet in excel_file.sheet_names[:3]:
                try:
                    df = pd.read_excel(f, sheet_name=sheet, dtype=str)
                    if len(df) > 0:
                        frames_qlkd.append(df)
                        break
                except:
                    continue
        except Exception as e:
            print(f"  ❌ {os.path.basename(f)}: {str(e)[:60]}")
            continue
    
    if not frames_qlkd:
        print("❌ Không đọc được dữ liệu QLKD từ file nào")
        return
    
    print("\n🔄 Đang gộp dữ liệu QLKD...")
    qlkd_data = pd.concat(frames_qlkd, ignore_index=True)
    print(f"✓ QLKD: {len(qlkd_data):,} dòng")

    print("🧹 Làm sạch dữ liệu QLKD...")
    qlkd_data = qlkd_data.dropna(how='all')
    qlkd_data = qlkd_data.fillna("")
    print(f"✓ Sau làm sạch: {len(qlkd_data):,} dòng")

    # Thêm cột nếu chưa có
    for col in ["Size", "Operation", "Sales"]:
        if col not in qlkd_data.columns:
            qlkd_data[col] = ""

    # ===== BƯỚC 2: ĐỌC DỮ LIỆU TỪ HDD_REPORT =====
    print("\n📁 BƯỚC 2: Đọc dữ liệu từ HDD_Report...")
    csv_files_report = sorted(glob.glob(os.path.join(FOLDER_HDD_REPORT, "*.csv")))
    excel_files_report = sorted(glob.glob(os.path.join(FOLDER_HDD_REPORT, "*.xls*")))
    
    all_files_report = csv_files_report + excel_files_report
    if not all_files_report:
        print(f"⚠️  Không tìm thấy file Report")
        report_data = pd.DataFrame()
    else:
        frames_report = []
        
        # Đọc CSV Report
        for i, f in enumerate(csv_files_report, 1):
            try:
                df = robust_read_csv(f)
                frames_report.append(df)
            except Exception as e:
                print(f"  ❌ {os.path.basename(f)}: {str(e)[:60]}")
                continue
        
        # Đọc Excel Report
        for i, f in enumerate(excel_files_report, len(csv_files_report) + 1):
            try:
                excel_file = pd.ExcelFile(f)
                for sheet in excel_file.sheet_names[:3]:
                    try:
                        df = pd.read_excel(f, sheet_name=sheet, dtype=str)
                        if len(df) > 0:
                            frames_report.append(df)
                            break
                    except:
                        continue
            except Exception as e:
                print(f"  ❌ {os.path.basename(f)}: {str(e)[:60]}")
                continue
        
        if frames_report:
            print("🔄 Đang gộp dữ liệu Report...")
            report_data = pd.concat(frames_report, ignore_index=True)
            print(f"✓ Report: {len(report_data):,} dòng")

            print("🧹 Làm sạch dữ liệu Report...")
            report_data = report_data.dropna(how='all')
            report_data = report_data.fillna("")
        else:
            print("⚠️  Không đọc được dữ liệu Report")
            report_data = pd.DataFrame()

    # ===== BƯỚC 3: MATCH QLKD VỚI REPORT =====
    # Lưu QLKD gốc để lookup "Nơi nhận"
    qlkd_data_original = qlkd_data.copy()
    soct_qlkd_col = None
    
    if len(report_data) > 0:
        print("\n🔍 Match dữ liệu QLKD với Report...")
        
        # Tìm cột "Số chứng từ" ở QLKD
        soct_qlkd_col = None
        for col in qlkd_data.columns:
            if "số chứng từ" in col.lower():
                soct_qlkd_col = col
                break
        
        # Tìm cột "SoCT" ở Report
        soct_report_col = None
        for col in report_data.columns:
            if col.strip() == "SoCT" or "soct" in col.lower():
                soct_report_col = col
                break
        
        if soct_qlkd_col and soct_report_col:
            # Lấy danh sách SoCT từ QLKD trước khi xóa (để ghép lại)
            soct_qlkd_set = set(qlkd_data[soct_qlkd_col].astype(str).str.strip())
            soct_qlkd_set.discard("")
            
            # Lấy danh sách SoCT từ Report
            soct_report_set = set(report_data[soct_report_col].astype(str).str.strip())
            soct_report_set.discard("")
            
            print(f"  ✓ Tìm thấy cột QLKD: '{soct_qlkd_col}'")
            print(f"  ✓ Tìm thấy cột Report: '{soct_report_col}'")
            print(f"  ✓ Danh sách SoCT ở QLKD: {len(soct_qlkd_set):,} mục")
            print(f"  ✓ Danh sách SoCT ở Report: {len(soct_report_set):,} mục")
            
            # Tìm những SoCT trùng giữa QLKD và Report
            soct_overlap = soct_qlkd_set & soct_report_set
            print(f"  ✓ SoCT trùng: {len(soct_overlap):,} mục")
            # Xóa các dòng ở QLKD trùng với Report
            before_delete = len(qlkd_data)
            qlkd_data_temp = qlkd_data[soct_qlkd_col].astype(str).str.strip()
            qlkd_data = qlkd_data[~qlkd_data_temp.isin(soct_overlap)]
            after_delete = len(qlkd_data)
            
            deleted_count = before_delete - after_delete
            print(f"🗑️  Xóa {deleted_count:,} dòng QLKD trùng")
            
            # Lọc Report chỉ lấy những SoCT trùng
            report_data_temp = report_data[soct_report_col].astype(str).str.strip()
            report_filtered = report_data[report_data_temp.isin(soct_overlap)].copy()
            print(f"🔀 Ghép {len(report_filtered):,} dòng Report")
            
            # Mapping cột Report -> QLKD
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
                "salesoff": "Sales"
            }
            
            # Chuẩn bị dữ liệu Report để ghép vào QLKD
            qlkd_cols = list(qlkd_data.columns)
            report_subset = pd.DataFrame()
            
            for report_col, qlkd_col in column_mapping.items():
                if qlkd_col in qlkd_cols:
                    # Tìm cột Report tương ứng
                    found_col = None
                    for rc in report_filtered.columns:
                        if rc.strip() == report_col or (report_col and rc.strip().lower() == report_col.lower()):
                            found_col = rc
                            break
                    
                    if found_col:
                        report_subset[qlkd_col] = report_filtered[found_col].astype(str)
                    elif qlkd_col not in report_subset.columns:
                        report_subset[qlkd_col] = ""
            
            # Thêm cột còn lại nếu QLKD có
            for col in qlkd_cols:
                if col not in report_subset.columns:
                    report_subset[col] = ""
            
            # Sắp xếp cột theo QLKD
            report_subset = report_subset[qlkd_cols]
            
            # Ghép QLKD + Report (chỉ những SoCT trùng)
            result = pd.concat([qlkd_data, report_subset], ignore_index=True)
            print(f"✓ Ghép xong: {len(result):,} dòng")
            
            final_data = result
        else:
            print(f"⚠️  Không tìm cột 'Số chứng từ' ở QLKD hoặc 'SoCT' ở Report")
            print(f"    QLKD columns: {list(qlkd_data.columns)}")
            print(f"    Report columns: {list(report_data.columns)}")
            final_data = qlkd_data
    else:
        print("\n⚠️  Không có dữ liệu Report, dùng chỉ QLKD")
        final_data = qlkd_data

    # ===== BƯỚC 5: ĐỌC BẢNG LOOKUP TỪ DATABASE =====
    print("\n📁 BƯỚC 5: Đọc bảng lookup từ Database...")
    db_file = r"D:\DataBase\DuckDB\Database_AP.duckdb"
    
    danh_muc_df = read_lookup_sheet(db_file, "D_Category")
    khu_vuc_df = read_lookup_sheet(db_file, "A_Region")
    b_size_df = read_lookup_sheet(db_file, "B_Size")
    e_tshirt_df = read_lookup_sheet(db_file, "E_T-Shirt")
    print("✓ Đọc Database xong")

    # ===== BƯỚC 6: XUẤT EXCEL =====    
    print("\n📊 Xử lý dữ liệu trước xuất...")
    
    # Convert "Đơn giá", "Số lượng", "Sales" thành number
    for col in ["Đơn giá", "Số lượng", "Sales"]:
        if col in final_data.columns:
            final_data[col] = pd.to_numeric(
                final_data[col].astype(str).str.replace(",", "."),
                errors="coerce"
            ).fillna(0).astype(float)
    print("  🔄 Convert 'Đơn giá', 'Số lượng', 'Sales' thành số ✓")
    
    # Xử lý "Nơi nhận" - nếu trống thì lookup từ QLKD gốc
    if "Nơi nhận" in final_data.columns and soct_qlkd_col and "Nơi nhận" in qlkd_data_original.columns:
        print("  🔀 Xử lý cột 'Nơi nhận' ✓")
        # Tạo mapping từ "Số chứng từ" -> "Nơi nhận" từ QLKD gốc
        noi_nhan_mapping = {}
        for idx, row in qlkd_data_original.iterrows():
            soct_key = str(row[soct_qlkd_col]).strip()
            noi_nhan_val = str(row["Nơi nhận"]).strip()
            if soct_key and noi_nhan_val:
                noi_nhan_mapping[soct_key] = noi_nhan_val
        
        # Cập nhật "Nơi nhận" nếu trống
        for idx, row in final_data.iterrows():
            noi_nhan_current = str(final_data.at[idx, "Nơi nhận"]).strip()
            if not noi_nhan_current:  # Nếu trống
                soct_val = str(final_data.at[idx, soct_qlkd_col]).strip() if soct_qlkd_col in final_data.columns else ""
                if soct_val in noi_nhan_mapping:
                    final_data.at[idx, "Nơi nhận"] = noi_nhan_mapping[soct_val]
    
    # Thêm cột "Tên viết tắt" và "Mã màu" từ "Mã hàng"
    if "Mã hàng" in final_data.columns:
        print("  📝 Thêm 'Tên viết tắt', 'Mã màu' ✓")
        # Tên viết tắt = Mã hàng trừ 4 ký tự cuối
        final_data["Short_name"] = final_data["Mã hàng"].astype(str).apply(lambda x: x[:-4] if len(x) > 4 else "")
        # Mã màu = 4 ký tự cuối
        final_data["Code_color"] = final_data["Mã hàng"].astype(str).apply(lambda x: x[-4:] if len(x) >= 4 else x)
    
    # Lookup từ "Tên viết tắt" với sheet "04. Danh mục"
    if len(danh_muc_df) > 0 and "Short_name" in final_data.columns:
        print("  🔍 Lookup Danh mục ✓")
        lookup_cols = ["Brand", "System_item_name", "Report_item_name", "Product_type", "Gender", "Product_group","Group_Report"]
        
        # Tạo mapping từ danh mục
        for lookup_col in lookup_cols:
            if lookup_col not in final_data.columns:
                final_data[lookup_col] = ""
            
            if lookup_col in danh_muc_df.columns:
                # Tạo dict mapping từ Tên viết tắt -> lookup_col
                mapping = dict(zip(danh_muc_df["Short_name"], danh_muc_df[lookup_col]))
                
                # Apply mapping
                final_data[lookup_col] = final_data["Short_name"].apply(
                    lambda x: mapping.get(str(x).strip(), "")
                )
    
    # Lookup từ "Nơi nhận" với sheet "01. Khu vực"
    if len(khu_vuc_df) > 0 and "Nơi nhận" in final_data.columns:
        print("  🔍 Lookup Khu vực ✓")
        khu_vuc_cols = ["Region", "Warehouse"]
        
        # Tạo mapping từ Khu vực
        for khu_vuc_col in khu_vuc_cols:
            if khu_vuc_col not in final_data.columns:
                final_data[khu_vuc_col] = ""
            
            if khu_vuc_col in khu_vuc_df.columns and "Store_name" in khu_vuc_df.columns:
                # Tạo dict mapping từ Store_name -> khu_vuc_col
                mapping = dict(zip(khu_vuc_df["Store_name"], khu_vuc_df[khu_vuc_col]))
                
                # Apply mapping
                final_data[khu_vuc_col] = final_data["Nơi nhận"].apply(
                    lambda x: mapping.get(str(x).strip(), "")
                )
    
    # Lookup từ "Mã hàng" với sheet "E_T-Shirt"
    if len(e_tshirt_df) > 0 and "Mã hàng" in final_data.columns:
        if all(c in e_tshirt_df.columns for c in ["item_code", "T-shirt_name"]):
            print("  🔍 Lookup E_T-Shirt ✓")
            # Dọn dẹp item_code và Mã hàng trước khi merge
            e_tshirt_clean = e_tshirt_df[["item_code", "T-shirt_name"]].copy()
            e_tshirt_clean["item_code"] = e_tshirt_clean["item_code"].astype(str).str.strip()
            e_tshirt_clean = e_tshirt_clean.drop_duplicates("item_code")
            
            final_data["Mã hàng"] = final_data["Mã hàng"].astype(str).str.strip()
            
            final_data = final_data.merge(
                e_tshirt_clean,
                left_on="Mã hàng",
                right_on="item_code",
                how="left",
            )
            tshirt = final_data["T-shirt_name"].fillna("").astype(str).str.strip()
            if "Report_item_name" in final_data.columns:
                final_data["Report_item_name"] = np.where(tshirt != "", tshirt, final_data["Report_item_name"])
            else:
                final_data["Report_item_name"] = tshirt
            final_data = final_data.drop(columns=["item_code", "T-shirt_name"], errors="ignore")
    
    # Thêm cột "Trạng thái"
    print("\n📝 Thêm cột 'Trạng thái' ✓")
    if "Trạng thái" not in final_data.columns:
        final_data["Status"] = ""
    
    def get_trang_thai(row):
        # Kiểm tra "Product_type" có "Thanh lý"
        if "Product_type" in row.index:
            product_type = str(row["Product_type"]).strip()
            if "Thanh lý" in product_type or "thanh lý" in product_type.lower():
                return "Thanh lý"
        
        # Kiểm tra "Sales" = 30 hoặc 50
        if "Sales" in row.index:
            try:
                sales_val = float(row["Sales"])
                if sales_val in [30.0, 50.0]:
                    return "Sale"
            except:
                pass
        
        # Còn lại
        return "Nguyên giá"
    
    final_data["Status"] = final_data.apply(get_trang_thai, axis=1)

    print("  🔄 Điều chỉnh cột theo Power Query M ✓")
    final_data = adjust_output_columns(final_data, b_size_df)

    print("\n🧹 Làm sạch ký tự cấm...")
    final_data = clean_for_excel(final_data)
    print("✓ Ký tự cấm làm sạch xong")
    
    print("\n💾 Ghi vào DuckDB...")
    con = duckdb.connect(db_file)
    con.execute('DROP TABLE IF EXISTS "HDD_QLKD_Tong_hop"')
    con.execute('CREATE TABLE "HDD_QLKD_Tong_hop" AS SELECT * FROM final_data')
    con.close()
    print("✓ Ghi DuckDB xong")

    print("\n" + "-" * 80)
    print("✅ HOÀN THÀNH XỬ LÝ DỮ LIỆU HDD")
    print("-" * 80)
    print(f"📍 Database: {db_file}")
    print(f"📊 Số dòng: {len(final_data):,} | Số cột: {final_data.shape[1]}")

    # In tổng số lượng từ HDD_QLKD gốc (trước khi xóa)
    if "Số lượng" in qlkd_data_original.columns:
        tong_sl_qlkd = pd.to_numeric(
            qlkd_data_original["Số lượng"].astype(str).str.replace(",", "."),
            errors="coerce"
        ).fillna(0).sum()
        print(f"📊 Tổng số lượng từ HDD_QLKD (gộp): {tong_sl_qlkd:,.0f}")

    # In tổng số lượng từ file output sau xử lý
    output_qty_col = "Qty_TonKho" if "Qty_TonKho" in final_data.columns else "Số lượng"
    if output_qty_col in final_data.columns:
        tong_sl_output = pd.to_numeric(final_data[output_qty_col], errors="coerce").fillna(0).sum()
        print(f"📊 Tổng Qty_TonKho trong HDD_QLKD_Tong_hop: {tong_sl_output:,.0f}")
    
    print("-" * 80)

if __name__ == "__main__":
    main()

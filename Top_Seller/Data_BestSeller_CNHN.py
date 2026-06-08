# -*- coding: utf-8 -*-
import os, csv, glob, warnings, unicodedata, re, sys, io
import pandas as pd
import numpy as np
from tqdm import tqdm

# Set stdout encoding to UTF-8
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

FOLDER_BAN   = r"\\hovmfs01\PKD\PhanPhoi\Thong.Nguyen\Report_BestSeller\02.Data_SBan"
PATH_DATABASE= r"\\hovmfs01\PKD\PhanPhoi\Thong.Nguyen\Analysis_data\1.Processed_data\1.Data_Tracking.xlsx"
OUT_XLSX     = r"\\hovmfs01\PKD\PhanPhoi\Thong.Nguyen\Report_BestSeller\04.Data_Xly\Data_BestSeller_Khuvuc.xlsx".replace("Phooi","PhanPhoi")

REQ_COLS = [
    "TenCuaHang","SoChungTu","NgayChungTu","DienGiai","MaHang",
    "SoLuong","DonGia","ThueVat","ThanhTien","Size","TacNghiep","Sales"
]

warnings.filterwarnings("ignore", category=UserWarning)

# ===== Helpers =====
def strip_accents(s: str) -> str:
    if s is None: return ""
    s = str(s)
    s = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in s if not unicodedata.combining(ch))

def keyize(s: str) -> str:
    s = strip_accents(s).lower()
    return "".join(ch for ch in s if ch.isalnum())

CANON_KEYS = {
    "tencuahang":"TenCuaHang","sochungtu":"SoChungTu","ngaychungtu":"NgayChungTu",
    "diengiai":"DienGiai","mahang":"MaHang","soluong":"SoLuong","dongia":"DonGia",
    "thuevat":"ThueVat","thanhtien":"ThanhTien","size":"Size","mau":"Mau",
    "tacnghiep":"TacNghiep","sales":"Sales","sale":"Sales",
}

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    return df.rename(columns={c: " ".join(str(c).replace("\ufeff","").strip().split()) for c in df.columns})

def smart_rename(df: pd.DataFrame) -> pd.DataFrame:
    return df.rename(columns={c: CANON_KEYS.get(keyize(c), c) for c in df.columns})

def to_number(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.replace(r"[^\d\-,\.]", "", regex=True, n=1)
    s = s.str.replace(",", ".", regex=False)
    return pd.to_numeric(s, errors="coerce")

def extract_noidung_before_colon(s: pd.Series) -> pd.Series:
    s = s.astype(str)
    parts = s.str.split(":", n=1, expand=True)
    return parts[0].str.strip() if parts.shape[1] > 1 else pd.Series([""]*len(s))

def clean_for_excel(df: pd.DataFrame) -> pd.DataFrame:
    string_cols = df.select_dtypes(include=["object", "string"]).columns
    for c in string_cols:
        df[c] = df[c].astype(str).str.replace(r'[\x00-\x08\x0B-\x0C\x0E-\x1F]', '', regex=True)
    return df

def robust_read_csv(path: str) -> pd.DataFrame:
    encodings_try = ["utf-8-sig","utf-8","cp1258","cp1252","latin1","utf-16","utf-16-le","utf-16-be"]
    with open(path, "rb") as fb:
        raw = fb.read(200_000)
    prefer_utf16 = raw.count(b"\x00") > 100
    encodings = (["utf-16","utf-16-le","utf-16-be"] + encodings_try) if prefer_utf16 else encodings_try

    last_err = None
    for enc in encodings:
        try:
            with open(path, "r", encoding=enc, newline="") as f:
                sample = f.read(200_000)
            if not sample: raise RuntimeError("File rỗng")
            try:
                delimiter = csv.Sniffer().sniff(sample, delimiters=[",",";","\t","|"]).delimiter
            except Exception:
                delimiter = ","
            rows = []
            with open(path, "r", encoding=enc, newline="") as f:
                reader = csv.reader(f, delimiter=delimiter, quotechar='"', escapechar="\\", strict=False)
                for row in tqdm(reader, desc="    Reading rows", unit=" rows", leave=False, miniters=1000):
                    rows.append(row)
            if not rows: raise RuntimeError("Không có dữ liệu")
            header = [" ".join(h.replace("\ufeff","").strip().split()) for h in rows[0]]
            n_cols = len(header); fixed=[]
            for r in rows[1:]:
                if len(r) < n_cols: r = r + [""]*(n_cols-len(r))
                elif len(r) > n_cols:
                    r = r[:n_cols-1] + [delimiter.join(r[n_cols-1:])]
                fixed.append(r)
            df = pd.DataFrame(fixed, columns=header).fillna("").astype(str)
            df = normalize_columns(df); df = smart_rename(df)
            return df
        except Exception as e:
            last_err = e; continue
    raise RuntimeError(f"Không đọc được file: {path}. Lỗi cuối: {last_err}")

# ===== Main =====
def main():
    print("=" * 60)
    print("BẮTĐẦU XỬ LÝ DỮ LIỆU BÁN")
    print("=" * 60)
    
    csv_files = sorted(glob.glob(os.path.join(FOLDER_BAN, "*.csv")))
    if not csv_files:
        raise FileNotFoundError(f"Không tìm thấy CSV trong thư mục: {FOLDER_BAN}")
    
    print(f"\n📁 Tìm thấy {len(csv_files)} file CSV")

    frames=[]
    print("📖 Đang đọc file CSV...")
    for i, f in enumerate(csv_files, 1):
        print(f"  [{i}/{len(csv_files)}] {os.path.basename(f)}")
        df = robust_read_csv(f)
        for c in REQ_COLS:
            if c not in df.columns: df[c] = ""
        frames.append(df[REQ_COLS].copy())
    
    print("🔄 Đang gộp dữ liệu...")
    data = pd.concat(frames, ignore_index=True)
    print(f"✓ Tổng cộng {len(data):,} dòng")

    print("\n⏰ Xử lý ngày tháng...")
    # Ngày & Thang/Nam/Quy
    data["NgayChungTu"] = pd.to_datetime(data["NgayChungTu"], errors="coerce", dayfirst=True, infer_datetime_format=True)
    data["Month"] = data["NgayChungTu"].dt.month
    data["Year"]   = data["NgayChungTu"].dt.year
    data["Quarter"]   = data["NgayChungTu"].dt.quarter
    print("✓ Ngày tháng xử lý xong")

    print("📝 Xử lý nội dung (trước dấu ':')...")
    # NoiDung = phần TRƯỚC ':'
    data["NoiDung"] = extract_noidung_before_colon(data["DienGiai"])
    print("✓ Nội dung xử lý xong")

    print("🔤 Xử lý mã hàng...")
    # TenVietTat & MaMau
    s_ma = data["MaHang"].astype(str)
    data["Short_name"] = np.where(s_ma.str.len() >= 4, s_ma.str[:-4], s_ma)
    data["Code_Color"]      = np.where(s_ma.str.len() >= 4, s_ma.str[-4:], "")
    print("✓ Mã hàng xử lý xong")

    print("🔢 Chuyển đổi số liệu...")
    # Ép số - dùng vectorized operations
    data[["SoLuong","DonGia","ThanhTien","Sales"]] = data[["SoLuong","DonGia","ThanhTien","Sales"]].apply(to_number)
    print("✓ Số liệu chuyển đổi xong")

    print("🗄️  Đọc Database...")
    # Đọc Database & merge
    dm = pd.read_excel(PATH_DATABASE, sheet_name="D_Category", dtype=str)
    kv = pd.read_excel(PATH_DATABASE, sheet_name="A_Region", dtype=str)
    dt = pd.read_excel(PATH_DATABASE, sheet_name="F_DataTracking", dtype=str)
    dm = normalize_columns(dm); kv = normalize_columns(kv); dt = normalize_columns(dt)

    for c in ["Short_name","Brand","System_item_name","Report_item_name","Product_type","Gender","Product_group"]:
        if c not in dm.columns: raise KeyError(f"Thiếu cột '{c}' trong 'D_Category'")
    for c in ["Store_name","Region","Warehouse"]:
        if c not in kv.columns: raise KeyError(f"Thiếu cột '{c}' trong 'A_Region'")
    
    # Kiểm tra các cột trong F_DataTracking
    dt_required = ["System_item_name","Operation","Color_code","Composition","Color_tone","Color_group","Form","Style","Attribute","Description","Price","Dist_plan","Production_month","Production_year"]
    missing_cols = [c for c in dt_required if c not in dt.columns]
    if missing_cols: raise KeyError(f"Thiếu cột trong 'F_DataTracking': {missing_cols}")
    
    # Chuẩn bị F_DataTracking: đổi tên cột để khớp với data
    dt_merge = dt[dt_required].rename(columns={
        "System_item_name": "Report_item_name",
        "Operation": "TacNghiep",
        "Color_code": "Code_Color"
    })
    print("✓ Database đọc xong")

    print("🔗 Gộp dữ liệu với Danh mục, Khu vực & F_DataTracking...")
    data = data.merge(
        dm[["Short_name","Brand","System_item_name","Report_item_name","Product_type","Gender","Product_group"]].rename(columns={"Short_name":"Short_name"}),
        on="Short_name", how="left"
    ).merge(
        kv[["Store_name","Region","Warehouse"]].rename(columns={"Store_name":"TenCuaHang"}),
        on="TenCuaHang", how="left"
    ).merge(
        dt_merge,
        on=["Report_item_name","TacNghiep","Code_Color"], how="inner"
    )
    print("✓ Gộp xong")

    print("🏷️  Xác định trạng thái (Thanh Lý / Sale / Nguyên Giá)...")
    # Trạng_Thái (robust với hoa/thường)
    product_type = data["Product_type"].astype(str).str.strip()
    sales = pd.to_numeric(data["Sales"], errors="coerce")

    mask_thanhly = product_type.str.contains("Thanh lý", case=False, na=False)
    mask_sale    = (~mask_thanhly) & sales.isin([30, 50])  # chỉ gán Sale khi KHÔNG phải Thanh Lý

    data["Status"] = np.select(
        [mask_thanhly, mask_sale],
        ["Thanh Lý", "Sale"],
    default="Nguyên Giá",
)
    print("✓ Trạng thái xác định xong")
    
    print("🔍 Lọc dữ liệu (Status = Nguyên Giá, Nội dung, Nhãn hiệu, Gender)...")
    # Lọc chỉ giữ Status = "Nguyên Giá"
    before_status = len(data)
    data = data[data["Status"] == "Nguyên Giá"]
    print(f"✓ Sau lọc Status: {len(data):,}/{before_status:,} dòng ({len(data)/before_status*100:.1f}%)")
    # Lọc Nội dung & Gender - dùng mask boolean thay vì copy nhiều lần
    before_filter = len(data)
    mask_content = data["NoiDung"].astype(str).str.strip().isin(["Bán","Tặng"])
    mask_brand   = data["Brand"].astype(str).str.strip().isin(["Hiệu Pierre Cardin","Hiệu An Phước"])
    mask_gender  = ~data["Product_group"].astype(str).str.strip().isin(["Bao bì","Hợp đồng"])
    data = data[mask_content & mask_brand & mask_gender]
    print(f"✓ Sau lọc: {len(data):,}/{before_filter:,} dòng ({len(data)/before_filter*100:.1f}%)")

    print("🔢 Xử lý cột TacNghiep (lấy giá trị sau '/')...")
    # Lấy ký tự sau dấu "/" và ép sang số
    tacnghiep_vals = data["TacNghiep"].astype(str).str.split("/").str[-1].str.strip()
    tacnghiep_nums = pd.to_numeric(tacnghiep_vals, errors="coerce")
    # Lọc chỉ giữ 1-299, loại bỏ còn lại
    before_tacnghiep = len(data)
    mask_tacnghiep = (tacnghiep_nums >= 1) & (tacnghiep_nums <= 299)
    data = data[mask_tacnghiep]
    print(f"✓ Sau lọc TacNghiep: {len(data):,}/{before_tacnghiep:,} dòng ({len(data)/before_tacnghiep*100:.1f}%)")

    print("📊 Nhóm dữ liệu...")
    # === NHÓM TỔNG HỢP TRƯỚC TÍNH RANK ===
    # Bỏ 3 cột rồi group by theo các cột xuất
    cols_to_drop = ["NgayChungTu","SoChungTu","DienGiai"]
    existing_drop = [c for c in cols_to_drop if c in data.columns]
    if existing_drop:
        data = data.drop(columns=existing_drop)

    # Tạo cột "Operation" từ "TacNghiep" để hiển thị trong Excel
    data["Operation"] = data["TacNghiep"]

    # Cột group theo danh sách xuất
    group_cols = [
        "MaHang","Short_name","Code_Color",
        "Brand","System_item_name","Report_item_name","Product_type","Gender","Product_group",
        "Status","Operation","NoiDung","Region",
        "Composition","Color_tone","Color_group","Form","Style","Attribute","Description","Price","Dist_plan","Production_month","Production_year",
    ]
    
    # Fillna và group by
    for col in group_cols:
        data[col] = data[col].fillna("")
    data = data.groupby(group_cols, dropna=False, as_index=False, sort=False, observed=True).agg({
        "SoLuong": "sum",
        "Month": "first"  # Lấy tháng đầu tiên của mỗi group
    })
    print(f"✓ Nhóm xong: {len(data):,} dòng")

    print("🏆 Tính toán rank...")
    # Tạo cột rank
    data["rank"] = 0
    
    # Áo: rank theo Report_item_name + Form + Color_group + Month + Region
    mask_ao = data["Product_group"].astype(str).str.strip() == "Áo"
    if mask_ao.any():
        rank_cols_ao = ["Report_item_name", "Form", "Color_group", "Month", "Region"]
        # Lấy dữ liệu áo, sort theo SoLuong giảm dần, đánh STT trong mỗi group
        ao_data = data[mask_ao].copy()
        ao_data = ao_data.sort_values(rank_cols_ao + ["SoLuong"], ascending=[True]*len(rank_cols_ao) + [False])
        ao_data["rank"] = ao_data.groupby(rank_cols_ao, dropna=False, sort=False).cumcount() + 1
        data.loc[mask_ao, "rank"] = ao_data["rank"]
    
    # Quần, Váy, Vest bộ: rank theo Report_item_name + Form + Style + Month + Region
    mask_other = data["Product_group"].astype(str).str.strip().isin(["Quần", "Váy", "Vest bộ"])
    if mask_other.any():
        rank_cols_other = ["Report_item_name", "Form", "Style", "Month", "Region"]
        # Lấy dữ liệu, sort theo SoLuong giảm dần, đánh STT trong mỗi group
        other_data = data[mask_other].copy()
        other_data = other_data.sort_values(rank_cols_other + ["SoLuong"], ascending=[True]*len(rank_cols_other) + [False])
        other_data["rank"] = other_data.groupby(rank_cols_other, dropna=False, sort=False).cumcount() + 1
        data.loc[mask_other, "rank"] = other_data["rank"]
    
    # Những Product_group còn lại: group theo Report_item_name + Month + Region
    mask_remaining = (data["rank"] == 0)
    if mask_remaining.any():
        remaining_data = data[mask_remaining].copy()
        remaining_data = remaining_data.sort_values(["Report_item_name", "Month", "Region", "SoLuong"], ascending=[True, True, True, False])
        remaining_data["rank"] = remaining_data.groupby(["Report_item_name", "Month", "Region"], dropna=False, sort=False).cumcount() + 1
        data.loc[mask_remaining, "rank"] = remaining_data["rank"]
    
    data["rank"] = data["rank"].astype(int)
    print("✓ Rank tính toán xong")

    print("📸 Thêm đường dẫn hình ảnh...")
    # Thêm cột Front view và Side view
    base_path = r"\\hovmfs01\PKD\PhanPhoi\Thong.Nguyen\Report_BestSeller\03.Hinh_anh_sp"
    data["Front view"] = base_path + "\\" + data["MaHang"].astype(str) + " T.PNG"
    data["Side view"] = base_path + "\\" + data["MaHang"].astype(str) + " C.PNG"
    print("✓ Đường dẫn hình ảnh thêm xong")

    print("🎯 Sắp xếp thứ tự cột...")
    # Thứ tự cột khi xuất
    ordered_cols = [
        "MaHang","Short_name","Code_Color","NoiDung",
        "SoLuong","DonGia","Operation","Month",
        "Brand","System_item_name","Report_item_name","Product_type","Gender","Product_group","Region",
        "Status",
        "Composition","Color_tone","Color_group","Form","Style","Attribute","Description","Price","Dist_plan","Production_month","Production_year",
        "rank","Front view","Side view",
    ]
    final_cols = [c for c in ordered_cols if c in data.columns]
    data_export = data[final_cols].copy()
    print("✓ Thứ tự cột xong")

    print("🧹 Làm sạch ký tự cấm...")
    # Làm sạch ký tự cấm rồi ghi Excel
    data = clean_for_excel(data)
    print("✓ Ký tự cấm làm sạch xong")
    
    print("💾 Ghi file Excel...")
    os.makedirs(os.path.dirname(OUT_XLSX), exist_ok=True)
    
    # Thử ghi Excel với retry - 1 sheet duy nhất
    import time
    max_retries = 3
    for attempt in range(max_retries):
        try:
            with pd.ExcelWriter(OUT_XLSX, engine="xlsxwriter", datetime_format="yyyy-mm-dd") as w:
                # Ghi tất cả dữ liệu vào 1 sheet
                data.to_excel(w, sheet_name="Data", index=False)
            print("✓ Ghi file Excel xong")
            print(f"  - Ghi 1 sheet 'Data' với {len(data):,} dòng")
            break
        except PermissionError:
            if attempt < max_retries - 1:
                print(f"  ⏳ File đang bị sử dụng, chờ {2**(attempt+1)}s...")
                time.sleep(2**(attempt+1))
            else:
                print("  ⚠️ Lỗi: File vẫn bị lock, bỏ qua Excel")
        except Exception as e:
            print(f"  ⚠️ Lỗi ghi Excel: {e}")
            break

    print("\n" + "=" * 60)
    print("✅ HOÀN THÀNH XỬ LÝ DỮ LIỆU BÁN")
    print("=" * 60)
    print(f"📍 Địa chỉ file: {OUT_XLSX}")
    print(f"📊 Số dòng: {len(data):,} | Số cột: {data.shape[1]}")
    print("✓ Cột 'Region' đã được thêm vào file Excel")
    print("=" * 60)

if __name__ == "__main__":
    main()


# -*- coding: utf-8 -*-
"""
bao_cao_ban_chay_ban_cham.py — Hệ thống xử lý báo cáo Best Seller & Slow Seller PKD
Tác giả: Thong.Nguyen | An Phước Group
Chạy: python bao_cao_ban_chay_ban_cham.py          → Giao diện đồ họa (GUI)
      python bao_cao_ban_chay_ban_cham.py --cli    → Giao diện dòng lệnh (CLI)
"""
import os, glob, re, sys, io, time, threading, warnings
import pandas as pd
import numpy as np
import unicodedata

# UTF-8 stdout (chỉ wrap nếu encoding sai, không wrap khi đã là UTF-8)
try:
    if hasattr(sys.stdout, "buffer") and getattr(sys.stdout, "encoding", "utf-8").lower() != "utf-8":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

warnings.filterwarnings("ignore", category=UserWarning)

# ─────────────────────────────────────────────
#  CẤU HÌNH ĐƯỜNG DẪN
# ─────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # 01.Python_Projects (dung_chung)
from dung_chung import duong_dan  # noqa: E402

FOLDER_BAN_2025 = os.path.join(duong_dan.ban_le, "2025")
FOLDER_BAN_2026 = os.path.join(duong_dan.ban_le, "2026")
MASTER_DIR      = duong_dan.master
OUT_DIR         = duong_dan.thu_muc_ket_qua("BaoCao_TopSeller")   # 04_KetQua/BaoCao_TopSeller

# ─────────────────────────────────────────────
#  HÀM TIỆN ÍCH
# ─────────────────────────────────────────────
def strip_accents(s):
    s = unicodedata.normalize("NFD", str(s) if s else "")
    return "".join(c for c in s if not unicodedata.combining(c))

def keyize(s):
    return "".join(c for c in strip_accents(s).lower() if c.isalnum())

def clean_for_excel(df):
    for c in df.select_dtypes(include=["object", "string"]).columns:
        df[c] = df[c].astype(str).str.replace(r"[\x00-\x08\x0B-\x0C\x0E-\x1F]", "", regex=True)
    return df

# ─────────────────────────────────────────────
#  LOAD DỮ LIỆU PHỤ TRỢ (cho GUI dropdown)
# ─────────────────────────────────────────────
def load_available_khpp_months():
    """Lấy danh sách tháng KHPP từ F_DataTracking.parquet"""
    try:
        path = os.path.join(MASTER_DIR, "F_DataTracking.parquet")
        df = pd.read_parquet(path, columns=["Dist_plan"])
        months = [str(m).strip() for m in df["Dist_plan"].dropna().unique()
                  if re.match(r"^T\d{2}\.\d{4}$", str(m).strip())]
        months.sort(key=lambda x: (int(x[3:]), int(x[1:3])), reverse=True)
        return months
    except Exception:
        return []

def load_available_regions():
    """Lấy danh sách khu vực từ file Parquet bán hàng"""
    try:
        files = []
        for folder in [FOLDER_BAN_2026, FOLDER_BAN_2025]:
            if os.path.exists(folder):
                files.extend(sorted(glob.glob(os.path.join(folder, "*.parquet"))))
        if not files:
            return []
        df = pd.read_parquet(files[0], columns=["Region"])
        regions = sorted(df["Region"].dropna().astype(str).str.strip().unique().tolist())
        return [r for r in regions if r]
    except Exception:
        return []

# ─────────────────────────────────────────────
#  XỬ LÝ BÁO CÁO CHÍNH
# ─────────────────────────────────────────────
def run_processing(report_type, time_grouping, region, khpp_filter, export_year="2026", log_func=print):
    """
    Tham số:
        report_type   : "Bán chạy (Best Seller)" | "Bán chậm (Slow Seller)"
        time_grouping : "Theo Tháng" | "Theo Quý"
        region        : "Tất cả HTCH" | tên khu vực cụ thể (vd: "Miền Nam")
        khpp_filter   : "Mặc định (6 tháng KHPP gần nhất)" | "Tất cả" | "Txx.xxxx"
        export_year   : "2026" | "2025" | "Tất cả"
    """
    sep = "=" * 60
    log_func(sep)
    log_func(" BẮT ĐẦU XỬ LÝ BÁO CÁO PKD")
    log_func(sep)
    log_func(f"  Loại báo cáo : {report_type}")
    log_func(f"  Thời gian    : {time_grouping}")
    log_func(f"  Khu vực      : {region}")
    log_func(f"  Lọc KHPP     : {khpp_filter}")
    log_func(f"  Năm xuất     : {export_year}")
    log_func("-" * 60)

    # ── 1. ĐỌC FILE PARQUET BÁN HÀNG ──────────────────────────
    files = []
    for folder in [FOLDER_BAN_2025, FOLDER_BAN_2026]:
        if os.path.exists(folder):
            files.extend(sorted(glob.glob(os.path.join(folder, "*.parquet"))))
    if not files:
        raise FileNotFoundError(f"Không tìm thấy file Parquet trong: {FOLDER_BAN_2025} hoặc {FOLDER_BAN_2026}")
    log_func(f"📁 Tìm thấy {len(files)} file Parquet (2025 & 2026)")

    frames = []
    for i, f in enumerate(files, 1):
        log_func(f"  [{i}/{len(files)}] {os.path.basename(f)}")
        frames.append(pd.read_parquet(f))

    data = pd.concat(frames, ignore_index=True)
    log_func(f"✓ Tổng: {len(data):,} dòng gốc")

    # ── 2. CHUẨN HÓA CỘT ──────────────────────────────────────
    data = data.rename(columns={
        "Store_name": "TenCuaHang",
        "Qty_Ban":    "SoLuong",
        "Nội dung":   "NoiDung",
    })

    # Tháng / Năm / Quý
    data["Month"]   = pd.to_numeric(data.get("Month",   pd.Series()), errors="coerce").fillna(0).astype(int)
    data["Year"]    = pd.to_numeric(data.get("Year",    pd.Series()), errors="coerce").fillna(0).astype(int)
    data["Quarter"] = data["Quarter"].fillna("").astype(str).str.strip() if "Quarter" in data.columns else ""

    # Mã hàng
    s_ma = data["MaHang"].astype(str)
    data["Code_Color"] = np.where(s_ma.str.len() >= 4, s_ma.str[-4:], "")
    data["SoLuong"]    = pd.to_numeric(data.get("SoLuong", pd.Series()), errors="coerce").fillna(0).astype(int)

    # Tháng bán mới nhất để ghi log
    tmp = data[(data["Month"].between(1, 12)) & (data["Year"] >= 2000)][["Month", "Year"]]
    if not tmp.empty:
        idx = (tmp["Year"] * 12 + tmp["Month"]).idxmax()
        log_func(f"📅 Tháng bán mới nhất trong data: {int(tmp.loc[idx,'Month']):02d}/{int(tmp.loc[idx,'Year'])}")

    # ── 3. ĐỌC DATABASE & MERGE ───────────────────────────────
    log_func(f"🗄️  Đọc F_DataTracking từ: {MASTER_DIR}")
    path_dt = os.path.join(MASTER_DIR, "F_DataTracking.parquet")
    path_ts = os.path.join(MASTER_DIR, "E_T-Shirt.parquet")

    if not os.path.exists(path_dt):
        raise FileNotFoundError(f"Không tìm thấy F_DataTracking.parquet tại: {MASTER_DIR}")

    dt = pd.read_parquet(path_dt)
    dt_cols = ["System_item_name", "Operation", "Color_code",
               "Composition", "Color_tone", "Color_group",
               "Form", "Style", "Attribute", "Description",
               "Price", "Dist_plan", "Production_month", "Production_year",'Qty_LSX']
    missing = [c for c in dt_cols if c not in dt.columns]
    if missing:
        raise KeyError(f"Thiếu cột trong F_DataTracking: {missing}")

    dt_merge = (dt[dt_cols]
                .rename(columns={"System_item_name": "Report_item_name",
                                 "Operation":        "Operation",
                                 "Color_code":       "Code_Color"}))

    # T-Shirt mapping
    ts_map = {}
    try:
        ts = pd.read_parquet(path_ts)
        ts_col = next((c for c in ts.columns if keyize(c) == "itemcode"), None) or \
                 ("item_code" if "item_code" in ts.columns else None)
        if ts_col and "T-shirt_name" in ts.columns:
            ts_map = dict(zip(ts[ts_col].astype(str).str.strip(),
                              ts["T-shirt_name"].astype(str).str.strip()))
            log_func(f"✓ Bản đồ E_T-Shirt: {len(ts_map)} mục")
    except Exception:
        pass

    # Chuẩn hóa key merge
    for col in ["Report_item_name", "Operation", "Code_Color"]:
        data[col]     = data[col].astype(str).str.strip()
        dt_merge[col] = dt_merge[col].astype(str).str.strip()

    log_func("🔗 Ghép với F_DataTracking...")
    data = data.merge(dt_merge, on=["Report_item_name", "Operation", "Code_Color"], how="inner")
    log_func(f"✓ Sau ghép: {len(data):,} dòng")

    # ── 4. LỌC CƠ BẢN ────────────────────────────────────────
    log_func("🔍 Lọc dữ liệu cơ bản...")
    n0 = len(data)

    st  = data["Status"].astype(str).str.strip().str.lower()
    nd  = data["NoiDung"].astype(str).str.strip().str.lower()
    br  = data["Brand"].astype(str).str.strip().str.lower()
    pg  = data["Product_group"].astype(str).str.strip().str.lower()
    tn  = pd.to_numeric(data["Operation"].astype(str).str.split("/").str[-1].str.strip(), errors="coerce")

    data = data[
        (st == "nguyên giá") &
        nd.isin(["bán", "tặng"]) &
        br.isin(["hiệu pierre cardin", "hiệu an phước"]) &
        ~pg.isin(["bao bì", "hợp đồng"]) &
        tn.between(1, 299) &
        (data["SoLuong"] > 0)
    ]
    log_func(f"✓ Sau lọc cơ bản: {len(data):,} / {n0:,} dòng")

    # ── 5. LỌC KHU VỰC ───────────────────────────────────────
    if region != "Tất cả HTCH" and "Region" in data.columns:
        data = data[data["Region"].astype(str).str.strip() == region]
        log_func(f"✓ Sau lọc khu vực [{region}]: {len(data):,} dòng")

    # ── 5b. DỮ LIỆU CƠ SỞ ĐỂ TÍNH TỔNG BÁN LŨY KẾ (2025 & 2026) ──
    data_base = data.copy()
    data_base["sales_idx"] = data_base["Year"] * 12 + data_base["Month"]

    if export_year != "Tất cả":
        try:
            y_val = int(export_year)
            data = data[data["Year"] == y_val]
            log_func(f"✓ Lọc dữ liệu năm xuất [{export_year}]: {len(data):,} dòng")
        except Exception:
            pass

    # ── 6. LỌC KHPP (Dist_plan) ───────────────────────────────
    log_func("🔍 Lọc KHPP (Dist_plan)...")
    data["Dist_plan"] = data["Dist_plan"].fillna("").astype(str).str.strip()

    if khpp_filter == "Mặc định (6 tháng KHPP gần nhất)":
        kp = data["Dist_plan"].str.extract(r"^T(\d{2})\.(\d{4})$")
        khpp_idx = pd.to_numeric(kp[1], errors="coerce") * 12 + pd.to_numeric(kp[0], errors="coerce")
        is_slow = ("Slow" in report_type) or ("chậm" in report_type.lower())

        if not is_slow:
            # ── BÁN CHẠY (Best Seller) ──
            # Dù gom Tháng hay Quý, dòng bán tháng M lấy KHPP từ [M-5 .. M]
            sales_idx = data["Year"] * 12 + data["Month"]
            data = data[(khpp_idx >= sales_idx - 5) & (khpp_idx <= sales_idx)]
            log_func("  → Bán chạy: Cửa sổ KHPP [M-5 .. M] (vd: Tháng 2 → T09.2025-T02.2026)")
        else:
            # ── BÁN CHẬM (Slow Seller) ──
            if time_grouping == "Theo Tháng":
                # Theo Tháng: dòng bán tháng M lấy KHPP từ [M-6 .. M-1]
                # Ví dụ bán Tháng 2/2026 → KHPP từ T08.2025 đến T01.2026
                sales_idx = data["Year"] * 12 + data["Month"]
                data = data[(khpp_idx >= sales_idx - 6) & (khpp_idx <= sales_idx - 1)]
                log_func("  → Bán chậm / Theo Tháng: Cửa sổ KHPP [M-6 .. M-1] (vd: Tháng 2 → T08.2025-T01.2026)")
            else:
                # Theo Quý: Quý Q (tháng bắt đầu M_start) lấy KHPP từ [M_start - 7 .. M_start]
                # Ví dụ Quý 1/2026 (bắt đầu Tháng 1) → KHPP từ T06.2025 đến T01.2026
                qp = data["Quarter"].astype(str).str.extract(r"^Q(\d)\.(\d{4})$")
                qtr_num = pd.to_numeric(qp[0], errors="coerce").fillna(0).astype(int)
                qtr_y   = pd.to_numeric(qp[1], errors="coerce").fillna(0).astype(int)
                m_start = (qtr_num - 1) * 3 + 1   # Q1→1, Q2→4, Q3→7, Q4→10
                q_start_idx = qtr_y * 12 + m_start
                data = data[(khpp_idx >= q_start_idx - 7) & (khpp_idx <= q_start_idx)]
                log_func("  → Bán chậm / Theo Quý: Cửa sổ KHPP [M_start-7 .. M_start] (vd: Quý 1 → T06.2025-T01.2026)")



    elif khpp_filter == "Tất cả":
        data = data[data["Dist_plan"].str.match(r"^T\d{2}\.\d{4}$", na=False)]
        log_func("  → Giữ tất cả tháng KHPP hợp lệ")
    else:
        data = data[data["Dist_plan"] == khpp_filter]
        log_func(f"  → Lọc chính xác tháng: {khpp_filter}")

    log_func(f"✓ Sau lọc KHPP: {len(data):,} dòng")

    if len(data) == 0:
        raise ValueError("Không còn dữ liệu sau khi áp dụng các bộ lọc!")

    # ── 7. GROUPBY & TỔNG HỢP ────────────────────────────────
    log_func("📊 Gom nhóm và tổng hợp...")
    time_col = "Month" if time_grouping == "Theo Tháng" else "Quarter"

    # Định dạng Month thành chuỗi 2 chữ số sau khi dùng để tính KHPP
    if time_col == "Month":
        data["Month"] = data["Month"].apply(lambda x: f"{x:02d}" if x > 0 else "")

    group_cols = [
        "MaHang", "Code_Color", "Brand", "Report_item_name", "Operation",
        "Product_type", "Gender", "Product_group", "Group_Report",
        "Status", "NoiDung", "Year",
        "Composition", "Color_tone", "Color_group", "Form", "Style",
        "Attribute", "Description", "Price",
        "Dist_plan", "Production_month", "Production_year","Qty_LSX",
        time_col
    ]
    group_cols = [c for c in group_cols if c in data.columns]

    for c in group_cols:
        if data[c].dtype == object:
            data[c] = data[c].fillna("")

    df = (data.groupby(group_cols, dropna=False, as_index=False, sort=False, observed=True)
               .agg(SoLuong=("SoLuong", "sum")))
    log_func(f"✓ Sau gom nhóm: {len(df):,} dòng")

    # Thêm cột Ban_Month / Ban_Quarter
    qty_col = "Ban_Month" if time_grouping == "Theo Tháng" else "Ban_Quarter"
    df[qty_col] = df["SoLuong"]

    # ── Tính Tong_Ban lũy kế từ quá khứ đến từng mốc thời gian (Month/Quarter) ──
    if time_col == "Month":
        df["_m_num"] = pd.to_numeric(df["Month"], errors="coerce").fillna(0).astype(int)
        df["cutoff_idx"] = df["Year"] * 12 + df["_m_num"]
    else:
        qp = df["Quarter"].astype(str).str.extract(r"^Q(\d)\.(\d{4})$")
        q_num = pd.to_numeric(qp[0], errors="coerce").fillna(0).astype(int)
        q_yr  = pd.to_numeric(qp[1], errors="coerce").fillna(0).astype(int)
        m_end = q_num * 3
        df["cutoff_idx"] = q_yr * 12 + m_end

    cutoff_maps = {}
    for c_idx in df["cutoff_idx"].unique():
        sub = data_base[data_base["sales_idx"] <= c_idx]
        cutoff_maps[c_idx] = sub.groupby(["MaHang", "Operation"])["SoLuong"].sum().to_dict()

    df["Tong_Ban"] = df.apply(
        lambda r: cutoff_maps.get(r["cutoff_idx"], {}).get((r["MaHang"], r["Operation"]), 0),
        axis=1
    ).astype(int)
    df = df.drop(columns=[c for c in ["_m_num", "cutoff_idx"] if c in df.columns])

    # Gộp Production_month + Production_year → Production_date (MM/YYYY)
    if "Production_month" in df.columns and "Production_year" in df.columns:
        pm = pd.to_numeric(df["Production_month"], errors="coerce").fillna(0).astype(int)
        py = pd.to_numeric(df["Production_year"],  errors="coerce").fillna(0).astype(int)
        df["Production_date"] = pm.apply(lambda x: f"{x:02d}" if x > 0 else "") + "/" + \
                                 py.apply(lambda x: str(x) if x > 0 else "")
        df["Production_date"] = df["Production_date"].str.strip("/")
        df = df.drop(columns=["Production_month", "Production_year"])

    # ── 8. THAY TÊN ÁO THUN (E_T-Shirt) ─────────────────────
    if ts_map:
        df["Report_item_name"] = df["MaHang"].astype(str).str.strip().map(ts_map).fillna(df["Report_item_name"])

    # ── 9. XẾP HẠNG (RANK) ────────────────────────────────────
    log_func("🏆 Tính xếp hạng...")
    asc = (report_type == "Bán chậm (Slow Seller)")   # Slow: tăng dần, Best: giảm dần

    df["Product_group_c"] = df["Product_group"].astype(str).str.strip() if "Product_group" in df.columns else ""
    df["Group_Report_c"]  = df["Group_Report"].astype(str).str.strip()  if "Group_Report"  in df.columns else ""
    df["rank"] = 0

    def _rank(mask, key_cols):
        """
        Xếp hạng các dòng trong mask theo key_cols + SoLuong.
        Rank tính xuyên suốt các tháng/quý trong cùng nhóm sản phẩm,
        KHÔNG tính riêng theo từng tháng (vì mỗi nhóm+tháng đã duy nhất sau groupby).
        """
        if not mask.any():
            return
        sub = df.loc[mask].copy()
        # Sắp xếp: key_cols tăng dần, SoLuong theo hướng asc (Best=giảm, Slow=tăng)
        sub = sub.sort_values(key_cols + ["SoLuong"],
                              ascending=[True] * len(key_cols) + [asc])
        # cumcount() trong từng nhóm → rank 1, 2, 3...
        sub["rank"] = sub.groupby(key_cols, dropna=False, sort=False).cumcount() + 1
        # Gán lại theo index để tránh lệch thứ tự
        df.loc[sub.index, "rank"] = sub["rank"]

    # ── Mapping ưu tiên rank theo Report_item_name (cao nhất) và Group_Report ──
    # Report_item_name dùng Form + Style
    _ITEM_STYLE   = {"Ví An Phuoc", "Ví Nam AP", "Ví Nam PIE", "Ví PIE"}
    # Group_Report dùng Form + Color_group
    _GR_COLOR     = {"Áo Khác", "Áo Khoác", "Áo Thun", "Chemise", "Áo Golf"}
    # Group_Report dùng Form + Style
    _GR_STYLE     = {"Quần Golf", 
                     "Quần Jean", "Quần Kaki", "Quần Short", "Quần Tây",
                     "Váy"}
    # Group_Report dùng chỉ Form (không Style)
    _GR_FORM      = {"Dây Nịt", "Giày, Dép", "Ví"}

    # Key rank: tính trong từng nhóm sản phẩm THEO TỪNG THÁNG/QUÝ
    # 1) Ưu tiên cao nhất: theo Report_item_name cụ thể → Form + Style
    _rank(df["Report_item_name"].isin(_ITEM_STYLE),
          ["Report_item_name", "Form",  time_col])
    # 2) Group_Report → Form + Color_group
    _rank((df["rank"] == 0) & df["Group_Report_c"].isin(_GR_COLOR),
          ["Report_item_name", "Form", "Color_group", time_col])
    # 3) Group_Report → Form + Style
    _rank((df["rank"] == 0) & df["Group_Report_c"].isin(_GR_STYLE),
          ["Report_item_name", "Form", "Style", time_col])
    # 3b) Group_Report → chỉ Form (Dây Nịt)
    _rank((df["rank"] == 0) & df["Group_Report_c"].isin(_GR_FORM),
          ["Report_item_name", "Form", time_col])
    # 4) Fallback: chỉ Report_item_name
    _rank(df["rank"] == 0,
          ["Report_item_name", time_col])

    df["rank"] = df["rank"].astype(int)


    # ── 10. CỘT X (LOGIC POWER QUERY) ────────────────────────
    log_func("⚡ Tạo cột X (Power Query)...")
    for c in ["Report_item_name", "Form", "Color_group", "Style"]:
        if c in df.columns:
            df[c] = df[c].fillna("").astype(str)

    def _x(row):
        item = str(row.get("Report_item_name", ""))
        gr   = row.get("Group_Report_c",  "")
        t    = str(row.get(time_col, ""))
        r    = str(row["rank"])
        # Ưu tiên 1: theo Report_item_name cụ thể → Form + Style
        if item in _ITEM_STYLE:
            return f"{item}{row['Form']}{row['Style']}{r}{t}"
        # Ưu tiên 2: theo Group_Report → Form + Color_group
        if gr in _GR_COLOR:
            return f"{item}{row['Form']}{row['Color_group']}{r}{t}"
        # Ưu tiên 3: theo Group_Report → Form + Style
        if gr in _GR_STYLE:
            return f"{item}{row['Form']}{row['Style']}{r}{t}"
        # Ưu tiên 3b: theo Group_Report → chỉ Form (Dây Nịt)
        if gr in _GR_FORM:
            return f"{item}{row['Form']}{r}{t}"
        # Fallback
        return f"{item}{r}{t}"

    df["X"] = df.apply(_x, axis=1)

    # ── 11. FRONT VIEW ────────────────────────────────────────
    img_base = duong_dan.hinh_anh
    df["Front view"] = img_base + "\\" + df["MaHang"].astype(str) + " T.PNG"

    # ── 12. XÓA CỘT PHỤ & SẮP XẾP CỘT ──────────────────────
    drop_cols = ["Short_name", "Group_Report", "Product_type", "Gender",
                 "Status", "NoiDung", "Product_group",
                 "Product_group_c", "Group_Report_c", "TacNghiep", "SoLuong", "Year"]
    df = df.drop(columns=[c for c in drop_cols if c in df.columns])

    col_order = [
        "MaHang", "Code_Color", "Brand", "Report_item_name", "Operation",
        "Composition", "Color_tone", "Color_group", "Form", "Style",
        "Attribute", "Description", "Price",
        "Dist_plan", "Production_date","Qty_LSX",
        "Tong_Ban", qty_col, time_col,
        "rank", "Front view", "X", 
    ]
    final_cols = [c for c in col_order if c in df.columns]
    extras     = [c for c in df.columns if c not in final_cols]
    df = df[final_cols + extras]

    df = clean_for_excel(df)

    # ── 13. XUẤT EXCEL ────────────────────────────────────────
    type_slug  = "BestSeller" if "Best" in report_type else "SlowSeller"
    time_slug  = "Month" if time_grouping == "Theo Tháng" else "Quarter"
    reg_slug   = "" if region == "Tất cả HTCH" else f"_{region.replace(' ', '')}"
    yr_slug    = "" if export_year == "Tất cả" else f"_{export_year}"

    # Hậu tố tháng cụ thể
    khpp_slug = ""
    if khpp_filter not in ("Mặc định (6 tháng KHPP gần nhất)", "Tất cả"):
        khpp_slug = f"_{khpp_filter}"

    filename = f"Data_{type_slug}_{time_slug}{reg_slug}{khpp_slug}{yr_slug}.xlsx"
    out_path  = os.path.join(OUT_DIR, filename)
    os.makedirs(OUT_DIR, exist_ok=True)

    log_func(f"💾 Xuất Excel: {out_path}")
    for attempt in range(3):
        try:
            with pd.ExcelWriter(out_path, engine="xlsxwriter", datetime_format="yyyy-mm-dd") as w:
                df.to_excel(w, sheet_name="Data", index=False)
            log_func(f"✅ Thành công! {len(df):,} dòng → {filename}")
            break
        except PermissionError:
            if attempt < 2:
                wait = 2 ** (attempt + 1)
                log_func(f"  ⚠️ File đang mở. Thử lại sau {wait}s...")
                time.sleep(wait)
            else:
                raise PermissionError(f"Không thể ghi '{out_path}'. Vui lòng đóng file Excel và chạy lại.")

    log_func("=" * 60)
    log_func("🎉 HOÀN THÀNH")
    log_func("=" * 60)
    return out_path


# ─────────────────────────────────────────────
#  GIAO DIỆN DÒNG LỆNH (CLI)
# ─────────────────────────────────────────────
def run_cli_mode():
    print("\n" + "=" * 55)
    print(" HỆ THỐNG BÁO CÁO PKD — DÒNG LỆNH")
    print("=" * 55)

    # 1. Loại báo cáo
    print("\n1. Loại báo cáo:")
    print("   [1] Bán chạy (Best Seller)   [2] Bán chậm (Slow Seller)")
    c = input("Chọn (mặc định 1): ").strip()
    report_type = "Bán chậm (Slow Seller)" if c == "2" else "Bán chạy (Best Seller)"

    # 2. Thời gian
    print("\n2. Gom nhóm thời gian:")
    print("   [1] Theo Tháng   [2] Theo Quý")
    c = input("Chọn (mặc định 1): ").strip()
    time_grouping = "Theo Quý" if c == "2" else "Theo Tháng"

    # 3. Khu vực
    print("\n3. Đang tải danh sách khu vực...")
    regions = load_available_regions()
    print("   [1] Tất cả HTCH")
    for i, r in enumerate(regions, 2):
        print(f"   [{i}] {r}")
    c = input("Chọn (mặc định 1): ").strip()
    try:
        ci = int(c)
        region = regions[ci - 2] if 2 <= ci <= len(regions) + 1 else "Tất cả HTCH"
    except Exception:
        region = "Tất cả HTCH"

    # 4. KHPP
    print("\n4. Đang tải danh sách tháng KHPP...")
    months = load_available_khpp_months()
    print("   [1] Mặc định (6 tháng KHPP gần nhất — cửa sổ trượt)")
    print("   [2] Tất cả")
    for i, m in enumerate(months, 3):
        print(f"   [{i}] {m}")
    c = input("Chọn (mặc định 1): ").strip()
    try:
        ci = int(c)
        if ci == 2:
            khpp_filter = "Tất cả"
        elif 3 <= ci <= len(months) + 2:
            khpp_filter = months[ci - 3]
        else:
            khpp_filter = "Mặc định (6 tháng KHPP gần nhất)"
    except Exception:
        khpp_filter = "Mặc định (6 tháng KHPP gần nhất)"

    # 5. Năm xuất báo cáo
    print("\n5. Năm xuất báo cáo:")
    print("   [1] 2026 (mặc định)   [2] 2025   [3] Tất cả")
    c = input("Chọn (mặc định 1): ").strip()
    if c == "2":
        export_year = "2025"
    elif c == "3":
        export_year = "Tất cả"
    else:
        export_year = "2026"

    # Xác nhận
    print("\n" + "-" * 45)
    print(f"  Loại     : {report_type}")
    print(f"  Thời gian: {time_grouping}")
    print(f"  Khu vực  : {region}")
    print(f"  KHPP     : {khpp_filter}")
    print(f"  Năm xuất : {export_year}")
    print("-" * 45)
    if input("Xác nhận chạy? (Y/N, mặc định Y): ").strip().upper() == "N":
        print("Đã hủy.")
        return

    try:
        out = run_processing(report_type, time_grouping, region, khpp_filter, export_year)
        print(f"\n📍 File kết quả:\n👉 {out}\n")
    except Exception as e:
        import traceback
        print(f"\n❌ Lỗi: {e}")
        traceback.print_exc()

    input("\nBấm Enter để thoát...")


# ─────────────────────────────────────────────
#  GIAO DIỆN ĐỒ HỌA (GUI)
# ─────────────────────────────────────────────
def run_gui_mode():
    import tkinter as tk
    from tkinter import ttk, messagebox
    from tkinter.scrolledtext import ScrolledText

    root = tk.Tk()
    root.title("Báo cáo PKD — Best Seller & Slow Seller")
    root.geometry("920x680")
    root.minsize(820, 580)

    # ── Màu & Font ──
    BG   = "#f0f2f5"
    CARD = "#ffffff"
    FG   = "#1a202c"
    PRIM = "#2d3748"
    ACC  = "#38a169"
    ACC2 = "#2f855a"

    root.configure(bg=BG)
    style = ttk.Style()
    style.theme_use("clam")
    style.configure(".", background=BG, foreground=FG, font=("Segoe UI", 10))
    style.configure("TFrame", background=BG)
    style.configure("Card.TFrame", background=CARD)
    style.configure("TLabel",      background=BG,   foreground=FG)
    style.configure("Card.TLabel", background=CARD, foreground=FG)
    style.configure("H.TLabel",    background=BG,   foreground=PRIM,
                    font=("Segoe UI", 13, "bold"))
    style.configure("Bold.TLabel", background=CARD, foreground=FG,
                    font=("Segoe UI", 10, "bold"))
    style.configure("Run.TButton", font=("Segoe UI", 11, "bold"),
                    background=ACC, foreground="#ffffff", padding=10)
    style.map("Run.TButton", background=[("active", ACC2)])
    style.configure("TButton", font=("Segoe UI", 9), padding=5)

    # ── Biến ──
    var_type   = tk.StringVar(value="Bán chạy (Best Seller)")
    var_time   = tk.StringVar(value="Theo Tháng")
    var_region = tk.StringVar(value="Tất cả HTCH")
    var_khpp   = tk.StringVar(value="Mặc định (6 tháng KHPP gần nhất)")
    var_year   = tk.StringVar(value="2026")

    # ── Tiêu đề ──
    hdr = ttk.Frame(root); hdr.pack(fill="x", padx=20, pady=12)
    ttk.Label(hdr, text="HỆ THỐNG BÁO CÁO PHÂN PHỐI PKD", style="H.TLabel").pack(anchor="w")
    ttk.Label(hdr, text="Best Seller & Slow Seller — Parquet Edition").pack(anchor="w", pady=2)

    # ── Layout 2 cột ──
    body = ttk.Frame(root); body.pack(fill="both", expand=True, padx=20, pady=4)

    left  = ttk.Frame(body, style="Card.TFrame", padding=15)
    right = ttk.Frame(body, style="Card.TFrame", padding=10)
    left .place(relx=0,    rely=0, relwidth=0.40, relheight=1)
    right.place(relx=0.42, rely=0, relwidth=0.58, relheight=1)

    # ── Panel trái: Tùy chọn ──
    def _lbl(parent, text):
        ttk.Label(parent, text=text, style="Bold.TLabel").pack(anchor="w", pady=(8, 2))

    def _combo(parent, var, values, width=32):
        cb = ttk.Combobox(parent, textvariable=var, values=values,
                          state="readonly", width=width)
        cb.pack(anchor="w", pady=(0, 4))
        return cb

    _lbl(left, "1. Loại báo cáo")
    cb_type = _combo(left, var_type, ["Bán chạy (Best Seller)", "Bán chậm (Slow Seller)"])

    _lbl(left, "2. Gom nhóm thời gian")
    cb_time = _combo(left, var_time, ["Theo Tháng", "Theo Quý"])

    _lbl(left, "3. Khu vực")
    cb_region = _combo(left, var_region, ["Tất cả HTCH"])

    _lbl(left, "4. Lọc tháng KHPP (Dist_plan)")
    cb_khpp = _combo(left, var_khpp,
                     ["Mặc định (6 tháng KHPP gần nhất)", "Tất cả"])

    _lbl(left, "5. Năm xuất báo cáo")
    cb_year = _combo(left, var_year, ["2026", "2025", "Tất cả"])

    ttk.Button(left, text="🔄 Cập nhật danh sách",
               command=lambda: _reload()).pack(anchor="e", pady=(2, 12))

    ttk.Separator(left, orient="horizontal").pack(fill="x", pady=6)
    btn_run = ttk.Button(left, text="⚡  CHẠY BÁO CÁO", style="Run.TButton")
    btn_run.pack(fill="x", pady=(6, 4))
    ttk.Button(left, text="📁 Mở thư mục kết quả",
               command=lambda: os.startfile(OUT_DIR) if os.path.exists(OUT_DIR) else None
               ).pack(fill="x")

    # ── Panel phải: Log ──
    ttk.Label(right, text="Nhật ký xử lý:", style="Bold.TLabel").pack(anchor="w", pady=(0, 4))
    log_box = ScrolledText(right, font=("Consolas", 9),
                           bg="#1a202c", fg="#f7fafc",
                           insertbackground="white", relief="flat")
    log_box.pack(fill="both", expand=True)

    # ── Status bar ──
    sb = ttk.Frame(root, height=24); sb.pack(fill="x", padx=20, pady=(4, 8))
    lbl_status = ttk.Label(sb, text="Trạng thái: Sẵn sàng"); lbl_status.pack(side="left")

    # ── Redirector log ──
    orig_stdout = sys.stdout

    class _Redir(io.StringIO):
        def write(self, s):
            orig_stdout.write(s)
            try:
                root.after(0, lambda: (log_box.insert(tk.END, s), log_box.see(tk.END)))
            except Exception:
                pass
        def flush(self):
            orig_stdout.flush()

    sys.stdout = _Redir()

    # ── Hàm load dropdown ──
    def _reload():
        lbl_status.configure(text="Trạng thái: Đang tải dữ liệu...")

        def _bg():
            rgns   = ["Tất cả HTCH"] + load_available_regions()
            months = ["Mặc định (6 tháng KHPP gần nhất)", "Tất cả"] + load_available_khpp_months()
            root.after(0, lambda: _finish(rgns, months))

        def _finish(rgns, months):
            cb_region.configure(values=rgns)
            cb_khpp  .configure(values=months)
            if var_region.get() not in rgns:
                var_region.set("Tất cả HTCH")
            if var_khpp.get() not in months:
                var_khpp.set("Mặc định (6 tháng KHPP gần nhất)")
            print(f"✓ Đã tải {len(rgns)-1} khu vực, {len(months)-2} tháng KHPP")
            lbl_status.configure(text="Trạng thái: Sẵn sàng")

        threading.Thread(target=_bg, daemon=True).start()

    # ── Hàm chạy xử lý ──
    def _run():
        for w in [btn_run, cb_type, cb_time, cb_region, cb_khpp, cb_year]:
            w.configure(state="disabled")
        lbl_status.configure(text="Trạng thái: Đang xử lý...")
        log_box.delete("1.0", tk.END)

        def _worker():
            t0 = time.time()
            try:
                path = run_processing(
                    var_type.get(), var_time.get(),
                    var_region.get(), var_khpp.get(),
                    var_year.get(),
                    log_func=print)
                root.after(0, lambda: _done_ok(path, time.time() - t0))
            except Exception as err:
                root.after(0, lambda: _done_err(err))

        threading.Thread(target=_worker, daemon=True).start()

    def _done_ok(path, dur):
        for w in [btn_run, cb_type, cb_time, cb_region, cb_khpp, cb_year]:
            w.configure(state="readonly" if w != btn_run else "normal")
        btn_run.configure(state="normal")
        lbl_status.configure(text=f"Trạng thái: Hoàn thành ({dur:.1f}s)")
        if messagebox.askyesno("✅ Thành công",
                               f"Xuất báo cáo xong trong {dur:.1f}s!\n\n{path}\n\nMở file ngay?"):
            try: os.startfile(path)
            except Exception as e: messagebox.showerror("Lỗi", str(e))

    def _done_err(err):
        for w in [btn_run, cb_type, cb_time, cb_region, cb_khpp, cb_year]:
            w.configure(state="readonly" if w != btn_run else "normal")
        btn_run.configure(state="normal")
        btn_run.configure(state="normal")
        lbl_status.configure(text="Trạng thái: Lỗi!")
        print(f"\n❌ LỖI: {err}")
        messagebox.showerror("Lỗi xử lý", str(err))

    btn_run.configure(command=_run)

    # Load dropdown khi mở app
    _reload()
    root.mainloop()


# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────
if __name__ == "__main__":
    if "--cli" in sys.argv:
        run_cli_mode()
    else:
        _ok = False
        try:
            import tkinter as _tk
            _r = _tk.Tk(); _r.withdraw(); _r.destroy()
            _ok = True
        except Exception as _e:
            print(f"ℹ️ Tkinter không khả dụng: {_e} → Chuyển sang CLI")

        if _ok:
            try:
                run_gui_mode()
            except Exception as _ge:
                import traceback
                print(f"❌ Lỗi GUI: {_ge}"); traceback.print_exc()
                print("ℹ️ Chuyển sang CLI...")
                try:
                    import tkinter as _tk2
                    if _tk2._default_root:
                        _tk2._default_root.destroy()
                except Exception:
                    pass
                run_cli_mode()
        else:
            run_cli_mode()

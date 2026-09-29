import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import sys
import argparse
import tkinter as tk
from tkinter import messagebox

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

def log(msg):
    try:
        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}")
    except Exception:
        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] (log error)")

# ── Đường dẫn ────────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "00.Shared"))  # 00.Shared (Get_Paths...)
import Get_Paths  # noqa: E402

BASE_NETWORK        = Path(Get_Paths.phan_tich_o_mang)
OUTPUT_FILE         = Path(Get_Paths.thu_muc_ket_qua("Inventory_Control")) / "Reallocation_Database.xlsx"
TRACKING_FILE       = BASE_NETWORK / r"1.Processed_data\1.Data_Tracking.xlsx"
# So ban: file System_sales.csv do 02.Data_Processing/Export_Parquet_To_Csv.py xuat ra (05.Data_Csv/02.Raw)
SYSTEM_SALES_FOLDER = Path(Get_Paths.csv_xuat) / "02.Raw"
SYSTEM_SALES_GLOB   = "System_sales*.csv"
# Ton kho: doc thang InventorySize.parquet (03.Data_Parquest/03.Inventory)
INVENTORY_FILE      = Path(Get_Paths.ton_kho_size)
HDD_FILE            = BASE_NETWORK / r"1.Processed_data\5.In_transit_stock_HDD.xlsx"

REGION_COLUMNS = ["TP. HCM", "Hà Nội", "Miền Tây", "Miền Trung - TN", "Miền Đông"]

# ── Ngưỡng phân loại cửa hàng ────────────────────────────────────────────────
ST_CHAY     = 0.75   # Bán chạy    : ST > 75%
ST_ON_DINH  = 0.50   # Bán ổn định : ST 50–75%
ST_CHAM     = 0.25   # Bán tương đối chậm : ST 25–50%

# Phân bổ budget Group B
RATE_TO_CHAY    = 0.65   # 65% tổng nguồn → cửa hàng Bán chạy
RATE_TO_ON_DINH = 0.35   # 35% tổng nguồn → cửa hàng Bán ổn định

# ── Tiện ích ─────────────────────────────────────────────────────────────────
def clean_name(x):
    return " ".join(str(x).replace('\ufeff', '').strip().split())

def safe_numeric(s):
    return pd.to_numeric(s, errors='coerce').fillna(0)

def ff(v) -> float:
    try:
        f = float(str(v).strip())
        return 0.0 if (f != f) else f
    except Exception:
        return 0.0

# ── 1. Load lookups ──────────────────────────────────────────────────────────
def load_lookups():
    log("Loading Lookups...")
    a_region   = pd.read_excel(TRACKING_FILE, sheet_name="A_Region",       engine="calamine")
    d_category = pd.read_excel(TRACKING_FILE, sheet_name="D_Category",     engine="calamine")
    f_tracking = pd.read_excel(TRACKING_FILE, sheet_name="F_DataTracking",  engine="calamine")
    for df in [a_region, d_category, f_tracking]:
        df.columns = [clean_name(c) for c in df.columns]

    return a_region, d_category, f_tracking

# ── 2. Load dữ liệu (lọc Nguyên giá ngay từ đầu) ────────────────────────────
def get_recent_months(n=3):
    now = datetime.now()
    y, m = now.year, now.month
    keys = set()
    for _ in range(n):
        keys.add((y, m))
        m -= 1
        if m == 0: m, y = 12, y - 1
    return keys

def load_data(report_item_names: list, d_category: pd.DataFrame, recent_months: int = 3):
    log(f"Loading data for: {report_item_names}")
    short_names = set(
        d_category[d_category["Report_item_name"].isin(report_item_names)]["Short_name"]
        .dropna().str.strip().str.upper()
    )
    recent_keys  = get_recent_months(recent_months)
    recent_years = {y for y, m in recent_keys}

    main_f = []; store_all_f = []; store_sz_f = []; store_rec_f = []

    for path in SYSTEM_SALES_FOLDER.glob(SYSTEM_SALES_GLOB):
        log(f"  Reading {path.name}")
        
        # Đọc header trước để xác định cột thực tế nhằm tối ưu hóa dùng usecols
        try:
            hdr_df = pd.read_csv(path, nrows=0, encoding='utf-8-sig')
            actual_cols = hdr_df.columns.tolist()
        except Exception:
            actual_cols = []
        
        # Danh sách các tên cột mong muốn hoặc bí danh của chúng
        target_keys = {
            "Store_name": ["store_name", "store_rp"],
            "Region": ["region"],
            "Year": ["year"],
            "Month": ["month"],
            "MaHang": ["mahang", "item_code"],
            "Operation": ["operation"],
            "Size": ["size"],
            "Qty_Ban": ["qty_ban", "total_ban"],
            "Status": ["status"],
            "Nội dung": ["nội dung", "noi dung", "noi_dung", "n?i dung"]
        }
        
        usecols = []
        for target, aliases in target_keys.items():
            for col in actual_cols:
                col_clean = " ".join(str(col).replace('\ufeff', '').strip().split()).lower()
                if col_clean == target.lower() or col_clean in aliases:
                    usecols.append(col)
                    break
        
        if len(usecols) >= 5:
            df = pd.read_csv(path, dtype=str, encoding='utf-8-sig', usecols=usecols, on_bad_lines='skip')
        else:
            df = pd.read_csv(path, dtype=str, encoding='utf-8-sig', on_bad_lines='skip')
            
        df.columns = [clean_name(c) for c in df.columns]
        df["MaHang"]    = df["MaHang"].fillna("").astype(str).str.strip().str.upper()
        df["Short_name"] = df["MaHang"].str[:-4]
        df = df[df["Short_name"].isin(short_names)].copy()
        if df.empty: continue

        df["Total_Ban"]  = safe_numeric(df.get("Qty_Ban", df.get("Total_Ban", 0)))
        df["Status_val"] = df.get("Status", "").fillna("").astype(str).str.lower()
        df["Noi_dung"]   = df.get("Nội dung", "").fillna("").astype(str).str.strip().str.lower()

        # Lọc NGAY: bỏ đổi trả và Sale/Thanh lý
        df = df[
            (df["Noi_dung"] != "đổi") &
            (~df["Status_val"].str.contains("sale|thanh", case=False, na=False))
        ].copy()
        if df.empty: continue

        main_f.append(df[["MaHang", "Operation", "Region", "Total_Ban"]])
        store_all_f.append(df[["Store_name", "Region", "MaHang", "Operation", "Total_Ban"]])

        if "Size" in df.columns:
            df["Size"] = df["Size"].fillna("").astype(str).str.strip()
            store_sz_f.append(df[["Store_name", "Region", "MaHang", "Operation", "Size", "Total_Ban"]])

        y_str = ''.join(filter(str.isdigit, path.stem))
        if y_str and int(y_str) in recent_years:
            df["Year"]  = pd.to_numeric(df.get("Year"),  errors="coerce")
            df["Month"] = pd.to_numeric(df.get("Month"), errors="coerce")
            mask = pd.Series(False, index=df.index)
            for y, m in recent_keys:
                mask |= (df["Year"] == y) & (df["Month"] == m)
            df_r = df[mask].copy()
            if not df_r.empty:
                cols_r = ["Store_name", "Region", "MaHang", "Operation", "Total_Ban", "Month", "Year"]
                if "Size" in df_r.columns:
                    cols_r.append("Size")
                store_rec_f.append(df_r[cols_r])

    def grp(frames, keys):
        if not frames: return pd.DataFrame()
        return pd.concat(frames).groupby(keys, dropna=False, as_index=False)["Total_Ban"].sum()

    sys_ban       = grp(main_f,     ["MaHang", "Operation", "Region"])
    store_ban_all = grp(store_all_f, ["Store_name", "Region", "MaHang", "Operation"])
    store_ban_size= grp(store_sz_f,  ["Store_name", "Region", "MaHang", "Operation", "Size"])

    if store_rec_f:
        store_rec_combined = pd.concat(store_rec_f)
        store_recent = store_rec_combined.groupby(
            ["Store_name", "Region", "MaHang", "Operation"], dropna=False, as_index=False
        ).agg(Ban_Recent_Store=("Total_Ban", "sum"), So_Thang_Ban=("Month", "nunique"))
        store_recent["Avg_Ban_Store"] = store_recent["Ban_Recent_Store"] / float(recent_months)

        # Lấy bán size gần đây để tính khả dụng chuyển hàng Chậm gần đây
        if "Size" in store_rec_combined.columns:
            store_ban_size_recent = store_rec_combined.groupby(
                ["Store_name", "Region", "MaHang", "Operation", "Size"], dropna=False, as_index=False
            )["Total_Ban"].sum().rename(columns={"Total_Ban": "Ban_Recent_Size"})
        else:
            store_ban_size_recent = pd.DataFrame(columns=["Store_name", "Region", "MaHang", "Operation", "Size", "Ban_Recent_Size"])
    else:
        store_recent = pd.DataFrame(columns=["Store_name", "Region", "MaHang", "Operation",
                                              "Ban_Recent_Store", "So_Thang_Ban", "Avg_Ban_Store"])
        store_ban_size_recent = pd.DataFrame(columns=["Store_name", "Region", "MaHang", "Operation", "Size", "Ban_Recent_Size"])

    # Tồn kho
    log(f"Reading {INVENTORY_FILE.name}")
    inv = pd.read_parquet(INVENTORY_FILE).fillna("").astype(str)
    inv.columns = [clean_name(c) for c in inv.columns]
    inv["MaHang"]    = inv["Mahang"].fillna("").astype(str).str.strip().str.upper()
    inv["Short_name"] = inv["MaHang"].str[:-4]
    inv = inv[inv["Short_name"].isin(short_names)].copy()

    inv["Total_Ton"]  = safe_numeric(inv["Qty_TonKho"])
    inv["Status_val"] = inv.get("Status", "").fillna("").astype(str).str.lower()
    # Lọc NGAY: chỉ giữ Nguyên Giá
    inv = inv[~inv["Status_val"].str.contains("sale|thanh", case=False, na=False)].copy()

    sys_ton        = inv.groupby(["MaHang", "Operation", "Region"],                     dropna=False, as_index=False)["Total_Ton"].sum()
    store_ton      = inv.groupby(["Store_name", "Region", "MaHang", "Operation"],       dropna=False, as_index=False)["Total_Ton"].sum()
    inv["Size"]    = inv["Size"].fillna("").astype(str).str.strip()
    store_ton_size = inv.groupby(["Store_name", "Region", "MaHang", "Operation", "Size"], dropna=False, as_index=False)["Total_Ton"].sum()

    # HDD (in-transit)
    if HDD_FILE.exists():
        hdd = pd.read_excel(HDD_FILE, sheet_name="HDD_QLKD_Tong_hop", engine="calamine")
        hdd.columns = [clean_name(c) for c in hdd.columns]
        hdd["MaHang"]    = hdd.get("Mahang", "").fillna("").astype(str).str.strip().str.upper()
        hdd["Short_name"] = hdd["MaHang"].str[:-4]
        hdd = hdd[hdd["Short_name"].isin(short_names)].copy()
        
        if not hdd.empty:
            hdd["Total_Ton"] = safe_numeric(hdd.get("Qty_TonKho", 0))
            if "Sales" in hdd.columns:
                hdd = hdd[~pd.to_numeric(hdd["Sales"], errors="coerce").isin([30, 50])].copy()
            sys_hdd = hdd.groupby(["MaHang", "Operation", "Region"], dropna=False, as_index=False)["Total_Ton"].sum()
            sys_ton = pd.concat([sys_ton, sys_hdd]).groupby(
                ["MaHang", "Operation", "Region"], dropna=False, as_index=False)["Total_Ton"].sum()

    # Chỉ giữ lại đúng 5 khu vực chính theo yêu cầu hiển thị
    valid_regs = ["TP. HCM", "Hà Nội", "Miền Tây", "Miền Trung - TN", "Miền Đông"]
    
    sys_ban = sys_ban[sys_ban["Region"].isin(valid_regs)].copy() if not sys_ban.empty else sys_ban
    store_ban_all = store_ban_all[store_ban_all["Region"].isin(valid_regs)].copy() if not store_ban_all.empty else store_ban_all
    store_recent = store_recent[store_recent["Region"].isin(valid_regs)].copy() if not store_recent.empty else store_recent
    sys_ton = sys_ton[sys_ton["Region"].isin(valid_regs)].copy() if not sys_ton.empty else sys_ton
    store_ton = store_ton[store_ton["Region"].isin(valid_regs)].copy() if not store_ton.empty else store_ton
    store_ton_size = store_ton_size[store_ton_size["Region"].isin(valid_regs)].copy() if not store_ton_size.empty else store_ton_size
    store_ban_size = store_ban_size[store_ban_size["Region"].isin(valid_regs)].copy() if not store_ban_size.empty else store_ban_size
    store_ban_size_recent = store_ban_size_recent[store_ban_size_recent["Region"].isin(valid_regs)].copy() if not store_ban_size_recent.empty else store_ban_size_recent

    return sys_ban, store_ban_all, store_recent, sys_ton, store_ton, store_ton_size, store_ban_size, store_ban_size_recent

# ── 3. Tháng XK ──────────────────────────────────────────────────────────────
def get_stock_month(dp, pm, py):
    dp = str(dp).strip()
    if dp == "CHƯA PP": return "CHƯA PP"
    ty, tm = None, None
    if dp.startswith("T") and "." in dp:
        try:
            p = dp[1:].split(".")
            tm = int(p[0])
            ty = int(p[1]) if len(p[1]) == 4 else int("20" + p[1])
        except Exception: pass
    if not ty:
        try:
            tm, ty = int(float(pm)), int(float(py))
            if ty < 100: ty += 2000
        except Exception: return "LỖI"
    diff = (datetime.now().year - ty) * 12 + datetime.now().month - tm
    return max(diff, 0)

# ── 4. Sheet 1 – Danh sách mã ────────────────────────────────────────────────
def process_system_sheet(sys_ban, sys_ton, d_category, f_tracking):
    log("Building Sheet 1 – Danh_Sach_Ma")
    df_ton = sys_ton.groupby(["MaHang", "Operation"], dropna=False, as_index=False).agg({"Total_Ton": "sum"})

    if not sys_ban.empty:
        sys_ban["Total_Ban"] = safe_numeric(sys_ban.get("Total_Ban", 0))
        sys_ban_agg = sys_ban.groupby(["MaHang", "Operation"], dropna=False, as_index=False).agg({"Total_Ban": "sum"})
        for reg in REGION_COLUMNS:
            sys_ban[reg] = np.where(sys_ban["Region"] == reg, sys_ban["Total_Ban"], 0)
        sys_ban_reg = sys_ban.groupby(["MaHang", "Operation"], dropna=False, as_index=False).agg({r: "sum" for r in REGION_COLUMNS})
    else:
        sys_ban_agg = pd.DataFrame(columns=["MaHang", "Operation", "Total_Ban"])
        sys_ban_reg = pd.DataFrame(columns=["MaHang", "Operation"] + REGION_COLUMNS)

    df = df_ton.merge(sys_ban_agg, on=["MaHang", "Operation"], how="left").fillna({"Total_Ban": 0})
    df = df.merge(sys_ban_reg,    on=["MaHang", "Operation"], how="left").fillna({r: 0 for r in REGION_COLUMNS})

    def top_regions(row):
        vals = sorted([(r, row[r]) for r in REGION_COLUMNS if row[r] > 0], key=lambda x: x[1], reverse=True)
        return pd.Series([
            vals[0][0] if vals else pd.NA,
            vals[1][0] if len(vals) > 1 else pd.NA,
            vals[0][1] if vals else 0,
            vals[1][1] if len(vals) > 1 else 0,
        ])

    if df.empty:
        df["Top1"] = pd.Series(dtype=str)
        df["Top2"] = pd.Series(dtype=str)
        df["Rate1"] = pd.Series(dtype=float)
        df["Rate2"] = pd.Series(dtype=float)
    else:
        df[["Top1", "Top2", "Rate1", "Rate2"]] = df.apply(top_regions, axis=1, result_type='expand')
    df["Short_name"] = df["MaHang"].str[:-4]
    df = df.merge(d_category[["Short_name", "Brand", "Report_item_name", "Group_Report", "Product_type"]],
                  on="Short_name", how="left")
    df = df.merge(
        f_tracking[["item_code", "Operation", "Dist_plan", "Production_month", "Production_year",
                     "Color_group", "Form", "Style"]].rename(columns={"item_code": "MaHang"}),
        on=["MaHang", "Operation"], how="left"
    )
    df["Tháng_XK"] = df.apply(
        lambda r: get_stock_month(r["Dist_plan"], r["Production_month"], r["Production_year"]), axis=1)

    is_t_plan = (df["Dist_plan"].fillna("").astype(str).str.startswith("T") &
                 df["Dist_plan"].fillna("").astype(str).str.contains(r"\.", regex=True))
    df = df[is_t_plan & (df["Total_Ton"] > 0)].copy()

    denom = df["Total_Ban"] + df["Total_Ton"]
    df["Ty_Le_Ban_Toan_Quoc"] = np.where(denom == 0, 0, np.round(df["Total_Ban"] / denom, 2))

    txk  = pd.to_numeric(df["Tháng_XK"], errors="coerce").fillna(999)
    rate = df["Ty_Le_Ban_Toan_Quoc"]
    ton  = df["Total_Ton"]
    df["Group"] = np.select(
        [txk < 6, ton < 20, rate > 0.80,
         (rate >= 0.30) & (rate <= 0.80) & (txk >= 6),
         (rate < 0.30) & (txk >= 6)],
        ["Group D", "Group E", "Group A", "Group B", "Group C"],
        default="Group E"
    )
    return df

# ── 5. Lệnh điều chuyển (2 bước: store-level → size-level) ──────────────────
def process_transfers(system_df, store_ton, store_ton_size, store_ban_all, store_ban_size, a_region, store_recent, store_ban_size_recent, selected_regions=None):
    """
    Group B – Logic 2 bước với Phân loại Ma trận 2D & Capped ST = 50%:
      Bước 1 (Store level):
        - Trang_Thai 2D gộp từ All-time ST và Recent ST:
          * Bán rất chạy : All ST >= 75% & Recent ST >= 65% (Đích ưu tiên 1)
          * Bán ổn định  : All ST >= 55% & Recent ST >= 40% (Đích ưu tiên 2)
          * Chậm gần đây : All ST >= 55% & Recent ST < 40% (Nguồn chuyển đi dư thừa)
          * Chậm bán     : All ST < 55% & Recent ST < 30% (Nguồn chuyển sạch 100%)
          * Trung bình   : Các trường hợp còn lại (Giữ nguyên hiện trạng)
        - Can_Nhan = số cần nhận để đạt ST target 50% (dựa trên số bán gần đây và tồn thực tế)
        - Budget: 65% → Bán rất chạy, 35% → Bán ổn định; ưu tiên ST cao nhất trước
      Bước 2 (Size level):
        - Từ Can_Nhan tổng của cửa hàng đích →
          xác định nhận size nào bao nhiêu cái theo TỈ LỆ BÁN SIZE của chính cửa hàng đó
        - Ở phía nguồn:
          * Chậm bán     -> Chuyển sạch 100% tồn size.
          * Chậm gần đây -> Chỉ chuyển phần dư thừa (Avail = Tồn_Size - Bán_Recent_Size).
    """
    log("Building Transfer Orders")
    valid_skus = system_df[system_df["Group"].isin(["Group A", "Group B"])].copy()
    if valid_skus.empty:
        return pd.DataFrame()

    # Build size-level dictionaries once for fast O(1) lookups
    store_ton_size_active = store_ton_size[store_ton_size["Total_Ton"] > 0]
    size_lookup_dict = {}
    for (mh, op, st), grp_sz in store_ton_size_active.groupby(["MaHang", "Operation", "Store_name"]):
        size_lookup_dict[(mh, op, st)] = grp_sz[["Size", "Total_Ton"]].values.tolist()

    ban_size_lookup_dict = {}
    for (mh, op, st), grp_sz in store_ban_size.groupby(["MaHang", "Operation", "Store_name"]):
        ban_size_lookup_dict[(mh, op, st)] = grp_sz[["Size", "Total_Ban"]].values.tolist()

    ban_size_recent_lookup_dict = {}
    if not store_ban_size_recent.empty:
        for (mh, op, st), grp_sz in store_ban_size_recent.groupby(["MaHang", "Operation", "Store_name"]):
            ban_size_recent_lookup_dict[(mh, op, st)] = {str(r["Size"]): float(r["Ban_Recent_Size"]) for _, r in grp_sz.iterrows()}

    # Store-level sell-through
    sl = store_ton.merge(store_ban_all, on=["Store_name", "Region", "MaHang", "Operation"],
                         how="outer").fillna(0)
    sl = sl.rename(columns={"Total_Ton": "St_Ton", "Total_Ban": "St_Ban"})
    
    # Lọc các cửa hàng tham gia điều chuyển theo selected_regions
    selected_regions_clean = [clean_name(r) for r in selected_regions] if selected_regions is not None else None
    if selected_regions_clean is not None:
        sl = sl[sl["Region"].isin(selected_regions_clean)].copy()

    # Ghép thêm số bán gần đây
    sl = sl.merge(store_recent, on=["Store_name", "Region", "MaHang", "Operation"], how="left").fillna(0)
    
    denom_all = sl["St_Ban"] + sl["St_Ton"]
    rate_all  = np.where(denom_all == 0, 0.0, sl["St_Ban"] / denom_all)
    
    denom_rec = sl["Ban_Recent_Store"] + sl["St_Ton"]
    rate_rec  = np.where(denom_rec == 0, 0.0, sl["Ban_Recent_Store"] / denom_rec)
    
    sl["Rate_All_Store"]    = rate_all
    sl["Rate_Recent_Store"] = rate_rec
    
    # Phân loại trạng thái 2D
    c_hot    = (rate_all >= 0.75) & (rate_rec >= 0.65)
    c_stable = (rate_all >= 0.55) & (rate_rec >= 0.40)
    c_slow   = (rate_all >= 0.55) & (rate_rec < 0.40)
    c_dead   = (rate_all < 0.55)  & (rate_rec < 0.30)
    
    sl["Trang_Thai"] = np.select(
        [c_hot, c_stable, c_slow, c_dead],
        ["Bán rất chạy", "Bán ổn định", "Chậm gần đây", "Chậm bán"],
        default="Trung bình"
    )

    # Gắn Group/Top1/Top2 vào sl
    sl = sl.merge(
        valid_skus[["MaHang", "Operation", "Group", "Top1", "Top2", "Total_Ton"]]
                  .rename(columns={"Total_Ton": "Sys_Ton"}),
        on=["MaHang", "Operation"], how="inner"
    )
    sl = sl.merge(a_region[["Store_name", "Store_RP", "Store_rank"]], on="Store_name", how="left")
    sl["Store_RP"] = sl["Store_RP"].fillna(sl["Store_name"])

    records = []
    SRC_STATES   = {"Chậm bán", "Chậm gần đây"}
    DEST_CHAY    = "Bán rất chạy"
    DEST_ON_DINH = "Bán ổn định"

    # ── GROUP A ───────────────────────────────────────────────────────────────
    # Logic: tổng tồn các CH không phải rank-I → phân bổ tỉ lệ về tất cả CH rank-I
    # trong top1 (hoặc top1+top2 nếu sys_ton > 100), theo tỉ lệ bán mã đó tại mỗi CH rank-I.
    # Sau đó chia size bằng Largest Remainder Method (giống Group B).
    def _lrm_size_alloc(N: int, ban_sizes: list, src_pool: dict) -> dict:
        """Phân bổ N pcs vào các size theo Largest Remainder Method (chỉ size có src_pool)."""
        eligible = [(str(sz), ban) for sz, ban in ban_sizes if str(sz) in src_pool and ban > 0]
        if not eligible: return {}
        total_elig = sum(b for _, b in eligible)
        if total_elig == 0: return {}
        raw    = [(sz, N * ban / total_elig) for sz, ban in eligible]
        floors = [(sz, int(v)) for sz, v in raw]
        rems   = [(sz, v - int(v)) for sz, v in raw]
        extra  = N - sum(f for _, f in floors)
        elig_map = dict(eligible)
        extra_set = {sz for sz, _ in sorted(rems, key=lambda x: (-x[1], -elig_map.get(x[0], 0)))[:int(extra)]}
        return {sz: fl + (1 if sz in extra_set else 0) for sz, fl in floors if fl + (1 if sz in extra_set else 0) > 0}

    for (mh, op), grp in sl[sl["Group"] == "Group A"].groupby(["MaHang", "Operation"]):
        sys_ton_val = grp["Sys_Ton"].iloc[0]
        top1, top2  = grp["Top1"].iloc[0], grp["Top2"].iloc[0]
        targets = [top1] if pd.notna(top1) else []
        if sys_ton_val > 100 and pd.notna(top2): targets.append(top2)

        # Tất cả CH rank-I trong các vùng mục tiêu
        tgt_mask = (a_region["Region"].isin(targets)) & \
                   (a_region["Store_rank"].fillna("").astype(str).str.strip().str.upper() == "I")
        if selected_regions_clean is not None:
            tgt_mask = tgt_mask & a_region["Region"].isin(selected_regions_clean)
        tgt_stores_df = a_region[tgt_mask].copy()
        if tgt_stores_df.empty: continue

        # Tổng tồn khả dụng từ các CH không phải rank-I trong vùng mục tiêu
        tgt_store_names = set(tgt_stores_df["Store_name"])
        src_rows_a = grp[~grp["Store_name"].isin(tgt_store_names)]

        # Xây pool tồn theo size từ nguồn (tất cả CH không phải rank-I)
        src_pool_a: dict = {}
        for _, src in src_rows_a.iterrows():
            if ff(src["St_Ton"]) <= 0: continue
            sizes = size_lookup_dict.get((mh, op, src["Store_name"]), [])
            for sz_size, sz_ton in sizes:
                s = str(sz_size)
                avail = ff(sz_ton)
                if avail <= 0: continue
                src_pool_a.setdefault(s, []).append({
                    "store_rp": src["Store_RP"], "region": src["Region"],
                    "tt": src.get("Trang_Thai", ""), "avail": avail
                })
        total_avail_a = sum(sum(e["avail"] for e in lst) for lst in src_pool_a.values())
        if total_avail_a <= 0: continue

        # Tỉ lệ bán mã tại mỗi CH rank-I → làm trọng số phân bổ
        dest_ban = {}
        for _, row in tgt_stores_df.iterrows():
            sn = row["Store_name"]
            store_info = grp[grp["Store_name"] == sn]
            ban_val = ff(store_info["St_Ban"].iloc[0]) if not store_info.empty else 0.0
            dest_ban[sn] = ban_val
        total_dest_ban = sum(dest_ban.values())

        # Phân bổ tổng cho từng CH rank-I (tỉ lệ bán; nếu đều = 0 thì chia đều)
        N_total = int(round(total_avail_a, 0))
        if total_dest_ban > 0:
            raw_a = [(sn, N_total * dest_ban[sn] / total_dest_ban) for sn in dest_ban]
        else:
            n_dest = len(dest_ban)
            raw_a = [(sn, N_total / n_dest) for sn in dest_ban]

        floors_a   = [(sn, int(v)) for sn, v in raw_a]
        rems_a     = [(sn, v - int(v)) for sn, v in raw_a]
        extra_a    = N_total - sum(f for _, f in floors_a)
        extra_set_a = {sn for sn, _ in sorted(rems_a, key=lambda x: (-x[1], -dest_ban.get(x[0], 0)))[:int(extra_a)]}
        store_receive_a = {sn: fl + (1 if sn in extra_set_a else 0) for sn, fl in floors_a
                           if fl + (1 if sn in extra_set_a else 0) > 0}

        # Bước 2: chia size bằng LRM cho từng CH đích rank-I
        for dest_sn, n_recv in store_receive_a.items():
            dest_row_df = tgt_stores_df[tgt_stores_df["Store_name"] == dest_sn]
            if dest_row_df.empty: continue
            dest_row    = dest_row_df.iloc[0]
            dest_rp     = dest_row.get("Store_RP", dest_sn)
            dest_region = dest_row.get("Region", "")

            ban_sizes_dest = ban_size_lookup_dict.get((mh, op, dest_sn), [])
            size_alloc_a = _lrm_size_alloc(n_recv, ban_sizes_dest, src_pool_a)
            if not size_alloc_a: continue  # CH đích không có lịch sử bán size

            for size, qty_want in sorted(size_alloc_a.items(),
                                         key=lambda x: -dict(ban_sizes_dest).get(x[0], 0) if ban_sizes_dest else 0):
                if qty_want <= 0 or size not in src_pool_a: continue
                qty_rem = qty_want
                for src_e in sorted(src_pool_a[size],
                                    key=lambda x: (0 if x["region"] == dest_region else 1, -x["avail"])):
                    if qty_rem <= 0: break
                    if src_e["avail"] <= 0: continue
                    take = round(min(src_e["avail"], float(qty_rem)), 0)
                    if take <= 0: continue
                    records.append({
                        "Group": "Group A", "MaHang": mh, "Operation": op, "Size": size,
                        "Từ_Cửa_Hàng": src_e["store_rp"], "Từ_Vùng": src_e["region"],
                        "Đến_Cửa_Hàng": dest_rp,          "Đến_Vùng": dest_region,
                        "Số_Lượng": take,
                        "Trang_Thai_Nguon": src_e["tt"], "Trang_Thai_Nhan": "",
                        "Cung_KV": "Nội vùng" if src_e["region"] == dest_region else "Liên vùng",
                    })
                    src_e["avail"] -= take
                    qty_rem -= take

    # ── GROUP B ───────────────────────────────────────────────────────────────
    def calc_can_nhan(ban, ton, target):
        """Số cần nhận thêm để đạt sell-through = target (tính dựa trên số bán gần đây)."""
        if target <= 0 or (ban + ton) == 0: return 0.0
        cur_st = ban / (ban + ton)
        if cur_st <= target: return 0.0
        ton_tgt = ban * (1.0 - target) / target
        return max(ton_tgt - ton, 0.0)

    for (mh, op), grp in sl[sl["Group"] == "Group B"].groupby(["MaHang", "Operation"]):
        src_rows = grp[grp["Trang_Thai"].isin(SRC_STATES)].copy()
        dst_chay = grp[grp["Trang_Thai"] == DEST_CHAY].copy()
        dst_on   = grp[grp["Trang_Thai"] == DEST_ON_DINH].copy()

        # Xây dựng pool tồn kho khả dụng từ các shop nguồn theo size
        src_pool = {}
        for _, src in src_rows.iterrows():
            sizes = size_lookup_dict.get((mh, op, src["Store_name"]), [])
            for sz_size, sz_ton in sizes:
                s = str(sz_size)
                
                # Tính lượng khả dụng chuyển đi theo từng trạng thái nguồn 2D
                if src["Trang_Thai"] == "Chậm bán":
                    avail = ff(sz_ton)  # Chuyển sạch 100%
                elif src["Trang_Thai"] == "Chậm gần đây":
                    recent_sales_map = ban_size_recent_lookup_dict.get((mh, op, src["Store_name"]), {})
                    ban_rec_sz = recent_sales_map.get(s, 0.0)
                    avail = max(ff(sz_ton) - ff(ban_rec_sz), 0.0)  # Chỉ chuyển phần dư thừa
                else:
                    avail = 0.0
                
                if avail <= 0: continue
                src_pool.setdefault(s, []).append({
                    "store": src["Store_name"], "store_rp": src["Store_RP"], "region": src["Region"],
                    "tt": src.get("Trang_Thai", ""), "avail": avail
                })

        # Tổng lượng cung khả dụng
        total_avail = sum(sum(item["avail"] for item in lst) for lst in src_pool.values())
        if total_avail <= 0 or (dst_chay.empty and dst_on.empty): continue

        # ── Bước 1: tính Can_Nhan tổng cho từng cửa hàng đích ────────────────
        store_receive: dict[str, float] = {}

        for dst_group, budget, target in [
            (dst_chay, round(total_avail * RATE_TO_CHAY, 0),    0.50), # Capped tối đa 50% ST
            (dst_on,   round(total_avail * RATE_TO_ON_DINH, 0), 0.50), # Capped tối đa 50% ST
        ]:
            if dst_group.empty or budget <= 0: continue
            dst_group = dst_group.copy()
            dst_group["_can"] = dst_group.apply(
                lambda r: calc_can_nhan(ff(r["Ban_Recent_Store"]), ff(r["St_Ton"]), target), axis=1)
            dst_group["_st"]  = np.where(
                (dst_group["Ban_Recent_Store"] + dst_group["St_Ton"]) > 0,
                dst_group["Ban_Recent_Store"] / (dst_group["Ban_Recent_Store"] + dst_group["St_Ton"]), 0.0)
            
            # Ưu tiên rank La mã: I -> II -> III -> IV -> nan
            rank_map = {"I": 1, "II": 2, "III": 3, "IV": 4}
            dst_group["_rank_sort"] = dst_group["Store_rank"].fillna("").astype(str).str.strip().str.upper().map(rank_map).fillna(99)
            dst_group = dst_group.sort_values(["_rank_sort", "_st"], ascending=[True, False])

            budget_left = budget
            for _, row in dst_group.iterrows():
                if row["_can"] <= 0 or budget_left <= 0: continue
                alloc = round(min(row["_can"], budget_left), 0)
                if alloc <= 0: continue
                store_receive[row["Store_name"]] = store_receive.get(row["Store_name"], 0.0) + alloc
                budget_left -= alloc

        if not store_receive: continue

        # ── Bước 2: phân bổ theo size dựa vào tỉ lệ bán size của cửa hàng đích ──
        for dest_store, total_receive in store_receive.items():
            dest_info = grp[grp["Store_name"] == dest_store]
            if dest_info.empty: continue
            dest_info   = dest_info.iloc[0]
            dest_region = str(dest_info.get("Region", ""))
            dest_tt     = str(dest_info.get("Trang_Thai", ""))
            dest_rp     = dest_info.get("Store_RP", dest_store)

            # Tỉ lệ bán size của cửa hàng đích (cho SKU này)
            ban_sizes = ban_size_lookup_dict.get((mh, op, dest_store), [])
            if not ban_sizes: continue

            total_ban_sz = sum(sz_ban for _, sz_ban in ban_sizes)
            if total_ban_sz == 0: continue

            # ── Largest Remainder Method: chia integer tổng = total_receive ──
            # Chỉ tính những size có src_pool (có hàng để chuyển)
            eligible = [(str(sz), ban) for sz, ban in ban_sizes if str(sz) in src_pool]
            if not eligible: continue

            total_elig_ban = sum(b for _, b in eligible)
            if total_elig_ban == 0: continue

            N = int(round(total_receive, 0))   # tổng cần nhận cố định
            raw_allocs = [(sz, N * ban / total_elig_ban) for sz, ban in eligible]
            floors     = [(sz, int(v)) for sz, v in raw_allocs]
            remainders = [(sz, v - int(v)) for sz, v in raw_allocs]
            total_floor = sum(f for _, f in floors)
            extra = N - total_floor            # số lẻ cần phân bổ thêm (>= 0)

            elig_ban_map = dict(eligible)
            sorted_rem = sorted(remainders,
                                key=lambda x: (-x[1], -elig_ban_map.get(x[0], 0)))
            extra_set = {sz for sz, _ in sorted_rem[:int(extra)]}

            size_alloc = {}
            for sz, fl in floors:
                qty = fl + (1 if sz in extra_set else 0)
                if qty > 0:
                    size_alloc[sz] = qty

            # ── Lấy hàng từ pool nguồn theo từng size (không vượt size_alloc) ─
            for size, qty_want in sorted(size_alloc.items(),
                                         key=lambda x: -elig_ban_map.get(x[0], 0)):
                if qty_want <= 0 or size not in src_pool: continue

                qty_rem = qty_want
                for src_e in sorted(src_pool[size],
                                    key=lambda x: (0 if x["region"] == dest_region else 1, -x["avail"])):
                    if qty_rem <= 0: break
                    if src_e["avail"] <= 0: continue
                    take = round(min(src_e["avail"], float(qty_rem)), 0)
                    if take <= 0: continue

                    records.append({
                        "Group": "Group B", "MaHang": mh, "Operation": op, "Size": size,
                        "Từ_Cửa_Hàng": src_e["store_rp"],  "Từ_Vùng": src_e["region"],
                        "Đến_Cửa_Hàng": dest_rp,          "Đến_Vùng": dest_region,
                        "Số_Lượng": take,
                        "Trang_Thai_Nguon": src_e["tt"], "Trang_Thai_Nhan": dest_tt,
                        "Cung_KV": "Nội vùng" if src_e["region"] == dest_region else "Liên vùng",
                    })
                    src_e["avail"] -= take
                    qty_rem -= take

    return pd.DataFrame(records) if records else pd.DataFrame()

# ── 6. Sheet 3 – Chi tiết cửa hàng ──────────────────────────────────────────
def process_store_details(system_df, store_ban_all, store_recent, store_ton, store_ton_size, store_ban_size, transfers, a_region, recent_months=3):
    log("Building Sheet 3 – Chi_Tiet_Cua_Hang")
    df = store_ton_size.merge(
        store_ban_size, on=["Store_name", "Region", "MaHang", "Operation", "Size"], how="outer"
    ).fillna(0)
    df = df.merge(
        system_df[["MaHang", "Operation", "Brand", "Report_item_name", "Group_Report",
                   "Product_type", "Dist_plan", "Tháng_XK", "Color_group", "Form", "Style", "Group"]],
        on=["MaHang", "Operation"], how="inner"
    )

    # Gắn xếp loại và rank cửa hàng
    df = df.merge(a_region[["Store_name", "Store_RP", "Store_rank"]], on="Store_name", how="left")
    df["Store_RP"] = df["Store_RP"].fillna(df["Store_name"])

    # Store-level metrics
    sl2 = store_ton.merge(store_ban_all, on=["Store_name", "Region", "MaHang", "Operation"],
                          how="outer").fillna(0)
    sl2 = sl2.merge(store_recent, on=["Store_name", "Region", "MaHang", "Operation"],
                    how="left").fillna(0)
    
    # Tính toán chính xác tỉ lệ bán 2D Matrix
    denom = sl2["Total_Ban"] + sl2["Total_Ton"]
    rate_all = np.where(denom == 0, 0, denom - denom) # placeholder
    rate_all = np.where(denom == 0, 0.0, sl2["Total_Ban"] / denom)
    
    denom2 = sl2["Ban_Recent_Store"] + sl2["Total_Ton"]
    rate_rec = np.where(denom2 == 0, 0.0, sl2["Ban_Recent_Store"] / denom2)
    
    sl2["Rate_All_Store"]    = np.round(rate_all, 2)
    sl2["Rate_Recent_Store"] = np.round(rate_rec, 2)
    
    # Đắp phân loại 2D
    c_hot    = (rate_all >= 0.75) & (rate_rec >= 0.65)
    c_stable = (rate_all >= 0.55) & (rate_rec >= 0.40)
    c_slow   = (rate_all >= 0.55) & (rate_rec < 0.40)
    c_dead   = (rate_all < 0.55)  & (rate_rec < 0.30)
    
    sl2["Trang_Thai"] = np.select(
        [c_hot, c_stable, c_slow, c_dead],
        ["Bán rất chạy", "Bán ổn định", "Chậm gần đây", "Chậm bán"],
        default="Trung bình"
    )
    sl2 = sl2.rename(columns={"Total_Ton": "Total_Ton_Store", "Total_Ban": "Total_Ban_Store_All"})

    df = df.merge(sl2, on=["Store_name", "Region", "MaHang", "Operation"], how="left")
    df["Ton_Size"] = df["Total_Ton"]
    df["Ban_Size"] = df["Total_Ban"]

    # Tỉ lệ bán size (size distribution)
    tot_ban = df.groupby(["Store_RP", "Region", "MaHang", "Operation"])["Ban_Size"].transform("sum")
    df["Ty_Le_Ban_Size"] = np.where(tot_ban == 0, 0, np.round(df["Ban_Size"] / tot_ban, 4))

    # Map Transfers
    if transfers is not None and not transfers.empty:
        send = (transfers.groupby(["Từ_Cửa_Hàng", "MaHang", "Operation", "Size"])
                .agg(Đến_Cửa_Hàng=("Đến_Cửa_Hàng", lambda x: ", ".join(str(i) for i in x.dropna().unique())),
                     Số_Lượng=("Số_Lượng", "sum")).reset_index())
        send["Hành_Động"] = "CHUYỂN ĐI"
        send = send.rename(columns={"Từ_Cửa_Hàng": "Store_RP"})

        recv = (transfers.groupby(["Đến_Cửa_Hàng", "MaHang", "Operation", "Size"])
                .agg(Từ_Cửa_Hàng=("Từ_Cửa_Hàng", lambda x: ", ".join(str(i) for i in x.dropna().unique())),
                     Số_Lượng=("Số_Lượng", "sum")).reset_index())
        recv["Hành_Động"] = "NHẬN VỀ"
        recv = recv.rename(columns={"Đến_Cửa_Hàng": "Store_RP", "Từ_Cửa_Hàng": "Đến_Cửa_Hàng"})

        tr = pd.concat([send, recv], ignore_index=True)
        df = df.merge(tr, on=["Store_RP", "MaHang", "Operation", "Size"], how="left")
    else:
        df["Hành_Động"] = pd.NA; df["Số_Lượng"] = pd.NA; df["Đến_Cửa_Hàng"] = pd.NA

    df = df.rename(columns={"Đến_Cửa_Hàng": "Cửa_Hàng_Đối_Tác", "Số_Lượng": "SL_Đề_Xuất"})
    
    df["Ton_Sau_Dieu_Chuyen"] = df["Ton_Size"]
    sl = pd.to_numeric(df["SL_Đề_Xuất"].fillna(0))
    df.loc[df["Hành_Động"] == "CHUYỂN ĐI", "Ton_Sau_Dieu_Chuyen"] = df["Ton_Size"] - sl
    df.loc[df["Hành_Động"] == "NHẬN VỀ", "Ton_Sau_Dieu_Chuyen"] = df["Ton_Size"] + sl

    out_cols = [
        "Brand", "Report_item_name", "Group_Report", "MaHang", "Operation",
        "Dist_plan", "Tháng_XK", "Group",
        "Store_RP", "Store_rank", "Region", "Color_group", "Form", "Style", "Size",
        "Ton_Size", "Ban_Size", "Ty_Le_Ban_Size",
        "Hành_Động", "SL_Đề_Xuất", "Ton_Sau_Dieu_Chuyen", "Cửa_Hàng_Đối_Tác",
        "Total_Ton_Store", "Total_Ban_Store_All", "Rate_All_Store", "Trang_Thai",
        "Ban_Recent_Store", "So_Thang_Ban", "Avg_Ban_Store", "Rate_Recent_Store",
    ]
    return df[[c for c in out_cols if c in df.columns]]

# ── 7. Sheet 2 – Tỉ lệ bán size (pivot) ─────────────────────────────────────
def process_size_pivot(sheet3_df):
    log("Building Sheet 2 – Ti_Le_Ban_Size")
    group_cols = ["Region", "Store_RP"]
    for col in ["Store_rank"]:
        if col in sheet3_df.columns:
            group_cols.append(col)
    group_cols.extend(["Color_group", "Form", "Style"])

    df = sheet3_df.groupby(
        group_cols + ["Size"], dropna=False, as_index=False
    )[["Ton_Size", "Ban_Size"]].sum()
    sum_ban = df.groupby(group_cols)["Ban_Size"].transform("sum")
    df["Rate"] = np.where(sum_ban == 0, 0, df["Ban_Size"] / sum_ban)
    return df.pivot_table(index=group_cols, columns="Size", values="Rate", aggfunc="mean").reset_index()

# ── 8. Dialogs Chọn Lọc (Tkinter) ────────────────────────────────────────────
PERIOD_OPTIONS = [1, 3, 6, 9, 12, 15, 18]

def choose_period_months() -> int | None:
    """Hiển thị dialog chọn số tháng gần nhất để lọc số bán."""
    BG         = "#1e1e2e"
    BG_ITEM    = "#313145"
    BG_HOVER   = "#3d3d58"
    BG_CHECKED = "#4a3f7a"
    ACCENT     = "#7c6af7"
    ACCENT2    = "#a78bfa"
    FG         = "#e2e8f0"
    FG_DIM     = "#94a3b8"
    BTN_OK_BG  = "#7c6af7"
    BTN_OK_FG  = "#ffffff"
    BTN_SEC_BG = "#313145"
    BTN_SEC_FG = "#cbd5e1"
    FONT_TITLE = ("Segoe UI", 14, "bold")
    FONT_SUB   = ("Segoe UI", 9)
    FONT_BTN   = ("Segoe UI", 9, "bold")
    FONT_NUM   = ("Segoe UI", 22, "bold")
    FONT_UNIT  = ("Segoe UI", 9)
    FONT_HINT  = ("Segoe UI", 8)

    selected_value = [None]
    root = tk.Tk()
    selected_var = tk.IntVar(value=3)  # Mặc định 3 tháng
    root.title("Chọn kỳ số liệu bán")
    root.configure(bg=BG)
    root.attributes("-topmost", True)
    root.after(200, lambda: root.attributes("-topmost", False))
    root.resizable(False, False)

    hdr = tk.Frame(root, bg=BG)
    hdr.pack(fill="x", padx=24, pady=(20, 4))
    tk.Label(hdr, text="Chọn kỳ số liệu bán", font=FONT_TITLE, bg=BG, fg=ACCENT2, anchor="w").pack(fill="x")
    tk.Label(
        hdr,
        text="Lấy số bán trong N tháng gần nhất (áp dụng tính số bán gần đây cửa hàng).",
        font=FONT_SUB, bg=BG, fg=FG_DIM, wraplength=460, justify="left", anchor="w",
    ).pack(fill="x", pady=(3, 0))
    tk.Frame(root, bg=ACCENT, height=2).pack(fill="x", padx=24, pady=(12, 14))

    card_frame = tk.Frame(root, bg=BG)
    card_frame.pack(padx=24, pady=(0, 14))

    card_refs = {}
    now = datetime.now()

    def _calc_from_str(val: int) -> str:
        m = now.month - (val - 1)
        y = now.year
        while m <= 0:
            m += 12
            y -= 1
        return f"Từ T{m:02d}/{str(y)[-2:]}"

    def _set_card(val: int, active: bool) -> None:
        card, lbl_num, lbl_unit, lbl_hint = card_refs[val]
        bg = BG_CHECKED if active else BG_ITEM
        fg_num = ACCENT2 if active else FG
        card.configure(bg=bg)
        lbl_num.configure(bg=bg, fg=fg_num)
        lbl_unit.configure(bg=bg)
        lbl_hint.configure(bg=bg)

    def _select(val: int) -> None:
        old = selected_var.get()
        selected_var.set(val)
        _set_card(old, False)
        _set_card(val, True)

    def _on_enter(val: int) -> None:
        if selected_var.get() != val:
            card, lbl_num, lbl_unit, lbl_hint = card_refs[val]
            card.configure(bg=BG_HOVER)
            lbl_num.configure(bg=BG_HOVER)
            lbl_unit.configure(bg=BG_HOVER)
            lbl_hint.configure(bg=BG_HOVER)

    def _on_leave(val: int) -> None:
        _set_card(val, selected_var.get() == val)

    for val in PERIOD_OPTIONS:
        is_default = (val == 3)
        bg0 = BG_CHECKED if is_default else BG_ITEM
        fg0 = ACCENT2 if is_default else FG

        card = tk.Frame(card_frame, bg=bg0, padx=18, pady=14, relief="flat", bd=0, cursor="hand2")
        card.pack(side="left", padx=5)

        lbl_num  = tk.Label(card, text=str(val),    font=FONT_NUM,  bg=bg0, fg=fg0,  cursor="hand2")
        lbl_unit = tk.Label(card, text="tháng",     font=FONT_UNIT, bg=bg0, fg=FG_DIM, cursor="hand2")
        lbl_hint = tk.Label(card, text=_calc_from_str(val), font=FONT_HINT, bg=bg0, fg=FG_DIM, cursor="hand2")
        lbl_num.pack()
        lbl_unit.pack()
        lbl_hint.pack(pady=(6, 0))

        card_refs[val] = (card, lbl_num, lbl_unit, lbl_hint)
        for w in (card, lbl_num, lbl_unit, lbl_hint):
            w.bind("<Button-1>", lambda e, v=val: _select(v))
            w.bind("<Enter>",    lambda e, v=val: _on_enter(v))
            w.bind("<Leave>",    lambda e, v=val: _on_leave(v))

    tk.Frame(root, bg=ACCENT, height=1).pack(fill="x", padx=24, pady=(4, 0))
    footer = tk.Frame(root, bg=BG, pady=12)
    footer.pack(fill="x", padx=24)

    def _confirm():
        selected_value[0] = selected_var.get()
        root.quit()

    def _cancel():
        selected_value[0] = None
        root.quit()

    def _make_footer_btn(parent, text, cmd, accent=False):
        b = tk.Button(parent, text=text, command=cmd,
                    font=FONT_BTN,
                    bg=BTN_OK_BG if accent else BTN_SEC_BG,
                    fg=BTN_OK_FG if accent else BTN_SEC_FG,
                    relief="flat", bd=0, padx=20, pady=7,
                    activebackground=ACCENT2 if accent else BG_HOVER,
                    activeforeground="#ffffff",
                    cursor="hand2")
        b.pack(side="right", padx=(6, 0))
        return b

    _make_footer_btn(footer, "  Xác nhận  ✔", _confirm, accent=True)
    _make_footer_btn(footer, "  Hủy  ✘", _cancel, accent=False)

    root.protocol("WM_DELETE_WINDOW", _cancel)
    root.mainloop()
    root.destroy()
    return selected_value[0]

def choose_multi_options(
    title: str,
    subtitle: str,
    options: list[str],
    confirm_text: str = "Xác nhận",
    min_selected: int = 1,
) -> list[str] | None:
    options = sorted({str(x).strip() for x in options if str(x).strip()})
    if len(options) <= 1:
        return options

    BG         = "#1e1e2e"
    BG_PANEL   = "#2a2a3e"
    BG_ITEM    = "#313145"
    BG_HOVER   = "#3d3d58"
    BG_CHECKED = "#4a3f7a"
    ACCENT     = "#7c6af7"
    ACCENT2    = "#a78bfa"
    FG         = "#e2e8f0"
    FG_DIM     = "#94a3b8"
    BTN_OK_BG  = "#7c6af7"
    BTN_OK_FG  = "#ffffff"
    BTN_SEC_BG = "#313145"
    BTN_SEC_FG = "#cbd5e1"
    FONT_TITLE = ("Segoe UI", 14, "bold")
    FONT_SUB   = ("Segoe UI", 9)
    FONT_ITEM  = ("Segoe UI", 9)
    FONT_BTN   = ("Segoe UI", 9, "bold")
    FONT_COUNT = ("Segoe UI", 9)
    COLS       = 4

    selected = [None]
    root = tk.Tk()
    root.title(title)
    root.configure(bg=BG)
    root.attributes("-topmost", True)
    root.after(200, lambda: root.attributes("-topmost", False))
    root.resizable(True, True)

    hdr = tk.Frame(root, bg=BG)
    hdr.pack(fill="x", padx=20, pady=(18, 2))
    tk.Label(hdr, text=title, font=FONT_TITLE, bg=BG, fg=ACCENT2, anchor="w").pack(fill="x")
    tk.Label(hdr, text=subtitle, font=FONT_SUB, bg=BG, fg=FG_DIM,
             wraplength=720, justify="left", anchor="w").pack(fill="x", pady=(3, 0))

    tk.Frame(root, bg=ACCENT, height=2).pack(fill="x", padx=20, pady=(10, 0))

    toolbar = tk.Frame(root, bg=BG_PANEL, pady=6)
    toolbar.pack(fill="x", padx=20, pady=(0, 0))

    count_var = tk.StringVar()

    def _update_count():
        n = sum(v.get() for v in vars_list)
        count_var.set(f"Đã chọn: {n} / {len(options)}")

    def _select_all():
        for v in vars_list: v.set(True)
        for cell, label in cell_widgets: _set_cell_color(cell, label, True)
        _update_count()

    def _clear_all():
        for v in vars_list: v.set(False)
        for cell, label in cell_widgets: _set_cell_color(cell, label, False)
        _update_count()

    def _make_toolbar_btn(parent, text, cmd, accent=False):
        b = tk.Button(parent, text=text, command=cmd,
                    font=FONT_BTN,
                    bg=ACCENT if accent else BTN_SEC_BG,
                    fg=BTN_OK_FG if accent else BTN_SEC_FG,
                    relief="flat", bd=0, padx=14, pady=4,
                    activebackground=ACCENT2 if accent else BG_HOVER,
                    activeforeground="#ffffff",
                    cursor="hand2")
        b.pack(side="left", padx=(0, 6))
        return b

    _make_toolbar_btn(toolbar, "☑  Chọn tất cả", _select_all)
    _make_toolbar_btn(toolbar, "☐  Bỏ chọn tất cả", _clear_all)
    tk.Label(toolbar, textvariable=count_var, font=FONT_COUNT, bg=BG_PANEL, fg=FG_DIM).pack(side="right", padx=8)

    outer = tk.Frame(root, bg=BG, padx=20)
    outer.pack(fill="both", expand=True, pady=(6, 0))

    canvas = tk.Canvas(outer, bg=BG, highlightthickness=0)
    vscroll = tk.Scrollbar(outer, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=vscroll.set)

    vscroll.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)

    grid_frame = tk.Frame(canvas, bg=BG)
    canvas_window = canvas.create_window((0, 0), window=grid_frame, anchor="nw")

    def _on_frame_configure(event):
        canvas.configure(scrollregion=canvas.bbox("all"))

    def _on_canvas_configure(event):
        canvas.itemconfig(canvas_window, width=event.width)

    grid_frame.bind("<Configure>", _on_frame_configure)
    canvas.bind("<Configure>", _on_canvas_configure)

    def _on_mousewheel(event):
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
    canvas.bind_all("<MouseWheel>", _on_mousewheel)

    vars_list = []
    cell_widgets = []

    def _set_cell_color(cell_frame, lbl, checked: bool):
        color = BG_CHECKED if checked else BG_ITEM
        cell_frame.configure(bg=color)
        lbl.configure(bg=color)

    def _on_enter(cell_frame, lbl, var):
        if not var.get():
            cell_frame.configure(bg=BG_HOVER)
            lbl.configure(bg=BG_HOVER)

    def _on_leave(cell_frame, lbl, var):
        _set_cell_color(cell_frame, lbl, var.get())

    def _on_toggle(var, cell_frame, lbl):
        _set_cell_color(cell_frame, lbl, var.get())
        _update_count()

    for idx, opt in enumerate(options):
        row, col = divmod(idx, COLS)
        var = tk.BooleanVar(value=True)
        vars_list.append(var)

        cell = tk.Frame(grid_frame, bg=BG_CHECKED, padx=8, pady=6, relief="flat", bd=0)
        cell.grid(row=row, column=col, padx=4, pady=4, sticky="nsew")
        grid_frame.columnconfigure(col, weight=1)

        lbl = tk.Checkbutton(
            cell, text=opt, variable=var,
            font=FONT_ITEM, bg=BG_CHECKED, fg=FG,
            selectcolor=ACCENT,
            activebackground=BG_HOVER, activeforeground=FG,
            relief="flat", bd=0, anchor="w",
            wraplength=160,
            cursor="hand2",
        )
        lbl.configure(command=lambda v=var, c=cell, lo=lbl: _on_toggle(v, c, lo))
        lbl.pack(fill="x")

        cell.bind("<Enter>", lambda e, c=cell, lo=lbl, v=var: _on_enter(c, lo, v))
        cell.bind("<Leave>", lambda e, c=cell, lo=lbl, v=var: _on_leave(c, lo, v))
        lbl.bind("<Enter>",  lambda e, c=cell, lo=lbl, v=var: _on_enter(c, lo, v))
        lbl.bind("<Leave>",  lambda e, c=cell, lo=lbl, v=var: _on_leave(c, lo, v))

        cell_widgets.append((cell, lbl))

    _update_count()

    root.update_idletasks()
    w = min(max(820, root.winfo_reqwidth() + 40), 1200)
    h = min(max(480, root.winfo_reqheight() + 40), 800)
    root.geometry(f"{w}x{h}")

    tk.Frame(root, bg=ACCENT, height=1).pack(fill="x", padx=20, pady=(8, 0))
    footer = tk.Frame(root, bg=BG, pady=12)
    footer.pack(fill="x", padx=20)

    def _confirm():
        selected[0] = [options[i] for i, v in enumerate(vars_list) if v.get()]
        if len(selected[0]) < min_selected:
            messagebox.showwarning("Thiếu lựa chọn", f"Cần chọn ít nhất {min_selected} giá trị.")
            return
        root.quit()

    def _cancel():
        selected[0] = None
        root.quit()

    def _make_footer_btn(parent, text, cmd, accent=False):
        b = tk.Button(parent, text=text, command=cmd,
                    font=FONT_BTN,
                    bg=BTN_OK_BG if accent else BTN_SEC_BG,
                    fg=BTN_OK_FG if accent else BTN_SEC_FG,
                    relief="flat", bd=0, padx=20, pady=7,
                    activebackground=ACCENT2 if accent else BG_HOVER,
                    activeforeground="#ffffff",
                    cursor="hand2")
        b.pack(side="right", padx=(6, 0))
        return b

    _make_footer_btn(footer, f"  {confirm_text}  ✔", _confirm, accent=True)
    _make_footer_btn(footer, "  Hủy  ✘", _cancel, accent=False)

    root.protocol("WM_DELETE_WINDOW", _cancel)
    root.mainloop()
    root.destroy()
    return selected[0]

# ── 9. Main pipeline ─────────────────────────────────────────────────────────
def run_pipeline(report_item_names: list, recent_months: int = 3, selected_regions: list = None):
    a_region, d_category, f_tracking = load_lookups()
    
    # Chuẩn hóa tên vùng chọn lọc nếu có chọn lọc
    if selected_regions is not None:
        selected_regions = [clean_name(r) for r in selected_regions]

    sys_ban, store_ban_all, store_recent, sys_ton, store_ton, store_ton_size, store_ban_size, store_ban_size_recent = \
        load_data(report_item_names, d_category, recent_months)

    sheet1    = process_system_sheet(sys_ban, sys_ton, d_category, f_tracking)
    transfers = process_transfers(sheet1, store_ton, store_ton_size, store_ban_all, store_ban_size, a_region, store_recent, store_ban_size_recent, selected_regions)
    sheet3    = process_store_details(sheet1, store_ban_all, store_recent, store_ton,
                                       store_ton_size, store_ban_size, transfers, a_region, recent_months)
    sheet2    = process_size_pivot(sheet3)

    log(f"Saving → {OUTPUT_FILE}")
    # Loại bỏ các cột không mong muốn ở các sheet xuất ra Excel
    sheet1_out = sheet1.drop(columns=["Short_name", "Product_type"], errors="ignore")
    sheet3_out = sheet3.drop(columns=["Product_type"], errors="ignore")

    try:
        with pd.ExcelWriter(OUTPUT_FILE, engine="xlsxwriter") as writer:
            sheet1_out.to_excel(writer, sheet_name="Danh_Sach_Ma",      index=False)
            sheet2.to_excel(writer, sheet_name="Ti_Le_Ban_Size",    index=False)
            sheet3_out.to_excel(writer, sheet_name="Chi_Tiet_Cua_Hang", index=False)
            if transfers is not None and not transfers.empty:
                transfers.to_excel(writer, sheet_name="Lenh_Dieu_Chuyen", index=False)
    except PermissionError:
        fallback_file = OUTPUT_FILE.parent / f"{OUTPUT_FILE.stem}_LOCKED{OUTPUT_FILE.suffix}"
        log(f"WARNING: File {OUTPUT_FILE.name} is currently open in Excel and locked! Saving to fallback file instead: {fallback_file}")
        with pd.ExcelWriter(fallback_file, engine="xlsxwriter") as writer:
            sheet1_out.to_excel(writer, sheet_name="Danh_Sach_Ma",      index=False)
            sheet2.to_excel(writer, sheet_name="Ti_Le_Ban_Size",    index=False)
            sheet3_out.to_excel(writer, sheet_name="Chi_Tiet_Cua_Hang", index=False)
            if transfers is not None and not transfers.empty:
                transfers.to_excel(writer, sheet_name="Lenh_Dieu_Chuyen", index=False)
    log("Done!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build Reallocation Database")
    parser.add_argument("--report_item", required=False, help="Tên mặt hàng (Report_item_name)")
    parser.add_argument("--items", required=False, help="Danh sách mặt hàng, cách nhau bằng dấu phẩy")
    parser.add_argument("--months", type=int, default=3, help="Số tháng gần nhất")
    parser.add_argument("--regions", required=False, help="Danh sách khu vực, cách nhau bằng dấu phẩy")
    args = parser.parse_args()

    # Nếu được gọi qua CLI từ webapp hoặc dòng lệnh với các đối số này
    if args.report_item or args.items:
        selected_items = [i.strip() for i in args.items.split(",")] if args.items else []
        if args.report_item and args.report_item not in selected_items:
            selected_items.append(args.report_item)
            
        selected_regions = [r.strip() for r in args.regions.split(",")] if args.regions else None
        months = args.months
        
        log(f"CLI Run: Items={selected_items}, Months={months}, Regions={selected_regions}")
        run_pipeline(selected_items, recent_months=months, selected_regions=selected_regions)
    else:
        # Launch beautiful Tkinter dialogs to let the user select everything like the old code!
        log("No command line argument --report_item provided. Launching UI dialogs...")
        a_region, d_category, f_tracking = load_lookups()
        
        # 1. Chọn Khu vực (đầu tiên)
        options_regions = ["Hà Nội", "Miền Tây", "Miền Trung - TN", "TP. HCM", "Miền Đông"]
        selected_regions = choose_multi_options(
            "Chọn khu vực", "Chọn một hoặc nhiều khu vực cần lọc dữ liệu",
            options_regions, "Tiếp tục"
        )
        if not selected_regions:
            log("Region selection cancelled. Exiting.")
            sys.exit(0)
            
        # 2. Chọn số tháng gần nhất
        months = choose_period_months()
        if months is None:
            log("Month selection cancelled. Exiting.")
            sys.exit(0)

        # 3. Chọn Nhóm báo cáo (Group_Report)
        options_groups = list(d_category["Group_Report"].dropna().unique())
        selected_groups = choose_multi_options(
            "Chọn nhóm báo cáo", "Chọn một hoặc nhiều nhóm báo cáo để lọc mặt hàng",
            options_groups, "Tiếp tục"
        )
        if not selected_groups:
            log("Group Report selection cancelled. Exiting.")
            sys.exit(0)

        # 4. Chọn Tên mặt hàng (Report_item_name - lọc tự động theo Group_Report đã chọn)
        filtered_cats = d_category[d_category["Group_Report"].isin(selected_groups)]
        options_items = list(filtered_cats["Report_item_name"].dropna().unique())
        selected_items = choose_multi_options(
            "Chọn mặt hàng báo cáo", "Chọn một hoặc nhiều mặt hàng cần phân tích",
            options_items, "Hoàn tất"
        )
        if not selected_items:
            log("Report item selection cancelled. Exiting.")
            sys.exit(0)

        log(f"UI Selection Completed: Regions={selected_regions}, Months={months}, Groups={selected_groups}, Items={selected_items}")
        run_pipeline(selected_items, recent_months=months, selected_regions=selected_regions)

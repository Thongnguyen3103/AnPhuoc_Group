# -*- coding: utf-8 -*-
"""
dc_data.py
Truy vấn DuckDB, ráp dữ liệu theo key Combined_PK
Combined_PK = MaHang || Operation
"""
import re
import duckdb
import pandas as pd
import dc_config as cfg

# ─────────────────────────────────────────────
# DATABASE — Kết nối & truy vấn
# ─────────────────────────────────────────────


def connect(db_path):
    return duckdb.connect(db_path, read_only=True)


def load_scope_stores(con, selected_regions=None, excluded_stores=None):
    """Danh sách CH trong phạm vi luân chuyển (Mục 1), sau khi người vận hành
    chọn vùng tham gia và loại bỏ thủ công một số CH."""
    df = con.execute("SELECT * FROM A_Region").fetchdf()
    df = df[df["Store_rank"].isin(cfg.VALID_STORE_RANKS)]
    df = df[df["Region"].isin(cfg.VALID_STORE_REGIONS)]
    if selected_regions:
        df = df[df["Region"].isin(selected_regions)]
    if excluded_stores:
        df = df[~df["Store_name"].isin(excluded_stores)]
    df = df.rename(columns={"Store_rank": "Loai_CH", "Địa chỉ": "Dia_chi"})
    return df[["Store_name", "Region", "Warehouse", "Loai_CH", "Dia_chi"]].drop_duplicates("Store_name")


def load_geo_csv(path):
    """Đọc ViTri_DiaLy_CuaHang.csv (tạo bởi generate_geo.py, người dùng có thể đã sửa tay)."""
    import os
    if not path or not os.path.exists(path):
        return None
    df = pd.read_csv(path, encoding="utf-8-sig")
    keep = [c for c in ["Store_name", "Lat", "Lon"] if c in df.columns]
    return df[keep].drop_duplicates("Store_name")


def load_inventory_all_regions(con, combined_pks):
    """Tồn theo TẤT CẢ vị trí (không lọc theo phạm vi CH đợt này) — dùng để tách
    'Tồn HTCH' (đúng 5 vùng kinh doanh, loại CLOSE) và 'Tồn Các Kho' (kho nội bộ,
    event, thanh lý...)."""
    ph = ",".join(["?"] * len(combined_pks))
    q = f"""
        SELECT Store_name, Region, (Mahang || Operation) AS Combined_PK, Qty_TonKho
        FROM Inventory
        WHERE (Mahang || Operation) IN ({ph})
    """
    df = con.execute(q, combined_pks).fetchdf()
    df["Qty_TonKho"] = df["Qty_TonKho"].fillna(0)
    df["La_HTCH"] = df["Region"].isin(cfg.VALID_STORE_REGIONS)
    return df


def load_store_avg_monthly_sales_all_sku(con, store_names, eval_months):
    """Bán bình quân tháng TOÀN CH (mọi mã hàng, không riêng danh sách đang chạy)
    trong kỳ đánh giá — dùng đúng công thức Định mức tồn Mục 7.1."""
    years = sorted(set(y for y, m in eval_months))
    ph_year = ",".join(["?"] * len(years))
    q = f"""SELECT Store_name, Year, Month, Qty_Ban FROM System_sales
        WHERE Year IN ({ph_year}) AND "Nội dung" = 'Bán'"""
    df = con.execute(q, years).fetchdf()
    df = df[df.apply(lambda r: (int(r["Year"]), int(r["Month"])) in eval_months, axis=1)]
    if store_names is not None:
        df = df[df["Store_name"].isin(store_names)]
    g = df.groupby("Store_name")["Qty_Ban"].sum() / len(eval_months)
    return g.to_dict()


def load_store_total_inventory_all_sku(con, store_names):
    """Tổng tồn hiện tại toàn CH (mọi mã hàng) — dùng cho Hạn mức nhận Mục 7.2."""
    q = "SELECT Store_name, Qty_TonKho FROM Inventory"
    df = con.execute(q).fetchdf()
    if store_names is not None:
        df = df[df["Store_name"].isin(store_names)]
    return df.groupby("Store_name")["Qty_TonKho"].sum().to_dict()


def load_sku_master(con, combined_pks):
    """Thuộc tính mã hàng từ F_DataTracking + phân loại Product_group từ D_Category (nếu khớp System_item_name)."""
    ph = ",".join(["?"] * len(combined_pks))
    q = f"""
        SELECT Combined_PK, Brand, System_item_name, Operation, Color_code, item_code,
               Composition, Color_tone, Color_group, Form, Style, Attribute, Description,
               Price, Dist_plan, Sub_Brand
        FROM F_DataTracking
        WHERE Combined_PK IN ({ph})
    """
    df = con.execute(q, combined_pks).fetchdf()
    # Gắn Product_type / Product_group / Group_Report từ D_Category theo System_item_name (đại diện, không theo màu)
    cat = con.execute("SELECT DISTINCT System_item_name, Product_type, Gender, Product_group, Group_Report, Report_item_name FROM D_Category").fetchdf()
    cat = cat.drop_duplicates("System_item_name")
    df = df.merge(cat, on="System_item_name", how="left")
    return df


def load_inventory_size(con, combined_pks, store_names):
    """Tồn hiện tại theo size, theo CH (InventorySize), lọc theo CH trong phạm vi."""
    ph = ",".join(["?"] * len(combined_pks))
    q = f"""
        SELECT Store_name, Region, Warehouse, (Mahang || Operation) AS Combined_PK,
               Mahang, Operation, Size, Qty_TonKho
        FROM InventorySize
        WHERE (Mahang || Operation) IN ({ph})
    """
    df = con.execute(q, combined_pks).fetchdf()
    if store_names is not None:
        df = df[df["Store_name"].isin(store_names)]
    df["Qty_TonKho"] = df["Qty_TonKho"].fillna(0)
    return df


def load_sales(con, combined_pks, store_names):
    """Bán theo tháng, theo size, theo CH — từ System_sales (nguồn bán đầy đủ nhất)."""
    ph = ",".join(["?"] * len(combined_pks))
    q = f"""
        SELECT Store_name, Region, Warehouse, (MaHang || Operation) AS Combined_PK,
               MaHang, Operation, Size, Year, Month, Qty_Ban
        FROM System_sales
        WHERE (MaHang || Operation) IN ({ph}) AND "Nội dung" = 'Bán'
    """
    df = con.execute(q, combined_pks).fetchdf()
    if store_names is not None:
        df = df[df["Store_name"].isin(store_names)]
    df["Qty_Ban"] = df["Qty_Ban"].fillna(0)
    return df


def load_nhap_tu_sx(con, combined_pks, store_names):
    """Phân phối lần đầu / hàng đang chuyển đến — dùng để suy ra 'nhận lũy kế' theo CH."""
    ph = ",".join(["?"] * len(combined_pks))
    q = f"""
        SELECT Store_name, Region, Warehouse, (MaHang || Operation) AS Combined_PK,
               MaHang, Operation, Size, Year, Month, SoLuong, LyDo
        FROM NhapTuSX
        WHERE (MaHang || Operation) IN ({ph})
    """
    df = con.execute(q, combined_pks).fetchdf()
    if store_names is not None:
        df = df[df["Store_name"].isin(store_names)]
    df["SoLuong"] = df["SoLuong"].fillna(0)
    return df


def load_size_order(con, system_item_names):
    """Lấy thứ tự size (số hoặc chữ) cho từng System_item_name để xét liền kề (Mục 6.2)."""
    numeric = con.execute("SELECT * FROM C_BasicSizeChart").fetchdf()
    numeric = numeric[numeric["System_item_name"].isin(system_item_names)]
    order_map = {}
    for _, r in numeric.iterrows():
        seq = []
        for i in range(1, 12):
            v = r.get(f"Size_{i}")
            if pd.notna(v) and str(v).strip() != "":
                seq.append(str(v).strip().replace(".0", ""))
        if seq:
            order_map[r["System_item_name"]] = seq
    return order_map


def parse_dist_plan(dist_plan):
    """'T02.2026' -> (2026, 2). Trả về None nếu không parse được (vd 'Chưa PP')."""
    if not isinstance(dist_plan, str):
        return None
    m = re.match(r"T?(\d{1,2})\.(\d{4})", dist_plan.strip())
    if not m:
        return None
    return int(m.group(2)), int(m.group(1))


def months_between(y1, m1, y2, m2):
    return (y2 - y1) * 12 + (m2 - m1)

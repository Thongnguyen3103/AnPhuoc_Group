# -*- coding: utf-8 -*-
"""TransferDataLoader — Đọc dữ liệu trực tiếp từ file Parquet (02.Master, 03.Data_Parquest).
Không dùng file .duckdb: DuckDB chỉ chạy trong RAM, mỗi bảng (A_Region, System_sales...) là 1 VIEW
trỏ thẳng vào file parquet (xem 00.Shared/Read_Write_Parquet.py)."""
import re
import pandas as pd
from Config import Config_Parameters as cfg
from Config import Paths_Transfer as paths  # noqa: F401  (đưa 00.Shared vào sys.path)
import Read_Write_Parquet

TABLES = ["A_Region", "Inventory", "InventorySize", "System_sales", "F_DataTracking",
          "D_Category", "C_BasicSizeChart", "NhapTuSX"]


class TransferDataLoader:
    """Đọc dữ liệu từ Parquet. data_root: gốc kho dữ liệu (00.Data_AnPhuoc_Group) — None = theo
    00.Shared/Config_Paths.yaml. Giữ 1 kết nối DuckDB trong RAM cho cả phiên chạy."""

    def __init__(self, data_root=None):
        self.data_root = data_root
        self.con = Read_Write_Parquet.connect_parquet_views(TABLES, data_root)

    def close(self):
        self.con.close()

    def load_scope_stores(self, selected_regions=None, excluded_stores=None):
        """Danh sách CH trong phạm vi luân chuyển (Mục 1), sau khi người vận hành
        chọn vùng tham gia và loại bỏ thủ công một số CH."""
        df = self.con.execute("SELECT * FROM A_Region").fetchdf()
        df = df[df["Store_rank"].isin(cfg.VALID_STORE_RANKS)]
        df = df[df["Region"].isin(cfg.VALID_STORE_REGIONS)]
        if selected_regions:
            df = df[df["Region"].isin(selected_regions)]
        if excluded_stores:
            df = df[~df["Store_name"].isin(excluded_stores)]
        df = df.rename(columns={"Store_rank": "Loai_CH", "Địa chỉ": "Dia_chi"})
        return df[["Store_name", "Region", "Warehouse", "Loai_CH", "Dia_chi"]].drop_duplicates("Store_name")

    @staticmethod
    def load_geo_csv(path):
        """Đọc ViTri_DiaLy_CuaHang.csv (tạo bởi Generate_Store_Coordinates.py, người dùng có thể đã sửa tay)."""
        import os
        if not path or not os.path.exists(path):
            return None
        df = pd.read_csv(path, encoding="utf-8-sig")
        keep = [c for c in ["Store_name", "Lat", "Lon"] if c in df.columns]
        return df[keep].drop_duplicates("Store_name")

    def load_inventory_all_regions(self, combined_pks):
        """Tồn theo TẤT CẢ vị trí (không lọc theo phạm vi CH đợt này) — dùng để tách
        'Tồn HTCH' (đúng 5 vùng kinh doanh, loại CLOSE) và 'Tồn Các Kho' (kho nội bộ,
        event, thanh lý...)."""
        ph = ",".join(["?"] * len(combined_pks))
        q = f"""
            SELECT Store_name, Region, (Mahang || Operation) AS Combined_PK, Qty_TonKho
            FROM Inventory
            WHERE (Mahang || Operation) IN ({ph})
        """
        df = self.con.execute(q, combined_pks).fetchdf()
        df["Qty_TonKho"] = df["Qty_TonKho"].fillna(0)
        df["La_HTCH"] = df["Region"].isin(cfg.VALID_STORE_REGIONS)
        return df

    def load_store_avg_monthly_sales_all_sku(self, store_names, eval_months):
        """Bán bình quân tháng TOÀN CH (mọi mã hàng, không riêng danh sách đang chạy)
        trong kỳ đánh giá — dùng đúng công thức Định mức tồn Mục 7.1."""
        years = sorted(set(y for y, m in eval_months))
        ph_year = ",".join(["?"] * len(years))
        q = f"""SELECT Store_name, Year, Month, Qty_Ban FROM System_sales
            WHERE Year IN ({ph_year}) AND "Nội dung" = 'Bán'"""
        df = self.con.execute(q, years).fetchdf()
        df = df[df.apply(lambda r: (int(r["Year"]), int(r["Month"])) in eval_months, axis=1)]
        if store_names is not None:
            df = df[df["Store_name"].isin(store_names)]
        g = df.groupby("Store_name")["Qty_Ban"].sum() / len(eval_months)
        return g.to_dict()

    def load_store_group_sales(self, store_names, eval_months):
        """Bán theo CH × (Group_Report, Color_group, Form, Style) trong eval_months, MỌI mã —
        dùng cho hạn mức nhận theo nhóm hàng (Mục 8). Trả về tổng SL bán (chưa chia tháng)."""
        years = sorted(set(y for y, m in eval_months))
        ph_year = ",".join(["?"] * len(years))
        q = f"""
            WITH ft AS (
                SELECT f.Combined_PK, c.Group_Report, f.Color_group, f.Form, f.Style
                FROM F_DataTracking f
                LEFT JOIN (SELECT DISTINCT ON (System_item_name) System_item_name, Group_Report FROM D_Category) c
                       USING (System_item_name))
            SELECT s.Store_name, s.Year, s.Month, ft.Group_Report, ft.Color_group, ft.Form, ft.Style,
                   SUM(s.Qty_Ban) AS Qty_Ban
            FROM System_sales s JOIN ft ON ft.Combined_PK = (s.MaHang || s.Operation)
            WHERE s.Year IN ({ph_year}) AND s."Nội dung" = 'Bán'
            GROUP BY ALL"""
        df = self.con.execute(q, years).fetchdf()
        months = set(eval_months)
        df = df[[(int(y), int(m)) in months for y, m in zip(df["Year"], df["Month"])]]
        if store_names is not None:
            df = df[df["Store_name"].isin(store_names)]
        return df

    def load_store_group_inventory(self, store_names, status="Nguyên giá"):
        """Tồn hiện tại theo CH × (Brand, Group_Report, Color_group, Form, Style), MỌI mã có
        Status = status — dòng 'tồn toàn CH (nguyên giá)' ở Sheet 8."""
        q = """
            WITH ft AS (
                SELECT f.Combined_PK, f.Brand, f.System_item_name, c.Report_item_name, c.Group_Report,
                       f.Color_group, f.Form, f.Style
                FROM F_DataTracking f
                LEFT JOIN (SELECT DISTINCT ON (System_item_name) System_item_name, Report_item_name, Group_Report
                           FROM D_Category) c USING (System_item_name))
            SELECT i.Store_name, ft.Brand, COALESCE(ft.Report_item_name, ft.System_item_name) AS Report_item_name,
                   ft.Group_Report, ft.Color_group, ft.Form, ft.Style,
                   SUM(i.Qty_TonKho) AS Qty_TonKho
            FROM Inventory i JOIN ft ON ft.Combined_PK = (i.Mahang || i.Operation)
            WHERE i.Status = ?
            GROUP BY ALL"""
        df = self.con.execute(q, [status]).fetchdf()
        if store_names is not None:
            df = df[df["Store_name"].isin(store_names)]
        return df

    def load_store_total_inventory_all_sku(self, store_names):
        """Tổng tồn hiện tại toàn CH (mọi mã hàng) — dùng cho Hạn mức nhận Mục 7.2."""
        q = "SELECT Store_name, Qty_TonKho FROM Inventory"
        df = self.con.execute(q).fetchdf()
        if store_names is not None:
            df = df[df["Store_name"].isin(store_names)]
        return df.groupby("Store_name")["Qty_TonKho"].sum().to_dict()

    def load_sku_master(self, combined_pks):
        """Thuộc tính mã hàng từ F_DataTracking + phân loại Product_group từ D_Category (nếu khớp System_item_name)."""
        ph = ",".join(["?"] * len(combined_pks))
        q = f"""
            SELECT Combined_PK, Brand, System_item_name, Operation, Color_code, item_code,
                   Composition, Color_tone, Color_group, Form, Style, Attribute, Description,
                   Price, Dist_plan, Sub_Brand
            FROM F_DataTracking
            WHERE Combined_PK IN ({ph})
        """
        df = self.con.execute(q, combined_pks).fetchdf()
        # Gắn Product_type / Product_group / Group_Report từ D_Category theo System_item_name (đại diện, không theo màu)
        cat = self.con.execute("SELECT DISTINCT System_item_name, Product_type, Gender, Product_group, Group_Report, Report_item_name FROM D_Category").fetchdf()
        cat = cat.drop_duplicates("System_item_name")
        df = df.merge(cat, on="System_item_name", how="left")
        return df

    def load_inventory_size(self, combined_pks, store_names):
        """Tồn hiện tại theo size, theo CH (InventorySize), lọc theo CH trong phạm vi."""
        ph = ",".join(["?"] * len(combined_pks))
        q = f"""
            SELECT Store_name, Region, Warehouse, (Mahang || Operation) AS Combined_PK,
                   Mahang, Operation, Size, Qty_TonKho
            FROM InventorySize
            WHERE (Mahang || Operation) IN ({ph})
        """
        df = self.con.execute(q, combined_pks).fetchdf()
        if store_names is not None:
            df = df[df["Store_name"].isin(store_names)]
        df["Qty_TonKho"] = df["Qty_TonKho"].fillna(0)
        return df

    def load_sales(self, combined_pks, store_names):
        """Bán theo tháng, theo size, theo CH — từ System_sales (nguồn bán đầy đủ nhất)."""
        ph = ",".join(["?"] * len(combined_pks))
        q = f"""
            SELECT Store_name, Region, Warehouse, (MaHang || Operation) AS Combined_PK,
                   MaHang, Operation, Size, Year, Month, Qty_Ban
            FROM System_sales
            WHERE (MaHang || Operation) IN ({ph}) AND "Nội dung" = 'Bán'
        """
        df = self.con.execute(q, combined_pks).fetchdf()
        if store_names is not None:
            df = df[df["Store_name"].isin(store_names)]
        df["Qty_Ban"] = df["Qty_Ban"].fillna(0)
        return df

    def load_nhap_tu_sx(self, combined_pks, store_names):
        """Phân phối lần đầu / hàng đang chuyển đến — dùng để suy ra 'nhận lũy kế' theo CH."""
        ph = ",".join(["?"] * len(combined_pks))
        q = f"""
            SELECT Store_name, Region, Warehouse, (MaHang || Operation) AS Combined_PK,
                   MaHang, Operation, Size, Year, Month, SoLuong, LyDo
            FROM NhapTuSX
            WHERE (MaHang || Operation) IN ({ph})
        """
        df = self.con.execute(q, combined_pks).fetchdf()
        if store_names is not None:
            df = df[df["Store_name"].isin(store_names)]
        df["SoLuong"] = df["SoLuong"].fillna(0)
        return df

    def load_size_order(self, system_item_names):
        """Lấy thứ tự size (số hoặc chữ) cho từng System_item_name để xét liền kề (Mục 6.2)."""
        numeric = self.con.execute("SELECT * FROM C_BasicSizeChart").fetchdf()
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

    @staticmethod
    def parse_dist_plan(dist_plan):
        """'T02.2026' -> (2026, 2). Trả về None nếu không parse được (vd 'Chưa PP')."""
        if not isinstance(dist_plan, str):
            return None
        m = re.match(r"T?(\d{1,2})\.(\d{4})", dist_plan.strip())
        if not m:
            return None
        return int(m.group(2)), int(m.group(1))

    @staticmethod
    def months_between(y1, m1, y2, m2):
        return (y2 - y1) * 12 + (m2 - m1)

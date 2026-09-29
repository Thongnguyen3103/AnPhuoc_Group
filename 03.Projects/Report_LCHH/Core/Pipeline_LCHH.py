# -*- coding: utf-8 -*-
"""
====================================================================
 LCHHPipeline - XAY DUNG DATABASE BAO CAO LENH DIEU CHUYEN HANG HOA
====================================================================
Nguon:
  07.Lenh_HHLC   -> LENH dieu chuyen (CHUAN - moi dong 1 yeu cau chuyen)
  08.History_LC  -> Lich su dieu chuyen DA THUC HIEN (CH -> CH), co trang thai nhap kho
  09.TraKho      -> Cua hang TRA HANG VE KHO

Key doi chieu 1 lenh:  Store_from + Store_to + MaHang + Operation + Size
Quy tac thoi gian   :  chi tinh moc History/TraKho co ym >= ym cua lenh
                       (ym = Year*12 + Month)

Tra kho (theo yeu cau nghiep vu):
  Cua hang NHAN hang (Store_to) sau khi da NHAP KHO CH lai dem tra ve kho.
  -> khop TraKho.Store_name = Lenh.Store_to  +  MaHang/Operation/Size
  -> chi co y nghia khi lenh do da thuc nhap (Qty_DaNhapKho > 0)
"""
from __future__ import annotations

import hashlib
import os

import pandas as pd

from Common_Utils import join_unique, key_norm, mode_or_first, read_many, store_norm, ym_of

SKU = ["MaHang_k", "Operation_k", "Size_k"]          # khoa san pham da chuan hoa
ROUTE = ["Store_from_k", "Store_to_k"] + SKU         # khoa 1 lenh da chuan hoa


class LCHHPipeline:
    """Doc + doi chieu du lieu luan chuyen hang hoa cho 1 hoac nhieu ky bao cao.

    Su dung:
        pipeline = LCHHPipeline(cfg)
        result = pipeline.run(periods)   # periods: [(year, month), ...]
        pipeline.save(result)
    """

    def __init__(self, cfg):
        self.cfg = cfg
        self.alias = cfg.store_alias
        self.lenh = self.hist = self.trakho = None
        self.dim_store = self.dim_product = None

    # ------------------------------------------------------------------
    # 1. Doc du lieu
    # ------------------------------------------------------------------
    def extract(self):
        print("[1] Doc du lieu nguon ...")
        lenh = read_many(self.cfg.paths["lenh"])
        lenh["ym"] = ym_of(lenh["Year"], lenh["Month"])

        hist = read_many(self.cfg.paths["history"])
        hist["ym"] = ym_of(hist["Year"], hist["Month"])

        trakho = read_many(self.cfg.paths["trakho"])
        trakho["ym"] = ym_of(trakho["Year"], trakho["Month"])

        self.lenh, self.hist, self.trakho = lenh, hist, trakho
        return lenh, hist, trakho

    # ------------------------------------------------------------------
    # 2. Chuan hoa -> staging
    # ------------------------------------------------------------------
    def clean(self):
        print("[2] Chuan hoa khoa doi chieu ...")
        lenh, hist, trakho, alias = self.lenh, self.hist, self.trakho, self.alias

        for df in (lenh, hist, trakho):
            df["MaHang_k"] = key_norm(df["MaHang"])
            df["Operation_k"] = key_norm(df["Operation"])
            df["Size_k"] = key_norm(df["Size"])

        lenh["Store_from_k"] = store_norm(lenh["Store_from"], alias)
        lenh["Store_to_k"] = store_norm(lenh["Store_to"], alias)
        hist["Store_from_k"] = store_norm(hist["Store_from"], alias)
        hist["Store_to_k"] = store_norm(hist["Store_to"], alias)
        trakho["Store_name_k"] = store_norm(trakho["Store_name"], alias)

        n_dup = lenh.duplicated().sum()
        lenh = lenh.drop_duplicates().copy()
        print(f"   - Lenh: bo {n_dup} dong trung lap hoan toan -> con {len(lenh):,}")

        self.lenh = lenh
        return lenh, hist, trakho

    # ------------------------------------------------------------------
    # 3. Dimension
    # ------------------------------------------------------------------
    def build_dims(self):
        print("[3] Dung dim_store (tu A_Region), dim_product ...")
        hist, trakho, alias = self.hist, self.trakho, self.alias

        reg = pd.read_parquet(self.cfg.paths["region"])
        reg["store_key"] = store_norm(reg["Store_name"], alias)
        reg = reg.drop_duplicates("store_key")
        dim_store = (reg[["store_key", "Store_name", "Region", "Warehouse"]]
                     .rename(columns={"Store_name": "store_std"})
                     .reset_index(drop=True))

        pcols = ["MaHang", "MaHang_k", "Report_item_name", "Brand", "Product_type",
                 "Gender", "Product_group", "Group_Report"]
        prod = pd.concat([hist[pcols], trakho[pcols]], ignore_index=True)
        dim_product = (prod.groupby("MaHang_k")
                       .agg(MaHang=("MaHang", mode_or_first),
                            Report_item_name=("Report_item_name", mode_or_first),
                            Brand=("Brand", mode_or_first),
                            Product_type=("Product_type", mode_or_first),
                            Gender=("Gender", mode_or_first),
                            Product_group=("Product_group", mode_or_first),
                            Group_Report=("Group_Report", mode_or_first))
                       .reset_index())

        print(f"   - dim_store   : {len(dim_store):,} cua hang")
        print(f"   - dim_product : {len(dim_product):,} ma hang")
        self.dim_store, self.dim_product = dim_store, dim_product
        return dim_store, dim_product

    # ------------------------------------------------------------------
    # 4. Gom lenh ve grain (1 dong / 1 lenh)
    # ------------------------------------------------------------------
    @staticmethod
    def aggregate_lenh(lenh: pd.DataFrame) -> pd.DataFrame:
        print("[4] Gom lenh ve grain Store_from+Store_to+MaHang+Operation+Size ...")

        g = (lenh.groupby(ROUTE, as_index=False)
             .agg(Store_from=("Store_from", "first"),
                  Store_to=("Store_to", "first"),
                  MaHang=("MaHang", "first"),
                  Operation=("Operation", "first"),
                  Size=("Size", "first"),
                  Report_item_name=("Report_item_name", "first"),
                  NgayChungTu_min=("NgayChungTu", "min"),
                  Year=("Year", "first"),
                  Month=("Month", "first"),
                  Quarter=("Quarter", "first"),
                  ym=("ym", "min"),
                  Qty_Lenh=("Qty_Chuyen", "sum"),
                  so_dong_lenh=("Qty_Chuyen", "size"),
                  ly_do=("Note", join_unique)))

        g["lenh_id"] = [
            "L" + hashlib.md5("||".join(map(str, r)).encode("utf-8")).hexdigest()[:10]
            for r in g[ROUTE].itertuples(index=False, name=None)
        ]
        cols = ["lenh_id"] + [c for c in g.columns if c != "lenh_id"]
        g = g[cols]
        print(f"   -> {len(g):,} lenh (grain)")
        return g

    # ------------------------------------------------------------------
    # 5. Doi chieu History (da dieu chuyen / da nhap kho / dang di duong)
    # ------------------------------------------------------------------
    @staticmethod
    def match_history(fact: pd.DataFrame, hist: pd.DataFrame):
        print("[5] Doi chieu History_LC ...")

        h = hist.merge(fact[["lenh_id"] + ROUTE + ["ym"]].rename(columns={"ym": "ym_lenh"}),
                       on=ROUTE, how="inner")
        h = h[h["ym"] >= h["ym_lenh"]].copy()          # quy tac thoi gian

        is_nhap = h["TrangThaiNhap"].astype("string").str.contains("nhập kho", case=False, na=False)
        is_didg = h["TrangThaiNhap"].astype("string").str.contains("đi đường", case=False, na=False)
        h["_q_nhap"] = h["Qty_Chuyen"].where(is_nhap, 0)
        h["_q_didg"] = h["Qty_Chuyen"].where(is_didg, 0)
        h["_dt_nhap"] = h["NgayChungTu"].where(is_nhap)   # ngay nhap kho CH (de xet dung han)

        agg = (h.groupby("lenh_id")
               .agg(Qty_DaChuyen=("Qty_Chuyen", "sum"),
                    Qty_DaNhapKho=("_q_nhap", "sum"),
                    Qty_DiDuong=("_q_didg", "sum"),
                    _ngay_hist_min=("NgayChungTu", "min"),
                    _ngay_nhap_min=("_dt_nhap", "min"),
                    so_dong_history=("Qty_Chuyen", "size"),
                    Status_list=("Status", join_unique),
                    TrangThaiNhap_list=("TrangThaiNhap", join_unique),
                    Region_from=("Region_from", mode_or_first),
                    Warehouse_from=("Warehouse_from", mode_or_first),
                    Region_to=("Region_to", mode_or_first),
                    Warehouse_to=("Warehouse_to", mode_or_first))
               .reset_index())

        fact = fact.merge(agg, on="lenh_id", how="left")
        for c in ["Qty_DaChuyen", "Qty_DaNhapKho", "Qty_DiDuong", "so_dong_history"]:
            fact[c] = fact[c].fillna(0).astype("int64")
        fact["khop_history"] = fact["so_dong_history"] > 0

        br = h[["lenh_id", "Store_from", "Store_to", "MaHang", "Operation", "Size",
                "Qty_Chuyen", "Status", "TrangThaiNhap", "Region_from", "Region_to",
                "Year", "Month", "__src_file"]].copy()

        print(f"   - lenh khop History : {int(fact['khop_history'].sum()):,} / {len(fact):,} "
              f"({fact['khop_history'].mean()*100:.1f}%)")
        print(f"   - lenh da nhap kho  : {int((fact['Qty_DaNhapKho'] > 0).sum()):,}")
        print(f"   - lenh dang di duong: {int((fact['Qty_DiDuong'] > 0).sum()):,}")
        return fact, br

    # ------------------------------------------------------------------
    # 6. Doi chieu TraKho (CH NHAN tra hang ve kho sau khi da nhap)
    # ------------------------------------------------------------------
    @staticmethod
    def match_trakho(fact: pd.DataFrame, trakho: pd.DataFrame):
        print("[6] Doi chieu TraKho (theo cua hang NHAN = Store_to) ...")

        t = trakho.merge(
            fact[["lenh_id", "Store_to_k", "ym"]].rename(columns={"ym": "ym_lenh"})
            .merge(fact[["lenh_id"] + SKU], on="lenh_id"),
            left_on=["Store_name_k"] + SKU, right_on=["Store_to_k"] + SKU, how="inner")
        t = t[t["ym"] >= t["ym_lenh"]].copy()
        # Cau truc TraKho moi: moi dong = 1 lan tra kho THUC (cot TrangThai da bo)

        agg = (t.groupby("lenh_id")
               .agg(Qty_TraKho=("Qty_Tra", "sum"),
                    so_dong_trakho=("Qty_Tra", "size"),
                    Kho_Nhan_list=("Kho_Nhan", join_unique))
               .reset_index())

        fact = fact.merge(agg, on="lenh_id", how="left")
        for c in ["Qty_TraKho", "so_dong_trakho"]:
            fact[c] = fact[c].fillna(0).astype("int64")

        fact["co_tra_kho_sau_nhan"] = (fact["Qty_TraKho"] > 0) & (fact["Qty_DaNhapKho"] > 0)
        _vuot = (fact["Qty_TraKho"] - fact["Qty_DaNhapKho"]).clip(lower=0)
        fact["Qty_TraKho_vuot_nhan"] = _vuot.where(fact["Qty_DaNhapKho"] > 0, 0).astype("int64")

        br = t[["lenh_id", "Store_name", "MaHang", "Operation", "Size", "Qty_Tra",
                "Kho_Nhan", "Region", "Year", "Month", "__src_file"]].copy()

        print(f"   - lenh co tra kho (sau khi nhap): "
              f"{int(fact['co_tra_kho_sau_nhan'].sum()):,}")
        print(f"   - lenh tra kho VUOT so nhan (tra ca ton CH): "
              f"{int((fact['Qty_TraKho_vuot_nhan'] > 0).sum()):,}")
        return fact, br

    # ------------------------------------------------------------------
    # 6b. Chuyen di tiep: CH NHAN (Store_to) chuyen SKU do di CH khac
    #     Khop CHAT theo dung khoa cua lenh: MaHang + Operation + Size.
    # ------------------------------------------------------------------
    @staticmethod
    def match_chuyen_di_tiep(fact: pd.DataFrame, hist: pd.DataFrame) -> pd.DataFrame:
        print("[6b] Doi chieu chuyen di tiep (CH nhan chuyen SKU di noi khac) ...")

        key = fact[["lenh_id", "Store_to_k", "ym"] + SKU].rename(
            columns={"ym": "ym_lenh", "Store_to_k": "_ch_nhan_k"})
        h = hist.merge(key, left_on=["Store_from_k"] + SKU,
                       right_on=["_ch_nhan_k"] + SKU, how="inner")
        h = h[h["ym"] >= h["ym_lenh"]].copy()
        h = h[h["Store_from_k"] != h["Store_to_k"]]

        agg = (h.groupby("lenh_id")
               .agg(Qty_ChuyenDiTiep=("Qty_Chuyen", "sum"),
                    so_dong_chuyen_tiep=("Qty_Chuyen", "size"),
                    ChuyenDiTiep_toi=("Store_to", join_unique))
               .reset_index())

        fact = fact.merge(agg, on="lenh_id", how="left")
        fact["Qty_ChuyenDiTiep"] = fact["Qty_ChuyenDiTiep"].fillna(0).astype("int64")
        fact["so_dong_chuyen_tiep"] = fact["so_dong_chuyen_tiep"].fillna(0).astype("int64")
        fact["ChuyenDiTiep_toi"] = fact["ChuyenDiTiep_toi"].fillna("")

        print(f"   - lenh co chuyen di tiep: {int((fact['Qty_ChuyenDiTiep'] > 0).sum()):,} "
              f"(tong SL {int(fact['Qty_ChuyenDiTiep'].sum()):,})")
        return fact

    # ------------------------------------------------------------------
    # 7. Suy ra trang thai thuc hien
    # ------------------------------------------------------------------
    @staticmethod
    def derive_status(fact: pd.DataFrame, cho_thuc_hien_ngay: int = 10) -> pd.DataFrame:
        print("[7] Suy ra trang_thai_thuc_hien ...")
        today = pd.Timestamp.today().normalize()

        def status(r):
            chua_qua_han_cho = today <= r["NgayChungTu_min"] + pd.Timedelta(days=cho_thuc_hien_ngay)
            if (not r["khop_history"]) and r["Qty_TraKho"] == 0:
                return "Đang chờ thực hiện" if chua_qua_han_cho else "Chưa thực hiện"
            if r["Qty_DaNhapKho"] > 0 and r["Qty_TraKho"] > 0:
                return "Nhận rồi trả kho" if r["Qty_TraKho"] >= r["Qty_DaNhapKho"] \
                    else "Nhận rồi trả kho một phần"
            if r["Qty_DaNhapKho"] >= r["Qty_Lenh"] and r["Qty_Lenh"] > 0:
                return "Đã thực hiện"
            if r["Qty_DaNhapKho"] > 0:
                return "Thực hiện một phần"
            if r["Qty_DiDuong"] > 0:
                return "Đang đi đường"
            if r["Qty_DaChuyen"] > 0:
                return "Thực hiện một phần"
            return "Đang chờ thực hiện" if chua_qua_han_cho else "Chưa thực hiện"

        fact["trang_thai_thuc_hien"] = fact.apply(status, axis=1)
        print(fact["trang_thai_thuc_hien"].value_counts().to_string())
        return fact

    # ------------------------------------------------------------------
    # 7b. Danh gia DUNG HAN
    # ------------------------------------------------------------------
    @staticmethod
    def derive_han(fact: pd.DataFrame, days: int) -> pd.DataFrame:
        print(f"[7b] Danh gia dung han ({days} ngay, theo NGAY) ...")

        han_chot = fact["NgayChungTu_min"] + pd.Timedelta(days=days)
        exec_dt = fact["_ngay_nhap_min"].fillna(fact["_ngay_hist_min"])
        fact["Ngay_thuc_hien"] = exec_dt
        fact["So_ngay_thuc_hien"] = (exec_dt - fact["NgayChungTu_min"]).dt.days
        fact["So_ngay_tre"] = (exec_dt - han_chot).dt.days.clip(lower=0)

        today = pd.Timestamp.today().normalize()
        executed = fact["Qty_DaNhapKho"] > 0
        in_transit = (~executed) & (fact["Qty_DiDuong"] > 0)
        overdue_pending = (~executed) & (~in_transit) & (han_chot < today)

        dg = pd.Series("Chưa tới hạn", index=fact.index)
        dg = dg.mask(in_transit, "Đang đi đường")
        dg = dg.mask(overdue_pending, "Trễ hạn - chưa thực hiện")
        dg = dg.mask(executed & (exec_dt <= han_chot), "Đúng hạn")
        dg = dg.mask(executed & (exec_dt > han_chot), "Trễ hạn")
        fact["Danh_gia_han"] = dg

        print(fact["Danh_gia_han"].value_counts().to_string())
        return fact

    # ------------------------------------------------------------------
    # 8. Hoan thien fact + enrich dim
    # ------------------------------------------------------------------
    def finalize_fact(self, fact: pd.DataFrame) -> pd.DataFrame:
        print("[8] Enrich dim + sap xep cot ...")
        dim_store, dim_product = self.dim_store, self.dim_product

        ds = dim_store.set_index("store_key")
        for side, kcol in [("from", "Store_from_k"), ("to", "Store_to_k")]:
            for attr in ("Region", "Warehouse"):
                col = f"{attr}_{side}"
                from_master = fact[kcol].map(ds[attr])
                fact[col] = from_master.fillna(fact[col]) if col in fact.columns else from_master

        dp = dim_product.set_index("MaHang_k")
        for c in ["Brand", "Product_type", "Gender", "Product_group", "Group_Report"]:
            fact[c] = fact["MaHang_k"].map(dp[c])
        fact["Report_item_name"] = fact["Report_item_name"].fillna(
            fact["MaHang_k"].map(dp["Report_item_name"]))

        fact = fact.rename(columns={"NgayChungTu_min": "NgayChungTu_YeuCau"})

        order = [
            "NgayChungTu_YeuCau", "Year", "Month", "Quarter",
            "Store_from", "Region_from",
            "Store_to", "Region_to",
            "MaHang", "Report_item_name", "Operation", "Size",
            "Brand", "Product_type", "Gender", "Product_group", "Group_Report",
            "Qty_Lenh",
            "Qty_DaChuyen", "Qty_DaNhapKho", "Qty_DiDuong", "Status_list",
            "Qty_TraKho", "Qty_TraKho_vuot_nhan", "Kho_Nhan_list",
            "Qty_ChuyenDiTiep", "ChuyenDiTiep_toi",
            "trang_thai_thuc_hien",
            "Ngay_thuc_hien", "So_ngay_thuc_hien", "So_ngay_tre", "Danh_gia_han",
            "ly_do",
        ]
        drop_tech = ["lenh_id", "ym", "NgayChungTu_max", "Han_chot", "Ngay_tra_kho",
                     "so_dong_lenh", "so_dong_history", "so_dong_trakho",
                     "so_dong_chuyen_tiep", "_ngay_hist_min", "_ngay_nhap_min",
                     "Store_from_k", "Store_to_k", "MaHang_k", "Operation_k", "Size_k",
                     "_ch_nhan_k", "khop_history", "co_tra_kho_sau_nhan", "TrangThaiNhap_list",
                     "Warehouse_from", "Warehouse_to"]
        order = [c for c in order if c in fact.columns] + \
                [c for c in fact.columns if c not in order and c not in drop_tech]
        return fact[order]

    # ------------------------------------------------------------------
    # 9. Xay dung ket qua cho 1 ky (khong ghi file)
    # ------------------------------------------------------------------
    def compute_period(self, year: int, month: int, han_days: int | None = None):
        han_days = self.cfg.han_thuc_hien_ngay if han_days is None else han_days
        ym = year * 12 + month
        tag = f"{month:02d}.{year}"
        print("\n" + "=" * 64)
        print(f" KY BAO CAO {tag}")
        print("=" * 64)

        lp = self.lenh[self.lenh["ym"] == ym].copy()
        if lp.empty:
            print(f" [!] Khong co lenh cho {tag} (chua co file KQ_HHLC_{month:02d}) -> bo qua")
            return None
        n_dup = int(lp.duplicated().sum())
        lp = lp.drop_duplicates().copy()
        print(f"   Lenh tho: {len(lp) + n_dup:,} | trung lap bo: {n_dup} -> {len(lp):,}")

        fact = self.aggregate_lenh(lp)
        fact, _ = self.match_history(fact, self.hist)
        fact, _ = self.match_trakho(fact, self.trakho)
        fact = self.match_chuyen_di_tiep(fact, self.hist)
        fact = self.derive_status(fact, cho_thuc_hien_ngay=10)
        fact = self.derive_han(fact, han_days)
        fact = self.finalize_fact(fact)

        miss_store = sorted((set(lp["Store_from_k"]) | set(lp["Store_to_k"])) - set(self.dim_store["store_key"]))
        if miss_store:
            print(f"   [!] Cua hang khong co trong A_Region: {miss_store}")

        print(f"   Qty_Lenh={int(fact['Qty_Lenh'].sum()):,}  DaNhapKho={int(fact['Qty_DaNhapKho'].sum()):,}  "
              f"DiDuong={int(fact['Qty_DiDuong'].sum()):,}  TraKho={int(fact['Qty_TraKho'].sum()):,}")
        print(fact.groupby("trang_thai_thuc_hien")
              .agg(So_lenh=("Qty_Lenh", "size"), Qty_Lenh=("Qty_Lenh", "sum"))
              .sort_values("So_lenh", ascending=False).to_string())
        return fact

    # ------------------------------------------------------------------
    def run(self, periods: list[tuple[int, int]]) -> pd.DataFrame:
        """Chay toan bo pipeline cho danh sach ky (year, month) -> 1 DataFrame gop."""
        self.extract()
        self.clean()
        self.build_dims()

        frames = []
        for (y, m) in periods:
            f = self.compute_period(y, m)
            if f is not None:
                frames.append(f)

        if not frames:
            raise SystemExit("\nKhong co ky nao co du lieu -> khong xuat file.")
        return pd.concat(frames, ignore_index=True)

    def save(self, result: pd.DataFrame, filename: str = "KQ_LCHH.parquet") -> str:
        fp = os.path.join(self.cfg.output_dir, filename)
        result.to_parquet(fp, index=False)
        print(f"\n=> {fp}")
        print(f"   {len(result):,} dong x {result.shape[1]} cot")
        return fp

# -*- coding: utf-8 -*-
"""
====================================================================
 PerformanceAnalyzer - HIEU SUAT BAN SAU LUAN CHUYEN (bao cao DOC LAP)
====================================================================
Tu doc & xu ly tu data GOC (tai su dung LCHHPipeline), roi ghep them:
  01.System_sales/<nam>/System_sales_MM  <- ban theo thang, CHI doc thang can
  03.Inventory/InventorySize.parquet     <- ton kho HIEN TAI (snapshot)

Nguyen tac:
  - Gan doanh so vao CUA HANG NHAN (Store_to) cua lenh, khop MaHang+Operation+Size.
  - Tinh ban KE TU thang luan chuyen M (xem docstring goc trong README.md).
"""
from __future__ import annotations

import os

import pandas as pd

from Pipeline_LCHH import SKU, LCHHPipeline


def _kU(s):   # MaHang / Operation / Size
    return s.astype("string").str.strip().str.upper()


def _kL(s):   # ten cua hang
    return s.astype("string").str.strip().str.lower()


def _ym_to_py(ym):
    y = (ym - 1) // 12
    return y, ym - 12 * y


class PerformanceAnalyzer:
    """Hieu suat ban sau luan chuyen - tai su dung LCHHPipeline de dung ket qua luan chuyen."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.pipeline = LCHHPipeline(cfg)

    def _sales_path(self, ym: int):
        y, m = _ym_to_py(ym)
        return y, m, os.path.join(self.cfg.paths["sales"], str(y), f"System_sales_{m:02d}.parquet")

    def run(self, periods: list[tuple[int, int]]) -> pd.DataFrame:
        cfg = self.cfg
        ahead = cfg.sales_months_ahead
        noi_dung_ok = cfg.sales_noi_dung

        # ---- 1. dung ket qua luan chuyen TU DATA GOC ----
        print("[1] Xu ly luan chuyen tu data goc ...")
        lc = self.pipeline.run(periods)

        n0 = len(lc)
        lc = lc[lc["trang_thai_thuc_hien"] != "Chưa thực hiện"].copy()
        print(f"   Bo {n0 - len(lc):,} lenh 'Chua thuc hien' -> con {len(lc):,}")

        lc["ym_lc"] = lc["Year"].astype("int64") * 12 + lc["Month"].astype("int64")
        lc = lc.reset_index(drop=True)
        lc["_rid"] = lc.index
        lc["Store_to_k"] = _kL(lc["Store_to"])
        lc["MaHang_k"] = _kU(lc["MaHang"])
        lc["Operation_k"] = _kU(lc["Operation"])
        lc["Size_k"] = _kU(lc["Size"])
        print(f"\n   -> {len(lc):,} lenh | thang luan chuyen: "
              + ", ".join(f"{m:02d}.{y}" for y, m in sorted({_ym_to_py(v) for v in lc['ym_lc']})))

        ym_min, ym_max = int(lc["ym_lc"].min()), int(lc["ym_lc"].max())
        read_yms = list(range(ym_min, ym_max + ahead + 1))

        # ---- 2. doc ban CHI cac thang can ----
        print(f"[2] Doc ban {len(read_yms)} thang (M .. M+{ahead}) ...")
        frames, got_yms = [], []
        for ym in read_yms:
            y, m, fp = self._sales_path(ym)
            if not os.path.exists(fp):
                print(f"   - {y}-{m:02d}: khong co file -> bo qua")
                continue
            d = pd.read_parquet(fp, columns=["Store_name", "MaHang", "Operation", "Size",
                                             "Qty_Ban", "Nội dung", "Year", "Month"])
            d = d[d["Nội dung"].isin(noi_dung_ok)]
            d["ym"] = d["Year"].astype("int64") * 12 + d["Month"].astype("int64")
            d["Store_to_k"] = _kL(d["Store_name"])
            d["MaHang_k"] = _kU(d["MaHang"])
            d["Operation_k"] = _kU(d["Operation"])
            d["Size_k"] = _kU(d["Size"])
            frames.append(d[["Store_to_k"] + SKU + ["ym", "Qty_Ban"]])
            got_yms.append(ym)
            print(f"   - {y}-{m:02d}: {len(d):,} dong ban")

        sales = (pd.concat(frames, ignore_index=True)
                 .groupby(["Store_to_k"] + SKU + ["ym"], as_index=False)["Qty_Ban"].sum()
                 ) if frames else pd.DataFrame(columns=["Store_to_k"] + SKU + ["ym", "Qty_Ban"])

        # ---- 3. ton kho hien tai ----
        print("[3] Doc ton kho hien tai (InventorySize) ...")
        inv = pd.read_parquet(cfg.paths["inventory"])
        inv = inv.rename(columns={"Mahang": "MaHang"})
        inv["Store_to_k"] = _kL(inv["Store_name"])
        inv["MaHang_k"] = _kU(inv["MaHang"])
        inv["Operation_k"] = _kU(inv["Operation"])
        inv["Size_k"] = _kU(inv["Size"])
        inv_g = (inv.groupby(["Store_to_k"] + SKU, as_index=False)["Qty_TonKho"].sum()
                 .rename(columns={"Qty_TonKho": "Ton_hien_tai"}))

        # ---- 4. cua so ban theo tung lenh (ke tu thang luan chuyen M) ----
        print("[4] Tinh Qty_Ban 30/60/90 ngay (theo thang, tu M) ...")
        j = lc[["_rid", "ym_lc", "Store_to_k"] + SKU].merge(
            sales, on=["Store_to_k"] + SKU, how="left")
        j["delta"] = j["ym"] - j["ym_lc"]
        j = j[j["delta"].between(0, ahead)]

        def win(dmax):
            return j[j["delta"] <= dmax].groupby("_rid")["Qty_Ban"].sum()

        agg = pd.DataFrame(index=lc["_rid"])
        agg["Qty_Ban_30d"] = win(0)
        agg["Qty_Ban_60d"] = win(1)
        agg["Qty_Ban_90d"] = win(2)
        agg["Qty_Ban_LuyKe"] = win(ahead)
        agg = agg.astype("float64").fillna(0.0)

        got_set = set(got_yms)
        lc["So_thang_ban_co_DL"] = lc["ym_lc"].apply(
            lambda m0: sum((m0 + k) in got_set for k in range(0, ahead + 1)))

        # ---- 5. rap ket qua ----
        print("[5] Rap ket qua + danh gia ...")
        res = lc.merge(agg, left_on="_rid", right_index=True, how="left")
        res = res.merge(inv_g, on=["Store_to_k"] + SKU, how="left")
        for c in ["Qty_Ban_30d", "Qty_Ban_60d", "Qty_Ban_90d", "Qty_Ban_LuyKe", "Ton_hien_tai"]:
            res[c] = res[c].fillna(0)

        raw = (res["Ton_hien_tai"] - res["Qty_DaNhapKho"] + res["Qty_Ban_LuyKe"]
               + res["Qty_TraKho"] + res.get("Qty_ChuyenDiTiep", 0))
        res["Ton_truoc_dieu_chuyen"] = raw.clip(lower=0)
        res["Ton_sau_dieu_chuyen"] = res["Ton_truoc_dieu_chuyen"] + res["Qty_DaNhapKho"]
        res["Hang_thieu_khong_ro"] = (-raw).clip(lower=0)
        res["canh_bao_lech_ton"] = res["Hang_thieu_khong_ro"] > 0

        def ratio(a, b):
            return (a / b).where(b > 0)
        res["Ty_le_ban_90d"] = ratio(res["Qty_Ban_90d"], res["Qty_DaNhapKho"]).round(2)
        res["Ty_le_ban_LuyKe"] = ratio(res["Qty_Ban_LuyKe"], res["Qty_DaNhapKho"]).round(2)

        def danhgia(r):
            if r["Qty_DaNhapKho"] <= 0:
                return "Không nhận"
            if r["Qty_Ban_LuyKe"] <= 0:
                return "Chưa bán"
            rt = r["Qty_Ban_LuyKe"] / r["Qty_DaNhapKho"]
            if rt >= 1:
                return "Bán tốt"
            if rt >= 0.5:
                return "Bán khá"
            return "Bán chậm"
        res["Danh_gia_ban"] = res.apply(danhgia, axis=1)

        keep = [
            "NgayChungTu_YeuCau", "Year", "Month", "Quarter",
            "Store_from", "Region_from", "Store_to", "Region_to",
            "MaHang", "Report_item_name", "Operation", "Size",
            "Brand", "Product_type", "Gender", "Product_group", "Group_Report",
            "Qty_Lenh",
            "Ton_truoc_dieu_chuyen", "Ton_sau_dieu_chuyen",
            "Qty_Ban_30d", "Qty_Ban_60d", "Qty_Ban_90d", "Qty_Ban_LuyKe",
            "So_thang_ban_co_DL", "Ton_hien_tai",
            "Ty_le_ban_90d", "Ty_le_ban_LuyKe", "Danh_gia_ban",
        ]
        return res[[c for c in keep if c in res.columns]]

    def save(self, res: pd.DataFrame, filename: str = "KQ_LCHH_HieuSuat.parquet") -> str:
        fp = os.path.join(self.cfg.output_dir, filename)
        res.to_parquet(fp, index=False)

        res = res.copy()
        res["_nhan"] = res["Ton_sau_dieu_chuyen"] - res["Ton_truoc_dieu_chuyen"]
        print(f"\n=> {fp}")
        print(f"   {len(res):,} dong x {res.shape[1] - 1} cot")
        print(f"   Tong: nhan={int(res['_nhan'].sum()):,}  ban_luyke={int(res['Qty_Ban_LuyKe'].sum()):,}  "
              f"ton_hien_tai={int(res['Ton_hien_tai'].sum()):,}")
        print("\n   Danh_gia_ban:")
        print(res.groupby("Danh_gia_ban")
              .agg(So_lenh=("Qty_Lenh", "size"),
                   Nhan=("_nhan", "sum"),
                   Ban_LuyKe=("Qty_Ban_LuyKe", "sum"),
                   Ton_hien_tai=("Ton_hien_tai", "sum"))
              .sort_values("So_lenh", ascending=False).to_string())
        return fp

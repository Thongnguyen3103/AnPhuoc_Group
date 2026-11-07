# -*- coding: utf-8 -*-
"""
====================================================================
 MasterLCBuilder - MASTER DATA LUAN CHUYEN + DIEN BIEN LENH + BAN LUAN CHUYEN
====================================================================
Chi dung du lieu nen (so luong, ngay, trang thai). Chi so do bao cao bo sung.

  [1] Master_MaHang_LC  1 dong / SKU (MaHang + TNSX) x Size x Lan LC x Cua hang nhan
  [2] Data_LuanChuyen   1 dong / lenh: ngay lenh x CH gui x CH nhan x SKU x Size
  [3] Data_Ban_LC       1 dong / ngay ban x CH x SKU x Size x Noi dung x Status x dot LC

Quy tac (xem PLAN_Master_Data_LC.md):
  - Chi tinh lenh trong 07.Lenh_HHLC. History chi dung de doi chieu thuc hien.
  - Lan LC dem theo THANG: thang thu n co lenh cua SKU tren toan he thong = lan n.
  - History khop tuyen + SKU + Size, gan vao lenh gan nhat truoc do, khong vuot Qty_Lenh.
  - Ban LC tai dung cua hang nhan + SKU + Size. Hang LC ban truoc, khong vuot so da nhan.
  - Tra kho, chuyen di, Thanh ly, Tang lam giam so con lai nhung khong tinh la ban LC.
"""
from __future__ import annotations

import calendar
import glob
import hashlib
import os
from collections import defaultdict

import pandas as pd

from Common_Utils import join_unique, key_norm, mode_or_first, read_many, store_norm

SIZE_KEYS = ["MaHang_k", "Operation_k", "Size_k"]
ROUTE = ["Store_from_k", "Store_to_k"] + SIZE_KEYS
PAIR = ["Store_k"] + SIZE_KEYS
PROD_COLS = ["Report_item_name", "Brand", "Product_type", "Gender", "Product_group", "Group_Report"]

NOI_DUNG_BAN = ("Bán", "Đổi")
STATUS_BAN = ("Nguyên giá", "Sale")
NHOM_TUOI_THANG = 6
NHOM_TREN_6_THANG = "Trên 6 tháng"
NHOM_KHONG_LC = "Không phải LC"


def _hash_id(prefix: str, frame: pd.DataFrame) -> list[str]:
    return [prefix + hashlib.md5("||".join(map(str, r)).encode("utf-8")).hexdigest()[:12]
            for r in frame.itertuples(index=False, name=None)]


def _month_label(s: pd.Series) -> pd.Series:
    return s.dt.strftime("%Y-%m")


class MasterLCBuilder:
    def __init__(self, cfg, year: int, month: int):
        self.cfg = cfg
        self.alias = cfg.store_alias
        self.year, self.month = year, month
        self.cutoff = pd.Timestamp(year, month, calendar.monthrange(year, month)[1])
        self.han_days = cfg.han_thuc_hien_ngay
        self.out_dir = os.path.join(cfg.output_dir, "Master")
        self.lenh = self.hist = self.trakho = self.sales = None
        self.store_std = self.dim_product = None
        self.stats: dict[str, float] = {}

    # ------------------------------------------------------------------
    # 1. Doc + chuan hoa
    # ------------------------------------------------------------------
    def _add_keys(self, df: pd.DataFrame) -> pd.DataFrame:
        df["MaHang_k"] = key_norm(df["MaHang"])
        df["Operation_k"] = key_norm(df["Operation"])
        df["Size_k"] = key_norm(df["Size"])
        return df

    def _read_sales(self) -> pd.DataFrame:
        frames = []
        for fp in sorted(glob.glob(os.path.join(self.cfg.paths["sales"], "*", "System_sales_*.parquet"))):
            y = int(os.path.basename(os.path.dirname(fp)))
            m = int(os.path.basename(fp)[-10:-8])
            if self.first_order_ym <= (y, m) <= (self.year, self.month):
                frames.append(pd.read_parquet(fp))
        s = pd.concat(frames, ignore_index=True).rename(columns={"Nội dung": "Noi_Dung"})
        s = self._add_keys(s)
        s["Store_k"] = store_norm(s["Store_name"], self.alias)
        s["NgayChungTu"] = pd.to_datetime(s["NgayChungTu"]).dt.normalize()
        return s[s["NgayChungTu"] <= self.cutoff].copy()

    def load(self):
        print("[1] Doc du lieu nguon ...")
        lenh = self._add_keys(read_many(self.cfg.paths["lenh"]))
        hist = self._add_keys(read_many(self.cfg.paths["history"]))
        trakho = self._add_keys(read_many(self.cfg.paths["trakho"]))

        n0 = len(lenh)
        lenh = lenh.drop_duplicates().copy()
        lenh["Store_from_k"] = store_norm(lenh["Store_from"], self.alias)
        lenh["Store_to_k"] = store_norm(lenh["Store_to"], self.alias)
        lenh["NgayChungTu"] = pd.to_datetime(lenh["NgayChungTu"]).dt.normalize()
        lenh = lenh[lenh["NgayChungTu"] <= self.cutoff]
        same = lenh["Store_from_k"] == lenh["Store_to_k"]
        print(f"   - Lenh: bo {n0 - len(lenh):,} dong trung/sau ky, bo {int(same.sum())} dong CH gui = CH nhan")
        self.stats["lenh_gui_bang_nhan"] = int(same.sum())
        thieu_khoa = lenh[ROUTE].isna().any(axis=1)
        print(f"   - Lenh: bo {int(thieu_khoa.sum())} dong thieu khoa (TNSX/Size/cua hang trong)")
        self.stats["lenh_thieu_khoa"] = int(thieu_khoa.sum())
        lenh = lenh[~same & ~thieu_khoa].copy()
        if lenh.empty:
            raise SystemExit("Khong co lenh nao trong ky.")

        hist["Store_from_k"] = store_norm(hist["Store_from"], self.alias)
        hist["Store_to_k"] = store_norm(hist["Store_to"], self.alias)
        hist["NgayChungTu"] = pd.to_datetime(hist["NgayChungTu"]).dt.normalize()
        hist = hist[(hist["NgayChungTu"] <= self.cutoff) & (hist["Store_from_k"] != hist["Store_to_k"])].copy()

        trakho["Store_k"] = store_norm(trakho["Store_name"], self.alias)
        trakho["NgayChungTu"] = pd.to_datetime(trakho["NgayChungTu_dt"]).dt.normalize()
        trakho = trakho[trakho["NgayChungTu"] <= self.cutoff].copy()

        d0 = lenh["NgayChungTu"].min()
        self.first_order_ym = (d0.year, d0.month)
        self.lenh, self.hist, self.trakho = lenh, hist, trakho
        self.sales = self._read_sales()

        reg = pd.read_parquet(self.cfg.paths["region"])
        reg["store_key"] = store_norm(reg["Store_name"], self.alias)
        reg = reg.drop_duplicates("store_key").set_index("store_key")
        self.store_std, self.store_region = reg["Store_name"], reg["Region"]

        ma_lc = set(lenh["MaHang_k"].dropna())
        prod = pd.concat([d.loc[d["MaHang_k"].isin(ma_lc), ["MaHang_k"] + PROD_COLS].drop_duplicates()
                          for d in (hist, trakho, self.sales)], ignore_index=True)
        self.dim_product = prod.groupby("MaHang_k")[PROD_COLS].agg(mode_or_first)
        self.stats["sales_rows"] = len(self.sales)

    # ------------------------------------------------------------------
    # 2. Lenh + lan luan chuyen
    # ------------------------------------------------------------------
    def build_orders(self) -> pd.DataFrame:
        print("[2] Gom lenh + danh so lan luan chuyen ...")
        keys = ["NgayChungTu"] + ROUTE
        o = (self.lenh.groupby(keys, as_index=False)
             .agg(Store_from_raw=("Store_from", "first"), Store_to_raw=("Store_to", "first"),
                  MaHang=("MaHang", "first"), TNSX=("Operation", "first"), Size=("Size", "first"),
                  Report_item_name=("Report_item_name", "first"),
                  Qty_Lenh=("Qty_Chuyen", "sum"), Ly_Do=("Note", join_unique)))
        o = o.rename(columns={"NgayChungTu": "Ngay_Lenh"})
        o["Thang_LC"] = _month_label(o["Ngay_Lenh"])

        thang = o[["MaHang_k", "Operation_k", "Thang_LC"]].drop_duplicates().sort_values("Thang_LC")
        thang["Lan_LC"] = thang.groupby(["MaHang_k", "Operation_k"]).cumcount() + 1
        o = o.merge(thang, on=["MaHang_k", "Operation_k", "Thang_LC"], how="left")

        o["Lenh_ID"] = _hash_id("L", o[["Ngay_Lenh"] + ROUTE])
        o["Ma_LC_ID"] = _hash_id("M", o[SIZE_KEYS + ["Lan_LC", "Store_to_k"]])
        print(f"   -> {len(o):,} lenh, {o[['MaHang_k', 'Operation_k']].drop_duplicates().shape[0]:,} SKU, "
              f"SL {o['Qty_Lenh'].sum():,.0f}")
        return o

    # ------------------------------------------------------------------
    # 3. Doi chieu History vao lenh
    # ------------------------------------------------------------------
    def match_history(self, o: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        print("[3] Doi chieu History vao lenh ...")
        h = self.hist.sort_values("NgayChungTu")
        l = o[ROUTE + ["Ngay_Lenh", "Lenh_ID", "Qty_Lenh"]].sort_values("Ngay_Lenh")
        for c in ROUTE:
            h[c], l[c] = h[c].astype(object), l[c].astype(object)
        h = pd.merge_asof(h, l, left_on="NgayChungTu", right_on="Ngay_Lenh", by=ROUTE, direction="backward")
        h = h[h["Lenh_ID"].notna()].copy()

        h["_nhap"] = h["TrangThaiNhap"].astype("string").str.contains("nhập kho", case=False, na=False)
        h["_didg"] = h["TrangThaiNhap"].astype("string").str.contains("đi đường", case=False, na=False)
        h = h.sort_values(["Lenh_ID", "NgayChungTu"], kind="stable")
        cum = h.groupby("Lenh_ID")["Qty_Chuyen"].cumsum()
        room = (h["Qty_Lenh"] - (cum - h["Qty_Chuyen"])).clip(lower=0)
        h["Qty_Khop"] = pd.concat([room, h["Qty_Chuyen"]], axis=1).min(axis=1)
        self.stats["hist_vuot_lenh"] = float((h["Qty_Chuyen"] - h["Qty_Khop"]).sum())
        h["_q_nhap"] = h["Qty_Khop"].where(h["_nhap"], 0)
        h["_q_didg"] = h["Qty_Khop"].where(h["_didg"], 0)
        h["_d_nhap"] = h["NgayChungTu"].where(h["_nhap"] & (h["Qty_Khop"] > 0))
        h["_d_didg"] = h["NgayChungTu"].where(h["_didg"] & (h["Qty_Khop"] > 0))

        agg = (h.groupby("Lenh_ID")
               .agg(Qty_DaNhap=("_q_nhap", "sum"), Qty_DiDuong=("_q_didg", "sum"),
                    Ngay_Nhan_Dau=("_d_nhap", "min"), Ngay_Nhan_Cuoi=("_d_nhap", "max"),
                    Ngay_DiDuong_Dau=("_d_didg", "min"))
               .reset_index())
        o = o.merge(agg, on="Lenh_ID", how="left")
        o[["Qty_DaNhap", "Qty_DiDuong"]] = o[["Qty_DaNhap", "Qty_DiDuong"]].fillna(0)
        return o, h

    # ------------------------------------------------------------------
    # 4. [2] Data_LuanChuyen
    # ------------------------------------------------------------------
    def build_luan_chuyen(self, o: pd.DataFrame) -> pd.DataFrame:
        print("[4] Dung Data_LuanChuyen ...")
        o = o.copy()
        o["Qty_DaXuat"] = o["Qty_DaNhap"] + o["Qty_DiDuong"]
        con = (o["Qty_Lenh"] - o["Qty_DaXuat"]).clip(lower=0)
        het_ton = o["Ly_Do"].str.contains("hết tồn", case=False, na=False)
        o["Qty_Huy"] = con.where(het_ton, 0)
        o["Qty_ChuaThucHien"] = con.where(~het_ton, 0)
        o["Han_Chot"] = o["Ngay_Lenh"] + pd.Timedelta(days=self.han_days)

        chua_xuat = o["Qty_DaXuat"] <= 0
        qua_han = self.cutoff > o["Han_Chot"]
        tt = pd.Series("Thực hiện một phần", index=o.index)
        tt = tt.mask(o["Qty_DaNhap"] >= o["Qty_Lenh"], "Đã thực hiện")
        tt = tt.mask((o["Qty_DaNhap"] <= 0) & (o["Qty_DiDuong"] > 0), "Đang đi đường")
        tt = tt.mask(chua_xuat, "Chưa thực hiện").mask(chua_xuat & ~qua_han, "Đang chờ thực hiện")
        tt = tt.mask(chua_xuat & het_ton, "Hủy - hết tồn")
        o["Trang_Thai"] = tt

        dh = pd.Series("Chưa tới hạn", index=o.index)
        dh = dh.mask(qua_han, "Trễ - chưa nhận")
        dh = dh.mask(o["Ngay_Nhan_Dau"].notna() & (o["Ngay_Nhan_Dau"] <= o["Han_Chot"]), "Đúng hạn")
        dh = dh.mask(o["Ngay_Nhan_Dau"].notna() & (o["Ngay_Nhan_Dau"] > o["Han_Chot"]), "Trễ hạn")
        dh = dh.mask(tt == "Hủy - hết tồn", "Không xét")
        o["Dung_Han"] = dh
        o["So_Ngay_Thuc_Hien"] = (o["Ngay_Nhan_Dau"] - o["Ngay_Lenh"]).dt.days
        o["Thang_Nhan_Dau"] = _month_label(o["Ngay_Nhan_Dau"])

        for side, kcol, raw in (("from", "Store_from_k", "Store_from_raw"), ("to", "Store_to_k", "Store_to_raw")):
            o[f"Store_{side}"] = o[kcol].map(self.store_std).fillna(o[raw])
            o[f"Region_{side}"] = o[kcol].map(self.store_region)
        for c in PROD_COLS:
            mapped = o["MaHang_k"].map(self.dim_product[c])
            o[c] = mapped.fillna(o[c]) if c in o.columns else mapped

        cols = ["Lenh_ID", "Ma_LC_ID", "Ngay_Lenh", "Thang_LC", "Lan_LC", "Store_from", "Region_from",
                "Store_to", "Region_to", "MaHang", "TNSX", "Size"] + PROD_COLS + \
               ["Qty_Lenh", "Qty_DaXuat", "Qty_DaNhap", "Qty_DiDuong", "Qty_ChuaThucHien", "Qty_Huy",
                "Ngay_DiDuong_Dau", "Ngay_Nhan_Dau", "Ngay_Nhan_Cuoi", "Thang_Nhan_Dau", "So_Ngay_Thuc_Hien",
                "Han_Chot", "Dung_Han", "Trang_Thai", "Ly_Do"]
        self.stats["di_duong_qua_han"] = float(o.loc[(o["Qty_DiDuong"] > 0) & qua_han, "Qty_DiDuong"].sum())
        return o, o[cols].sort_values(["Ngay_Lenh", "Store_to", "MaHang", "TNSX", "Size"]).reset_index(drop=True)

    # ------------------------------------------------------------------
    # 5. [1] Master_MaHang_LC
    # ------------------------------------------------------------------
    @staticmethod
    def build_master(o: pd.DataFrame) -> pd.DataFrame:
        print("[5] Dung Master_MaHang_LC ...")
        m = (o.groupby("Ma_LC_ID", as_index=False)
             .agg(MaHang=("MaHang", "first"), TNSX=("TNSX", "first"), Size=("Size", "first"),
                  Lan_LC=("Lan_LC", "first"), Thang_LC=("Thang_LC", "first"),
                  Store_to=("Store_to", "first"), Region_to=("Region_to", "first"),
                  Ngay_Lenh=("Ngay_Lenh", "min"), So_CH_Gui=("Store_from", "nunique"),
                  Qty_Lenh=("Qty_Lenh", "sum"), Qty_Nhan=("Qty_DaNhap", "sum"), Qty_DiDuong=("Qty_DiDuong", "sum"),
                  Ngay_Nhan_Dau=("Ngay_Nhan_Dau", "min"), Ngay_Nhan_Cuoi=("Ngay_Nhan_Cuoi", "max"),
                  **{c: (c, "first") for c in PROD_COLS}))
        print(f"   -> {len(m):,} dong; SKU theo lan LC:")
        sku = m.drop_duplicates(["MaHang", "TNSX", "Lan_LC"]).groupby("Lan_LC").size()
        print(sku.to_string())
        return m.sort_values(["Thang_LC", "MaHang", "TNSX", "Size", "Store_to"]).reset_index(drop=True)

    # ------------------------------------------------------------------
    # 6. [3] Data_Ban_LC - phan bo ban vao lo nhan
    # ------------------------------------------------------------------
    def build_ban(self, o: pd.DataFrame, h: pd.DataFrame, master: pd.DataFrame) -> pd.DataFrame:
        print("[6] Phan bo ban vao lo luan chuyen ...")
        o = o.rename(columns={"Store_to_k": "Store_k"})
        first = o.groupby(PAIR)["Ngay_Lenh"].min()
        first_month = (first - pd.to_timedelta(first.dt.day - 1, unit="D")).rename("_tu_ngay")

        rec = h[h["_nhap"] & (h["Qty_Khop"] > 0)].merge(o[["Lenh_ID", "Ma_LC_ID"]], on="Lenh_ID")
        rec = rec.rename(columns={"Store_to_k": "Store_k"})

        s = self.sales.merge(first_month.reset_index(), on=PAIR, how="inner")
        s = s[s["NgayChungTu"] >= s["_tu_ngay"]].copy()
        trong_pv = s["Noi_Dung"].isin(NOI_DUNG_BAN) & s["Status"].isin(STATUS_BAN)
        ban, khac = s[trong_pv], s[~trong_pv]

        tra = self.trakho.merge(first_month.reset_index(), on=PAIR, how="inner")
        chuyen = self.hist.rename(columns={"Store_from_k": "Store_k"}).merge(first_month.reset_index(), on=PAIR, how="inner")

        # (ngay, thu tu trong ngay, loai, qty, thong tin): nhap -> khach doi tra -> ban -> xuat khac
        events = defaultdict(list)
        for r in rec[PAIR + ["NgayChungTu", "Qty_Khop", "Ma_LC_ID"]].itertuples(index=False):
            events[r[:4]].append((r[4], 0, "nhap", r[5], r[6]))
        for r in ban[PAIR + ["NgayChungTu", "Qty_Ban", "Noi_Dung", "Status"]].itertuples(index=False):
            events[r[:4]].append((r[4], 1 if r[5] < 0 else 2, "ban", r[5], (r[6], r[7])))
        for r in khac[PAIR + ["NgayChungTu", "Qty_Ban"]].itertuples(index=False):
            events[r[:4]].append((r[4], 3, "khac", r[5], None))
        for r in tra[PAIR + ["NgayChungTu", "Qty_Tra"]].itertuples(index=False):
            events[r[:4]].append((r[4], 3, "tra", r[5], None))
        for r in chuyen[PAIR + ["NgayChungTu", "Qty_Chuyen"]].itertuples(index=False):
            events[r[:4]].append((r[4], 3, "chuyen", r[5], None))

        rows, giam = [], defaultdict(float)
        for key, evs in events.items():
            lots: dict[str, list[float]] = {}  # Ma_LC_ID -> [con lai, da ban LC], theo thu tu nhan
            for d, _, typ, qty, info in sorted(evs, key=lambda e: (e[0], e[1])):
                if typ == "nhap":
                    lots.setdefault(info, [0.0, 0.0])[0] += qty
                elif typ == "ban":
                    nd, st = info
                    con = qty
                    if qty > 0:
                        for lot, v in lots.items():
                            take = min(v[0], con)
                            if take > 0:
                                v[0] -= take
                                v[1] += take
                                con -= take
                                rows.append((*key, d, nd, st, lot, take))
                            if con <= 0:
                                break
                    else:
                        for lot, v in reversed(list(lots.items())):
                            back = min(v[1], -con)
                            if back > 0:
                                v[0] += back
                                v[1] -= back
                                con += back
                                rows.append((*key, d, nd, st, lot, -back))
                            if con >= 0:
                                break
                    if con != 0:
                        rows.append((*key, d, nd, st, None, con))
                elif qty > 0:
                    con = qty
                    for v in lots.values():
                        take = min(v[0], con)
                        v[0] -= take
                        con -= take
                        giam[typ] += take
                        if con <= 0:
                            break
        self.stats.update({f"lo_giam_{k}": v for k, v in giam.items()})

        out = pd.DataFrame(rows, columns=PAIR + ["Ngay_Ban", "Noi_Dung", "Status", "Ma_LC_ID", "Qty_Ban"])
        grp = PAIR + ["Ngay_Ban", "Noi_Dung", "Status", "Ma_LC_ID"]
        out = out.groupby(grp, dropna=False, as_index=False)["Qty_Ban"].sum()
        out = out[out["Qty_Ban"] != 0].copy()

        info = master.set_index("Ma_LC_ID")[["Lan_LC", "Thang_LC"]]
        out["Lan_LC"] = out["Ma_LC_ID"].map(info["Lan_LC"])
        out["Thang_LC"] = out["Ma_LC_ID"].map(info["Thang_LC"])
        out["Thang_Ban"] = _month_label(out["Ngay_Ban"])
        out["Loai_Hang"] = out["Ma_LC_ID"].notna().map({True: "LC", False: "Tồn sẵn"})

        tuoi = (out["Ngay_Ban"].dt.year * 12 + out["Ngay_Ban"].dt.month
                - pd.to_datetime(out["Thang_LC"], format="%Y-%m").dt.year * 12
                - pd.to_datetime(out["Thang_LC"], format="%Y-%m").dt.month)
        nhom = out["Thang_LC"].where(tuoi < NHOM_TUOI_THANG, NHOM_TREN_6_THANG)
        out["Nhom_Thang_LC"] = nhom.where(out["Loai_Hang"] == "LC", NHOM_KHONG_LC)

        names = ban.drop_duplicates(PAIR).set_index(PAIR)
        idx = pd.MultiIndex.from_frame(out[PAIR])
        for c, src in (("Store_name", "Store_name"), ("Region", "Region"), ("MaHang", "MaHang"),
                       ("TNSX", "Operation"), ("Size", "Size")):
            out[c] = names[src].reindex(idx).to_numpy()
        for c in PROD_COLS:
            out[c] = out["MaHang_k"].map(self.dim_product[c])
        self.stats["ban_nguon"] = float(ban["Qty_Ban"].sum())
        self.stats["ban_khac_khong_tinh"] = float(khac["Qty_Ban"].sum())

        cols = ["Thang_Ban", "Ngay_Ban", "Store_name", "Region", "MaHang", "TNSX", "Size"] + PROD_COLS + \
               ["Noi_Dung", "Status", "Loai_Hang", "Ma_LC_ID", "Lan_LC", "Thang_LC", "Nhom_Thang_LC", "Qty_Ban"]
        # Phan bo chay tu thang dau de biet lo con lai; file chi ghi ban cua thang chay
        self.ban_tat_ca = out[cols]
        thang_chay = f"{self.year}-{self.month:02d}"
        ky = self.ban_tat_ca[self.ban_tat_ca["Thang_Ban"] == thang_chay]
        return ky.sort_values(["Ngay_Ban", "Store_name", "MaHang", "TNSX", "Size"]).reset_index(drop=True)

    # ------------------------------------------------------------------
    # 7. Doi soat
    # ------------------------------------------------------------------
    def check(self, master: pd.DataFrame, lc: pd.DataFrame, ban: pd.DataFrame) -> bool:
        print("\n[7] Doi soat")
        ok = True

        def chk(name, a, b):
            nonlocal ok
            good = abs(a - b) < 0.5
            ok &= good
            print(f"   {'OK  ' if good else 'LECH'} {name}: {a:,.0f} | {b:,.0f}")

        chk("Qty_Lenh file LC = lenh sach", lc["Qty_Lenh"].sum(), self.lenh["Qty_Chuyen"].sum())
        chk("Qty_Lenh master = file LC", master["Qty_Lenh"].sum(), lc["Qty_Lenh"].sum())
        chk("Qty_Nhan master = Qty_DaNhap file LC", master["Qty_Nhan"].sum(), lc["Qty_DaNhap"].sum())
        chk("Lenh = Nhap + DiDuong + ChuaTH + Huy", lc["Qty_Lenh"].sum(),
            lc[["Qty_DaNhap", "Qty_DiDuong", "Qty_ChuaThucHien", "Qty_Huy"]].sum().sum())
        chk("Qty_Ban phan bo = ban nguon cap theo doi", self.ban_tat_ca["Qty_Ban"].sum(), self.stats["ban_nguon"])
        print(f"   File ban thang chay: {ban['Qty_Ban'].sum():,.0f} cai, "
              f"trong do LC {ban.loc[ban['Loai_Hang'] == 'LC', 'Qty_Ban'].sum():,.0f}")

        lo = self.ban_tat_ca[self.ban_tat_ca["Loai_Hang"] == "LC"].groupby("Ma_LC_ID")["Qty_Ban"].sum()
        vuot = lo.sub(master.set_index("Ma_LC_ID")["Qty_Nhan"], fill_value=0).clip(lower=0).sum()
        chk("Ban LC vuot so da nhan", vuot, 0)
        print(f"   Tham khao: History vuot lenh {self.stats['hist_vuot_lenh']:,.0f}; "
              f"di duong qua han {self.stats['di_duong_qua_han']:,.0f}; "
              f"lenh CH gui = nhan da bo {self.stats['lenh_gui_bang_nhan']:,.0f} dong; "
              f"lenh thieu khoa da bo {self.stats['lenh_thieu_khoa']:,.0f} dong; "
              f"Thanh ly + Tang tai cap theo doi {self.stats['ban_khac_khong_tinh']:,.0f}")
        print(f"   Lo bi giam (khong tinh ban LC): " +
              ", ".join(f"{k[8:]} {v:,.0f}" for k, v in self.stats.items() if k.startswith("lo_giam_")))
        return ok

    # ------------------------------------------------------------------
    def run(self):
        self.load()
        orders = self.build_orders()
        orders, h = self.match_history(orders)
        orders, lc = self.build_luan_chuyen(orders)
        master = self.build_master(orders)
        ban = self.build_ban(orders, h, master)
        ok = self.check(master, lc, ban)
        return master, lc, ban, ok

    def save(self, master: pd.DataFrame, lc: pd.DataFrame, ban: pd.DataFrame) -> None:
        os.makedirs(self.out_dir, exist_ok=True)
        for name, df in (("Master_MaHang_LC", master), ("Data_LuanChuyen", lc), ("Data_Ban_LC", ban)):
            fp = os.path.join(self.out_dir, f"{name}.parquet")
            df.to_parquet(fp, index=False)
            print(f"=> {fp}  ({len(df):,} dong x {df.shape[1]} cot)")

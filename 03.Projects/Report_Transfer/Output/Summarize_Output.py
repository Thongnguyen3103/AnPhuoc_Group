# -*- coding: utf-8 -*-
"""OutputSummarizer — Tổng hợp Sheet 3/4/5/6 (bảng nội bộ) từ kết quả phân bổ."""
import pandas as pd
from Geo.Compute_Geo_Distance import GeoLocator as geo


class OutputSummarizer:
    """Tổng hợp Sheet 3/4/5/6 (bảng nội bộ) từ kết quả phân bổ."""

    # ─────────────────────────────────────────────
    # SHEET 3 — Chi tiết size & đề xuất xuất/nhận
    # ─────────────────────────────────────────────

    @staticmethod
    def build_sheet3(df_store_size, detail_df):
        """Chi tiết bán – tồn theo size, theo CH, kèm đề xuất SL xuất / nhận."""
        base = df_store_size.copy()
        if not detail_df.empty:
            xuat = detail_df.groupby(["Combined_PK", "CH_xuat", "Size"])["So_luong"].sum().rename("De_xuat_xuat")
            nhan = detail_df.groupby(["Combined_PK", "CH_nhan", "Size"])["So_luong"].sum().rename("De_xuat_nhan")
            base = base.merge(xuat, left_on=["Combined_PK", "Store_name", "Size"], right_index=True, how="left")
            base = base.merge(nhan, left_on=["Combined_PK", "Store_name", "Size"], right_index=True, how="left")
        else:
            base["De_xuat_xuat"] = 0
            base["De_xuat_nhan"] = 0
        base["De_xuat_xuat"] = base["De_xuat_xuat"].fillna(0).astype(int)
        base["De_xuat_nhan"] = base["De_xuat_nhan"].fillna(0).astype(int)
        cols = ["Combined_PK", "Store_name", "Region", "Size", "Ton_hien_tai", "Ban_3T",
                "Toc_do_ban_size", "Thang_ton_size", "Trong_cua_so", "Size_gay",
                "De_xuat_xuat", "De_xuat_nhan"]
        return base[cols].sort_values(["Combined_PK", "Store_name", "Size"])

    @staticmethod
    def build_sheet4(detail_df, store_meta):
        if detail_df.empty:
            return detail_df
        rows = []
        for _, r in detail_df.iterrows():
            m_out = store_meta.get(r["CH_xuat"], {})
            m_in = store_meta.get(r["CH_nhan"], {})
            d_km = geo.haversine_km(m_out.get("Lat"), m_out.get("Lon"), m_in.get("Lat"), m_in.get("Lon"))
            rows.append(dict(
                Combined_PK=r["Combined_PK"], Size=r["Size"],
                CH_xuat=r["CH_xuat"], Region_xuat=r["Vung_xuat"],
                CH_nhan=r["CH_nhan"], Region_nhan=r["Vung_nhan"],
                Loai_lenh=r["Noi_lien_vung"], Khoang_cach_km=(round(d_km, 1) if d_km is not None else None),
                SL_chuyen=r["So_luong"], Gia_ban=r["Gia_ban"], Gia_tri_chuyen=r["Gia_tri"],
                Ton_xuat_truoc=r.get("Ton_CH_xuat_truoc"), Ton_xuat_sau=r.get("Ton_CH_xuat_du_kien"),
                Ton_nhan_truoc=r.get("Ton_CH_nhan_truoc"), Ton_nhan_sau=r.get("Ton_CH_nhan_du_kien"),
                Ly_do=r["Ly_do"],
                Dat_lo=("✓" if r.get("Dat_lo_toi_thieu") else "✗"),
            ))
        return pd.DataFrame(rows)

    @staticmethod
    def build_sheet4_with_stock(detail_df, inv_by_size, store_meta):
        """Gộp tồn trước/sau (Mục 8/9) + khoảng cách thật rồi trả sheet 4 hoàn chỉnh."""
        if detail_df.empty:
            return detail_df
        inv_idx = inv_by_size.set_index(["Combined_PK", "Store_name", "Size"])["Qty_TonKho"].to_dict()
        enriched = []
        for _, r in detail_df.iterrows():
            ton_xuat_truoc = inv_idx.get((r["Combined_PK"], r["CH_xuat"], r["Size"]), 0)
            ton_nhan_truoc = inv_idx.get((r["Combined_PK"], r["CH_nhan"], r["Size"]), 0)
            d = r.to_dict()
            d["Ton_CH_xuat_truoc"] = ton_xuat_truoc
            d["Ton_CH_xuat_du_kien"] = ton_xuat_truoc - r["So_luong"]
            d["Ton_CH_nhan_truoc"] = ton_nhan_truoc
            d["Ton_CH_nhan_du_kien"] = ton_nhan_truoc + r["So_luong"]
            enriched.append(d)
        return OutputSummarizer.build_sheet4(pd.DataFrame(enriched), store_meta)

    @staticmethod
    def build_sheet5(sheet4_df):
        """Tổng hợp lệnh gọn — STT + các cột chính, sort theo CH xuất."""
        if sheet4_df.empty:
            return sheet4_df
        grp = sheet4_df.groupby(["CH_xuat", "Combined_PK", "Size", "CH_nhan"]).agg(
            SL_chuyen=("SL_chuyen", "sum"), Gia_tri_chuyen=("Gia_tri_chuyen", "sum"),
            Region_xuat=("Region_xuat", "first"), Region_nhan=("Region_nhan", "first"),
            Loai_lenh=("Loai_lenh", "first"), Khoang_cach_km=("Khoang_cach_km", "first"),
            Dat_lo=("Dat_lo", "first"),
        ).reset_index().sort_values(["CH_xuat", "CH_nhan"]).reset_index(drop=True)
        grp.insert(0, "STT", grp.index + 1)
        cols = ["STT", "CH_xuat", "Combined_PK", "Size", "SL_chuyen", "Gia_tri_chuyen", "CH_nhan",
                "Region_xuat", "Region_nhan", "Loai_lenh", "Khoang_cach_km", "Dat_lo"]
        return grp[cols]

    @staticmethod
    def build_sheet6(df_store, sheet4_df, scope_stores_df):
        """Tổng hợp xuất – nhận – tồn theo cửa hàng (toàn bộ các mã trong đợt)."""
        stores = scope_stores_df.set_index("Store_name")
        ton_dau = df_store.groupby("Store_name")["Ton"].sum() if not df_store.empty else pd.Series(dtype=float)
        nhan = sheet4_df.groupby("CH_nhan")["SL_chuyen"].sum() if not sheet4_df.empty else pd.Series(dtype=float)
        xuat = sheet4_df.groupby("CH_xuat")["SL_chuyen"].sum() if not sheet4_df.empty else pd.Series(dtype=float)
        rows = []
        for st in scope_stores_df["Store_name"]:
            td = ton_dau.get(st, 0)
            nh = nhan.get(st, 0)
            xu = xuat.get(st, 0)
            rows.append(dict(
                Store_name=st, Region=stores.loc[st, "Region"] if st in stores.index else "",
                Loai_CH=stores.loc[st, "Loai_CH"] if st in stores.index else "",
                Ton_dau_ky=td, Tong_xuat=xu, Tong_nhan=nh, Ton_cuoi_du_kien=td + nh - xu,
            ))
        return pd.DataFrame(rows)

    @staticmethod
    def _sheet8_attrs(row):
        """Thuộc tính nhóm theo danh mục (khóa Mục 8): Quần → Form, Style; còn lại → Color_group."""
        from Config import Config_Parameters as cfg
        gr = str(row.get("Group_Report") or "").strip()
        cols = next((v for k, v in cfg.NHOM_KEY_THEO_DANH_MUC.items() if gr.lower().startswith(k.lower())),
                    cfg.NHOM_KEY_MAC_DINH)
        src = {"Color_group": "Group_color"}            # df_sku lưu Color_group ở cột Group_color
        return [" ".join(str(row.get(src.get(c, c)) or "").split()) for c in cols]

    @staticmethod
    def group_label_sheet8(row):
        """Nhãn nhóm Sheet 8 = tên sản phẩm + thuộc tính, vd 'Chemise Nam Dài PIE - Màu' /
        'Quần Tây Nam AP - Modern - Lưng Thường'."""
        ten = " ".join(str(row.get("Ten_san_pham") or "").split())
        return " - ".join([ten] + [a for a in OutputSummarizer._sheet8_attrs(row) if a])

    @staticmethod
    def group_match_key_sheet8(row):
        """Khóa so khớp nhóm Sheet 8: tên sản phẩm + thuộc tính (bỏ phân biệt hoa/thường)."""
        ten = " ".join(str(row.get("Ten_san_pham") or "").split()).casefold()
        return (ten,) + tuple(a.casefold() for a in OutputSummarizer._sheet8_attrs(row))

    @staticmethod
    def build_sheet8(df_store, detail_df, kho_df, df_sku, group_inv=None):
        """Sheet 8 — Cửa hàng × Nhóm hàng × Mã (CHỈ các mã trong file điều chuyển): tồn ban đầu /
        SL chuyển / SL nhận (từ CH) / SL nhận từ kho / tồn cuối. Sort theo CH → nhóm → mã;
        cuối mỗi nhóm trong 1 CH có 2 dòng:
          - 'Total <nhóm> — mã điều chuyển': cộng các mã trong file;
          - '<nhóm> — tồn toàn CH (nguyên giá)': tồn MỌI mã nguyên giá cùng nhóm tại CH (group_inv),
            chuyển/nhận như dòng trên, tồn cuối = tồn toàn CH − chuyển + nhận.
        Cuối sheet có TỔNG CỘNG (chỉ mã điều chuyển)."""
        key = ["Store_name", "Combined_PK"]
        base = (df_store[key + ["Ton"]].copy() if not df_store.empty else pd.DataFrame(columns=key + ["Ton"]))
        parts = [base]
        if detail_df is not None and not detail_df.empty:
            parts.append(detail_df.groupby(["CH_xuat", "Combined_PK"])["So_luong"].sum().rename("SL_chuyen")
                         .reset_index().rename(columns={"CH_xuat": "Store_name"}))
            parts.append(detail_df.groupby(["CH_nhan", "Combined_PK"])["So_luong"].sum().rename("SL_nhan")
                         .reset_index().rename(columns={"CH_nhan": "Store_name"}))
        if kho_df is not None and not kho_df.empty:
            parts.append(kho_df.groupby(["CH_nhan", "Combined_PK"])["SL_chia"].sum().rename("SL_nhan_kho")
                         .reset_index().rename(columns={"CH_nhan": "Store_name"}))
        df = parts[0]
        for p in parts[1:]:
            df = df.merge(p, on=key, how="outer")
        num = ["Ton", "SL_chuyen", "SL_nhan", "SL_nhan_kho"]
        for c in num:
            if c not in df.columns:
                df[c] = 0
            df[c] = df[c].fillna(0).astype(int)
        df = df[df["Combined_PK"].isin(set(df_sku["Combined_PK"]))]           # chỉ mã đang luân chuyển
        df = df[(df[num] != 0).any(axis=1)]
        df["Ton_cuoi"] = df["Ton"] - df["SL_chuyen"] + df["SL_nhan"] + df["SL_nhan_kho"]
        num = num + ["Ton_cuoi"]

        sku = df_sku.set_index("Combined_PK")
        nhom = {pk: OutputSummarizer.group_label_sheet8(r) for pk, r in sku.iterrows()}
        nhom_key = {pk: OutputSummarizer.group_match_key_sheet8(r) for pk, r in sku.iterrows()}
        df["Nhom_hang"] = df["Combined_PK"].map(nhom)
        df["Nhom_key"] = df["Combined_PK"].map(nhom_key)
        ton_toan_ch = {}
        if group_inv is not None and not group_inv.empty:
            gi = group_inv.copy()
            gi["Nhom_key"] = [OutputSummarizer.group_match_key_sheet8(dict(
                Ten_san_pham=n, Group_Report=g, Group_color=c, Form=f, Style=t))
                for n, g, c, f, t in zip(gi["Report_item_name"], gi["Group_Report"], gi["Color_group"], gi["Form"], gi["Style"])]
            ton_toan_ch = gi.groupby(["Store_name", "Nhom_key"])["Qty_TonKho"].sum().to_dict()
        df = df.join(sku[["Ma_Hang", "Ten_san_pham"]], on="Combined_PK")
        region = (df_store.drop_duplicates("Store_name").set_index("Store_name")["Region"]
                  if not df_store.empty else pd.Series(dtype=object))
        df["Region"] = df["Store_name"].map(region)
        df = df.sort_values(["Store_name", "Nhom_hang", "Combined_PK"])

        cols = ["Store_name", "Region", "Nhom_hang", "Combined_PK", "Ma_Hang", "Ten_san_pham"] + num
        out = []
        for (st, nh), g in df.groupby(["Store_name", "Nhom_hang"], sort=True):
            out.append(g[cols].assign(La_total=False))
            tot = {c: None for c in cols}
            tot.update({c: int(g[c].sum()) for c in num})
            tot.update(Store_name=st, Region=g["Region"].iloc[0], Nhom_hang=f"Total {nh} — mã điều chuyển")
            out.append(pd.DataFrame([tot]).assign(La_total=True))
            if group_inv is not None:
                ton_all = int(ton_toan_ch.get((st, g["Nhom_key"].iloc[0]), 0))
                full = dict(tot)
                full.update(Nhom_hang=f"{nh} — tồn toàn CH (nguyên giá)", Ton=ton_all,
                            Ton_cuoi=ton_all - tot["SL_chuyen"] + tot["SL_nhan"] + tot["SL_nhan_kho"])
                out.append(pd.DataFrame([full]).assign(La_total="full"))
        if not out:
            return pd.DataFrame(columns=cols + ["La_total"])
        res = pd.concat(out, ignore_index=True)
        tong = {c: None for c in cols}
        tong.update({c: int(df[c].sum()) for c in num})
        tong["Store_name"] = "TỔNG CỘNG"
        return pd.concat([res, pd.DataFrame([tong]).assign(La_total="grand")], ignore_index=True)

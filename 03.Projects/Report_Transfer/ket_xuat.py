# -*- coding: utf-8 -*-
"""
ket_xuat.py
Dựng Sheet 3 (chi tiết size + đề xuất)
Dựng Sheet 4 (lệnh chi tiết + tồn dự kiến + khoảng cách km)
Dựng Sheet 5 (tổng hợp lệnh gọn), Sheet 6 (tổng hợp theo cửa hàng).
"""
import pandas as pd
import dia_ly as geo

# ─────────────────────────────────────────────
# SHEET 3 — Chi tiết size & đề xuất xuất/nhận
# ─────────────────────────────────────────────


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
        ))
    return pd.DataFrame(rows)


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
    return build_sheet4(pd.DataFrame(enriched), store_meta)


def build_sheet5(sheet4_df):
    """Tổng hợp lệnh gọn — STT + các cột chính, sort theo CH xuất."""
    if sheet4_df.empty:
        return sheet4_df
    grp = sheet4_df.groupby(["CH_xuat", "Combined_PK", "Size", "CH_nhan"]).agg(
        SL_chuyen=("SL_chuyen", "sum"), Gia_tri_chuyen=("Gia_tri_chuyen", "sum"),
        Region_xuat=("Region_xuat", "first"), Region_nhan=("Region_nhan", "first"),
        Loai_lenh=("Loai_lenh", "first"), Khoang_cach_km=("Khoang_cach_km", "first"),
    ).reset_index().sort_values(["CH_xuat", "CH_nhan"]).reset_index(drop=True)
    grp.insert(0, "STT", grp.index + 1)
    cols = ["STT", "CH_xuat", "Combined_PK", "Size", "SL_chuyen", "Gia_tri_chuyen", "CH_nhan",
            "Region_xuat", "Region_nhan", "Loai_lenh", "Khoang_cach_km"]
    return grp[cols]


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

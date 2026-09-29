# -*- coding: utf-8 -*-
"""
phan_bo.py
Sinh lệnh điều chuyển chi tiết theo size
Ghép nguồn theo khoảng cách.
"""
import pandas as pd
import tham_so as cfg
import tinh_toan as comp


def _sort_by_distance(candidates, dest_store, store_meta):
    import dia_ly as geo
    dest_meta = store_meta.get(dest_store, {})
    dest_lat, dest_lon = dest_meta.get("Lat"), dest_meta.get("Lon")

    def sort_key(c):
        (src_store, _sz), _avail = c
        src_meta = store_meta.get(src_store, {})
        d = geo.haversine_km(dest_lat, dest_lon, src_meta.get("Lat"), src_meta.get("Lon"))
        if d is None:
            same_region = 0 if src_meta.get("Region") == dest_meta.get("Region") else 1
            return (1, same_region, 99999)
        return (0, 0, d)

    return sorted(candidates, key=sort_key)


def _reserve_sizes(size_weight_map, k=cfg.GIU_LAI_SO_SIZE):
    ranked = sorted(size_weight_map.items(), key=lambda kv: -kv[1])
    return [s for s, _ in ranked[:k]]


def compute_target_qty(toc_do_ban_ch, ton_hien_co, he_so=cfg.TON_MUC_TIEU_HE_SO):
    return max(0, round(toc_do_ban_ch * he_so - ton_hien_co))


def build_transfer_orders(df_sku, df_store, inv_by_size, size_weight_by_sku, size_seq_by_sku,
                           so_ch_pham_vi, master_lookup, store_meta):
    """Trả về detail_df — lệnh điều chuyển chi tiết theo size.

    Ghi chú: Pha 2 (cắt giảm khi tổng nhu cầu vượt hạn mức cộng dồn nhiều mã cùng
    đợt — xem README Mục 5.3) CHƯA được cài trong bản này; nếu cần, bổ sung một hàm
    riêng nhận vào detail_df + han_muc_nhan_ch rồi cắt giảm/gắn cờ trước khi ghi Excel."""
    detail_rows = []

    inv_idx = inv_by_size.set_index(["Combined_PK", "Store_name", "Size"])["Qty_TonKho"].to_dict()
    used_quota = {}

    for _, sku in df_sku.iterrows():
        pk = sku["Combined_PK"]
        if sku["Lan_dieu_chuyen"] not in ("Lan1", "Lan2", "Lan3"):
            continue
        trang_thai = sku["Trang_thai"]
        lan = sku["Lan_dieu_chuyen"]
        stores_sku = df_store[df_store["Combined_PK"] == pk].copy()
        if stores_sku.empty:
            continue
        weight_map = size_weight_by_sku.get(pk, {})
        size_seq = size_seq_by_sku.get(pk, sorted(weight_map.keys()))
        reserve_default = set(_reserve_sizes(weight_map))

        stores_sku = stores_sku.sort_values("Chi_so_hieu_suat", ascending=False)
        tong_ton_ma = sku["Tong_ton"]

        importers, exporters = [], []

        # ---- LẦN 3: gom điểm theo ma trận xu hướng (Mục 11.3/12), KHÔNG lặp lại Lần 2 ----
        if lan == "Lan3" and trang_thai != "Bán rất chậm":
            has_trend = stores_sku["Hanh_dong_L3"].notna().any() if "Hanh_dong_L3" in stores_sku.columns else False
            if has_trend:
                gom = stores_sku[stores_sku["Hanh_dong_L3"].isin(["ĐIỂM GOM CHÍNH", "ƯU TIÊN NHẬN"])]
                gom = gom.sort_values(["Hanh_dong_L3", "Hieu_suat_ky"], ascending=[True, False])
            else:
                # Chưa có Hiệu suất kỳ Lần 2 lưu trong du_lieu/lich_su_hieu_suat_ky.json (chưa
                # chạy Lần 2 qua công cụ) — fallback: gom về CH có Hiệu suất kỳ cao nhất.
                gom = stores_sku.sort_values("Hieu_suat_ky", ascending=False)
            gom = gom.head(cfg.GOM_DIEM_L3_MAX)
            gom_names = set(gom["Store_name"])
            for _, r in gom.iterrows():
                importers.append((r, 1))
            for _, r in stores_sku.iterrows():
                if r["Store_name"] not in gom_names and r["Ton"] > 0:
                    exporters.append((r, "het"))  # rút hết, không giữ size tối thiểu (Mục 11.3)

        elif trang_thai == "Sắp hết hàng":
            pct = comp.top_pct_for(trang_thai, tong_ton_ma, lan)
            n_top = comp.top_n_stores(pct, so_ch_pham_vi)
            top_stores = set(stores_sku.head(n_top)["Store_name"])
            for _, r in stores_sku.iterrows():
                if r["Store_name"] in top_stores:
                    importers.append((r, 1))
                elif r["Ton"] > 0:
                    exporters.append((r, "het"))

        elif trang_thai == "Bán tốt":
            eligible = stores_sku[(stores_sku["Nhom"].isin(["A", "B", "C"])) &
                                   (stores_sku["So_thang_ton"].fillna(99) < 3)]
            tong_suat_chia_dukien = eligible["Suat_chia"].sum()
            chia_rong = tong_ton_ma >= tong_suat_chia_dukien and tong_suat_chia_dukien > 0
            if chia_rong:
                for _, r in eligible.iterrows():
                    importers.append((r, 2))
            else:
                pct = comp.top_pct_for(trang_thai, tong_ton_ma, lan)
                n_top = comp.top_n_stores(pct, so_ch_pham_vi)
                top_stores = stores_sku.head(n_top)
                for _, r in top_stores.iterrows():
                    importers.append((r, 2))
            for _, r in stores_sku.iterrows():
                if r["Nhom"] == "D" and r["Ton"] > 0:
                    exporters.append((r, "giu2"))

        elif trang_thai == "Bán trung bình – chậm":
            if lan == "Lan2":
                # Mục 11.2 — siết vai trò: chỉ nhóm A và CH gắn cờ BÁN HẾT được nhận;
                # nhóm B chỉ giữ; C-D là nguồn xuất; D xuất TOÀN BỘ không giữ size tối thiểu.
                for _, r in stores_sku.iterrows():
                    if r["Nhom"] == "A" or r.get("Co_BanHet") == "✓":
                        importers.append((r, 1))
                    elif r["Nhom"] == "D" and r["Ton"] > 0:
                        exporters.append((r, "het"))
                    elif r["Nhom"] == "C" and r["Ton"] > 0:
                        exporters.append((r, "giu2"))
                exporters.sort(key=lambda t: 0 if t[0]["Nhom"] == "D" else 1)
            else:
                for _, r in stores_sku.iterrows():
                    action = r["Hanh_dong_matran"]
                    if action in ("NHẬN ƯU TIÊN 1", "NHẬN BỔ SUNG (chỉ bù size gãy)"):
                        importers.append((r, 1 if action == "NHẬN ƯU TIÊN 1" else 3))
                    elif action == "NHẬN ƯU TIÊN 2":
                        importers.append((r, 2))
                    elif r.get("Co_BanHet") == "✓":
                        importers.append((r, 2))
                    elif action in ("XUẤT", "XUẤT MỘT PHẦN", "XUẤT — nguồn rút đầu tiên"):
                        exporters.append((r, "giu2"))
                exporters.sort(key=lambda t: 0 if t[0]["Nhom"] == "D" else 1)

        else:
            for _, r in stores_sku.iterrows():
                if r["Nhom"] == "A" or r.get("Co_BanHet") == "✓":
                    importers.append((r, 1))
            worst = stores_sku.sort_values("Chi_so_hieu_suat").query("Ton > 0")
            for _, r in worst.iterrows():
                exporters.append((r, "giu2"))

        importers.sort(key=lambda t: (t[1], -t[0]["Chi_so_hieu_suat"]))

        supply = {}
        for r, mode in exporters:
            st = r["Store_name"]
            reserve = set() if mode == "het" else reserve_default
            for sz in size_seq:
                q = inv_idx.get((pk, st, sz), 0)
                if q <= 0:
                    continue
                keep = 1 if sz in reserve else 0
                avail = max(0, q - keep)
                if avail > 0:
                    supply[(st, sz)] = supply.get((st, sz), 0) + avail

        for r, prio in importers:
            st = r["Store_name"]
            toc_do = r.get("Toc_do_ban") or 0
            ton_hien_co = r.get("Ton") or 0
            qty_target = compute_target_qty(toc_do, ton_hien_co)

            already = used_quota.get(st, 0)
            if qty_target <= 0:
                continue

            n_window = r.get("Suat_chia") or len(size_seq)
            window = comp.best_window(size_seq, weight_map, n_window)
            ton_by_size_r = {sz: inv_idx.get((pk, st, sz), 0) for sz in window}
            size_gay = [s for s in window if ton_by_size_r.get(s, 0) == 0]
            order = size_gay + [s for s in sorted(window, key=lambda s: -weight_map.get(s, 0)) if s not in size_gay]

            remaining = qty_target
            for sz in order:
                if remaining <= 0:
                    break
                candidates = [(k_, v) for k_, v in supply.items() if k_[1] == sz and v > 0]
                if not candidates:
                    continue
                ordered_candidates = _sort_by_distance(candidates, st, store_meta)
                lay = min(remaining, 1)
                for (src_store, src_size), avail in ordered_candidates:
                    if lay <= 0:
                        break
                    take = min(lay, avail, remaining)
                    if take <= 0:
                        continue
                    supply[(src_store, src_size)] -= take
                    remaining -= take
                    lay -= take
                    lien_noi = "Nội vùng" if store_meta.get(src_store, {}).get("Region") == store_meta.get(st, {}).get("Region") else "Liên vùng"
                    ly_do = "Bù size gãy" if sz in size_gay else "Tăng chiều sâu (tâm cửa sổ)"
                    if trang_thai == "Sắp hết hàng":
                        ly_do = "Gom về nhóm bán chạy"
                    detail_rows.append(dict(
                        Combined_PK=pk, Ten_san_pham=sku.get("Ten_san_pham"), Trang_thai_ma=trang_thai,
                        CH_xuat=src_store, Vung_xuat=store_meta.get(src_store, {}).get("Region"),
                        CH_nhan=st, Vung_nhan=store_meta.get(st, {}).get("Region"),
                        Size=sz, So_luong=take, Gia_ban=sku.get("Gia_ban"),
                        Gia_tri=take * (sku.get("Gia_ban") or 0), Noi_lien_vung=lien_noi, Ly_do=ly_do,
                        Lan_dieu_chuyen=lan,
                    ))
            used_quota[st] = already + (qty_target - remaining)

    detail_df = pd.DataFrame(detail_rows)
    return detail_df


def apply_batch_minimum(detail_df):
    if detail_df.empty:
        return detail_df
    grp = detail_df.groupby(["CH_xuat", "CH_nhan"]).agg(SL=("So_luong", "sum"), GT=("Gia_tri", "sum")).reset_index()
    grp["Dat_lo_toi_thieu"] = (grp["SL"] >= cfg.LO_TOI_THIEU_SL) | (grp["GT"] >= cfg.LO_TOI_THIEU_GIA_TRI)
    detail_df = detail_df.merge(grp[["CH_xuat", "CH_nhan", "Dat_lo_toi_thieu"]], on=["CH_xuat", "CH_nhan"], how="left")
    return detail_df

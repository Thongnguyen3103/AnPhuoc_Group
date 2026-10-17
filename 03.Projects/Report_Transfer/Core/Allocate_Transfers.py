# -*- coding: utf-8 -*-
"""TransferAllocator — Sinh lệnh điều chuyển chi tiết theo size, ghép nguồn theo khoảng cách."""
import pandas as pd
from Config import Config_Parameters as cfg
from Core.Compute_Metrics import MetricRules as comp


class TransferAllocator:
    """Sinh lệnh điều chuyển chi tiết theo size, ghép nguồn theo khoảng cách."""

    @staticmethod
    def _sort_by_distance(candidates, dest_store, store_meta):
        from Geo.Compute_Geo_Distance import GeoLocator as geo
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

    @staticmethod
    def _reserve_sizes(size_weight_map, k=cfg.GIU_LAI_SO_SIZE):
        ranked = sorted(size_weight_map.items(), key=lambda kv: -kv[1])
        return [s for s, _ in ranked[:k]]

    @staticmethod
    def _reserve_sizes_adjacent(size_seq, size_weight_map, k=cfg.GIU_LAI_SO_SIZE):
        """k size LIỀN KỀ trên trục size có tổng tỷ trọng bán cao nhất (Mục 8.3/8.4)."""
        return comp.best_window(size_seq, size_weight_map, k)

    @staticmethod
    def _gom_ma_gay(pk, sku, stores_sku, inv_idx, size_seq, store_meta, store_size_sales, pair_qty):
        """Mã gãy size — dồn TOÀN BỘ size còn hàng về 1–2 CH có số bán các size đó trong kỳ cao
        nhất (hoà → Hiệu suất kỳ, Hiệu suất CH). CH còn lại xuất hết (trừ CH bảo hộ / Không rút)."""
        import math
        stores = stores_sku["Store_name"].tolist()
        sizes_con = [sz for sz in size_seq if any(inv_idx.get((pk, st, sz), 0) > 0 for st in stores)]
        if not sizes_con:
            return []
        tong_ton = sum(inv_idx.get((pk, st, sz), 0) for st in stores for sz in sizes_con)
        n_nhan = 1 if tong_ton <= cfg.MA_GAY_TON_1_CH else cfg.MA_GAY_SO_CH_TOI_DA

        def score(r):
            ban = sum(store_size_sales.get((pk, r["Store_name"], sz), 0) for sz in sizes_con)
            return (ban, r.get("Hieu_suat_ky") or 0, r.get("Chi_so_hieu_suat") or 0)

        ranked = sorted((r for _, r in stores_sku.iterrows()), key=score, reverse=True)
        nhan = ranked[:n_nhan]
        nhan_names = {r["Store_name"] for r in nhan}
        supply = {}
        for r in ranked[n_nhan:]:
            if r.get("Bao_ho_CH_moi") == "✓" or r.get("Khong_rut") == "✓":
                continue
            for sz in sizes_con:
                q = inv_idx.get((pk, r["Store_name"], sz), 0)
                if q > 0:
                    supply[(r["Store_name"], sz)] = q
        quota = math.ceil(sum(supply.values()) / len(nhan)) if nhan else 0
        rows = []
        for r in nhan:
            st, con = r["Store_name"], quota
            for sz in sizes_con:
                if con <= 0:
                    break
                cand = [(k, v) for k, v in supply.items() if k[1] == sz and v > 0 and k[0] not in nhan_names]
                for (src, _sz), avail in TransferAllocator._sort_with_consolidation(cand, st, store_meta, pair_qty):
                    if con <= 0:
                        break
                    take = min(avail, con)
                    supply[(src, sz)] -= take
                    con -= take
                    pair_qty[(src, st)] = pair_qty.get((src, st), 0) + take
                    rows.append(dict(
                        Combined_PK=pk, Ten_san_pham=sku.get("Ten_san_pham"), Trang_thai_ma=sku["Trang_thai"],
                        CH_xuat=src, Vung_xuat=store_meta.get(src, {}).get("Region"),
                        CH_nhan=st, Vung_nhan=store_meta.get(st, {}).get("Region"),
                        Size=sz, So_luong=take, Gia_ban=sku.get("Gia_ban"),
                        Gia_tri=take * (sku.get("Gia_ban") or 0),
                        Noi_lien_vung="Nội vùng" if store_meta.get(src, {}).get("Region") == store_meta.get(st, {}).get("Region") else "Liên vùng",
                        Ly_do="Gom mã gãy size", Lan_dieu_chuyen=sku["Lan_dieu_chuyen"],
                    ))
        return rows

    last_skipped_cap = {}

    @staticmethod
    def _allocate_gom_theo_ton(pk, sku, stores_sku, inv_idx, size_seq, sizes_all, weight_map, store_meta,
                               pair_qty, used_nhom, detail_rows, sku_start, unmet_out, skipped_cap, kho_stock=None):
        """GOM THEO TỒN — mọi trạng thái, mọi Lần:
        1) T = tồn mục tiêu / điểm = số size bộ chính × GOM_CAI_MOI_SIZE[lần] (≥ TON_TOI_THIEU_SAU_DC);
           N = tồn phạm vi ÷ T (≥1) — số điểm bán phụ thuộc lượng tồn, không fix cứng.
        2) Xếp CH: cờ BÁN HẾT → Hiệu suất kỳ → Hiệu suất CH → đang có hàng. Lấy N CH đầu; CH đã nhận
           đủ hạn mức nhóm (1,5 tháng bán, cộng dồn các mã cùng nhóm) bị bỏ qua → CH kế tiếp thay.
        3) Mỗi điểm: mục tiêu = tồn ÷ N chia theo tỷ trọng size bộ chính (mỗi size ≥1). Cấp VÒNG TRÒN
           từng cái qua các điểm → không điểm nào (kể cả CH top 1) lấy quá phần chia đều.
        4) CH ngoài N (trừ Không rút / bảo hộ) rút hết về N điểm (điểm giữ ít size đó nhất nhận trước).
        5) Áp tồn tối thiểu (0 hoặc ≥3) + ghi nhu cầu chưa đủ cho bước chia kho."""
        import math
        from Geo.Compute_Geo_Distance import GeoLocator as geo
        lan = sku["Lan_dieu_chuyen"]
        k = cfg.GOM_CAI_MOI_SIZE.get(lan, 1.0)
        bo_set = {x for x in str(sku.get("Bo_size_chinh") or "").split(" · ") if x}
        bo_sizes = [s for s in size_seq if str(s) in bo_set] or list(size_seq)
        T = max(cfg.TON_TOI_THIEU_SAU_DC, math.ceil(len(bo_sizes) * k))

        rows_by = {r["Store_name"]: r for _, r in stores_sku.iterrows()}
        protected = {st for st, r in rows_by.items()
                     if r.get("Khong_rut") == "✓" or r.get("Bao_ho_CH_moi") == "✓"}
        hold = {(st, sz): inv_idx.get((pk, st, sz), 0) for st in rows_by for sz in sizes_all}
        tot = {st: sum(hold[(st, sz)] for sz in sizes_all) for st in rows_by}
        total = sum(tot.values())
        if total <= 0:
            return
        N = max(1, int(total // T))

        def rank_key(st):
            r = rows_by[st]
            return (r.get("Co_BanHet") == "✓", r.get("Hieu_suat_ky") or 0, r.get("Chi_so_hieu_suat") or 0, tot[st] > 0)

        ranked = sorted(rows_by, key=rank_key, reverse=True)
        share = total / N
        points, giu = [], set()   # giu: CH đã đủ hạn mức nhóm — giữ hàng, không nhận thêm, không bị rút
        for st in ranked:
            if len(points) + len(giu) >= N:
                break
            r = rows_by[st]
            nk, hm = r.get("Nhom_han_muc"), r.get("Han_muc_nhom")
            can_nhan = max(0, math.ceil(share) - tot[st])
            if nk is not None and hm is not None and not pd.isna(hm) and can_nhan > 0:
                if hm - used_nhom.get((st, nk), 0) < can_nhan:
                    skipped_cap[(st, nk)] = skipped_cap.get((st, nk), 0) + 1
                    if tot[st] > 0:
                        giu.add(st)
                    continue
            points.append(st)
        if not points:
            points = [ranked[0]]
        share = total / len(points)

        tong_w = sum(weight_map.get(s, 0) for s in bo_sizes)
        need = {}
        for p in points:
            for sz in bo_sizes:
                w = (weight_map.get(sz, 0) / tong_w) if tong_w else 1 / len(bo_sizes)
                need[(p, sz)] = max(0, max(1, round(share * w)) - hold[(p, sz)])
        pset = set(points) | giu
        if cfg.GOM_GIU_CH_DU_BO:
            # B2: CH ngoài N đang có bộ hợp lệ (≥ ngưỡng tồn, ≥ GIU_LAI_SO_SIZE size) → GIỮ (không rút, không nhận)
            for st in rows_by:
                if st not in pset and st not in protected and tot[st] >= cfg.TON_TOI_THIEU_SAU_DC \
                        and sum(1 for sz in sizes_all if hold[(st, sz)] > 0) >= cfg.GIU_LAI_SO_SIZE:
                    pset.add(st)
                    giu.add(st)
        supply = {(st, sz): hold[(st, sz)] for st in rows_by if st not in pset and st not in protected
                  for sz in sizes_all if hold[(st, sz)] > 0}
        # Kho làm nguồn bù thiếu TRƯỚC (CHIA_KHO_TRUOC / ô GUI) — chỉ dùng để bù, không nhận hàng rút về
        kho_names = set(kho_stock.get("__names__", ())) if kho_stock else set()
        for (kho_, sz_), q_ in (kho_stock.get(pk, {}) if kho_stock else {}).items():
            if q_ > 0:
                supply[(kho_, sz_)] = q_
                hold[(kho_, sz_)] = q_

        def kho_duoc_chia(kho_, p_):
            vung_kho = cfg.KHO_CHIA_THEO_VUNG.get(kho_)
            vung_p = rows_by[p_].get("Region")
            if vung_kho is not None:
                return vung_kho == vung_p
            rieng = [k_ for k_, v_ in cfg.KHO_CHIA_THEO_VUNG.items() if v_ == vung_p]
            return not rieng or cfg.KHO_RIENG_VUNG_LAY_THEM_KHO_CHUNG
        # Điểm bán DƯ nhiều hơn THIẾU → làm điểm CHO: chuyển phần dư từng size (trên mục tiêu size), không
        # nhận; điểm còn lại làm điểm NHẬN. Mỗi CH 1 vai trò / mã (không vừa xuất vừa nhận).
        donors = set()
        for p in points:
            if p in protected:
                continue
            du = {}
            for sz in bo_sizes:
                w = (weight_map.get(sz, 0) / tong_w) if tong_w else 1 / len(bo_sizes)
                muc_tieu = max(1, round(share * w))
                if hold[(p, sz)] > muc_tieu:
                    du[sz] = hold[(p, sz)] - muc_tieu
            thieu = sum(need[(p, sz)] for sz in bo_sizes)
            if sum(du.values()) > thieu:
                donors.add(p)
                for sz in bo_sizes:
                    need[(p, sz)] = 0
                for sz, q in du.items():
                    supply[(p, sz)] = supply.get((p, sz), 0) + q
        points = [p for p in points if p not in donors]
        if not points:
            TransferAllocator._enforce_min_stock(
                pk, sku, stores_sku, [], set(), sizes_all, inv_idx,
                detail_rows, sku_start, store_meta, pair_qty, used_nhom=used_nhom)
            return

        moves = {}

        def move(src, dst, sz, q=1):
            supply[(src, sz)] -= q
            hold[(src, sz)] -= q
            hold[(dst, sz)] += q
            moves[(src, dst, sz, "fill")] = moves.get((src, dst, sz, "fill"), 0) + q

        # 3) cấp vòng tròn từng cái — size gãy (thiếu nhiều) tự được ưu tiên vì need lớn hơn.
        # Điểm hết hạn mức nhóm (cộng dồn các mã trước + đã cấp ở mã này) thì dừng nhận.
        room = {}
        for p in points:
            r = rows_by[p]
            nk, hm = r.get("Nhom_han_muc"), r.get("Han_muc_nhom")
            room[p] = (hm - used_nhom.get((p, nk), 0)) if nk is not None and hm is not None and not pd.isna(hm) else float("inf")
        got = {p: 0 for p in points}
        for sz in bo_sizes:
            cand_cache = {}
            progress = True
            while progress:
                progress = False
                for p in points:
                    if need.get((p, sz), 0) <= 0:
                        continue
                    if got[p] >= room[p]:
                        for z_ in bo_sizes:
                            need[(p, z_)] = 0   # hết hạn mức: không nhận thêm, không đẩy sang kho
                        continue
                    if p not in cand_cache:
                        cand = [(key, v) for key, v in supply.items() if key[1] == sz and v > 0]
                        cand_cache[p] = [c[0][0] for c in TransferAllocator._sort_with_consolidation(cand, p, store_meta, pair_qty)]
                        if kho_names:   # kho trước (đúng vùng), rồi tới CH
                            cand_cache[p] = ([x for x in cand_cache[p] if x in kho_names and kho_duoc_chia(x, p)]
                                             + [x for x in cand_cache[p] if x not in kho_names])
                    srcs = [s_ for s_ in cand_cache[p] if supply.get((s_, sz), 0) > 0]
                    cand_cache[p] = srcs
                    if not srcs:
                        continue
                    move(srcs[0], p, sz)
                    pair_qty[(srcs[0], p)] = pair_qty.get((srcs[0], p), 0) + 1
                    need[(p, sz)] -= 1
                    got[p] += 1
                    progress = True
        if unmet_out is not None:
            for (p, sz), q in need.items():
                if q > 0:
                    unmet_out.append(dict(Combined_PK=pk, CH_nhan=p, Size=sz, SL_thieu=q, Gia_ban=sku.get("Gia_ban"),
                                          Trang_thai_ma=sku["Trang_thai"], Lan_dieu_chuyen=lan, Uu_tien=1))

        def moves_fill_total(mv):
            """SL đã cấp (bước 3) theo điểm nhận — để tính hạn mức còn lại."""
            out = {}
            for (s_, d_, z_, kind), q in mv.items():
                out[(d_, z_)] = out.get((d_, z_), 0) + q
            return out

        # 4) CH ngoài N: rút hết về N điểm (điểm còn hạn mức nhóm nhận trước)
        def dist(a, b):
            ma, mb = store_meta.get(a, {}), store_meta.get(b, {})
            km = geo.haversine_km(ma.get("Lat"), ma.get("Lon"), mb.get("Lat"), mb.get("Lon"))
            return km if km is not None else 99999

        nhan_them = {}

        def het_han_muc(g):
            r = rows_by[g]
            nk, hm = r.get("Nhom_han_muc"), r.get("Han_muc_nhom")
            if nk is None or hm is None or pd.isna(hm):
                return False
            return used_nhom.get((g, nk), 0) + nhan_them.get(g, 0) >= hm

        for (src, sz), q in moves_fill_total(moves).items():
            nhan_them[src] = nhan_them.get(src, 0) + q
        # Mọi điểm đã đủ hạn mức → MỞ THÊM điểm: CH xếp hạng kế tiếp còn hạn mức, chưa xuất cái nào
        # ở mã này (1 vai trò / mã); CH đó giữ lại hàng đang có (bỏ khỏi nguồn rút).
        da_xuat = {s_ for (s_, _d, _z, _k) in moves}

        def mo_them_diem(src_dang_rut):
            for st in ranked:
                if st in points or st in giu or st in donors or st in da_xuat or st == src_dang_rut:
                    continue
                if het_han_muc(st):
                    continue
                for key_ in [k_ for k_ in supply if k_[0] == st]:
                    supply[key_] = 0
                points.append(st)
                return st
            return None

        for (src, sz) in sorted(k_ for k_, v in supply.items() if v > 0 and k_[0] not in kho_names):
            q = supply[(src, sz)]
            while q > 0:
                con_han_muc = [g for g in points if not het_han_muc(g)]
                if not con_han_muc and mo_them_diem(src):
                    con_han_muc = [points[-1]]
                dst = min(con_han_muc or points, key=lambda g: (hold[(g, sz)], dist(src, g)))
                da_xuat.add(src)
                nhan_them[dst] = nhan_them.get(dst, 0) + 1
                supply[(src, sz)] -= 1
                hold[(src, sz)] -= 1
                hold[(dst, sz)] += 1
                moves[(src, dst, sz, "push")] = moves.get((src, dst, sz, "push"), 0) + 1
                pair_qty[(src, dst)] = pair_qty.get((src, dst), 0) + 1
                q -= 1

        if kho_names:   # ghi lại tồn kho còn lại cho các mã sau / bước chia kho phần thiếu
            kho_stock[pk] = {k_: v for k_, v in supply.items() if k_[0] in kho_names}
        nk_of = {st: rows_by[st].get("Nhom_han_muc") for st in points}
        for (src, dst, sz, kind), q in moves.items():
            if nk_of.get(dst) is not None:
                used_nhom[(dst, nk_of[dst])] = used_nhom.get((dst, nk_of[dst]), 0) + q
            detail_rows.append(dict(
                Combined_PK=pk, Ten_san_pham=sku.get("Ten_san_pham"), Trang_thai_ma=sku["Trang_thai"],
                CH_xuat=src, Vung_xuat=store_meta.get(src, {}).get("Region"),
                CH_nhan=dst, Vung_nhan=store_meta.get(dst, {}).get("Region"),
                Size=sz, So_luong=q, Gia_ban=sku.get("Gia_ban"), Gia_tri=q * (sku.get("Gia_ban") or 0),
                Noi_lien_vung="Nội vùng" if store_meta.get(src, {}).get("Region") == store_meta.get(dst, {}).get("Region") else "Liên vùng",
                Ly_do="Bù đủ size điểm bán" if kind == "fill" else "Rút về điểm bán",
                Lan_dieu_chuyen=lan,
            ))
        TransferAllocator._enforce_min_stock(
            pk, sku, stores_sku, [rows_by[p] for p in points], set(), sizes_all, inv_idx,
            detail_rows, sku_start, store_meta, pair_qty, used_nhom=used_nhom)

    @staticmethod
    def _enforce_min_stock(pk, sku, stores_sku, importer_rows, exporter_names, size_seq, inv_idx,
                           detail_rows, sku_start, store_meta, pair_qty, used_nhom=None):
        """Sau điều chuyển, mỗi CH × mã phải còn 0 hoặc ≥ cfg.TON_TOI_THIEU_SAU_DC cái (mọi trạng thái):
        1) CH nhận mà tồn sau nhận vẫn < ngưỡng → huỷ các lệnh nhận của CH đó (hàng ở lại nguồn);
        2) CH còn 1..ngưỡng-1 cái, hoặc CH đã xuất mà còn < GIU_LAI_SO_SIZE size → rút nốt toàn bộ
           về các CH đang giữ ≥ ngưỡng (ưu tiên CH nhận của mã; không có thì CH giữ nhiều/hiệu suất
           cao nhất). Mỗi cái giao cho CH có size đó trong cửa sổ, đang giữ ÍT size đó nhất, hoà → gần hơn.
        CH 'Không rút' / bảo hộ không bị rút. Sửa detail_rows tại chỗ (các dòng từ sku_start)."""
        from Geo.Compute_Geo_Distance import GeoLocator as geo
        MIN = cfg.TON_TOI_THIEU_SAU_DC
        rows_by = {r["Store_name"]: r for _, r in stores_sku.iterrows()}
        stores = list(rows_by)
        protected = {st for st, r in rows_by.items()
                     if r.get("Khong_rut") == "✓" or r.get("Bao_ho_CH_moi") == "✓"}
        importer_names = [r["Store_name"] for r in importer_rows]

        def holdings():
            h = {(st, sz): inv_idx.get((pk, st, sz), 0) for st in stores for sz in size_seq}
            out_q = {}
            for d in detail_rows[sku_start:]:
                h[(d["CH_xuat"], d["Size"])] = h.get((d["CH_xuat"], d["Size"]), 0) - d["So_luong"]
                h[(d["CH_nhan"], d["Size"])] = h.get((d["CH_nhan"], d["Size"]), 0) + d["So_luong"]
                out_q[d["CH_xuat"]] = out_q.get(d["CH_xuat"], 0) + d["So_luong"]
            tot = {}
            for (st, _sz), q in h.items():
                tot[st] = tot.get(st, 0) + q
            return h, tot, out_q

        # 1) huỷ lệnh nhận khiến CH nhận vẫn < ngưỡng (lặp vì huỷ có thể làm đổi tồn nguồn)
        for _ in range(5):
            h, tot, _o = holdings()
            recv = {d["CH_nhan"] for d in detail_rows[sku_start:]}
            bad = {st for st in recv if 0 < tot.get(st, 0) < MIN}
            if not bad:
                break
            keep = [d for d in detail_rows[sku_start:] if d["CH_nhan"] not in bad]
            for d in detail_rows[sku_start:]:
                if d["CH_nhan"] in bad:
                    k = (d["CH_xuat"], d["CH_nhan"])
                    pair_qty[k] = pair_qty.get(k, 0) - d["So_luong"]
            del detail_rows[sku_start:]
            detail_rows.extend(keep)

        # 2) rút nốt tồn lẻ
        h, tot, out_q = holdings()
        small = set()
        for st in stores:
            t = tot.get(st, 0)
            if st in protected or t <= 0:
                continue
            so_size = sum(1 for sz in size_seq if h.get((st, sz), 0) > 0)
            if t < MIN or (out_q.get(st, 0) > 0 and so_size < cfg.GIU_LAI_SO_SIZE):
                small.add(st)
        if not small:
            return
        dests = [st for st in importer_names if tot.get(st, 0) >= MIN and st not in small and st not in out_q]
        if not dests:
            dests = [st for st in stores if tot.get(st, 0) >= MIN and st not in small and st not in out_q]
        if not dests:
            # mọi CH đều lẻ → gom về 1 CH giữ nhiều nhất / hiệu suất cao nhất
            best = max(small, key=lambda st: (tot.get(st, 0), rows_by[st].get("Chi_so_hieu_suat") or 0))
            small.discard(best)
            dests = [best]
        # Không giới hạn top-N theo hiệu suất (tránh dồn về CH top) — rải đều theo "giữ ít size đó nhất",
        # CH còn hạn mức nhận nhóm được ưu tiên.
        used_nhom = used_nhom if used_nhom is not None else {}
        them = {}

        def het_han_muc(g):
            r = rows_by[g]
            nk, hm = r.get("Nhom_han_muc"), r.get("Han_muc_nhom")
            if nk is None or hm is None or pd.isna(hm):
                return False
            return used_nhom.get((g, nk), 0) + them.get(g, 0) >= hm

        window = {st: set(rows_by[st].get("Cua_so_list") or []) for st in dests}

        def dist(a, b):
            ma, mb = store_meta.get(a, {}), store_meta.get(b, {})
            km = geo.haversine_km(ma.get("Lat"), ma.get("Lon"), mb.get("Lat"), mb.get("Lon"))
            return km if km is not None else 99999

        moves = {}
        for src in sorted(small):
            for sz in size_seq:
                q = h.get((src, sz), 0)
                if q <= 0:
                    continue
                cand = [g for g in dests if g != src and sz in window.get(g, ())] or [g for g in dests if g != src]
                while q > 0 and cand:
                    dst = min(cand, key=lambda g: (het_han_muc(g), h.get((g, sz), 0), dist(src, g)))
                    them[dst] = them.get(dst, 0) + 1
                    h[(dst, sz)] = h.get((dst, sz), 0) + 1
                    h[(src, sz)] -= 1
                    q -= 1
                    moves[(src, dst, sz)] = moves.get((src, dst, sz), 0) + 1
        for (src, dst, sz), q in moves.items():
            pair_qty[(src, dst)] = pair_qty.get((src, dst), 0) + q
            nk = rows_by[dst].get("Nhom_han_muc")
            if nk is not None:
                used_nhom[(dst, nk)] = used_nhom.get((dst, nk), 0) + q
            detail_rows.append(dict(
                Combined_PK=pk, Ten_san_pham=sku.get("Ten_san_pham"), Trang_thai_ma=sku["Trang_thai"],
                CH_xuat=src, Vung_xuat=store_meta.get(src, {}).get("Region"),
                CH_nhan=dst, Vung_nhan=store_meta.get(dst, {}).get("Region"),
                Size=sz, So_luong=q, Gia_ban=sku.get("Gia_ban"), Gia_tri=q * (sku.get("Gia_ban") or 0),
                Noi_lien_vung="Nội vùng" if store_meta.get(src, {}).get("Region") == store_meta.get(dst, {}).get("Region") else "Liên vùng",
                Ly_do=f"Rút nốt tồn lẻ (<{MIN} cái)", Lan_dieu_chuyen=sku["Lan_dieu_chuyen"],
            ))

    @staticmethod
    def size_needs(window, size_gay, weight_map, ton_by_size, ton_muc_tieu):
        """Mục 6 — nhu cầu nhận theo size: tồn mục tiêu của CH chia theo tỷ trọng bán các
        size trong cửa sổ, trừ tồn hiện có của size đó. Size gãy nhận tối thiểu 1."""
        tong_w = sum(weight_map.get(s, 0) for s in window)
        out = {}
        for s in window:
            w = (weight_map.get(s, 0) / tong_w) if tong_w else (1 / len(window))
            need = max(0, round(ton_muc_tieu * w - ton_by_size.get(s, 0)))
            if s in size_gay:
                need = max(need, 1)
            out[s] = need
        return out

    @staticmethod
    def _sort_with_consolidation(candidates, dest_store, store_meta, pair_qty, km_them=None):
        """Mục 7C — gom chuyến: trong các nguồn đã sắp theo khoảng cách, ưu tiên nguồn ĐÃ CÓ
        chuyến tới CH nhận này trong đợt, nếu chỉ xa hơn nguồn gần nhất không quá km_them."""
        from Geo.Compute_Geo_Distance import GeoLocator as geo
        km_them = cfg.GOM_CHUYEN_KM_THEM if km_them is None else km_them
        ordered = TransferAllocator._sort_by_distance(candidates, dest_store, store_meta)
        if not pair_qty or not ordered:
            return ordered
        dest = store_meta.get(dest_store, {})

        def dist(src):
            s = store_meta.get(src, {})
            return geo.haversine_km(dest.get("Lat"), dest.get("Lon"), s.get("Lat"), s.get("Lon"))

        d_min = dist(ordered[0][0][0])
        dest_region = dest.get("Region")

        def ok_gom(src):
            if (src, dest_store) not in pair_qty:
                return False
            d = dist(src)
            if d is None or d_min is None:
                # thiếu toạ độ: chỉ gom khi cùng vùng với CH nhận
                return store_meta.get(src, {}).get("Region") == dest_region
            return d <= d_min + km_them

        gom = [c for c in ordered if ok_gom(c[0][0])]
        gom.sort(key=lambda c: -pair_qty[(c[0][0], dest_store)])   # chuyến đang lớn nhất trước
        gom_keys = {c[0] for c in gom}
        return gom + [c for c in ordered if c[0] not in gom_keys]

    @staticmethod
    def build_warehouse_orders(unmet_df, inv_kho, store_meta, hold_after=None):
        """Đề xuất chia từ KHO đi CH (Sheet 7) cho phần nhu cầu CH nhận CHƯA được đáp ứng
        bởi điều chuyển giữa các CH. Kho riêng vùng (cfg.KHO_CHIA_THEO_VUNG) chỉ đi CH đúng
        vùng và được lấy TRƯỚC; kho chung (cfg.KHO_CHIA_CHUNG) đi mọi vùng."""
        cols = ["Combined_PK", "Size", "Kho_xuat", "CH_nhan", "Vung_nhan", "SL_chia", "Gia_ban",
                "Gia_tri", "SL_thieu_ban_dau", "Trang_thai_ma", "Lan_dieu_chuyen"]
        if unmet_df is None or unmet_df.empty or inv_kho is None or inv_kho.empty:
            return pd.DataFrame(columns=cols)
        stock = inv_kho.groupby(["Combined_PK", "Store_name", "Size"])["Qty_TonKho"].sum().to_dict()
        rows = []
        unmet_df = unmet_df.sort_values(["Uu_tien"], kind="stable")
        for _, u in unmet_df.iterrows():
            st = u["CH_nhan"]
            vung = store_meta.get(st, {}).get("Region")
            kho_rieng = [k for k, v in cfg.KHO_CHIA_THEO_VUNG.items() if v == vung]
            kho_list = kho_rieng + list(cfg.KHO_CHIA_CHUNG)
            if kho_rieng and not cfg.KHO_RIENG_VUNG_LAY_THEM_KHO_CHUNG:
                kho_list = kho_rieng
            con = int(u["SL_thieu"])
            for kho in kho_list:
                if con <= 0:
                    break
                key = (u["Combined_PK"], kho, u["Size"])
                co = int(stock.get(key, 0))
                if co <= 0:
                    continue
                lay = min(con, co)
                stock[key] = co - lay
                con -= lay
                rows.append(dict(Combined_PK=u["Combined_PK"], Size=u["Size"], Kho_xuat=kho, CH_nhan=st,
                                 Vung_nhan=vung, SL_chia=lay, Gia_ban=u["Gia_ban"],
                                 Gia_tri=lay * (u["Gia_ban"] or 0), SL_thieu_ban_dau=int(u["SL_thieu"]),
                                 Trang_thai_ma=u["Trang_thai_ma"], Lan_dieu_chuyen=u["Lan_dieu_chuyen"]))
        df = pd.DataFrame(rows, columns=cols)
        if hold_after is not None and not df.empty:
            # tồn tối thiểu: CH đang 0 cái mà kho chỉ chia 1..ngưỡng-1 cái → bỏ (không tạo tồn lẻ)
            g = df.groupby(["Combined_PK", "CH_nhan"])["SL_chia"].sum()
            bo = {k for k, q in g.items()
                  if 0 < hold_after.get(k, 0) + q < cfg.TON_TOI_THIEU_SAU_DC}
            df = df[[(p, c) not in bo for p, c in zip(df["Combined_PK"], df["CH_nhan"])]]
        return df

    @staticmethod
    def compute_target_qty(toc_do_ban_ch, ton_hien_co, he_so=cfg.TON_MUC_TIEU_HE_SO):
        return max(0, round(toc_do_ban_ch * he_so - ton_hien_co))

    @staticmethod
    def build_transfer_orders(df_sku, df_store, inv_by_size, size_weight_by_sku, size_seq_by_sku,
                               so_ch_pham_vi, master_lookup, store_meta, unmet_out=None, store_size_sales=None,
                               kho_stock=None):
        """Trả về detail_df — lệnh điều chuyển chi tiết theo size.

        Ghi chú: Pha 2 (cắt giảm khi tổng nhu cầu vượt hạn mức cộng dồn nhiều mã cùng
        đợt — xem README Mục 5.3) CHƯA được cài trong bản này; nếu cần, bổ sung một hàm
        riêng nhận vào detail_df + han_muc_nhan_ch rồi cắt giảm/gắn cờ trước khi ghi Excel."""
        detail_rows = []
        pair_qty = {}   # (CH xuất, CH nhận) -> SL đã lên lệnh trong đợt (gom chuyến Mục 7C)
        used_nhom = {}  # (CH nhận, khóa nhóm) -> SL đã nhận trong đợt (hạn mức nhóm Mục 8)
        skipped_cap = TransferAllocator.last_skipped_cap = {}   # (CH, khóa nhóm) -> số mã bị loại do hết hạn mức

        inv_idx = inv_by_size.set_index(["Combined_PK", "Store_name", "Size"])["Qty_TonKho"].to_dict()
        inv_sizes = inv_by_size.groupby("Combined_PK")["Size"].unique().to_dict()
        used_quota = {}

        for _, sku in df_sku.iterrows():
            pk = sku["Combined_PK"]
            sku_start = len(detail_rows)   # các dòng lệnh của mã này = detail_rows[sku_start:]
            if sku["Lan_dieu_chuyen"] not in ("Lan1", "Lan2", "Lan3"):
                continue
            if sku.get("De_xuat_sale"):
                continue   # tồn phạm vi < ngưỡng tối thiểu: để nguyên, đề xuất sale/thanh lý (Sheet 1)
            trang_thai = sku["Trang_thai"]
            lan = sku["Lan_dieu_chuyen"]
            stores_sku = df_store[df_store["Combined_PK"] == pk].copy()
            if stores_sku.empty:
                continue
            weight_map = size_weight_by_sku.get(pk, {})
            size_seq = size_seq_by_sku.get(pk, sorted(weight_map.keys()))
            reserve_default = set(TransferAllocator._reserve_sizes_adjacent(size_seq, weight_map))

            stores_sku = stores_sku.sort_values("Chi_so_hieu_suat", ascending=False)
            tong_ton_ma = sku["Tong_ton"]

            importers, exporters = [], []

            # ---- MÃ GÃY SIZE: không rải — gom size còn lại về 1–2 CH bán các size đó tốt nhất ----
            if sku.get("Ma_gay_size") == "✓":
                detail_rows.extend(TransferAllocator._gom_ma_gay(
                    pk, sku, stores_sku, inv_idx, size_seq, store_meta, store_size_sales or {}, pair_qty))
                gay_nhan = {d["CH_nhan"] for d in detail_rows[sku_start:]}
                sizes_all = list(size_seq) + [z for z in inv_sizes.get(pk, []) if z not in set(size_seq)]
                TransferAllocator._enforce_min_stock(
                    pk, sku, stores_sku, [r for _, r in stores_sku.iterrows() if r["Store_name"] in gay_nhan],
                    set(), sizes_all, inv_idx, detail_rows, sku_start, store_meta, pair_qty)
                continue

            # ---- GOM THEO TỒN: 1 công thức chung cho mọi trạng thái / mọi Lần ----
            if cfg.CHE_DO_PHAN_BO == "GOM_THEO_TON":
                sizes_all = list(size_seq) + [z for z in inv_sizes.get(pk, []) if z not in set(size_seq)]
                TransferAllocator._allocate_gom_theo_ton(
                    pk, sku, stores_sku, inv_idx, size_seq, sizes_all, weight_map, store_meta, pair_qty,
                    used_nhom, detail_rows, sku_start, unmet_out, skipped_cap, kho_stock=kho_stock)
                continue

            # ---- LẦN 3: gom điểm theo ma trận xu hướng (Mục 11.3/12), KHÔNG lặp lại Lần 2 ----
            if lan == "Lan3" and trang_thai != "Bán rất chậm":
                has_trend = stores_sku["Hanh_dong_L3"].notna().any() if "Hanh_dong_L3" in stores_sku.columns else False
                if has_trend:
                    gom = stores_sku[stores_sku["Hanh_dong_L3"].isin(["ĐIỂM GOM CHÍNH", "ƯU TIÊN NHẬN"])]
                    gom = gom.sort_values(["Hanh_dong_L3", "Hieu_suat_ky"], ascending=[True, False])
                else:
                    # Chưa có Hiệu suất kỳ Lần 2 lưu trong Data/lich_su_hieu_suat_ky.json (chưa
                    # chạy Lần 2 qua công cụ) — fallback: gom về CH có Hiệu suất kỳ cao nhất.
                    gom = stores_sku.sort_values("Hieu_suat_ky", ascending=False)
                # Số điểm gom theo lượng tồn còn lại: tồn ÷ suất chia TB (1 bộ size), trong [1, MAX]
                suat_tb = stores_sku["Suat_chia"].mean() if "Suat_chia" in stores_sku.columns else 0
                n_gom = int(stores_sku["Ton"].sum() // suat_tb) if suat_tb else cfg.GOM_DIEM_L3_MAX
                gom = gom.head(max(1, min(cfg.GOM_DIEM_L3_MAX, n_gom)))
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

            # Mỗi CH chỉ giữ 1 vai trò trong cùng 1 mã: CH đã là CH nhận thì không làm nguồn xuất.
            importer_names = {r["Store_name"] for r, _ in importers}
            exporters = [(r, m) for r, m in exporters if r["Store_name"] not in importer_names]
            # CH bảo hộ (CH mới) chỉ được nhận, không bị rút hàng.
            exporters = [(r, m) for r, m in exporters if r.get("Bao_ho_CH_moi") != "✓"]
            # CH chọn tay "Không rút" trên GUI (CH mới / CH không tham gia rút) — chỉ nhận.
            exporters = [(r, m) for r, m in exporters if r.get("Khong_rut") != "✓"]

            importers.sort(key=lambda t: (t[1], -t[0]["Chi_so_hieu_suat"]))

            supply = {}
            for r, mode in exporters:
                st = r["Store_name"]
                if mode == "het":
                    reserve = set()
                else:
                    sizes_co = [sz for sz in size_seq if inv_idx.get((pk, st, sz), 0) > 0]
                    reserve = set(TransferAllocator._reserve_sizes_adjacent(sizes_co, weight_map))
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
                qty_target = TransferAllocator.compute_target_qty(toc_do, ton_hien_co)

                already = used_quota.get(st, 0)
                # Mục 8 — hạn mức nhận theo nhóm hàng (cộng dồn mọi mã cùng nhóm trong đợt)
                nhom_key = r.get("Nhom_han_muc")
                if nhom_key is not None:
                    han_muc = r.get("Han_muc_nhom")
                    suat = r.get("Suat_chia") or 0
                    if han_muc is not None and not pd.isna(han_muc) and han_muc >= suat:
                        room = han_muc - used_nhom.get((st, nhom_key), 0)
                    else:
                        # chưa bán nhóm (hoặc bán quá ít, hạn mức < suất chia) → tối đa suất chia / mã
                        room = suat
                    qty_target = min(qty_target, max(0, int(room)))
                if qty_target <= 0:
                    continue

                # Mục 5: dùng ĐÚNG cửa sổ size / size gãy đã tính ở Sheet 2 (lịch sử CH → vùng →
                # toàn HT + Phụ lục B). Thiếu cột (dữ liệu cũ) → tính lại theo toàn hệ thống.
                window = r.get("Cua_so_list")
                if not isinstance(window, list) or not window:
                    n_window = r.get("Suat_chia") or len(size_seq)
                    window = comp.best_window(size_seq, weight_map, n_window)
                ton_by_size_r = {sz: inv_idx.get((pk, st, sz), 0) for sz in window}
                size_gay = r.get("Size_gay_list")
                if not isinstance(size_gay, list):
                    size_gay = [s for s in window if ton_by_size_r.get(s, 0) == 0]
                order = size_gay + [s for s in sorted(window, key=lambda s: -weight_map.get(s, 0)) if s not in size_gay]
                # Mục 6: nhu cầu từng size = tồn mục tiêu × tỷ trọng size (trong cửa sổ) − tồn size;
                # size gãy tối thiểu 1. Tổng không vượt qty_target.
                size_need = TransferAllocator.size_needs(window, size_gay, weight_map, ton_by_size_r,
                                                         toc_do * cfg.TON_MUC_TIEU_HE_SO)

                remaining = qty_target
                for sz in order:
                    if remaining <= 0:
                        break
                    need_sz = min(size_need.get(sz, 0), remaining)
                    if need_sz <= 0:
                        continue
                    candidates = [(k_, v) for k_, v in supply.items() if k_[1] == sz and v > 0 and k_[0] != st]
                    if not candidates:
                        if unmet_out is not None:
                            unmet_out.append(dict(Combined_PK=pk, CH_nhan=st, Size=sz, SL_thieu=need_sz,
                                                  Gia_ban=sku.get("Gia_ban"), Trang_thai_ma=trang_thai,
                                                  Lan_dieu_chuyen=lan, Uu_tien=prio))
                        continue
                    ordered_candidates = TransferAllocator._sort_with_consolidation(
                        candidates, st, store_meta, pair_qty)
                    lay = need_sz
                    for (src_store, src_size), avail in ordered_candidates:
                        if lay <= 0:
                            break
                        take = min(lay, avail, remaining)
                        if take <= 0:
                            continue
                        supply[(src_store, src_size)] -= take
                        remaining -= take
                        lay -= take
                        pair_qty[(src_store, st)] = pair_qty.get((src_store, st), 0) + take
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
                    if lay > 0 and unmet_out is not None:
                        unmet_out.append(dict(Combined_PK=pk, CH_nhan=st, Size=sz, SL_thieu=lay,
                                              Gia_ban=sku.get("Gia_ban"), Trang_thai_ma=trang_thai,
                                              Lan_dieu_chuyen=lan, Uu_tien=prio))
                used_quota[st] = already + (qty_target - remaining)
                if nhom_key is not None:
                    used_nhom[(st, nhom_key)] = used_nhom.get((st, nhom_key), 0) + (qty_target - remaining)

            # ---- TỒN TỐI THIỂU SAU ĐIỀU CHUYỂN (mọi trạng thái): mỗi CH × mã còn 0 hoặc ≥ ngưỡng;
            # CH đã xuất còn lại phải đủ GIU_LAI_SO_SIZE size. ----
            sizes_all = list(size_seq) + [z for z in inv_sizes.get(pk, []) if z not in set(size_seq)]
            TransferAllocator._enforce_min_stock(
                pk, sku, stores_sku, [r for r, _p in importers], {r["Store_name"] for r, _m in exporters},
                sizes_all, inv_idx, detail_rows, sku_start, store_meta, pair_qty)

        detail_df = pd.DataFrame(detail_rows)
        return detail_df

    @staticmethod
    def optimize_trips(detail_df, inv_by_size, df_sku, store_meta, kho_names=()):
        """B5 — Lập lại lệnh từng mã theo bài toán vận tải TỐI THIỂU SỐ CHUYẾN trên chênh lệch tồn đầu → cuối
        (tồn cuối từng CH giữ nguyên), cặp CH đã có chuyến ở mã trước rẻ hơn (gom chuyến giữa các mã). Sau đó bỏ
        chuyến ≤ TOI_UU_BO_CHUYEN_LE_MAX cái chỉ thêm chiều sâu (nơi nhận đã có size đó) nếu 2 đầu vẫn đạt tồn
        cuối 0 hoặc ≥ ngưỡng. Lệnh từ kho giữ nguyên."""
        from Core.Allocate_By_SellThrough import SellThroughAllocator as SA
        if detail_df is None or detail_df.empty:
            return detail_df
        kho_names = set(kho_names)
        h0 = inv_by_size.groupby(["Combined_PK", "Store_name", "Size"])["Qty_TonKho"].sum().to_dict()
        info = df_sku.set_index("Combined_PK")
        rows, used = [], set()
        for pk, g in detail_df.groupby("Combined_PK", sort=False):
            net = {}
            for r in g.itertuples():
                net[(r.CH_xuat, r.Size)] = net.get((r.CH_xuat, r.Size), 0) - r.So_luong
                net[(r.CH_nhan, r.Size)] = net.get((r.CH_nhan, r.Size), 0) + r.So_luong
            sur = {k: -v for k, v in net.items() if v < 0}
            dem = {k: v for k, v in net.items() if v > 0}
            gia = g["Gia_ban"].iloc[0]
            sku = info.loc[pk] if pk in info.index else {}
            for s, t, z, q in SA.min_trip_orders(sur, dem, store_meta, used, time_limit=cfg.TOI_UU_SO_CHUYEN_GIAY):
                used.add((s, t))
                rs, rd = store_meta.get(s, {}).get("Region"), store_meta.get(t, {}).get("Region")
                ly_do = ("Lấy từ Kho" if s in kho_names else
                         "Bù size gãy" if h0.get((pk, t, z), 0) <= 0 else "Gom về điểm bán")
                rows.append(dict(
                    Combined_PK=pk, Ten_san_pham=sku.get("Ten_san_pham"), Trang_thai_ma=sku.get("Trang_thai"),
                    CH_xuat=s, Vung_xuat=rs, CH_nhan=t, Vung_nhan=rd, Size=z, So_luong=q, Gia_ban=gia,
                    Gia_tri=q * (gia or 0), Noi_lien_vung="Nội vùng" if rs == rd else "Liên vùng",
                    Ly_do=ly_do, Lan_dieu_chuyen=sku.get("Lan_dieu_chuyen"),
                ))
        d1 = pd.DataFrame(rows)
        if d1.empty:
            return d1
        # bỏ chuyến lẻ chỉ thêm chiều sâu
        MIN = cfg.TON_TOI_THIEU_SAU_DC
        tot = {}
        for (p, s_, z), v in h0.items():
            tot[(p, s_)] = tot.get((p, s_), 0) + v
        for r in d1.itertuples():
            tot[(r.Combined_PK, r.CH_xuat)] = tot.get((r.Combined_PK, r.CH_xuat), 0) - r.So_luong
            tot[(r.Combined_PK, r.CH_nhan)] = tot.get((r.Combined_PK, r.CH_nhan), 0) + r.So_luong
        by_trip = {k: g for k, g in d1.groupby(["CH_xuat", "CH_nhan"])}
        drop = []
        for (s_, t), lines in by_trip.items():
            if s_ in kho_names or lines["So_luong"].sum() > cfg.TOI_UU_BO_CHUYEN_LE_MAX:
                continue
            if not all(h0.get((r.Combined_PK, t, r.Size), 0) > 0 for r in lines.itertuples()):
                continue                      # có bù size gãy → giữ chuyến
            delta = {}
            for r in lines.itertuples():
                delta[(r.Combined_PK, s_)] = delta.get((r.Combined_PK, s_), 0) + r.So_luong
                delta[(r.Combined_PK, t)] = delta.get((r.Combined_PK, t), 0) - r.So_luong
            if all((tot.get(k, 0) + dv == 0) or (tot.get(k, 0) + dv >= MIN) for k, dv in delta.items()):
                for k, dv in delta.items():
                    tot[k] = tot.get(k, 0) + dv
                drop.extend(lines.index)
        return d1.drop(index=drop).reset_index(drop=True)

    @staticmethod
    def validate_orders(detail_df, df_store, inv_by_size, nhan_them=None):
        """Kiểm tra ràng buộc lệnh sau phân bổ — trả về list cảnh báo (rỗng = đạt).
        Không chặn chạy, chỉ để ghi log."""
        if detail_df.empty:
            return []
        warns = []
        n_self = int((detail_df["CH_xuat"] == detail_df["CH_nhan"]).sum())
        if n_self:
            warns.append(f"{n_self} dòng lệnh có CH xuất = CH nhận.")
        xuat = detail_df[["Combined_PK", "CH_xuat"]].drop_duplicates()
        nhan = detail_df[["Combined_PK", "CH_nhan"]].drop_duplicates()
        both = xuat.merge(nhan, left_on=["Combined_PK", "CH_xuat"], right_on=["Combined_PK", "CH_nhan"])
        if len(both):
            warns.append(f"{len(both)} cặp (mã, CH) vừa xuất vừa nhận.")
        if "Bao_ho_CH_moi" in df_store.columns:
            bao_ho = set(zip(df_store.loc[df_store["Bao_ho_CH_moi"] == "✓", "Combined_PK"],
                             df_store.loc[df_store["Bao_ho_CH_moi"] == "✓", "Store_name"]))
            n_bh = sum(1 for k in zip(xuat["Combined_PK"], xuat["CH_xuat"]) if k in bao_ho)
            if n_bh:
                warns.append(f"{n_bh} cặp (mã, CH bảo hộ) bị xuất hàng.")
        inv_idx = inv_by_size.groupby(["Combined_PK", "Store_name", "Size"])["Qty_TonKho"].sum()
        xuat_sz = detail_df.groupby(["Combined_PK", "CH_xuat", "Size"])["So_luong"].sum()
        ton = inv_idx.reindex(xuat_sz.index).fillna(0)
        n_vuot = int((xuat_sz.values > ton.values).sum())
        if n_vuot:
            warns.append(f"{n_vuot} (mã, CH, size) xuất vượt tồn.")
        ton = inv_by_size.groupby(["Combined_PK", "Store_name"])["Qty_TonKho"].sum()
        ra = detail_df.groupby(["Combined_PK", "CH_xuat"])["So_luong"].sum().rename_axis(ton.index.names)
        vao = detail_df.groupby(["Combined_PK", "CH_nhan"])["So_luong"].sum().rename_axis(ton.index.names)
        cuoi = ton.sub(ra, fill_value=0).add(vao, fill_value=0)
        if nhan_them is not None and not nhan_them.empty:   # hàng lấy từ kho trước (Sheet 7)
            cuoi = cuoi.add(nhan_them.groupby(["Combined_PK", "CH_nhan"])["So_luong"].sum()
                            .rename_axis(ton.index.names), fill_value=0)
        if "Khong_rut" in df_store.columns or "Bao_ho_CH_moi" in df_store.columns:
            prot = df_store[(df_store.get("Khong_rut") == "✓") | (df_store.get("Bao_ho_CH_moi") == "✓")]
            prot_set = set(zip(prot["Combined_PK"], prot["Store_name"]))
            cuoi = cuoi[[k not in prot_set for k in cuoi.index]]
        co_lenh = set(detail_df["Combined_PK"])
        n_le = int(((cuoi > 0) & (cuoi < cfg.TON_TOI_THIEU_SAU_DC)
                    & cuoi.index.get_level_values(0).isin(co_lenh)).sum())
        if n_le:
            warns.append(f"{n_le} (mã, CH) tồn cuối 1–{cfg.TON_TOI_THIEU_SAU_DC - 1} cái (mã có lệnh).")
        if "Dat_lo_toi_thieu" in detail_df.columns:
            cap = detail_df.drop_duplicates(["CH_xuat", "CH_nhan"])
            n_lo = int((~cap["Dat_lo_toi_thieu"].astype(bool)).sum())
            if n_lo:
                warns.append(f"{n_lo}/{len(cap)} cặp CH xuất→nhận chưa đạt lô tối thiểu "
                             f"(< {cfg.LO_TOI_THIEU_SL} cái và < {cfg.LO_TOI_THIEU_GIA_TRI:,.0f}đ).")
        return warns

    @staticmethod
    def apply_batch_minimum(detail_df):
        if detail_df.empty:
            return detail_df
        grp = detail_df.groupby(["CH_xuat", "CH_nhan"]).agg(SL=("So_luong", "sum"), GT=("Gia_tri", "sum")).reset_index()
        grp["Dat_lo_toi_thieu"] = (grp["SL"] >= cfg.LO_TOI_THIEU_SL) | (grp["GT"] >= cfg.LO_TOI_THIEU_GIA_TRI)
        detail_df = detail_df.merge(grp[["CH_xuat", "CH_nhan", "Dat_lo_toi_thieu"]], on=["CH_xuat", "CH_nhan"], how="left")
        return detail_df

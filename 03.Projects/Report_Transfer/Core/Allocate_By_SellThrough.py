# -*- coding: utf-8 -*-
"""SellThroughAllocator — Phương án phân bổ ĐỘC LẬP theo tỷ lệ bán (CHE_DO_PHAN_BO = "TY_LE_BAN").

Mỗi mã:
1) Xếp CH theo Tỷ lệ bán tại CH (bán ÷ (bán + tồn)) giảm dần; bằng nhau → Store rank (I > II > III > IV).
2) Chia lại TOÀN BỘ tồn của mã từ CH xếp đầu xuống: mỗi CH nhận 1 bộ đủ size (các size bộ chính còn
   hàng), số cái/size theo loại CH (TY_LE_BAN_CAI_MOI_SIZE: I = 3, II = 2, III/IV = 1; tổng ≥ ngưỡng tồn
   tối thiểu). CH không đủ bộ thì bỏ qua sang CH kế tiếp. Phần còn lại (size bộ chính dư, size phụ) rải
   vòng tròn cho các CH đã được chia (theo thứ hạng) → chia đến khi hết tồn. Kết quả = TỒN MỤC TIÊU
   từng CH × size; CH không được chia → mục tiêu 0.
3) Lệnh điều chuyển = chênh lệch tồn hiện tại ↔ tồn mục tiêu, giải bài toán vận tải có chi phí cố định
   (MILP, scipy HiGHS): tối thiểu SỐ CHUYẾN (cặp CH xuất → CH nhận) — cặp đã có chuyến ở mã trước rẻ hơn
   (gom chuyến giữa các mã), khoảng cách là tiêu chí phụ. Bài lớn / quá thời gian → thuật toán tham lam
   (khớp đúng số lượng trước, cặp sẵn có trước, lượng lớn trước).
CH "Không rút" / bảo hộ giữ nguyên tồn (không xuất, không tính vào phần chia lại)."""
import math

import numpy as np
import pandas as pd

from Config import Config_Parameters as cfg


class SellThroughAllocator:
    """Phân bổ theo tỷ lệ bán + tối thiểu số chuyến."""

    RANK_ORDER = {"I": 0, "II": 1, "III": 2, "IV": 3}

    # ------------------------------------------------------------------ 1-2) tồn mục tiêu
    @staticmethod
    def target_stock(pk, sku, stores_sku, inv_idx, size_seq, sizes_all, weight_map, fixed=None, excluded=None):
        """Trả về (targets {(CH, size): SL}, thứ hạng CH, CH giữ nguyên, tồn hiện tại).
        fixed: tập ô (CH, size) GIỮ NGUYÊN tồn hiện tại (không chuyển đi / không nhận thêm) — dùng để
        khử trường hợp 1 CH vừa xuất vừa nhận cùng mã."""
        fixed = fixed or set()
        excluded = excluded or set()   # CH buộc chuyển hết (mục tiêu 0) — tránh tồn cuối 1..ngưỡng-1
        rows = {r["Store_name"]: r for _, r in stores_sku.iterrows()}
        protected = {st for st, r in rows.items() if r.get("Khong_rut") == "✓" or r.get("Bao_ho_CH_moi") == "✓"}
        hold = {(st, sz): inv_idx.get((pk, st, sz), 0) for st in rows for sz in sizes_all}
        pool = {sz: sum(hold[(st, sz)] for st in rows if st not in protected and (st, sz) not in fixed)
                for sz in sizes_all}

        bo_set = {x for x in str(sku.get("Bo_size_chinh") or "").split(" · ") if x}
        chinh = [s for s in size_seq if str(s) in bo_set and pool.get(s, 0) > 0]
        if not chinh:
            chinh = [s for s in sizes_all if pool.get(s, 0) > 0]
        phu = [s for s in sizes_all if s not in chinh and pool.get(s, 0) > 0]

        def rank_key(st):
            r = rows[st]
            return (-(r.get("Ty_le_ban_tai_CH") or 0), SellThroughAllocator.RANK_ORDER.get(r.get("Loai_CH"), 9))

        ranked = sorted((st for st in rows if st not in protected and st not in excluded), key=rank_key)
        targets = {(st, sz): 0 for st in rows if st not in protected for sz in sizes_all}
        for st in protected:
            for sz in sizes_all:
                targets[(st, sz)] = hold[(st, sz)]
        for (st, sz) in fixed:
            targets[(st, sz)] = hold.get((st, sz), 0)

        # 2a) bộ đủ size theo loại CH, từ CH xếp đầu xuống
        remain = dict(pool)
        allocated = []
        min_q = cfg.TON_TOI_THIEU_SAU_DC
        for st in ranked:
            t = cfg.TY_LE_BAN_CAI_MOI_SIZE.get(rows[st].get("Loai_CH"), 1)
            t = max(t, math.ceil(min_q / len(chinh))) if chinh else t
            can = [sz for sz in chinh if (st, sz) not in fixed]
            if chinh and all(remain[sz] >= t for sz in can):
                for sz in can:
                    targets[(st, sz)] += t
                    remain[sz] -= t
                allocated.append(st)
        # chưa CH nào đủ 1 bộ → gom toàn bộ về CH xếp đầu
        if not allocated and ranked:
            allocated = [ranked[0]]
        # 2b) phần còn lại (size chính dư + size phụ) rải vòng tròn theo thứ hạng → hết tồn
        for sz in chinh + phu:
            nhan = [st for st in allocated if (st, sz) not in fixed]
            i = 0
            while remain.get(sz, 0) > 0 and nhan:
                targets[(nhan[i % len(nhan)], sz)] += 1
                remain[sz] -= 1
                i += 1
        return targets, ranked, protected, hold

    # ------------------------------------------------------------------ 3) lệnh tối thiểu số chuyến
    @staticmethod
    def min_trip_orders(surplus, deficit, store_meta, pair_used, time_limit=None):
        """surplus/deficit: {(CH, size): SL}. Trả về list (CH xuất, CH nhận, size, SL)."""
        if not surplus or not deficit:
            return []
        srcs = sorted({k[0] for k in surplus})
        dsts = sorted({k[0] for k in deficit})
        sizes = sorted({k[1] for k in surplus} | {k[1] for k in deficit}, key=str)
        arcs = [(i, j, s) for s in sizes for i in srcs if surplus.get((i, s), 0) > 0
                for j in dsts if deficit.get((j, s), 0) > 0 and i != j]
        pairs = sorted({(i, j) for i, j, _ in arcs})
        if not arcs:
            return []
        if len(arcs) <= cfg.TY_LE_BAN_MILP_MAX_BIEN:
            res = SellThroughAllocator._solve_milp(arcs, pairs, surplus, deficit, store_meta, pair_used,
                                                   time_limit or cfg.TY_LE_BAN_MILP_GIAY)
            if res is not None:
                return res
        return SellThroughAllocator._greedy(surplus, deficit, store_meta, pair_used)

    @staticmethod
    def _dist(store_meta, a, b):
        from Geo.Compute_Geo_Distance import GeoLocator as geo
        ma, mb = store_meta.get(a, {}), store_meta.get(b, {})
        d = geo.haversine_km(ma.get("Lat"), ma.get("Lon"), mb.get("Lat"), mb.get("Lon"))
        return float(d) if d is not None and np.isfinite(d) else 2000.0   # thiếu toạ độ → coi như xa

    @staticmethod
    def _solve_milp(arcs, pairs, surplus, deficit, store_meta, pair_used, time_limit):
        from scipy.optimize import milp, LinearConstraint, Bounds
        from scipy.sparse import lil_matrix
        nx, ny = len(arcs), len(pairs)
        pidx = {p: k for k, p in enumerate(pairs)}
        dist = {p: SellThroughAllocator._dist(store_meta, *p) for p in pairs}
        c = np.zeros(nx + ny)
        for k, (i, j, s) in enumerate(arcs):
            c[k] = 1e-5 * dist[(i, j)]                       # tiêu chí phụ: quãng đường
        for p, k in pidx.items():
            c[nx + k] = 0.2 if p in pair_used else 1.0        # chuyến mới đắt, chuyến đã có (mã trước) rẻ
            c[nx + k] += 1e-4 * dist[p]
        rhs = []
        A_eq = lil_matrix((len({(a[0], a[2]) for a in arcs}) + len({(a[1], a[2]) for a in arcs}), nx + ny))
        r = 0
        by_src, by_dst = {}, {}
        for k, (i, j, s) in enumerate(arcs):
            by_src.setdefault((i, s), []).append(k)
            by_dst.setdefault((j, s), []).append(k)
        for key, ks in by_src.items():
            for k in ks:
                A_eq[r, k] = 1
            rhs.append(surplus[key]); r += 1
        for key, ks in by_dst.items():
            for k in ks:
                A_eq[r, k] = 1
            rhs.append(deficit[key]); r += 1
        # liên kết: chỉ chuyển trên cặp (i, j) khi mở chuyến y_ij = 1
        A_link = lil_matrix((nx, nx + ny))
        for k, (i, j, s) in enumerate(arcs):
            A_link[k, k] = 1
            A_link[k, nx + pidx[(i, j)]] = -min(surplus[(i, s)], deficit[(j, s)])
        cons = [LinearConstraint(A_eq.tocsr(), np.array(rhs), np.array(rhs)),
                LinearConstraint(A_link.tocsr(), -np.inf, 0)]
        ub = np.concatenate([[min(surplus[(i, s)], deficit[(j, s)]) for i, j, s in arcs], np.ones(ny)])
        res = milp(c, constraints=cons, integrality=np.ones(nx + ny), bounds=Bounds(0, ub),
                   options={"time_limit": time_limit, "disp": False})
        if res.x is None:
            return None
        out = []
        for k, (i, j, s) in enumerate(arcs):
            q = int(round(res.x[k]))
            if q > 0:
                out.append((i, j, s, q))
        return out

    @staticmethod
    def _greedy(surplus, deficit, store_meta, pair_used):
        sup, dem = dict(surplus), dict(deficit)
        out, used = [], set(pair_used)
        sizes = sorted({k[1] for k in sup}, key=str)
        for s in sizes:
            while True:
                S = [(i, q) for (i, z), q in sup.items() if z == s and q > 0]
                D = [(j, q) for (j, z), q in dem.items() if z == s and q > 0]
                if not S or not D:
                    break
                best = None
                for i, qi in S:
                    for j, qj in D:
                        if i == j:
                            continue
                        key = ((i, j) not in used, qi != qj, -min(qi, qj), SellThroughAllocator._dist(store_meta, i, j))
                        if best is None or key < best[0]:
                            best = (key, i, j, min(qi, qj))
                if best is None:
                    break
                _k, i, j, q = best
                sup[(i, s)] -= q
                dem[(j, s)] -= q
                used.add((i, j))
                out.append((i, j, s, q))
        return out

    # ------------------------------------------------------------------ chạy toàn bộ
    @staticmethod
    def build_transfer_orders(df_sku, df_store, inv_by_size, size_weight_by_sku, size_seq_by_sku, store_meta):
        inv_idx = inv_by_size.set_index(["Combined_PK", "Store_name", "Size"])["Qty_TonKho"].to_dict()
        inv_sizes = inv_by_size.groupby("Combined_PK")["Size"].unique().to_dict()
        pair_used = set()
        rows_out = []
        for _, sku in df_sku.iterrows():
            pk = sku["Combined_PK"]
            if sku["Lan_dieu_chuyen"] not in ("Lan1", "Lan2", "Lan3") or sku.get("De_xuat_sale"):
                continue
            stores_sku = df_store[df_store["Combined_PK"] == pk]
            if stores_sku.empty:
                continue
            weight_map = size_weight_by_sku.get(pk, {})
            size_seq = size_seq_by_sku.get(pk, sorted(weight_map.keys()))
            sizes_all = list(size_seq) + [z for z in inv_sizes.get(pk, []) if z not in set(size_seq)]
            # Lặp khử "vừa xuất vừa nhận": CH thiếu ≥ dư → làm CH nhận, giữ phần size dư; ngược lại làm
            # CH xuất, chỉ gửi phần dư, không nhận size thiếu. Chia lại cho tới khi mỗi CH 1 vai trò.
            fixed, excluded = set(), set()
            for _ in range(10):
                targets, ranked, protected, hold = SellThroughAllocator.target_stock(
                    pk, sku, stores_sku, inv_idx, size_seq, sizes_all, weight_map, fixed, excluded)
                surplus, deficit = {}, {}
                for (st, sz), t in targets.items():
                    h = hold.get((st, sz), 0)
                    if st in protected:
                        continue
                    if h > t:
                        surplus[(st, sz)] = h - t
                    elif t > h:
                        deficit[(st, sz)] = t - h
                xuat = {k[0] for k in surplus}
                dual = xuat & {k[0] for k in deficit}
                tong = {}
                for (st, _z), t in targets.items():
                    if st not in protected:
                        tong[st] = tong.get(st, 0) + t
                le = {st for st, t in tong.items() if 0 < t < cfg.TON_TOI_THIEU_SAU_DC}
                if le:
                    excluded |= le                               # còn 1..2 cái → chuyển hết
                    fixed = {k for k in fixed if k[0] not in le}
                    continue
                if not dual:
                    break
                for st in dual:
                    du = sum(q for (s_, _z), q in surplus.items() if s_ == st)
                    thieu = sum(q for (s_, _z), q in deficit.items() if s_ == st)
                    giu = surplus if thieu >= du else deficit
                    fixed |= {k for k in giu if k[0] == st}
            for src, dst, sz, q in SellThroughAllocator.min_trip_orders(surplus, deficit, store_meta, pair_used):
                pair_used.add((src, dst))
                rs, rd = store_meta.get(src, {}).get("Region"), store_meta.get(dst, {}).get("Region")
                rows_out.append(dict(
                    Combined_PK=pk, Ten_san_pham=sku.get("Ten_san_pham"), Trang_thai_ma=sku["Trang_thai"],
                    CH_xuat=src, Vung_xuat=rs, CH_nhan=dst, Vung_nhan=rd, Size=sz, So_luong=q,
                    Gia_ban=sku.get("Gia_ban"), Gia_tri=q * (sku.get("Gia_ban") or 0),
                    Noi_lien_vung="Nội vùng" if rs == rd else "Liên vùng",
                    Ly_do="Chia theo tỷ lệ bán", Lan_dieu_chuyen=sku["Lan_dieu_chuyen"],
                ))
        return pd.DataFrame(rows_out)

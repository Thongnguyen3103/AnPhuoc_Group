# -*- coding: utf-8 -*-
"""PipelineTableBuilder — Ráp dữ liệu thô thành 4 bảng: SKU / CH / Size / (CH x Size)."""
import math
import pandas as pd
from Config import Config_Parameters as cfg
from Core.Load_Data_Parquet import TransferDataLoader as data
from Core.Compute_Metrics import MetricRules as comp


class PipelineTableBuilder:
    """Ráp dữ liệu thô thành 4 bảng: SKU / CH / Size / (CH x Size).
    loader: TransferDataLoader (đã mở kết nối DuckDB)."""

    def __init__(self, loader):
        self.loader = loader

    ACTION_DISPLAY_MAP = {
        "NHẬN ƯU TIÊN 1": "NHẬN ƯU TIÊN 1",
        "NHẬN ƯU TIÊN 2": "NHẬN ƯU TIÊN 2",
        "NHẬN BỔ SUNG (chỉ bù size gãy)": "NHẬN BỔ SUNG",
        "GIỮ — không nhận thêm": "GIỮ",
        "GIỮ": "GIỮ",
        "GIỮ — theo dõi": "GIỮ",
        "XUẤT MỘT PHẦN": "XUẤT MỘT PHẦN",
        "XUẤT": "XUẤT HẾT",
        "XUẤT — nguồn rút đầu tiên": "XUẤT HẾT",
        "GIỮ (bảo hộ CH mới)": "GIỮ (bảo hộ mới)",
    }

    @staticmethod
    def months_since_khpp(dist_plan_str):
        parsed = data.parse_dist_plan(dist_plan_str)
        if not parsed:
            return None
        y, m = parsed
        return data.months_between(y, m, cfg.CURRENT_YEAR, cfg.CURRENT_MONTH)

    ROUND_INDEX = {"Lan1": 1, "Lan2": 2, "Lan3": 3}

    @staticmethod
    def in_months(df, months):
        """Mask các dòng có (Year, Month) thuộc tập months."""
        months = set(months)
        return pd.Series([(int(y), int(mo)) in months for y, mo in zip(df["Year"], df["Month"])],
                         index=df.index, dtype=bool)

    @staticmethod
    def month_seq(y, m, n):
        """Dãy n tháng liên tiếp bắt đầu từ (y, m)."""
        out = []
        for i in range(m - 1, m - 1 + n):
            out.append((y + i // 12, i % 12 + 1))
        return out

    @staticmethod
    def round_window_months(dist_plan_str, khpp_group, lan):
        """Khung đánh giá của Lần (Mục 11 + yêu cầu nghiệp vụ):
        Lần 1 = mốc KHPP tháng đầu (Nhóm 1: 6T); Lần 2 = mốc+3 (9T); Lần 3 = mốc+6 (12T).
        Khung luôn cắt từ Dist_plan, KHÔNG kéo đến hiện tại — mã chạy trễ vẫn đánh giá
        đúng cửa sổ số liệu của Lần đó.

        "Kỳ đánh giá" (Mục 2: "chu kỳ 3 tháng GIỮA HAI LẦN điều chuyển"): Lần 1 là lần
        đầu tiên, không có "lần trước" để tính khoảng giữa — nên kỳ của Lần 1 là TOÀN BỘ
        cửa sổ mốc (6T/9T/12T theo Nhóm KHPP). Lần 2/3 là 3 tháng gần nhất đã chốt
        (cfg.EVAL_MONTHS — khoảng cách kể từ lần điều chuyển trước), KHÔNG cắt theo khung.

        Trả về (set tháng trong khung, set tháng trong kỳ đánh giá, số tháng khung,
        số tháng kỳ đánh giá). Nếu không parse được Dist_plan → (None, None, mốc, mốc)."""
        parsed = data.parse_dist_plan(dist_plan_str)
        moc = cfg.KHPP_GROUP_MONTHS[khpp_group]
        k = PipelineTableBuilder.ROUND_INDEX.get(lan)
        n = moc + 3 * (k - 1) if k else moc
        if not parsed:
            return None, None, n, n
        y, m = parsed
        # không vượt quá số tháng đã thực trôi (mã chưa đủ tháng thì khung cắt tại hiện tại)
        elapsed = data.months_between(y, m, cfg.CURRENT_YEAR, cfg.CURRENT_MONTH)
        n_eff = max(1, min(n, elapsed if elapsed and elapsed > 0 else n))
        win = PipelineTableBuilder.month_seq(y, m, n_eff)
        if lan == "Lan1":
            ky = win
        else:
            # Lần 2/3: kỳ = 3 tháng GẦN NHẤT đã chốt (cfg.EVAL_MONTHS — khoảng kể từ lần
            # điều chuyển trước, trùng "Kỳ đánh giá (3T)" in trên Dashboard). Không lấy
            # win[-3:] vì mã chạy trễ mốc / ép Lần sẽ bị lùi về tháng cũ. Bỏ các tháng
            # trước Dist_plan (mã chưa lên kệ) để không pha loãng tốc độ.
            ky = [ym for ym in cfg.EVAL_MONTHS if ym >= (y, m)] or win[-3:]
        return set(win), set(ky), n_eff, len(ky)

    def build_all(self, combined_pks, scope_stores_df, forced_round_map=None, hieu_suat_state=None):
        """forced_round_map: {Combined_PK: 'Lan1'|'Lan2'|'Lan3'} — GHI ĐÈ Lần tự suy theo mốc KHPP.
        hieu_suat_state: dict từ Data/lich_su_hieu_suat_ky.json, khoá 'PK|Store|Lan2' →
        {'hieu_suat_ky': ...} — mẫu số Xu hướng ở Lần 3 (Mục 12.1)."""
        hieu_suat_state = hieu_suat_state or {}
        forced_round_map = forced_round_map or {}
        store_names = scope_stores_df["Store_name"].tolist()
        so_ch_pham_vi = len(store_names)
        store_meta = scope_stores_df.set_index("Store_name")

        master = self.loader.load_sku_master(combined_pks)
        inv = self.loader.load_inventory_size(combined_pks, store_names)          # size-level, scope
        sales = self.loader.load_sales(combined_pks, store_names)                  # size-level, scope
        inv_all = self.loader.load_inventory_all_regions(combined_pks)             # toàn hệ thống (HTCH + Kho)
        sales_all = self.loader.load_sales(combined_pks, None)                     # toàn hệ thống, không lọc CH
        size_order_map = self.loader.load_size_order(master["System_item_name"].dropna().unique().tolist())

        # ---- Định mức tồn & hạn mức nhận cấp CH (Mục 7.1/7.2) — tính 1 lần, dùng chung mọi mã ----
        avg_monthly_all = self.loader.load_store_avg_monthly_sales_all_sku(store_names, cfg.EVAL_MONTHS)
        total_inv_all = self.loader.load_store_total_inventory_all_sku(store_names)
        dinh_muc_ton_ch = {}
        han_muc_nhan_ch = {}
        for st in store_names:
            loai = store_meta.loc[st, "Loai_CH"] if st in store_meta.index else "III"
            he_so = cfg.HE_SO_THANG_PHU.get(loai, 4.5)
            dm = avg_monthly_all.get(st, 0) * he_so
            dinh_muc_ton_ch[st] = round(dm, 1)
            han_muc_nhan_ch[st] = max(0, round(dm - total_inv_all.get(st, 0), 1))

        sku_rows, store_rows, size_rows, store_size_rows = [], [], [], []

        for _, m in master.iterrows():
            pk = m["Combined_PK"]
            ma_hang = m.get("item_code") or (pk[:-len(str(m.get("Operation")))] if m.get("Operation") else pk)
            khpp_group = comp.classify_khpp_group(m)
            moc_thang = PipelineTableBuilder.months_since_khpp(m.get("Dist_plan"))
            if pk in forced_round_map:
                lan, du = forced_round_map[pk], None  # ép tay/CSV — bỏ qua auto-detect theo mốc KHPP
            else:
                lan, du = comp.determine_round(moc_thang, khpp_group)

            inv_sku = inv[inv["Combined_PK"] == pk]                # scope, size-level
            sales_sku = sales[sales["Combined_PK"] == pk]           # scope, size-level
            inv_all_sku = inv_all[inv_all["Combined_PK"] == pk]      # toàn hệ thống
            sales_all_sku = sales_all[sales_all["Combined_PK"] == pk]

            # ---- Số bán (mã + CH + size) LUÔN lấy TOÀN LỊCH SỬ — không cắt theo khung Lần.
            # Chỉ "Kỳ đánh giá" (win_ky: 6T Lần 1 / 3T Lần 2-3, N tháng gần nhất) mới lọc
            # theo khung, dùng riêng cho các số *_ky / *_3T bên dưới. ----
            win_khung, win_ky, win_n, ky_n = PipelineTableBuilder.round_window_months(m.get("Dist_plan"), khpp_group, lan)

            ton_htch = inv_all_sku.loc[inv_all_sku["La_HTCH"], "Qty_TonKho"].sum()
            ton_kho = inv_all_sku.loc[~inv_all_sku["La_HTCH"], "Qty_TonKho"].sum()
            # Tách Tồn HTCH = CH vùng phía Nam/Trung (trừ HN) + CH Hà Nội
            ton_hn = inv_all_sku.loc[inv_all_sku["La_HTCH"] & (inv_all_sku["Region"] == "Hà Nội"), "Qty_TonKho"].sum()
            tong_ton = ton_htch + ton_kho
            tong_ban = sales_all_sku["Qty_Ban"].sum()
            tong_pp = tong_ton + tong_ban

            so_ch_co_hang = inv_all_sku.loc[(inv_all_sku["La_HTCH"]) & (inv_all_sku["Qty_TonKho"] > 0),
                                             "Store_name"].nunique()
            so_ch_da_ban = sales_all_sku.loc[sales_all_sku["Qty_Ban"] > 0, "Store_name"].nunique()
            so_ch_mau_so = so_ch_co_hang or 1
            so_thang_pp_moc = cfg.KHPP_GROUP_MONTHS[khpp_group]
            # "Số tháng bán" = SỐ THÁNG KHUNG CỦA LẦN (Lần 1: 6T, Lần 2: 9T, Lần 3: 12T
            # với Nhóm 1) — mã chạy trễ vẫn đánh giá đúng cửa sổ của Lần, không kéo dài.
            so_thang_ban = win_n
            # TB bán/tháng (toàn hệ thống) — KHÁC với Tốc độ bán chuẩn (chia thêm số CH)
            # Mục 14: tử số chỉ lấy số bán TRONG KHUNG Lần (cùng khoảng với mẫu số win_n);
            # không parse được Dist_plan (win_khung None) → giữ toàn lịch sử như cũ.
            tong_ban_khung = (sales_all_sku.loc[PipelineTableBuilder.in_months(sales_all_sku, win_khung), "Qty_Ban"].sum()
                              if win_khung else tong_ban)
            tb_ban_thang = tong_ban_khung / so_thang_ban if so_thang_ban else 0
            toc_do_chuan = tb_ban_thang / so_ch_mau_so if so_ch_mau_so else 0
            # "Kỳ đánh giá" = Lần 1: toàn bộ khung (6T/9T/12T theo Nhóm); Lần 2/3: 3 tháng cuối khung
            ban_ky_ma = (sales_all_sku[sales_all_sku.apply(
                lambda r: (int(r["Year"]), int(r["Month"])) in win_ky, axis=1)]["Qty_Ban"].sum()
                if win_ky and len(sales_all_sku) else 0)
            toc_do_chuan_ky = (ban_ky_ma / ky_n / so_ch_mau_so) if so_ch_mau_so and ky_n else 0

            # Tỷ lệ bán toàn mã (Mục 5.1, dùng cho Trạng thái mã) = kết hợp 30% số bán kỳ
            # đánh giá gần nhất (6T Lần 1 / 3T Lần 2-3) + 70% số bán lũy kế toàn mã. Với
            # Lần 1, kỳ == lũy kế (cùng cửa sổ) nên blend không đổi kết quả.
            # Trộn 2 TỶ LỆ (kỳ / lũy kế), không trộn 2 số lượng chung mẫu số — tránh kéo
            # thấp Trạng thái mã ở Lần 2/3 (xem MetricRules.blended_sell_through).
            tyle_ban_ma_pct, tyle_ky_pct, tyle_luyke_pct = comp.blended_sell_through(ban_ky_ma, tong_ban, tong_ton)

            trang_thai = comp.determine_status(tyle_ban_ma_pct, lan) if lan in ("Lan1", "Lan2", "Lan3") else "Chưa đủ mốc / kết thúc"
            # Lũy kế đã vượt ngưỡng Sắp hết → luôn Sắp hết hàng (tỷ lệ kỳ thấp vì hết hàng để bán,
            # không phải vì bán chậm — không để phần trộn 30% kỳ kéo mã xuống).
            if lan in cfg.STATUS_THRESHOLDS and tyle_luyke_pct > cfg.STATUS_THRESHOLDS[lan]["sap_het"]:
                trang_thai = "Sắp hết hàng"

            # ---- size-level (toàn hệ thống, cho Sheet "Tổng hợp SKU"/bộ size chính) ----
            size_ban_all = sales_all_sku.groupby("Size")["Qty_Ban"].sum().sort_values(ascending=False)
            weight_map = (size_ban_all / size_ban_all.sum()).to_dict() if size_ban_all.sum() else {}
            bo_chinh_list = comp.bo_size_chinh(list(size_ban_all.items())) if len(size_ban_all) else []
            n_bo_chinh = len(bo_chinh_list) or 1
            # Mã gãy size: số size BỘ CHÍNH còn hàng tại CH phạm vi < MA_GAY_TY_LE × số size bộ chính
            ton_size_scope = inv_sku.groupby("Size")["Qty_TonKho"].sum()
            so_size_con = sum(1 for s in bo_chinh_list if ton_size_scope.get(s, 0) > 0)
            ma_gay = bool(bo_chinh_list) and ton_size_scope.sum() > 0 and so_size_con < cfg.MA_GAY_TY_LE * len(bo_chinh_list)

            sku_rows.append(dict(
                Combined_PK=pk, Ma_Hang=ma_hang, Operation=m.get("Operation"),
                Ten_san_pham=m.get("Report_item_name") or m.get("System_item_name"),
                Thuong_hieu=m.get("Brand"), Gia_ban=m.get("Price"), Nhom_KHPP=f"Nhóm {khpp_group}",
                Group_Report=m.get("Group_Report"),
                So_thang_PP_moc=so_thang_pp_moc, Dot_chuyen=lan.replace("Lan", "Lần ") if lan.startswith("Lan") else lan,
                Dist_plan=m.get("Dist_plan"), Group_color=m.get("Color_group"), Form=m.get("Form"),
                Style=m.get("Style"), Composition=m.get("Composition"),
                Tong_ban=tong_ban,
                Ton_HTCH=ton_htch, Ton_HTCH_tru_HN=ton_htch - ton_hn, Ton_HN=ton_hn,
                Ton_Cac_Kho=ton_kho, Tong_ton=tong_ton,
                Tong_nhap=tong_pp, Ty_le_ban_pct=round(tyle_ban_ma_pct, 1),
                Ty_le_ban_ky_pct=round(tyle_ky_pct, 1), Ty_le_ban_luyke_pct=round(tyle_luyke_pct, 1),
                So_CH_co_hang=so_ch_co_hang, So_CH_da_ban=so_ch_da_ban,
                Ban_3T=int(ban_ky_ma), So_thang_ky=ky_n, So_thang_ban=so_thang_ban,
                TB_ban_thang=round(tb_ban_thang, 2), Toc_do_ban_chuan=round(toc_do_chuan, 2),
                Trang_thai=trang_thai, Lan_dieu_chuyen=lan, Thang_du_trong_lan=du,
                Bo_size_chinh=" · ".join(map(str, bo_chinh_list)), So_size=len(size_ban_all),
                So_size_chinh_con_hang=so_size_con, Ma_gay_size="✓" if ma_gay else None,
                # Tổng tồn tại CH phạm vi < ngưỡng tồn tối thiểu → không gom đủ được, để nguyên & đề xuất sale/thanh lý
                So_diem_ban=(max(1, int(ton_size_scope.sum() // max(cfg.TON_TOI_THIEU_SAU_DC, math.ceil(
                    len(bo_chinh_list) * cfg.GOM_CAI_MOI_SIZE.get(lan, 1.0)))))
                    if ton_size_scope.sum() > 0 and bo_chinh_list else None),
                De_xuat_sale=(f"✓ Tồn phạm vi {int(ton_size_scope.sum())} cái"
                              if 0 < ton_size_scope.sum() < cfg.TON_TOI_THIEU_SAU_DC else None),
            ))

            cum = 0
            tong_ban_all_size = size_ban_all.sum() or 1
            size_ton_scope = inv_sku.groupby("Size")["Qty_TonKho"].sum()  # InventorySize không có ở mức "toàn hệ thống" tách Kho, dùng tồn trong phạm vi CH đợt này để minh hoạ
            for s, w in size_ban_all.items():
                cum += w
                size_rows.append(dict(
                    Combined_PK=pk, Size=s, Ban_toan_HT=int(w),
                    Ty_trong=w / tong_ban_all_size, Luy_ke=cum / tong_ban_all_size,
                    Thuoc_bo_chinh="✓" if s in bo_chinh_list else None,
                    Ton_toan_HT=int(size_ton_scope.get(s, 0)),
                ))

            # ---- store-level (chỉ trong phạm vi CH đợt này) ----
            for st in store_names:
                inv_st = inv_sku[inv_sku["Store_name"] == st]
                sales_st = sales_sku[sales_sku["Store_name"] == st]
                ton_ch = inv_st["Qty_TonKho"].sum()
                ban_luyke = sales_st["Qty_Ban"].sum()
                ban_ky3t = (sales_st[sales_st.apply(lambda r: (int(r["Year"]), int(r["Month"])) in win_ky, axis=1)]["Qty_Ban"].sum()
                            if win_ky and len(sales_st) else 0)
                if ton_ch <= 0 and ban_luyke <= 0:
                    continue

                thang_co_ban = sales_st.loc[sales_st["Qty_Ban"] > 0, ["Year", "Month"]].drop_duplicates().shape[0]
                # bảo hộ CH mới xét theo số tháng THỰC (moc_thang); mẫu số tốc độ theo KHUNG Lần
                thang_tu_nhan = moc_thang if moc_thang is not None else thang_co_ban
                # Mục 14: tốc độ CH = số bán TRONG KHUNG Lần ÷ số tháng (cùng khoảng).
                sales_st_khung = sales_st[PipelineTableBuilder.in_months(sales_st, win_khung)] if win_khung else sales_st
                ban_khung_st = sales_st_khung["Qty_Ban"].sum()
                thang_co_ban_khung = sales_st_khung.loc[sales_st_khung["Qty_Ban"] > 0, ["Year", "Month"]].drop_duplicates().shape[0]
                if ton_ch > 0:
                    mau_so, nhanh = max(win_n, 1), "Tồn>0: số tháng khung Lần"
                else:
                    mau_so, nhanh = max(thang_co_ban_khung, 1), "Tồn=0: tháng có bán"
                toc_do_ch = ban_khung_st / mau_so if mau_so else 0
                hieu_suat = (toc_do_ch / toc_do_chuan) if toc_do_chuan else 0
                # Hiệu suất kỳ (BẮT BUỘC theo kỳ đánh giá — 6T Lần 1 / 3T Lần 2-3, không
                # dùng lũy kế — Mục 5.2/12.1)
                # Mục 3a: CH đã HẾT HÀNG → chia cho số tháng CÓ BÁN trong kỳ (không có tồn theo
                # tháng nên dùng tháng có bán thay cho tháng có hàng) — không phạt CH vì hết hàng.
                if ton_ch <= 0 and win_ky:
                    sales_st_ky = sales_st[PipelineTableBuilder.in_months(sales_st, win_ky)]
                    mau_so_ky = max(sales_st_ky.loc[sales_st_ky["Qty_Ban"] > 0, ["Year", "Month"]]
                                    .drop_duplicates().shape[0], 1)
                else:
                    mau_so_ky = ky_n
                hieu_suat_ky = ((ban_ky3t / mau_so_ky) / toc_do_chuan_ky) if toc_do_chuan_ky and mau_so_ky else 0
                # Xu hướng Lần 3 = Hiệu suất kỳ L3 ÷ Hiệu suất kỳ L2 đã lưu (Mục 12.1)
                xu_huong, xu_huong_nhan, hanh_dong_l3 = None, None, None
                if lan == "Lan3":
                    saved = hieu_suat_state.get(f"{pk}|{st}|Lan2")
                    hs_l2 = saved.get("hieu_suat_ky") if isinstance(saved, dict) else None
                    if hs_l2:
                        xu_huong = hieu_suat_ky / hs_l2
                        hanh_dong_l3, xu_huong_nhan = comp.trend_action(xu_huong, hieu_suat_ky)
                so_thang_ton = (ton_ch / toc_do_ch) if toc_do_ch else cfg.SENTINEL_THANG_TON
                nhan_luyke = ton_ch + ban_luyke
                tyle_ban_ch = (ban_luyke / nhan_luyke) if nhan_luyke else 0

                loai_ch = store_meta.loc[st, "Loai_CH"] if st in store_meta.index else "III"
                vung = store_meta.loc[st, "Region"] if st in store_meta.index else ""
                dia_chi = store_meta.loc[st, "Dia_chi"] if st in store_meta.index and "Dia_chi" in store_meta.columns else None

                bao_ho = (cfg.BAOHO_TU_DONG and thang_tu_nhan is not None
                          and thang_tu_nhan < cfg.BAOHO_SO_THANG)
                nhom = "B" if bao_ho else comp.perf_group(hieu_suat, ban_ky3t > 0)

                suat_chia_n = comp.suat_chia_lookup(n_bo_chinh, loai_ch)
                co_banhet = (not bao_ho) and comp.check_flag_banhet(
                    nhan_luyke, tyle_ban_ch, ton_ch, n_bo_chinh, thang_co_ban, suat_chia_n)

                hanh_dong_raw, cot_ton = comp.matrix_action(nhom, so_thang_ton) if not bao_ho else ("GIỮ (bảo hộ CH mới)", None)
                hanh_dong = PipelineTableBuilder.ACTION_DISPLAY_MAP.get(hanh_dong_raw, hanh_dong_raw)

                sizes_present = list(inv_st.loc[inv_st["Qty_TonKho"] >= 0, "Size"].unique()) or list(size_ban_all.index)
                item_name = m.get("System_item_name")
                size_seq_all = comp.build_size_sequence(list(size_ban_all.index) if len(size_ban_all) else sizes_present,
                                                          item_name, size_order_map)
                store_size_ban = sales_st.groupby("Size")["Qty_Ban"].sum()
                nguon_cua_so = "Lịch sử CH" if store_size_ban.sum() else None
                if store_size_ban.sum():
                    store_weight = (store_size_ban / store_size_ban.sum()).to_dict()
                else:
                    # thứ tự ưu tiên Mục 6.2: lịch sử CH → hồ sơ size VÙNG → toàn hệ thống
                    reg_ban = sales_sku[sales_sku["Region"] == vung].groupby("Size")["Qty_Ban"].sum() if len(sales_sku) else None
                    store_weight = ((reg_ban / reg_ban.sum()).to_dict()
                                     if reg_ban is not None and reg_ban.sum() else weight_map)
                window = comp.best_window(size_seq_all, store_weight, suat_chia_n)
                if nguon_cua_so is None:
                    if store_weight is weight_map:
                        # CH & vùng chưa có lịch sử → cửa sổ toàn hệ thống + lệch vùng Phụ lục B
                        window = comp.shift_window(window, size_seq_all,
                                                   cfg.PHU_LUC_B_OFFSET.get(vung, {}).get(loai_ch, 0))
                        nguon_cua_so = "Toàn HT + Phụ lục B"
                    else:
                        nguon_cua_so = "Hồ sơ vùng"
                window_set = set(window)
                ton_by_size_st = inv_st.groupby("Size")["Qty_TonKho"].sum().to_dict()
                size_gay = [s for s in window if ton_by_size_st.get(s, 0) == 0 and store_weight.get(s, weight_map.get(s, 0)) > 0]

                dinh_muc = dinh_muc_ton_ch.get(st, 0)
                han_muc = han_muc_nhan_ch.get(st, 0)

                store_rows.append(dict(
                    Combined_PK=pk, Store_name=st, Region=vung, Loai_CH=loai_ch, Dia_chi=dia_chi,
                    Nhan_luyke=nhan_luyke, Ban_luyke=ban_luyke, Ton=ton_ch, Ban_ky_3T=ban_ky3t, So_thang_ky=ky_n,
                    Thang_tu_nhan=thang_tu_nhan, Thang_co_ban=thang_co_ban, Nhanh_mau_so=nhanh,
                    Toc_do_ban=round(toc_do_ch, 2), Chi_so_hieu_suat=round(hieu_suat, 2),
                    Hieu_suat_ky=round(hieu_suat_ky, 2),
                    Xu_huong=(round(xu_huong, 2) if xu_huong is not None else None),
                    Xu_huong_nhan=xu_huong_nhan, Hanh_dong_L3=hanh_dong_l3,
                    So_thang_ton=round(so_thang_ton, 2), Ty_le_ban_tai_CH=round(tyle_ban_ch * 100, 1),
                    Nhom=nhom, Co_BanHet="✓" if co_banhet else None, Bao_ho_CH_moi="✓" if bao_ho else None,
                    Hanh_dong_matran=hanh_dong, Cua_so_size=("–".join([window[0], window[-1]]) if len(window) > 1 else (window[0] if window else None)),
                    Size_gay=" ".join(size_gay) if size_gay else None, Suat_chia=suat_chia_n,
                    Cua_so_list=list(window), Size_gay_list=list(size_gay), Nguon_cua_so=nguon_cua_so,
                    Dinh_muc_ton=dinh_muc, Han_muc_nhan=han_muc, Gia_ban=m.get("Price"),
                    So_thang_PP_moc=so_thang_pp_moc, Trang_thai_ma=trang_thai, Lan_dieu_chuyen=lan,
                ))

                # InventorySize chỉ có dòng size còn tồn > 0 → size đã bán hết tại CH không có
                # trong sizes_present, làm rơi số bán kỳ. Bổ sung các size có bán trong kỳ.
                sizes_ban_ky = (sales_st.loc[sales_st.apply(lambda r: (int(r["Year"]), int(r["Month"])) in win_ky, axis=1)
                                             & (sales_st["Qty_Ban"] != 0), "Size"].unique().tolist()
                                if win_ky and len(sales_st) else [])
                sizes_detail = list(sizes_present) + [s for s in sizes_ban_ky if s not in sizes_present]
                for sz in sizes_detail:
                    ton_sz = ton_by_size_st.get(sz, 0)
                    ban3t_sz = (sales_st[(sales_st["Size"] == sz) &
                                         (sales_st.apply(lambda r: (int(r["Year"]), int(r["Month"])) in win_ky, axis=1))]["Qty_Ban"].sum()
                                if win_ky and len(sales_st) else 0)
                    if ton_sz <= 0 and ban3t_sz <= 0 and sz not in window_set:
                        continue
                    toc_do_sz = ban3t_sz / ky_n if ban3t_sz and ky_n else 0
                    thang_ton_sz = (ton_sz / toc_do_sz) if toc_do_sz else cfg.SENTINEL_THANG_TON
                    store_size_rows.append(dict(
                        Combined_PK=pk, Store_name=st, Region=vung, Size=sz,
                        Ton_hien_tai=ton_sz, Ban_3T=ban3t_sz, Toc_do_ban_size=round(toc_do_sz, 2),
                        Thang_ton_size=round(thang_ton_sz, 2), Trong_cua_so=("✓" if sz in window_set else None),
                        Size_gay=("✓" if sz in size_gay else None),
                    ))

        df_sku = pd.DataFrame(sku_rows)
        df_store = pd.DataFrame(store_rows)
        df_size = pd.DataFrame(size_rows)
        df_store_size = pd.DataFrame(store_size_rows)
        return df_sku, df_store, df_size, df_store_size, so_ch_pham_vi

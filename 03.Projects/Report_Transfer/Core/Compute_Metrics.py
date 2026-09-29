# -*- coding: utf-8 -*-
"""MetricRules — Quy tắc tính chỉ số Mục 5 (mã/CH/size), trạng thái, nhóm hiệu suất, cờ BÁN HẾT, cửa sổ size, ma trận Mục 9 & 12, xác định Lần (Mục 11)."""
import math
import numpy as np
from Config import Config_Parameters as cfg


class MetricRules:
    """Quy tắc tính chỉ số Mục 5 (mã/CH/size), trạng thái, nhóm hiệu suất, cờ BÁN HẾT, cửa sổ size, ma trận Mục 9 & 12, xác định Lần (Mục 11)."""

    # ---------------------------------------------------------------- KHPP group
    @staticmethod
    def parse_round_label(text):
        """'Lần 1' / 'Lan 1' / '1' / 'lần1' -> 'Lan1'. Trả về None nếu không nhận diện được."""
        if text is None:
            return None
        s = str(text).strip().lower()
        if "1" in s:
            return "Lan1"
        if "2" in s:
            return "Lan2"
        if "3" in s:
            return "Lan3"
        return None

    @staticmethod
    def classify_khpp_group(row):
        text = " ".join(str(row.get(c, "")) for c in
                         ["Report_item_name", "Product_type", "Group_Report", "Product_group", "System_item_name"]).lower()
        price = row.get("Price") or 0
        if any(k in text for k in cfg.KHPP_GROUP3_KEYWORDS):
            return 3
        if any(k in text for k in cfg.KHPP_GROUP1_KEYWORDS):
            return 1
        if any(k in text for k in cfg.KHPP_GROUP2_KEYWORDS):
            return 3 if price > cfg.GIA_TRI_PHU_KIEN_CAO else 2
        # Mặc định theo nguyên tắc giá trị (Ghi chú Mục 3): đến 5tr -> Nhóm 2, trên 5tr -> Nhóm 3
        return 3 if price > cfg.GIA_TRI_PHU_KIEN_CAO else 2

    @staticmethod
    def determine_round(months_since_khpp, khpp_group):
        """Trả về ('ChuaDuMoc'|'Lan1'|'Lan2'|'Lan3'|'KetThuc', số tháng dư trong lần đó)."""
        if months_since_khpp is None:
            return "KhongXacDinh", None
        moc = cfg.KHPP_GROUP_MONTHS[khpp_group]
        if months_since_khpp < moc:
            return "ChuaDuMoc", moc - months_since_khpp
        if months_since_khpp < moc + 3:
            return "Lan1", months_since_khpp - moc
        if months_since_khpp < moc + 6:
            return "Lan2", months_since_khpp - moc - 3
        if months_since_khpp < moc + 9:
            return "Lan3", months_since_khpp - moc - 6
        return "KetThuc", None

    # ---------------------------------------------------------------- Trạng thái mã
    @staticmethod
    def determine_status(tyle_ban_pct, lan):
        """Ngưỡng chọn theo LẦN điều chuyển (số tháng mã trên kệ): Lan1 → 85/65/25,
        Lan2 → 88/70/30, Lan3 → 90/75/35 (Mục 5.1 + 11.2)."""
        th = cfg.STATUS_THRESHOLDS.get(lan, cfg.STATUS_THRESHOLDS["Lan1"])
        if tyle_ban_pct > th["sap_het"]:
            return "Sắp hết hàng"
        if tyle_ban_pct >= th["ban_tot"]:
            return "Bán tốt"
        if tyle_ban_pct >= th["ban_cham"]:
            return "Bán trung bình – chậm"
        return "Bán rất chậm"

    # ---------------------------------------------------------------- Ma trận xu hướng Lần 3 (Mục 12.2)
    TREND_MATRIX = {
        ("tang", "cao"): "ĐIỂM GOM CHÍNH",
        ("tang", "tb"): "ƯU TIÊN NHẬN",
        ("tang", "thap"): "NHẬN NHẸ / THEO DÕI",
        ("on_dinh", "cao"): "ƯU TIÊN NHẬN",
        ("on_dinh", "tb"): "GIỮ",
        ("on_dinh", "thap"): "HẠN CHẾ NHẬN",
        ("giam", "cao"): "GIỮ — cảnh báo",
        ("giam", "tb"): "XUẤT MỘT PHẦN",
        ("giam", "thap"): "ƯU TIÊN XUẤT",
        ("giam_manh", "cao"): "XUẤT MỘT PHẦN — rút sớm",
        ("giam_manh", "tb"): "ƯU TIÊN XUẤT",
        ("giam_manh", "thap"): "XUẤT HẾT / THU HỒI",
    }

    @staticmethod
    def trend_action(xu_huong, hieu_suat_ky_l3):
        """Mục 12.2 — Xu hướng (kỳ L3 ÷ kỳ L2) × Hiệu suất hiện tại. Trả về (hành động, nhãn xu hướng)."""
        if xu_huong is None or hieu_suat_ky_l3 is None:
            return None, None
        if xu_huong >= cfg.XUHUONG_TANG:
            row, row_label = "tang", "Tăng"
        elif xu_huong >= cfg.XUHUONG_ON_DINH:
            row, row_label = "on_dinh", "Ổn định"
        elif xu_huong >= cfg.XUHUONG_GIAM:
            row, row_label = "giam", "Giảm"
        else:
            row, row_label = "giam_manh", "Giảm mạnh"
        if hieu_suat_ky_l3 >= cfg.HIEUSUAT_CAO_L3:
            col = "cao"
        elif hieu_suat_ky_l3 >= cfg.HIEUSUAT_THAP_L3:
            col = "tb"
        else:
            col = "thap"
        return MetricRules.TREND_MATRIX[(row, col)], row_label

    # ---------------------------------------------------------------- Nhóm hiệu suất CH
    @staticmethod
    def perf_group(perf_index, ban_trong_ky_gan_nhat):
        if not ban_trong_ky_gan_nhat or perf_index is None or perf_index < cfg.PERF_C:
            return "D"
        if perf_index >= cfg.PERF_A:
            return "A"
        if perf_index >= cfg.PERF_B:
            return "B"
        return "C"

    @staticmethod
    def thang_ton_cot(so_thang_ton, nhom):
        """Cột của ma trận Mục 9. Nhóm D tốc độ 0 -> mặc định cột 'trên 3 tháng'."""
        if so_thang_ton is None or (nhom == "D" and not np.isfinite(so_thang_ton)):
            return "tren_3"
        if so_thang_ton < cfg.MATRIX_THANG_TON_THAP:
            return "duoi_1_5"
        if so_thang_ton <= cfg.MATRIX_THANG_TON_CAO:
            return "1_5_3"
        return "tren_3"

    MATRIX_ACTIONS = {
        ("A", "duoi_1_5"): "NHẬN ƯU TIÊN 1",
        ("A", "1_5_3"): "NHẬN BỔ SUNG (chỉ bù size gãy)",
        ("A", "tren_3"): "GIỮ — không nhận thêm",
        ("B", "duoi_1_5"): "NHẬN ƯU TIÊN 2",
        ("B", "1_5_3"): "GIỮ",
        ("B", "tren_3"): "XUẤT MỘT PHẦN",
        ("C", "duoi_1_5"): "GIỮ — theo dõi",
        ("C", "1_5_3"): "XUẤT MỘT PHẦN",
        ("C", "tren_3"): "XUẤT",
        ("D", "duoi_1_5"): "XUẤT",
        ("D", "1_5_3"): "XUẤT",
        ("D", "tren_3"): "XUẤT — nguồn rút đầu tiên",
    }

    @staticmethod
    def matrix_action(nhom, so_thang_ton):
        cot = MetricRules.thang_ton_cot(so_thang_ton, nhom)
        return MetricRules.MATRIX_ACTIONS[(nhom, cot)], cot

    # ---------------------------------------------------------------- Cờ BÁN HẾT
    @staticmethod
    def check_flag_banhet(nhan_luyke, tyle_ban_ch, ton_hien_tai, bo_size_chinh_n, so_thang_co_ban, suat_chia_n):
        if suat_chia_n is None or nhan_luyke is None:
            return False
        dk1 = nhan_luyke >= suat_chia_n
        dk2 = (tyle_ban_ch is not None and tyle_ban_ch >= cfg.BANHET_TYLE_BAN_TOI_THIEU
               and ton_hien_tai <= bo_size_chinh_n)
        dk3 = so_thang_co_ban is not None and so_thang_co_ban <= cfg.BANHET_SO_THANG_TOI_DA
        return bool(dk1 and dk2 and dk3)

    # ---------------------------------------------------------------- Bậc Top theo trạng thái/lần
    @staticmethod
    def top_pct_for(status, tong_ton, lan):
        table_sap_het = cfg.TOP_SAP_HET_LAN1 if lan == "Lan1" else cfg.TOP_SAP_HET_LAN2
        table_ban_tot = cfg.TOP_BAN_TOT_LAN1 if lan == "Lan1" else cfg.TOP_BAN_TOT_LAN2
        table = table_sap_het if status == "Sắp hết hàng" else table_ban_tot
        for ceiling, pct in table:
            if tong_ton <= ceiling:
                return pct
        return table[-1][1]

    @staticmethod
    def top_n_stores(pct, so_ch_trong_pham_vi):
        return max(3, math.ceil(pct * so_ch_trong_pham_vi))

    # ---------------------------------------------------------------- Suất chia
    @staticmethod
    def suat_chia_lookup(n_size_bo_chinh, loai_ch):
        keys = sorted(cfg.SUAT_CHIA_TABLE.keys())
        key = min(keys, key=lambda k: abs(k - n_size_bo_chinh)) if n_size_bo_chinh not in cfg.SUAT_CHIA_TABLE else n_size_bo_chinh
        base = cfg.SUAT_CHIA_TABLE[key][loai_ch]
        floor_val = math.ceil(cfg.SAN_CHUNG_TY_LE * n_size_bo_chinh)
        return max(base, min(base, floor_val)) if base >= floor_val else floor_val

    # ---------------------------------------------------------------- Cửa sổ size liền kề (Mục 6.2)
    @staticmethod
    def build_size_sequence(sizes_present, system_item_name, size_order_map):
        """Trả về list size đã sắp theo trục vật lý (số hoặc chữ)."""
        seq = size_order_map.get(system_item_name)
        if seq:
            ordered = [s for s in seq if s in set(sizes_present)]
            if ordered:
                return ordered
        # fallback: size chữ theo bảng mặc định, hoặc numeric sort
        alpha_present = [s for s in cfg.ALPHA_SIZE_ORDER if s in set(sizes_present)]
        if alpha_present:
            return alpha_present
        try:
            return sorted(sizes_present, key=lambda x: float(x))
        except (ValueError, TypeError):
            return sorted(sizes_present)

    @staticmethod
    def best_window(size_seq, weight_map, n):
        """Trượt cửa sổ N size liên tục trên size_seq, chọn dải có tổng tỷ trọng bán cao nhất (Mục 6.2)."""
        n = min(n, len(size_seq)) if size_seq else 0
        if n <= 0:
            return []
        best, best_score = size_seq[:n], -1
        for i in range(0, len(size_seq) - n + 1):
            window = size_seq[i:i + n]
            score = sum(weight_map.get(s, 0) for s in window)
            if score > best_score:
                best_score, best = score, window
        return best

    @staticmethod
    def bo_size_chinh(size_weight_sorted_desc, threshold=cfg.BO_SIZE_CHINH_LUYKE):
        """size_weight_sorted_desc: list (size, weight) đã sort giảm dần theo weight. Trả về set size thuộc bộ chính."""
        total = sum(w for _, w in size_weight_sorted_desc) or 1
        cum = 0
        out = []
        for s, w in size_weight_sorted_desc:
            cum += w
            out.append(s)
            if cum / total >= threshold:
                break
        return out

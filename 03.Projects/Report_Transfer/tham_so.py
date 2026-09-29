# -*- coding: utf-8 -*-
"""
tham_so.py
Tham số vận hành (Phụ lục C) + hằng số dùng chung
Chỉnh các giá trị trong PARAMS khi Trưởng Bộ phận Điều chuyển cập nhật tham số.
KHÔNG cần sửa logic ở các file khác.
"""

# ─────────────────────────────────────────────
# KỲ HIỆN TẠI — Đợt điều chuyển đang chạy
# Lấy tự động theo ngày hệ thống lúc chạy báo cáo (không cần sửa tay mỗi đợt).
# ─────────────────────────────────────────────
import datetime as _dt

_today = _dt.date.today()
CURRENT_YEAR = _today.year
CURRENT_MONTH = _today.month

# 3 tháng gần nhất dùng để tính "bán bình quân tháng" (Mục 7.1) và tốc độ bán kỳ (Mục 5.2/12.1)
def eval_window(current_year, current_month, n=3):
    out = []
    y, m = current_year, current_month
    m -= 1  # kỳ đánh giá 3 tháng gần nhất KHÔNG gồm tháng hiện tại (tháng hiện tại thường chưa chốt số)
    for _ in range(n):
        if m == 0:
            m = 12
            y -= 1
        out.append((y, m))
        m -= 1
    return list(reversed(out))

EVAL_MONTHS = eval_window(CURRENT_YEAR, CURRENT_MONTH, 3)          # kỳ đánh giá hiện hành
EVAL_MONTHS_PREV = eval_window(EVAL_MONTHS[0][0], EVAL_MONTHS[0][1], 3)  # kỳ liền trước

# ─────────────────────────────────────────────
# MỤC 3 — Phân nhóm KHPP: mốc tháng bắt đầu
# ─────────────────────────────────────────────
KHPP_GROUP_MONTHS = {1: 6, 2: 9, 3: 12}

# Từ khoá phân loại nhóm KHPP theo Product_type / Group_Report / Report_item_name (đối chiếu Mục 3)
KHPP_GROUP1_KEYWORDS = ["thun", "chemise", "quần tây", "quần short", "quần jean", "jean",
                         "quần golf", "áo golf", "kaki", "khaki", "polo"]
KHPP_GROUP3_KEYWORDS = ["vest", "áo khoác"]
# Phụ kiện (da/vải) mặc định Nhóm 2 trừ khi > 5tr -> Nhóm 3 (giá kiểm tra riêng)
KHPP_GROUP2_KEYWORDS = ["giày", "dép", "sandal", "dây nịt", "ví ", "ví,", "nón", "túi", "balo", "cặp", "vali", "phụ kiện"]
GIA_TRI_PHU_KIEN_CAO = 5_000_000

# ─────────────────────────────────────────────
# MỤC 5.1 — Ngưỡng trạng thái mã theo LẦN điều chuyển
# 3 cột "mốc 6/9/12 tháng" ứng với SỐ THÁNG MÃ ĐÃ TRÊN KỆ, tiến theo Lần:
# Lần 1 (~6 tháng) → 85/65/25; Lần 2 (~9 tháng) → 88/70/30; Lần 3 (~12 tháng) → 90/75/35.
# Căn cứ: "mã bán càng lâu trên kệ phải đạt tỷ lệ bán càng cao mới được đánh giá cùng
# mức" (Mục 5.1) + Ghi chú Mục 3: hàng Nhóm 2/3 (phụ kiện, vest) đi theo Mục 10,
# KHÔNG dùng Mục 5-9 → bảng này chỉ phục vụ hàng may mặc đi qua 3 Lần.
# ─────────────────────────────────────────────
STATUS_THRESHOLDS = {
    "Lan1": dict(sap_het=85, ban_tot=65, ban_cham=25),
    "Lan2": dict(sap_het=88, ban_tot=70, ban_cham=30),
    "Lan3": dict(sap_het=90, ban_tot=75, ban_cham=35),
}

# ─────────────────────────────────────────────
# MỤC 5.1 (mở rộng) — Trọng số kết hợp khi tính Tỷ lệ bán toàn mã dùng cho Trạng thái mã.
# "Kỳ đánh giá" = Lần 1: toàn bộ cửa sổ mốc Nhóm KHPP (6T/9T/12T, vì Lần 1 là lần
# đánh giá đầu tiên, không có "lần trước" để tính khoảng 3 tháng giữa hai lần —
# xem round_window_months); Lần 2/3: 3 tháng cuối khung (đúng định nghĩa "Kỳ đánh
# giá" ở Mục 2). Số bán kỳ đánh giá chiếm TRONG_SO_KY, số bán lũy kế toàn mã (từ
# Dist_plan đến mốc Lần) chiếm TRONG_SO_LUY_KE — cộng lại chia Tổng phân phối ra %
# so ngưỡng STATUS_THRESHOLDS. Với Lần 1, kỳ == lũy kế nên blend không đổi kết quả.
# ─────────────────────────────────────────────
TRONG_SO_KY = 0.30
TRONG_SO_LUY_KE = 0.70

# ─────────────────────────────────────────────
# PHỤ LỤC B — Độ lệch cửa sổ size mặc định theo vùng (số bậc size, so với TP.HCM)
# Miền Trung thiên size NHỎ: lệch −1 bậc mọi loại CH (29–34 so với 30–35...).
# Miền Tây thiên size LỚN: lệch +2/+2/+3/+4 theo loại I/II/III/IV (32–37, 33–37, 34–37, 35–38).
# TP.HCM & Đông Nam Bộ là chuẩn; vùng khác chưa có hồ sơ dùng dòng TP.HCM.
# ─────────────────────────────────────────────
PHU_LUC_B_OFFSET = {
    "Miền Trung - TN": {"I": -1, "II": -1, "III": -1, "IV": -1},
    "Miền Tây": {"I": 2, "II": 2, "III": 3, "IV": 4},
}

# ─────────────────────────────────────────────
# MỤC 5.2 — Nhóm hiệu suất cửa hàng
# ─────────────────────────────────────────────
PERF_A = 1.20
PERF_B = 0.80
PERF_C = 0.40

# Cờ BÁN HẾT (Mục 5.2 / Phụ lục C)
BANHET_TYLE_BAN_TOI_THIEU = 0.85
BANHET_SO_THANG_TOI_DA = 3

# Bảo hộ cửa hàng mới
BAOHO_SO_THANG = 2

# ─────────────────────────────────────────────
# MỤC 5.3 — Bộ size chính
# ─────────────────────────────────────────────
BO_SIZE_CHINH_LUYKE = 0.80

# ─────────────────────────────────────────────
# MỤC 6.1 — Suất chia theo danh mục & loại CH
# ─────────────────────────────────────────────
# key: số size trong bộ size chính của danh mục -> {loại CH: suất chia}
SUAT_CHIA_TABLE = {
    6: {'I': 6, 'II': 5, 'III': 4, 'IV': 4},   # Quần 10-11 size
    5: {'I': 5, 'II': 4, 'III': 3, 'IV': 3},   # Chemise 9-10 size / hàng 7 size sẽ override riêng bên dưới
    4: {'I': 4, 'II': 4, 'III': 3, 'IV': 3},   # Thun, T-shirt, jacket 6 size
    3: {'I': 3, 'II': 3, 'III': 2, 'IV': 2},   # Hàng 5 size trở xuống
}
SAN_CHUNG_TY_LE = 0.60  # không CH nào nhận dưới 60% bộ size chính
SENTINEL_THANG_TON = 99  # giá trị hiển thị khi tốc độ bán = 0

# ─────────────────────────────────────────────
# MỤC 7.1 — Hệ số tháng phủ định mức tồn
# ─────────────────────────────────────────────
HE_SO_THANG_PHU = {'I': 3.5, 'II': 4.0, 'III': 4.5, 'IV': 5.0}

# ─────────────────────────────────────────────
# MỤC 7.2 — Van điều tiết nhịp nhận
# ─────────────────────────────────────────────
VAN_DIEU_TIET_PCT = 0.125  # 12.5% định mức tồn / đợt (giữa 10-15%)

# ==== Mục 8 — Tồn mục tiêu cửa hàng nhận ====
TON_MUC_TIEU_HE_SO = 3.5

# ==== Mục 8.1 — Bậc Top "Sắp hết hàng" Lần 1 ====
TOP_SAP_HET_LAN1 = [(50, 0.03), (100, 0.05), (150, 0.10), (float('inf'), 0.15)]
# ==== Mục 8.2 — Bậc Top "Bán tốt" Lần 1 (trường hợp 1 - chưa đủ điều kiện chia rộng) ====
TOP_BAN_TOT_LAN1 = [(150, 0.20), (float('inf'), 0.30)]

# ==== Mục 11.2 — Lần 2 (siết còn ~ 1 nửa) ====
TOP_SAP_HET_LAN2 = [(30, 0.03), (60, 0.05), (float('inf'), 0.10)]
TOP_BAN_TOT_LAN2 = [(100, 0.10), (200, 0.20), (float('inf'), 0.30)]

# ==== Mục 12 — Ngưỡng xu hướng Lần 3 ====
XUHUONG_TANG = 1.20
XUHUONG_ON_DINH = 0.90
XUHUONG_GIAM = 0.70
HIEUSUAT_CAO_L3 = 1.20
HIEUSUAT_THAP_L3 = 0.75
GOM_DIEM_L3_MIN, GOM_DIEM_L3_MAX = 5, 10

# ==== Mục 9 — Ma trận điều chuyển: ngưỡng tháng tồn ====
MATRIX_THANG_TON_THAP = 1.5
MATRIX_THANG_TON_CAO = 3.0

# ==== Mục 14.1 — Lô tối thiểu ====
LO_TOI_THIEU_SL = 5
LO_TOI_THIEU_GIA_TRI = 1_000_000

# ==== Giữ tại CH xuất khi rút hàng (Mục 8.3/8.4) ====
GIU_LAI_SO_SIZE = 2   # 2 size liền kề bán tốt nhất, mỗi size 1 cái

# Vùng kinh doanh hợp lệ (loại các dòng "Kho...", "Event", "Ban Giám đốc"...)
VALID_STORE_REGIONS = ["TP. HCM", "Miền Tây", "Miền Trung - TN", "Miền Đông", "Hà Nội"]
VALID_STORE_RANKS = ["I", "II", "III", "IV"]

# Thứ tự size chữ mặc định để xét liền kề khi không phải size số (Phụ lục A)
ALPHA_SIZE_ORDER = ["XS", "S", "M", "L", "XL", "XXL", "2XL", "3XL", "XXXL"]

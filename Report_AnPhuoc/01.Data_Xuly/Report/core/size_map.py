# -*- coding: utf-8 -*-
"""Quy đổi size hệ thống -> size thực tế. Dùng chung cho mọi nguồn dữ liệu
(System_sales, Contract_sales, KhoXuat_CH, NhapTuSX, History_LC, TraKho,
HH_LuanChuyen, HDD, Inventory)."""

# Áp dụng chung cho mọi Report_item_name
SIZE_MAP = {
    "0S": "S", "0M": "M", "0L": "L", "XL": "XL",
    "2X": "XXL", "3X": "3XL", "3XL": "3XL",
    # đo/đặt riêng
    "D1": "DAT1", "D2": "DAT2", "D3": "DAT3", "TS": "DAT3",
    # phụ kiện / không size
    "00": "OneSize", "KHAC": "OneSize",
}

# Size số (5/7/9/11/13/15) chỉ mang nghĩa S/M/L/XL/XXL/3XL với hàng Nữ và Jupe/Váy —
# hàng khác (vd Giày) cũng dùng size số nhưng KHÔNG được quy đổi kiểu này.
FEMALE_SIZE_MAP = {
    "5": "S",  "05": "S",
    "7": "M",  "07": "M",
    "9": "L",  "09": "L",
    "11": "XL", "13": "XXL", "15": "3XL",
}
FEMALE_SIZE_KEYWORDS = ("Nữ", "Jupe", "Váy")


def actual_size(system_size, report_item_name) -> str:
    """Quy đổi size hệ thống -> size thực tế theo SIZE_MAP (và FEMALE_SIZE_MAP nếu là
    hàng Nữ/Jupe/Váy). Size không khớp map (vd size quần 30-39, size giày) giữ nguyên giá trị gốc."""
    s = str(system_size).strip().upper()
    if s in SIZE_MAP:
        return SIZE_MAP[s]

    name = str(report_item_name)
    is_female_group = any(kw in name for kw in FEMALE_SIZE_KEYWORDS)
    if is_female_group:
        if s in FEMALE_SIZE_MAP:
            return FEMALE_SIZE_MAP[s]
        stripped = s.lstrip("0")
        if stripped in FEMALE_SIZE_MAP:
            return FEMALE_SIZE_MAP[stripped]

    return s

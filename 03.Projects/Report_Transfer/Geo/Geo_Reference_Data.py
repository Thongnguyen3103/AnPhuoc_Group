# -*- coding: utf-8 -*-
"""
Geo_Reference_Data.py
Bảng tham chiếu toạ độ cho phường/quận và tỉnh/thành phố.
Hỗ trợ geocoding fallback khi không có địa chỉ chi tiết.

CẬP NHẬT: từ 01/07/2025 cả nước còn 34 tỉnh/thành (Nghị quyết 202/2025/QH15,
sáp nhập từ 63 tỉnh/thành cũ). PROVINCE_COORDS bên dưới dùng ĐÚNG 34 TÊN MỚI vì
địa chỉ trong database thường đã cập nhật theo tên tỉnh mới (vd "Tiền Giang" cũ
giờ ghi là "Đồng Tháp"). WARD_COORDS bổ sung tên các thành phố/tỉnh CŨ (vd "Mỹ
Tho", "Vũng Tàu", "Quy Nhơn"...) để khớp chính xác hơn khi địa chỉ vẫn còn nhắc
tên cũ, tránh bị rơi về toạ độ trung tâm tỉnh mới (có thể cách xa hàng trăm km).
"""

import re

# ── Đối chiếu tỉnh CŨ -> tỉnh MỚI (Nghị quyết 202/2025/QH15, hiệu lực 01/07/2025) ──
# Ghi chú tham khảo, không dùng trực tiếp trong code — để tiện tra cứu khi cần bổ sung.
# An Giang<-Kiên Giang | Bắc Ninh<-Bắc Giang | Cà Mau<-Bạc Liêu | Cần Thơ<-Hậu Giang,Sóc Trăng
# Đà Nẵng<-Quảng Nam | Đắk Lắk<-Phú Yên | Đồng Nai<-Bình Phước | Đồng Tháp<-Tiền Giang
# Gia Lai<-Bình Định | Hưng Yên<-Thái Bình | Khánh Hòa<-Ninh Thuận | Lào Cai<-Yên Bái
# Lâm Đồng<-Đắk Nông,Bình Thuận | Ninh Bình<-Hà Nam,Nam Định | Phú Thọ<-Vĩnh Phúc,Hòa Bình
# Quảng Ngãi<-Kon Tum | Quảng Trị<-Quảng Bình | Tây Ninh<-Long An | Thái Nguyên<-Bắc Kạn
# Tuyên Quang<-Hà Giang | TP.HCM<-Bình Dương,Bà Rịa-Vũng Tàu | Vĩnh Long<-Bến Tre,Trà Vinh
# Hải Phòng<-Hải Dương | (Hà Nội, Cao Bằng, Điện Biên, Hà Tĩnh, Lai Châu, Lạng Sơn,
# Nghệ An, Quảng Ninh, Sơn La, Thanh Hóa, Huế: KHÔNG sáp nhập)

PROVINCE_COORDS = {
    "hà nội": (21.0278, 105.8342),
    "tp. hcm": (10.7769, 106.7009),
    "hồ chí minh": (10.7769, 106.7009),
    "đà nẵng": (16.0544, 108.2022),
    "hải phòng": (20.8449, 106.6881),
    "cần thơ": (10.0452, 105.7469),
    "khánh hòa": (12.2388, 109.1967),
    "khánh hoà": (12.2388, 109.1967),
    "đồng nai": (10.9433, 106.8245),
    "an giang": (10.3860, 105.4350),
    "vũng tàu": (10.3450, 107.0840),
    "quảng ngãi": (15.1211, 108.7977),
    "quảng trị": (16.7500, 107.2000),
    "huế": (16.4637, 107.5909),
    "nghệ an": (19.2069, 104.9650),
    "hà tĩnh": (18.3432, 105.9069),
    "thanh hóa": (19.8067, 105.7838),
    "thanh hoá": (19.8067, 105.7838),
    "ninh bình": (20.2500, 105.9766),
    "hưng yên": (20.6464, 106.0511),
    "bắc ninh": (21.1861, 106.0763),
    "cao bằng": (22.6667, 106.2500),
    "lào cai": (22.4809, 103.9755),
    "lai châu": (22.3964, 103.4703),
    "sơn la": (21.3256, 103.9188),
    "thái nguyên": (21.5942, 105.8482),
    "phú thọ": (21.3227, 105.4023),
    "tuyên quang": (22.8233, 105.2280),
    "cà mau": (9.1768, 105.1525),
    "vĩnh long": (10.2537, 105.9722),
    "đồng tháp": (10.3600, 106.3600),   # trung tâm HC mới đặt tại TP. Mỹ Tho (Tiền Giang cũ)
    "đắk lắk": (12.6667, 108.0500),
    "đắc lắc": (12.6667, 108.0500),
    "gia lai": (13.7820, 109.2190),
    "lâm đồng": (11.9404, 108.4419),
    "tây ninh": (11.3100, 106.0989),
    "quảng ninh": (21.0064, 107.2925),
    "lạng sơn": (21.8537, 106.7610),
    "điện biên": (21.3833, 103.0167),
}

# ── Tên tỉnh/thành CŨ (trước sáp nhập) — vẫn khớp để không phụ thuộc việc DB đã
# cập nhật tên mới hay chưa. Trỏ thẳng tới toạ độ trung tâm tỉnh MỚI tương ứng. ──
PROVINCE_COORDS.update({
    "tp.hcm": PROVINCE_COORDS["tp. hcm"],
    "bình dương": PROVINCE_COORDS["tp. hcm"],
    "bà rịa": PROVINCE_COORDS["vũng tàu"],
    "bà rịa - vũng tàu": PROVINCE_COORDS["vũng tàu"],
    "kiên giang": PROVINCE_COORDS["an giang"],
    "bắc giang": PROVINCE_COORDS["bắc ninh"],
    "bạc liêu": PROVINCE_COORDS["cà mau"],
    "hậu giang": PROVINCE_COORDS["cần thơ"],
    "sóc trăng": PROVINCE_COORDS["cần thơ"],
    "quảng nam": PROVINCE_COORDS["đà nẵng"],
    "phú yên": PROVINCE_COORDS["đắk lắk"],
    "bình phước": PROVINCE_COORDS["đồng nai"],
    "tiền giang": PROVINCE_COORDS["đồng tháp"],
    "bình định": PROVINCE_COORDS["gia lai"],
    "thái bình": PROVINCE_COORDS["hưng yên"],
    "ninh thuận": PROVINCE_COORDS["khánh hòa"],
    "yên bái": PROVINCE_COORDS["lào cai"],
    "đắk nông": PROVINCE_COORDS["lâm đồng"],
    "đắc nông": PROVINCE_COORDS["lâm đồng"],
    "bình thuận": PROVINCE_COORDS["lâm đồng"],
    "hà nam": PROVINCE_COORDS["ninh bình"],
    "nam định": PROVINCE_COORDS["ninh bình"],
    "vĩnh phúc": PROVINCE_COORDS["phú thọ"],
    "hòa bình": PROVINCE_COORDS["phú thọ"],
    "hoà bình": PROVINCE_COORDS["phú thọ"],
    "kon tum": PROVINCE_COORDS["quảng ngãi"],
    "quảng bình": PROVINCE_COORDS["quảng trị"],
    "long an": PROVINCE_COORDS["tây ninh"],
    "bắc kạn": PROVINCE_COORDS["thái nguyên"],
    "hà giang": PROVINCE_COORDS["tuyên quang"],
    "hải dương": PROVINCE_COORDS["hải phòng"],
    "bến tre": PROVINCE_COORDS["vĩnh long"],
    "trà vinh": PROVINCE_COORDS["vĩnh long"],
    "thừa thiên huế": PROVINCE_COORDS["huế"],
})

# ── Cấp phường/quận nội đô TP.HCM & Hà Nội, và TÊN THÀNH PHỐ CŨ (nay là trung
# tâm/thị xã trong tỉnh mới) — khớp trước PROVINCE_COORDS để định vị chính xác
# hơn thay vì rơi về toạ độ trung tâm cả tỉnh mới (có thể lệch hàng trăm km). ──
WARD_COORDS = {
    "quận 1": (10.7757, 106.7005),
    "quận 3": (10.7889, 106.6900),
    "quận 5": (10.7599, 106.6677),
    "quận 7": (10.7388, 106.7100),
    "quận 10": (10.7723, 106.6722),
    "quận 11": (10.7603, 106.6460),
    "quận 12": (10.8544, 106.6362),
    "huyện bình chánh": (10.7446, 106.5851),
    "huyện bình tân": (10.7625, 106.6217),
    "huyện hóc môn": (10.8572, 106.6000),
    "quận ba đình": (21.0355, 105.8228),
    "quận cầu giấy": (21.0407, 105.7845),
    "quận hoàn kiếm": (21.0285, 105.8524),
    "quận hai bà trưng": (21.0110, 105.8608),
    "quận thanh xuân": (20.9838, 105.8124),
    "quận tây hồ": (21.0583, 105.8076),
    "phường 1": (10.7231, 106.3928),
    "phường 2": (10.7265, 106.3870),
    # Thành phố cũ trong TP.HCM mở rộng
    "thủ dầu một": (10.9800, 106.6520),
    "dĩ an": (10.9010, 106.7550),
    "thuận an": (10.9280, 106.7000),
    # Thành phố/thị xã cũ nay thuộc tỉnh mới — ưu tiên khớp trước tên tỉnh mới
    "mỹ tho": (10.3600, 106.3600),          # Tiền Giang cũ -> Đồng Tháp (trung tâm HC mới)
    "cao lãnh": (10.4593, 105.6325),        # Đồng Tháp cũ
    "rạch giá": (10.0125, 105.0808),        # Kiên Giang cũ -> An Giang
    "long xuyên": (10.3860, 105.4350),      # An Giang cũ
    "hà tiên": (10.3800, 104.4900),         # Kiên Giang cũ -> An Giang
    "quy nhơn": (13.7820, 109.2190),        # Bình Định cũ -> Gia Lai
    "pleiku": (13.9833, 108.0000),          # Gia Lai cũ
    "phan rang": (11.5675, 108.9877),       # Ninh Thuận cũ -> Khánh Hòa
    "tuy hòa": (13.0882, 109.2925),         # Phú Yên cũ -> Đắk Lắk
    "buôn ma thuột": (12.6667, 108.0500),   # Đắk Lắk cũ
    "đồng xoài": (11.5357, 106.9179),       # Bình Phước cũ -> Đồng Nai
    "phan thiết": (10.9333, 108.1000),      # Bình Thuận cũ -> Lâm Đồng
    "gia nghĩa": (12.0044, 107.6877),       # Đắk Nông cũ -> Lâm Đồng
    "đà lạt": (11.9404, 108.4419),          # Lâm Đồng cũ
    "bến tre city": (10.2433, 106.3756),
    "trà vinh city": (9.9347, 106.3453),
    "sóc trăng city": (9.6025, 105.9739),   # Sóc Trăng cũ -> Cần Thơ
    "vị thanh": (9.7845, 105.4701),         # Hậu Giang cũ -> Cần Thơ
    "bạc liêu city": (9.2940, 105.7216),    # Bạc Liêu cũ -> Cà Mau
    "nam định city": (20.4341, 106.1675),   # Nam Định cũ -> Ninh Bình
    "phủ lý": (20.5410, 105.9130),          # Hà Nam cũ -> Ninh Bình
    "hải dương city": (20.9373, 106.3145),  # Hải Dương cũ -> Hải Phòng
    "thái bình city": (20.4463, 106.3365),  # Thái Bình cũ -> Hưng Yên
    "bắc giang city": (21.2740, 106.1946),  # Bắc Giang cũ -> Bắc Ninh
    "việt trì": (21.3227, 105.4023),        # Phú Thọ cũ
    "vĩnh yên": (21.3089, 105.6049),        # Vĩnh Phúc cũ -> Phú Thọ
    "hòa bình city": (20.8171, 105.3376),   # Hòa Bình cũ -> Phú Thọ
    "yên bái city": (21.7051, 104.8708),    # Yên Bái cũ -> Lào Cai
    "hà giang city": (22.8025, 104.9784),   # Hà Giang cũ -> Tuyên Quang
    "bắc kạn city": (22.1470, 105.8347),    # Bắc Kạn cũ -> Thái Nguyên
    "đồng hới": (17.4680, 106.6220),        # Quảng Bình cũ -> Quảng Trị
    "tam kỳ": (15.5738, 108.4741),          # Quảng Nam cũ -> Đà Nẵng
    "kon tum city": (14.3545, 108.0076),    # Kon Tum cũ -> Quảng Ngãi
}


def normalize(s):
    if not isinstance(s, str):
        return ""
    s = s.lower().strip()
    s = re.sub(r"[\.\,\-\/]+", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s

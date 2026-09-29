# -*- coding: utf-8 -*-
"""
dc_geo.py
Suy toạ độ từ địa chỉ (WARD_COORDS ú tiên, fallback PROVINCE_COORDS)
Tính khoảng cách Haversine (km) giữa 2 cửa hàng.
"""
import math
import dc_geo_data as geo


def geocode_address(address, region_fallback=None):
    """Trả về (lat, lon, nguon) — nguon giải thích khớp theo cấp nào."""
    if not address or str(address).strip() in ("", "nan", "0", "NaN"):
        if region_fallback:
            key = geo.normalize(region_fallback).replace("tp. ", "").replace("tỉnh ", "")
            for k, v in geo.PROVINCE_COORDS.items():
                if k in key or key in k:
                    return v[0], v[1], f"Fallback theo Vùng: {region_fallback}"
        return None, None, "Không có địa chỉ / không xác định được"

    addr = str(address)
    addr_low = geo.normalize(addr)
    # 1) khớp cấp phường/quận/TP cũ (khoá dài, cụ thể hơn) — kiểm tra khoá dài nhất trước
    for key in sorted(geo.WARD_COORDS.keys(), key=len, reverse=True):
        if key in addr_low:
            lat, lon = geo.WARD_COORDS[key]
            return lat, lon, f"Khớp phường/quận: {key}"

    # 2) khớp cấp tỉnh/thành phố (chuỗi con, không phân biệt hoa/thường)
    for key in sorted(geo.PROVINCE_COORDS.keys(), key=len, reverse=True):
        if key in addr_low:
            lat, lon = geo.PROVINCE_COORDS[key]
            return lat, lon, f"Khớp tỉnh/TP: {key}"

    if region_fallback:
        key = geo.normalize(region_fallback)
        for k, v in geo.PROVINCE_COORDS.items():
            if k in key or key in k:
                return v[0], v[1], f"Fallback theo Vùng: {region_fallback}"
    return None, None, "Không khớp được địa danh nào"


def haversine_km(lat1, lon1, lat2, lon2):
    if None in (lat1, lon1, lat2, lon2):
        return None
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def build_region_distance_matrix(stores_with_coords_df, regions_order):
    """Trả về dict {(vung1,vung2): km} — khoảng cách giữa TÂM (centroid) toạ độ các
    cửa hàng có toạ độ của mỗi vùng. Dùng để vẽ ma trận 5x5 ở Dashboard."""
    centroids = {}
    for region in regions_order:
        sub = stores_with_coords_df[(stores_with_coords_df["Region"] == region) &
                                     stores_with_coords_df["Lat"].notna()]
        if len(sub):
            centroids[region] = (sub["Lat"].mean(), sub["Lon"].mean())
        else:
            centroids[region] = (None, None)
    out = {}
    for r1 in regions_order:
        for r2 in regions_order:
            lat1, lon1 = centroids[r1]
            lat2, lon2 = centroids[r2]
            out[(r1, r2)] = haversine_km(lat1, lon1, lat2, lon2)
    return out


def build_store_coords(scope_stores_df):
    """scope_stores_df cần cột Store_name, Region, Dia_chi. Trả về dict Store_name -> (lat, lon, nguon)."""
    out = {}
    for _, r in scope_stores_df.iterrows():
        lat, lon, src = geocode_address(r.get("Dia_chi"), r.get("Region"))
        out[r["Store_name"]] = (lat, lon, src)
    return out

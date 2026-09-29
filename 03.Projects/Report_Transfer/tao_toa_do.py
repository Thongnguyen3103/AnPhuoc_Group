# -*- coding: utf-8 -*-
"""
tao_toa_do.py
Tạo file ViTri_DiaLy_CuaHang.csv từ bảng A_Region
Suy toạ độ từ địa chỉ bằng geocoder (Nominatim hoặc JSON fallback).
"""
import os
import sys
import pandas as pd
import doc_du_lieu as data
import dia_ly as geo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))  # 01.Python_Projects (dung_chung)
from dung_chung import duong_dan  # noqa: E402

DEFAULT_OUTPUT = os.path.join(HERE, "du_lieu", "ViTri_DiaLy_CuaHang.csv")
DEFAULT_DB = duong_dan.duckdb_database_ap


def main():
    db_path = DEFAULT_DB
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Không tìm thấy database: {db_path}")

    con = data.connect(db_path)
    stores = data.load_scope_stores(con)
    if stores.empty:
        print("Không tìm thấy cửa hàng hợp lệ trong A_Region.")
        return

    rows = []
    for _, row in stores.iterrows():
        address = row.get("Dia_chi")
        region = row.get("Region")
        lat, lon, source = geo.geocode_address(address, region)
        rows.append({
            "Store_name": row["Store_name"],
            "Region": region,
            "Lat": lat,
            "Lon": lon,
            "Source": source,
        })

    out_df = pd.DataFrame(rows)
    out_df = out_df.drop_duplicates("Store_name")
    out_df.to_csv(DEFAULT_OUTPUT, index=False, encoding="utf-8-sig")

    total = len(out_df)
    missing = out_df[~out_df["Lat"].notna() | ~out_df["Lon"].notna()].shape[0]
    print(f"Đã tạo: {os.path.abspath(DEFAULT_OUTPUT)}")
    print(f"Tổng {total} cửa hàng.")
    print(f"{missing} cửa hàng chưa geocode chính xác (Lat/Lon thiếu).")
    if missing:
        print("Hãy mở file CSV và bổ sung Lat/Lon thủ công nếu cần.")


if __name__ == "__main__":
    main()

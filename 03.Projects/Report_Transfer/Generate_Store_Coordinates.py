# -*- coding: utf-8 -*-
"""
Generate_Store_Coordinates.py — Tạo file Data/ViTri_DiaLy_CuaHang.csv từ bảng A_Region.
Suy toạ độ từ địa chỉ bằng geocoder (bảng tham chiếu phường/tỉnh trong Geo/Geo_Reference_Data.py).
Chạy 1 lần (hoặc khi mở CH mới):  python Generate_Store_Coordinates.py
"""
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)   # Report_Transfer -> import Config/Core/...

from Config import Paths_Transfer as paths  # noqa: E402
from Core.Load_Data_Parquet import TransferDataLoader  # noqa: E402
from Geo.Compute_Geo_Distance import GeoLocator  # noqa: E402

DEFAULT_OUTPUT = paths.GEO_CSV
DEFAULT_DATA_ROOT = paths.DATA_ROOT_DEFAULT


def main():
    data_root = DEFAULT_DATA_ROOT
    if not os.path.isdir(data_root):
        raise FileNotFoundError(f"Không tìm thấy kho dữ liệu: {data_root}")

    loader = TransferDataLoader(data_root)
    try:
        stores = loader.load_scope_stores()
    finally:
        loader.close()
    if stores.empty:
        print("Không tìm thấy cửa hàng hợp lệ trong A_Region.")
        return

    rows = []
    for _, row in stores.iterrows():
        address = row.get("Dia_chi")
        region = row.get("Region")
        lat, lon, source = GeoLocator.geocode_address(address, region)
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

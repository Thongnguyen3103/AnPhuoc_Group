# -*- coding: utf-8 -*-
"""
Entrypoint: MASTER DATA LUAN CHUYEN HANG HOA.

  Master_MaHang_LC.parquet  - ma hang, TNSX, size, lan luan chuyen, cua hang nhan
  Data_LuanChuyen.parquet   - dien bien tung lenh: so luong, thoi gian, tien do
  Data_Ban_LC.parquet       - ban tai cua hang nhan, tach theo dot luan chuyen

Logic nam o Core/Master_LC.py. Ket qua: 04.Output/Report_LCHH/Master/

Cach chay:
  python Build_Master_LC.py 2026-10
  python Build_Master_LC.py            # hoi thang; Enter = Config_LCHH.yaml
"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "Core"))
from Load_Config import AppConfig           # noqa: E402
from Master_LC import MasterLCBuilder       # noqa: E402


def main():
    print("=" * 64)
    print(" MASTER DATA LUAN CHUYEN HANG HOA")
    print("=" * 64)

    cfg = AppConfig()
    periods = cfg.resolve_periods()
    if len(periods) != 1:
        raise SystemExit("Chi chon 1 thang chay.")
    year, month = periods[0]
    print(f" Thang chay: {month:02d}.{year}")

    builder = MasterLCBuilder(cfg, year, month)
    master, lc, ban, ok = builder.run()
    builder.save(master, lc, ban)
    print("\nHOAN TAT." if ok else "\nHOAN TAT NHUNG CO LECH DOI SOAT, xem muc [7].")


if __name__ == "__main__":
    main()

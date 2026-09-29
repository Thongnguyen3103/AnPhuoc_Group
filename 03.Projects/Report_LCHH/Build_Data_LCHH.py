# -*- coding: utf-8 -*-
"""
Entrypoint: XAY DUNG DATABASE BAO CAO LENH DIEU CHUYEN HANG HOA LUAN CHUYEN (LCHH).

Logic thuc su nam o Core/ (OOP):
  Core/Load_Config.py    -> AppConfig  (doc Config_LCHH.yaml + nguon du lieu dung chung)
  Core/Pipeline_LCHH.py  -> LCHHPipeline (doc + doi chieu + xuat KQ_LCHH.parquet)

Output (thu muc 04.Output/Report_LCHH/):
  KQ_LCHH.parquet - ket qua chinh, ghi de moi lan chay theo (cac) ky da chon.

Cach chay:
  python Build_Data_LCHH.py                # hoi thang / dung Config_LCHH.yaml
  python Build_Data_LCHH.py 2026-09
  python Build_Data_LCHH.py 2026-08 2026-09 2026-10
"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "Core"))
from Load_Config import AppConfig        # noqa: E402
from Pipeline_LCHH import LCHHPipeline   # noqa: E402


def main():
    print("=" * 64)
    print(" BUILD BAO CAO LENH DIEU CHUYEN HHLC")
    print("=" * 64)

    cfg = AppConfig()
    periods = cfg.resolve_periods()
    print(" Ky bao cao:", ", ".join(f"{m:02d}.{y}" for y, m in periods))

    pipeline = LCHHPipeline(cfg)
    result = pipeline.run(periods)
    pipeline.save(result)

    print("\nHOAN TAT.")


if __name__ == "__main__":
    main()

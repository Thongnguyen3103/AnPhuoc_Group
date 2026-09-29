# -*- coding: utf-8 -*-
"""
Entrypoint: XAY DUNG DATABASE BAO CAO LENH DIEU CHUYEN HANG HOA LUAN CHUYEN (LCHH).

Logic thuc su nam o src/ (OOP):
  src/config.py    -> AppConfig  (doc config/config.yaml + nguon du lieu dung chung)
  src/pipeline.py  -> LCHHPipeline (doc + doi chieu + xuat KQ_LCHH.parquet)

Output (thu muc output/):
  KQ_LCHH.parquet - ket qua chinh, ghi de moi lan chay theo (cac) ky da chon.

Cach chay:
  python build_report.py                # hoi thang / dung config/config.yaml
  python build_report.py 2026-09
  python build_report.py 2026-08 2026-09 2026-10
"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
from config import AppConfig        # noqa: E402
from pipeline import LCHHPipeline   # noqa: E402


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

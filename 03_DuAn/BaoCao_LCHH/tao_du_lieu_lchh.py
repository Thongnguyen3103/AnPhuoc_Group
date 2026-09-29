# -*- coding: utf-8 -*-
"""
Entrypoint: XAY DUNG DATABASE BAO CAO LENH DIEU CHUYEN HANG HOA LUAN CHUYEN (LCHH).

Logic thuc su nam o xu_ly/ (OOP):
  xu_ly/cau_hinh.py    -> AppConfig  (doc cau_hinh.yaml + nguon du lieu dung chung)
  xu_ly/quy_trinh_lchh.py  -> LCHHPipeline (doc + doi chieu + xuat KQ_LCHH.parquet)

Output (thu muc 04_KetQua/BaoCao_LCHH/):
  KQ_LCHH.parquet - ket qua chinh, ghi de moi lan chay theo (cac) ky da chon.

Cach chay:
  python tao_du_lieu_lchh.py                # hoi thang / dung cau_hinh.yaml
  python tao_du_lieu_lchh.py 2026-09
  python tao_du_lieu_lchh.py 2026-08 2026-09 2026-10
"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "xu_ly"))
from cau_hinh import AppConfig        # noqa: E402
from quy_trinh_lchh import LCHHPipeline   # noqa: E402


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

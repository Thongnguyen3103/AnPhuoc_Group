# -*- coding: utf-8 -*-
"""
Entrypoint: HIEU SUAT BAN SAU LUAN CHUYEN (bao cao DOC LAP).

Chay rieng, KHONG phu thuoc tao_du_lieu_lchh.py / KQ_LCHH.parquet - tu doc va
xu ly tu data goc (tai su dung xu_ly/quy_trinh_lchh.py), roi ghep them doanh so
+ ton kho. Xem README.md de biet chi tiet cong thuc.

Logic thuc su nam o xu_ly/hieu_suat.py -> class PerformanceAnalyzer.

Output: 04_KetQua/BaoCao_LCHH/KQ_LCHH_HieuSuat.parquet

Cach chay:
  python tao_du_lieu_hieu_suat.py 2026-08
  python tao_du_lieu_hieu_suat.py            # hoi thang; Enter = cau_hinh.yaml
"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "xu_ly"))
from cau_hinh import AppConfig                # noqa: E402
from hieu_suat import PerformanceAnalyzer  # noqa: E402


def main():
    print("=" * 64)
    print(" HIEU SUAT BAN SAU LUAN CHUYEN")
    print("=" * 64)

    cfg = AppConfig()
    periods = cfg.resolve_periods()
    print(" Ky bao cao:", ", ".join(f"{m:02d}.{y}" for y, m in periods))

    analyzer = PerformanceAnalyzer(cfg)
    result = analyzer.run(periods)
    analyzer.save(result)

    print("\nHOAN TAT.")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""
Entrypoint: HIEU SUAT BAN SAU LUAN CHUYEN (bao cao DOC LAP).

Chay rieng, KHONG phu thuoc build_report.py / KQ_LCHH.parquet - tu doc va
xu ly tu data goc (tai su dung src/pipeline.py), roi ghep them doanh so
+ ton kho. Xem README.md de biet chi tiet cong thuc.

Logic thuc su nam o src/performance.py -> class PerformanceAnalyzer.

Output: output/KQ_LCHH_HieuSuat.parquet

Cach chay:
  python build_performance.py 2026-08
  python build_performance.py            # hoi thang; Enter = config/config.yaml
"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
from config import AppConfig                # noqa: E402
from performance import PerformanceAnalyzer  # noqa: E402


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

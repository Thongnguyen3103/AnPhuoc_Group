# -*- coding: utf-8 -*-
"""
Entrypoint: HIEU SUAT BAN SAU LUAN CHUYEN (bao cao DOC LAP).

Chay rieng, KHONG phu thuoc Build_Data_LCHH.py / KQ_LCHH.parquet - tu doc va
xu ly tu data goc (tai su dung Core/Pipeline_LCHH.py), roi ghep them doanh so
+ ton kho. Xem README.md de biet chi tiet cong thuc.

Logic thuc su nam o Core/Analyze_Performance.py -> class PerformanceAnalyzer.

Output: 04.Output/Report_LCHH/KQ_LCHH_HieuSuat.parquet

Cach chay:
  python Build_Data_Performance.py 2026-08
  python Build_Data_Performance.py            # hoi thang; Enter = Config_LCHH.yaml
"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "Core"))
from Load_Config import AppConfig                # noqa: E402
from Analyze_Performance import PerformanceAnalyzer  # noqa: E402


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

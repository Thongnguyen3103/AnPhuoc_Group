#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
cap_nhat_bao_cao.py — Orchestrator chính của Hệ thống Báo Cáo Tổng Hợp An Phước
Thực hiện 1 lệnh duy nhất:
  [1] lam_moi_cache -> du_lieu_tam/cache_ban_hang.parquet
  [2] tong_hop_ban -> ban_payload (overview + top-N)
  [3] tong_hop_ton -> ton_payload (overview + size matrix)
  [4] kiem_tra      -> đối chiếu số liệu payload ↔ nguồn
  [5] xuat_html     -> gzip + base64 + nhúng vào 04_KetQua/BaoCao_TongHop/BaoCao_TongHop.html
"""
import os
import sys
import time
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND_DIR)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(BACKEND_DIR))))  # 01.Python_Projects (dung_chung)

from cac_buoc import lam_moi_cache
from cac_buoc import tong_hop_ban
from cac_buoc import tong_hop_ton
from cac_buoc import kiem_tra
import xuat_html


def main():
    start_time = time.time()
    force_refresh = '--force-cache' in sys.argv or '--force' in sys.argv

    print('#' * 70)
    print('  HỆ THỐNG TRÌNH SINH BÁO CÁO TỔNG HỢP (TỒN & SỐ BÁN) AN PHƯỚC')
    print(f'  Khởi chạy: {datetime.now():%d/%m/%Y %H:%M:%S}')
    print('#' * 70)

    try:
        # Stage 1: Refresh cache nếu cần
        lam_moi_cache.run(force=force_refresh)

        # Dictionary chuỗi dùng chung giữa Tồn và Bán
        shared_dict = {'list': [], 'map': {}}

        # Stage 2: Tổng hợp Số Bán & Xác định kỳ tham chiếu
        ban_payload, shared_dict, ref_year, ref_month = tong_hop_ban.run(shared_dict=shared_dict)

        # Stage 3: Tổng hợp Số Tồn
        ton_payload, shared_dict = tong_hop_ton.run(
            shared_dict=shared_dict,
            ref_year=ref_year,
            ref_month=ref_month
        )

        # Stage 4: Validate tính toàn vẹn
        kiem_tra.run(ton_payload, ban_payload)

        # Stage 5: Render & Xuất bản HTML tự chứa
        out_file = xuat_html.run(
            ton_payload=ton_payload,
            ban_payload=ban_payload,
            shared_dict=shared_dict,
            ref_year=ref_year,
            ref_month=ref_month
        )

        total_sec = time.time() - start_time
        print('\n' + '=' * 70)
        print(f'  HOÀN THÀNH TOÀN BỘ TIẾN TRÌNH BUILD ({total_sec:.1f} giây)')
        print(f'  File báo cáo sẵn sàng: {out_file}')
        print('=' * 70 + '\n')

    except Exception as e:
        print('\n' + '!' * 70)
        print(f'  LỖI TIẾN TRÌNH BUILD: {e}')
        print('!' * 70 + '\n')
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

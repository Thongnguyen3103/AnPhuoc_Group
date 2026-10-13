# -*- coding: utf-8 -*-
"""Đường dẫn của project Report_Transfer (lấy gốc từ 00.Shared/Config_Paths.yaml).
Đồng thời đưa 00.Shared vào sys.path để import Get_Paths / Read_Write_Parquet."""
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))          # Report_Transfer
SHARED_DIR = os.path.join(os.path.dirname(os.path.dirname(PROJECT_DIR)), "00.Shared")
if SHARED_DIR not in sys.path:
    sys.path.insert(0, SHARED_DIR)
import Get_Paths  # noqa: E402

DATA_DIR = os.path.join(PROJECT_DIR, "Data")
STATE_FILE = os.path.join(DATA_DIR, "lich_su_hieu_suat_ky.json")     # Hiệu suất kỳ đã lưu (Xu hướng Lần 3)
GEO_CSV = os.path.join(DATA_DIR, "ViTri_DiaLy_CuaHang.csv")          # toạ độ cửa hàng
KHONG_RUT_FILE = os.path.join(DATA_DIR, "CH_khong_rut.json")         # CH mới / không tham gia rút (chọn trên GUI)

DATA_ROOT_DEFAULT = Get_Paths.DATA_ROOT       # 00.Data_AnPhuoc_Group (chứa 02.Master, 03.Data_Parquest)


def output_dir_default():
    """04.Output/Report_Transfer (tự tạo)."""
    return Get_Paths.thu_muc_ket_qua("Report_Transfer")

# -*- coding: utf-8 -*-
"""Toàn bộ đường dẫn thư mục/file dùng trong pipeline, gom về 1 chỗ duy nhất.

Muốn đổi vị trí ổ đĩa, thư mục nguồn hay nơi lưu Parquet/CSV — chỉ cần sửa ở
đây, KHÔNG cần sửa từng file trong sources/, export/, utils/ nữa."""


class Paths:
    # ── Gốc dữ liệu ─────────────────────────────────────────────
    DATA_ROOT = r"D:\AnPhuocGroup\AnPhuoc_Data\00.Data_AnPhuoc_Group"

    # ── Nguồn (input) — nơi đọc file CSV/Excel gốc ─────────────
    SYSTEM_SALES_DIR = DATA_ROOT + r"\01.Source\01.System_sales"
    CONTRACT_SALES_DIR = DATA_ROOT + r"\01.Source\02.Contract_sales"
    INVENTORY_DIR = DATA_ROOT + r"\01.Source\03.Inventory_data"
    HDD_QLKD_DIR = DATA_ROOT + r"\01.Source\04.HDD\1.HDD_QLKD"
    HDD_REPORT_DIR = DATA_ROOT + r"\01.Source\04.HDD\2.HDD_Report"
    KHO_XUAT_DIR = DATA_ROOT + r"\01.Source\04.KhoXuat_CH"
    NHAP_SX_DIR = DATA_ROOT + r"\01.Source\05.NhapSX"
    DATA_TRACKING_2025_FILE = DATA_ROOT + r"\01.Source\07.Data_Raw\Data_Tracking_2025.xlsx"
    HISTORY_LC_DIR = DATA_ROOT + r"\01.Source\09.History_LC"
    TRA_KHO_DIR = DATA_ROOT + r"\01.Source\10.TraKho"

    # Nguồn nằm trên ổ mạng (không thuộc DATA_ROOT)
    HHLC_DIR = r"\\hovmfs01\PKD\PhanPhoi\DieuChuyen_HH_HTCH\Recode_DieuChuyen"
    DATA_TRACKING_FILE = r"\D:\AnPhuocGroup\AnPhuoc_Report\Analysis_data\1.Processed_data\1.Data_Tracking.xlsx"
    STORE_RANK_FILE = r"X:\Hang Ni\DOANH THU DOI CHIEU NXT\2026\1. DS TONG HOP XEP LOAI CUA HANG 2026.xlsx"
    DMHH_DIR = r"X:\ANAMAI BONJOUR"

    # ── Đầu ra (output) — nơi lưu kết quả ───────────────────────
    MASTER_DIR = DATA_ROOT + r"\02.Master"
    PARQUET_ROOT = DATA_ROOT + r"\03.Data_Parquest"
    INVENTORY_PARQUET_DIR = PARQUET_ROOT + r"\03.Inventory"
    CSV_EXPORT_DIR = DATA_ROOT + r"\05.Data_Csv"

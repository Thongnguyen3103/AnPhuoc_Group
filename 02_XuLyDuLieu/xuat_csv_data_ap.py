# -*- coding: utf-8 -*-
r"""Xuất các bảng Parquet đã xử lý ra CSV cho Data_ReportAP.

Ghi vào: 05.Data_Csv (key csv_xuat trong dung_chung/cau_hinh.yaml)
"""
import os
import sys
import time
import io
import subprocess
import msvcrt
import duckdb
import pandas as pd

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # 01.Python_Projects (dung_chung)
from dung_chung.doc_ghi_parquet import MASTER_DIR, PARQUET_ROOT
from dung_chung import duong_dan

OUT_DIR = duong_dan.csv_xuat
YEARS = (2024, 2025, 2026)


def _glob(*parts: str) -> str:
    """Glob pattern kiểu <PARQUET_ROOT>/<...>/*/*.parquet (năm/tháng)."""
    return os.path.join(PARQUET_ROOT, *parts, "*", "*.parquet")


def _master(name: str) -> str:
    return os.path.join(MASTER_DIR, f"{name}.parquet")


EXPORTS = [
    # (table_name, parquet_glob, extra_where, out_name, subdir)
    ("System_sales", _glob("01.System_sales"), f'"Year" IN {YEARS}', "System_sales.csv", "02.Raw"),
    ("Contract_sales", _glob("02.Contract_sales"), f'"Year" IN {YEARS}', "Contract_sales.csv", "02.Raw"),
    ("Inventory", os.path.join(PARQUET_ROOT, "03.Inventory", "InventorySize.parquet"), None, "Inventory.csv", "02.Raw"),
    ("KhoXuat_CH", _glob("06.KhoXuat_CH"), f'"Year" IN {YEARS}', "KhoXuat_CH.csv", "02.Raw"),
    ("NhapTuSX", _glob("05.NhapSX"), f'"Year" IN {YEARS}', "NhapTuSX.csv", "02.Raw"),
    ("A_Region", _master("A_Region"), None, "A_Region.csv", "01.Master"),
    ("B_Size", _master("B_Size"), None, "B_Size.csv", "01.Master"),
    ("D_Category", _master("D_Category"), None, "D_Category.csv", "01.Master"),
    ("C_BasicSizeChart", _master("C_BasicSizeChart"), None, "C_BasicSizeChart.csv", "01.Master"),
    ("E_T-Shirt", _master("E_T-Shirt"), None, "E_T-Shirt.csv", "01.Master"),
    ("F_DataTracking", _master("F_DataTracking"), None, "F_DataTracking.csv", "01.Master"),
    ("HDD_QLKD_Tong_hop", _master("HDD_QLKD_Tong_hop"), None, "HDD_QLKD_Tong_hop.csv", "01.Master"),
]


def _clear_readonly_hidden(path: str) -> None:
    """Bỏ thuộc tính Hidden/Read-only/System của file cũ trước khi ghi đè.
    File chỉ bị đặt thuộc tính Hidden vẫn có thể ghi đè được về mặt hệ điều hành,
    nhưng một số trường hợp (đồng bộ mạng, file do tiến trình khác tạo) Windows vẫn
    trả PermissionError — chủ động gỡ thuộc tính trước để tránh lỗi ghi không rõ nguyên nhân."""
    if os.path.exists(path):
        try:
            subprocess.run(["attrib", "-h", "-r", "-s", path], check=False)
        except Exception:
            pass


def _write_csv_with_retry(df: pd.DataFrame, out_path: str, max_retries: int = 3) -> bool:
    _clear_readonly_hidden(out_path)
    for attempt in range(max_retries):
        try:
            df.to_csv(out_path, index=False, encoding="utf-8-sig")
            return True
        except PermissionError:
            _clear_readonly_hidden(out_path)
            if attempt < max_retries - 1:
                wait = 2 ** (attempt + 1)
                print(f"  File đang mở, chờ {wait}s...")
                time.sleep(wait)
            else:
                print(f"  [LỖI] File đang bị khoá, không ghi được: {out_path}")
    return False


class ExportManager:
    """Xuất các bảng Parquet đã xử lý (System_sales, Inventory, các bảng Master...)
    ra CSV cho Data_ReportAP."""

    def __init__(self, exports=None):
        self.exports = exports if exports is not None else EXPORTS

    def select_exports_menu(self) -> list:
        """Checkbox chọn bảng cần export (↑↓ | Space tích | Enter xác nhận).
        Mặc định tất cả đã được tích sẵn."""
        names = [name for name, _, _, _, _ in EXPORTS]
        selected = [True] * len(names)
        cursor = 0

        def draw():
            os.system("cls")
            print("\n" + "=" * 50)
            print("     CHỌN BẢNG CẦN EXPORT")
            print("=" * 50)
            print("  ↑↓ di chuyển   Space tích/bỏ   Enter xác nhận")
            print("─" * 50)
            for i, name in enumerate(names):
                arrow = "▶" if i == cursor else " "
                check = "✓" if selected[i] else " "
                print(f"  {arrow} [{check}]  {name}")
            print("=" * 50)

        while True:
            draw()
            key = msvcrt.getch()
            if key == b"\xe0":
                key2 = msvcrt.getch()
                if key2 == b"H":
                    cursor = (cursor - 1) % len(names)
                elif key2 == b"P":
                    cursor = (cursor + 1) % len(names)
            elif key == b" ":
                selected[cursor] = not selected[cursor]
            elif key in (b"\r", b"\n"):
                return [EXPORTS[i] for i, s in enumerate(selected) if s]
            elif key == b"\x1b":
                return list(EXPORTS)

    def run(self, interactive: bool = False) -> None:
        exports = self.select_exports_menu() if interactive else self.exports

        con = duckdb.connect()
        for table_name, parquet_path, extra_where, out_name, subdir in exports:
            out_dir = os.path.join(OUT_DIR, subdir)
            os.makedirs(out_dir, exist_ok=True)
            out_path = os.path.join(out_dir, out_name)

            query = f"SELECT * FROM read_parquet('{parquet_path}')"
            if extra_where:
                query += f" WHERE {extra_where}"

            try:
                df = con.execute(query).df()
            except duckdb.Error as e:
                print(f"  [BỎ QUA] Không đọc được Parquet \"{table_name}\" ({parquet_path}): {e}")
                continue

            ok = _write_csv_with_retry(df, out_path)
            status = f"Đã ghi -> {out_path}" if ok else "GHI THẤT BẠI"
            print(f"[{table_name}] {len(df):,} dòng | {status}")

        con.close()
        print("\nHoàn tất.")


def main(exports=None, interactive=False):
    ExportManager(exports).run(interactive=interactive)


if __name__ == "__main__":
    main(interactive=True)

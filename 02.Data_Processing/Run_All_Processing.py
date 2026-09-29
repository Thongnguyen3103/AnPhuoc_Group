import msvcrt
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "00.Shared"))  # 00.Shared (Get_Paths...)
from Sources.Update_Master_Tables import DataTrackingProcessor
from Sources.Process_InTransit_HDD import HDDProcessor
from Sources.Process_Inventory import InventoryProcessor
from Sources.Process_Sales import SystemSalesProcessor, ContractSalesProcessor
from Sources.Process_Warehouse_To_Store import KhoXuatCHProcessor
from Sources.Process_Production_Receipt import NhapTuSXProcessor
from Sources.Process_Transfer_History import HistoryLCProcessor
from Sources.Process_Return_To_Warehouse import TraKhoProcessor
from Sources.Process_Transfer_Orders import LenhLuanChuyenProcessor
from Convert_Xls_To_Xlsx import ExcelFormatConverter, FOLDER_HDD_QLKD


# ──────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────

def timed(label: str, fn):
    print(f"\n{'─' * 60}")
    print(f"  {label}")
    print(f"{'─' * 60}")
    t0 = time.time()
    fn()
    print(f"  ✓ Xong ({time.time() - t0:.1f}s)")


# ──────────────────────────────────────────────────────────
# Các tác vụ
# ──────────────────────────────────────────────────────────

def run_master_refresh():
    timed("MASTER (Parquet) — cập nhật lookup tables", DataTrackingProcessor().run)


def run_hdd_ton():
    timed("FORMAT XLS → XLSX", lambda: ExcelFormatConverter().convert_folder(FOLDER_HDD_QLKD))
    timed("XỬ LÝ HDD", HDDProcessor().run)
    timed("XỬ LÝ TỒN KHO (+ HDD)", InventoryProcessor().run)


def run_ban_le(processor: SystemSalesProcessor = None, lookups=None):
    processor = processor or SystemSalesProcessor()
    timed("SỐ BÁN LẺ — System_sales", lambda: processor.run(lookups=lookups))


def run_ban_hd(processor: ContractSalesProcessor = None, lookups=None):
    processor = processor or ContractSalesProcessor()
    timed("BÁN HỢP ĐỒNG — Contract_sales", lambda: processor.run(lookups=lookups))


def run_kho_xuat_ch():
    timed("KHO XUẤT CH — KhoXuat_CH", KhoXuatCHProcessor().run)


def run_nhap_tu_sx():
    timed("NHẬP TỪ SX — NhapTuSX", NhapTuSXProcessor().run)


def run_history_lc():
    timed("LỊCH SỬ LUÂN CHUYỂN — History_LC", HistoryLCProcessor().run)


def run_tra_kho():
    timed("TRẢ KHO — TraKho", TraKhoProcessor().run)


def run_lenh_luan_chuyen():
    timed("LỆNH ĐIỀU CHUYỂN — HH_LuanChuyen", LenhLuanChuyenProcessor().run)


def run_all():
    run_master_refresh()
    run_hdd_ton()
    sales_lookups = SystemSalesProcessor().load_lookups()
    run_ban_le(lookups=sales_lookups)
    run_ban_hd(lookups=sales_lookups)
    run_kho_xuat_ch()
    run_nhap_tu_sx()
    run_history_lc()
    run_tra_kho()
    run_lenh_luan_chuyen()


# ──────────────────────────────────────────────────────────
# Menu items
# ──────────────────────────────────────────────────────────

MENU = [
    ("Master (Parquet)  (cập nhật lookup tables)",   run_master_refresh),
    ("HDD + Tồn kho     (format → HDD → Inventory)", run_hdd_ton),
    ("Số bán lẻ         (System_sales)",              run_ban_le),
    ("Bán Hợp Đồng      (Contract_sales)",            run_ban_hd),
    ("Kho Xuất CH       (KhoXuat_CH)",                run_kho_xuat_ch),
    ("Nhập từ SX        (NhapTuSX)",                  run_nhap_tu_sx),
    ("Lịch sử Luân chuyển (History_LC)",              run_history_lc),
    ("Trả Kho           (TraKho)",                    run_tra_kho),
    ("Lệnh Điều chuyển  (HH_LuanChuyen)",             run_lenh_luan_chuyen),
    ("Tất cả",                                        run_all),
]

IDX_BAN_LE     = 2
IDX_BAN_HD     = 3
IDX_KHO_XUAT   = 4
IDX_NHAP_SX    = 5
IDX_HISTORY_LC = 6
IDX_TRA_KHO    = 7
IDX_LENH_DC    = 8
IDX_ALL        = 9


# ──────────────────────────────────────────────────────────
# Interactive checkbox  (↑↓ | Space tích | Enter chạy)
# ──────────────────────────────────────────────────────────

IDX_CANCEL = len(MENU)   # cursor đặc biệt trỏ vào nút HỦY


def draw(selected: list, cursor: int) -> None:
    os.system("cls")
    print("\n" + "=" * 62)
    print("        BÁO CÁO AN PHƯỚC — CHỌN MỤC CẦN CHẠY")
    print("=" * 62)
    print("  ↑↓ di chuyển    Space tích/bỏ    Enter xác nhận")
    print("─" * 62)
    for i, (label, _) in enumerate(MENU):
        arrow = "▶" if i == cursor else " "
        check = "✓" if selected[i] else " "
        print(f"  {arrow} [{check}]  {label}")
    print("─" * 62)
    cancel_arrow = "▶" if cursor == IDX_CANCEL else " "
    print(f"  {cancel_arrow}  [ HỦY — Thoát không chạy ]")
    print("─" * 62)
    ticked = [MENU[i][0].split("(")[0].strip() for i, s in enumerate(selected) if s]
    if ticked:
        print(f"  Đã chọn: {', '.join(ticked)}")
    else:
        print("  Chưa chọn mục nào")
    print("=" * 62)


def checkbox_menu() -> list:
    """Trả về danh sách index các mục được tích, hoặc [] nếu hủy."""
    selected = [False] * len(MENU)
    cursor   = 0
    n_rows   = IDX_CANCEL + 1   # tổng số dòng điều hướng (menu + nút HỦY)

    while True:
        draw(selected, cursor)
        key = msvcrt.getch()

        if key == b"\xe0":                  # phím mũi tên
            key2 = msvcrt.getch()
            if key2 == b"H":               # ↑
                cursor = (cursor - 1) % n_rows
            elif key2 == b"P":             # ↓
                cursor = (cursor + 1) % n_rows

        elif key == b" ":                   # Space — tích / bỏ tích (chỉ cho menu items)
            if cursor < len(MENU):
                selected[cursor] = not selected[cursor]

        elif key in (b"\r", b"\n"):         # Enter
            if cursor == IDX_CANCEL:
                return []                   # HỦY
            return [i for i, s in enumerate(selected) if s]

        elif key == b"\x1b":               # Esc — cũng hủy
            return []


# ──────────────────────────────────────────────────────────
# Thực thi
# ──────────────────────────────────────────────────────────

def execute(indices: list) -> None:
    if not indices:
        print("\n  Không có mục nào được chọn.\n")
        return

    idx_set = set(indices)
    t_total = time.time()

    if IDX_ALL in idx_set:
        run_all()
    else:
        if 0 in idx_set:
            run_master_refresh()
        if 1 in idx_set:
            run_hdd_ton()

        sales = idx_set & {IDX_BAN_LE, IDX_BAN_HD}
        if sales:
            sales_lookups = SystemSalesProcessor().load_lookups()
            if IDX_BAN_LE in sales:
                run_ban_le(lookups=sales_lookups)
            if IDX_BAN_HD in sales:
                run_ban_hd(lookups=sales_lookups)

        if IDX_KHO_XUAT in idx_set:
            run_kho_xuat_ch()

        if IDX_NHAP_SX in idx_set:
            run_nhap_tu_sx()

        if IDX_HISTORY_LC in idx_set:
            run_history_lc()

        if IDX_TRA_KHO in idx_set:
            run_tra_kho()

        if IDX_LENH_DC in idx_set:
            run_lenh_luan_chuyen()

    labels = ", ".join(MENU[i][0].split("(")[0].strip() for i in indices)
    print(f"\n{'=' * 62}")
    print(f"  ✅ HOÀN THÀNH ({time.time() - t_total:.1f}s)")
    print(f"  Đã chạy: {labels}")
    print("=" * 62)


# ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    chosen = checkbox_menu()
    os.system("cls")
    execute(chosen)
    input("\n  Nhấn Enter để đóng...")

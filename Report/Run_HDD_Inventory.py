import importlib.util
import msvcrt
import os
import time
from pathlib import Path

REPORT_DIR = Path(__file__).parent


# ──────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────

def load_module(file_name: str):
    path = REPORT_DIR / file_name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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

def run_database_duckdb():
    timed("DATABASE DUCKDB — cập nhật lookup tables",
          load_module("Database_duckdb.py").main)


def run_hdd_ton():
    timed("FORMAT XLS → XLSX",       load_module("XuLy_FormatExcel.py").main)
    timed("XỬ LÝ HDD",               load_module("Xu_ly_HDD.py").main)
    timed("XỬ LÝ TỒN KHO (+ HDD)",  load_module("Xu_ly_Inventory.py").main)


def run_ban_le(mod=None, lookups=None):
    if mod is None:
        mod = load_module("XuLy_ChiTietBan.py")
        lookups = mod.load_db()
    timed("SỐ BÁN LẺ — System_sales",
          lambda: mod.process_system_sales(*lookups))


def run_ban_hd(mod=None, lookups=None):
    if mod is None:
        mod = load_module("XuLy_ChiTietBan.py")
        lookups = mod.load_db()
    timed("BÁN HỢP ĐỒNG — Contract_sales",
          lambda: mod.process_contract_sales(*lookups))


def run_all():
    run_database_duckdb()
    run_hdd_ton()
    mod = load_module("XuLy_ChiTietBan.py")
    lookups = mod.load_db()
    run_ban_le(mod, lookups)
    run_ban_hd(mod, lookups)


# ──────────────────────────────────────────────────────────
# Menu items
# ──────────────────────────────────────────────────────────

MENU = [
    ("Database DuckDB   (cập nhật lookup tables)",   run_database_duckdb),
    ("HDD + Tồn kho     (format → HDD → Inventory)", run_hdd_ton),
    ("Số bán lẻ         (System_sales)",              run_ban_le),
    ("Bán Hợp Đồng      (Contract_sales)",            run_ban_hd),
    ("Tất cả",                                        run_all),
]

IDX_ALL    = 4
IDX_BAN_LE = 2
IDX_BAN_HD = 3


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
            run_database_duckdb()
        if 1 in idx_set:
            run_hdd_ton()

        sales = idx_set & {IDX_BAN_LE, IDX_BAN_HD}
        if sales:
            mod     = load_module("XuLy_ChiTietBan.py")
            lookups = mod.load_db()
            if IDX_BAN_LE in sales:
                run_ban_le(mod, lookups)
            if IDX_BAN_HD in sales:
                run_ban_hd(mod, lookups)

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

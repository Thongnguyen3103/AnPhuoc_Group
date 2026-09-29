# -*- coding: utf-8 -*-
"""Convert file Excel 2003 (.xls) sang .xlsx bằng Excel COM (win32com), dùng
trước bước xử lý HDD_QLKD (Xu_ly_HDD chỉ đọc .csv/.xlsx)."""
import os
import sys
import glob
import win32com.client as win32

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "00.Shared"))  # 00.Shared (Get_Paths...)
import Get_Paths

FOLDER_HDD_QLKD = Get_Paths.nguon_hdd_qlkd


class ExcelFormatConverter:
    def convert_folder(self, folder_path: str) -> None:
        folder_path = os.path.abspath(folder_path)

        if not os.path.isdir(folder_path):
            print(f"[-] Lỗi: Thư mục '{folder_path}' không tồn tại.")
            return

        xls_files = glob.glob(os.path.join(folder_path, "*.xls"))
        if not xls_files:
            print(f"[-] Không tìm thấy file .xls nào trong thư mục '{folder_path}'.")
            return

        print(f"[+] Tìm thấy {len(xls_files)} file .xls. Bắt đầu chuyển đổi...\n")

        excel = None
        try:
            excel = win32.gencache.EnsureDispatch('Excel.Application')
            excel.Visible = False
            excel.DisplayAlerts = False

            count = 0
            for xls_file in xls_files:
                try:
                    abs_xls_file = os.path.abspath(xls_file)
                    xlsx_file = abs_xls_file + "x"

                    wb = excel.Workbooks.Open(abs_xls_file)

                    # Xóa các sheet không có dữ liệu (duyệt ngược để tránh lỗi index khi xóa)
                    sheet_count = wb.Sheets.Count
                    empty_sheets = []
                    for i in range(sheet_count, 0, -1):
                        sheet = wb.Sheets(i)
                        if excel.WorksheetFunction.CountA(sheet.Cells) == 0:
                            empty_sheets.append(sheet)
                    if len(empty_sheets) < sheet_count:
                        for sheet in empty_sheets:
                            sheet.Delete()

                    wb.SaveAs(xlsx_file, FileFormat=51)
                    wb.Close()
                    os.remove(abs_xls_file)

                    print(f"  -> Đã chuyển và xóa file cũ: {os.path.basename(xls_file)} => {os.path.basename(xlsx_file)}")
                    count += 1
                except Exception as e:
                    print(f"  -> [Lỗi] Không thể chuyển đổi {os.path.basename(xls_file)}: {e}")

            print(f"\n[+] Hoàn thành! Đã chuyển đổi thành công {count}/{len(xls_files)} file.")

        except Exception as e:
            print(f"[-] Lỗi hệ thống khi mở Excel: {e}")
            print("Hãy chắc chắn rằng máy tính của bạn đã cài đặt Microsoft Excel và thư viện pywin32.")
        finally:
            if excel:
                try:
                    excel.Application.Quit()
                except Exception:
                    pass


def main():
    ExcelFormatConverter().convert_folder(FOLDER_HDD_QLKD)


if __name__ == "__main__":
    print("=" * 60)
    print("   TOOL CHUYỂN ĐỔI EXCEL 2003 (.xls) SANG WORKSHEET (.xlsx)")
    print("=" * 60)

    folder_input = input("\nNhập đường dẫn thư mục chứa các file .xls (VD: D:\\Data\\Files): ")
    folder_input = folder_input.strip('"\'')

    if folder_input:
        ExcelFormatConverter().convert_folder(folder_input)
    else:
        print("[-] Đường dẫn không hợp lệ.")

    print("\n")
    os.system("pause")

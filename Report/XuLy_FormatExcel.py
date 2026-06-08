import os
import glob
import win32com.client as win32

def convert_xls_to_xlsx(folder_path):
    # Chuẩn hóa đường dẫn
    folder_path = os.path.abspath(folder_path)
    
    # Kiểm tra thư mục có tồn tại không
    if not os.path.isdir(folder_path):
        print(f"[-] Lỗi: Thư mục '{folder_path}' không tồn tại.")
        return

    # Tìm tất cả các file .xls (bao gồm cả Excel 2003)
    xls_files = glob.glob(os.path.join(folder_path, "*.xls"))
    
    if not xls_files:
        print(f"[-] Không tìm thấy file .xls nào trong thư mục '{folder_path}'.")
        return

    print(f"[+] Tìm thấy {len(xls_files)} file .xls. Bắt đầu chuyển đổi...\n")

    excel = None
    try:
        # Khởi tạo ứng dụng Excel ẩn trong background
        excel = win32.gencache.EnsureDispatch('Excel.Application')
        excel.Visible = False
        excel.DisplayAlerts = False # Tắt các cảnh báo của Excel
        
        count = 0
        for xls_file in xls_files:
            try:
                abs_xls_file = os.path.abspath(xls_file)
                # Đổi đuôi thành .xlsx
                xlsx_file = abs_xls_file + "x" 
                
                # Nếu file .xlsx đã tồn tại thì bỏ qua hoặc ghi đè (ở đây là ghi đè do DisplayAlerts=False)
                
                # Mở file .xls
                wb = excel.Workbooks.Open(abs_xls_file)
                
                # --- Xóa các sheet không có dữ liệu ---
                sheet_count = wb.Sheets.Count
                empty_sheets = []
                # Duyệt ngược để tránh bị lỗi index khi xóa sheet
                for i in range(sheet_count, 0, -1):
                    sheet = wb.Sheets(i)
                    # Hàm CountA đếm số ô có dữ liệu trong sheet. Nếu == 0 nghĩa là sheet trống
                    if excel.WorksheetFunction.CountA(sheet.Cells) == 0:
                        empty_sheets.append(sheet)
                
                # Xóa các sheet trống (chỉ thực hiện nếu file vẫn còn ít nhất 1 sheet có dữ liệu)
                if len(empty_sheets) < sheet_count:
                    for sheet in empty_sheets:
                        sheet.Delete()
                # --------------------------------------
                
                # Lưu dưới dạng .xlsx (FileFormat = 51)
                wb.SaveAs(xlsx_file, FileFormat=51)
                wb.Close()
                
                # Xóa file cũ
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
        # Đảm bảo đóng Excel khi xong
        if excel:
            try:
                excel.Application.Quit()
            except:
                pass

if __name__ == "__main__":
    print("="*60)
    print("   TOOL CHUYỂN ĐỔI EXCEL 2003 (.xls) SANG WORKSHEET (.xlsx)")
    print("="*60)
    
    # Nhập đường dẫn từ người dùng
    folder_input = input("\nNhập đường dẫn thư mục chứa các file .xls (VD: D:\\Data\\Files): ")
    
    # Loại bỏ dấu ngoặc kép nếu người dùng kéo thả thư mục vào cmd/terminal
    folder_input = folder_input.strip('"\'')
    
    if folder_input:
        convert_xls_to_xlsx(folder_input)
    else:
        print("[-] Đường dẫn không hợp lệ.")
        
    print("\n")
    os.system("pause") # Dừng màn hình để xem kết quả trước khi tắt

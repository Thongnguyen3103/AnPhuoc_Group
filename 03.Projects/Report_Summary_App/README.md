# Báo cáo Tổng hợp An Phước — Web app nội bộ

Web app có đăng nhập cho Báo cáo Tổng hợp (Tồn & Số bán, 10 sheet), dùng cho ~20–30 người
trong mạng nội bộ. Kiến trúc chi tiết: **[ARCHITECTURE.md](ARCHITECTURE.md)**.

> File HTML offline cũ (`04.Output/Report_Summary/BaoCao_TongHop.html`) vẫn được tạo và dùng như trước.

## 1. Cài đặt lần đầu

```powershell
cd D:\AnPhuocGroup\AnPhuoc_Data\01.Python_Projects\03.Projects\Report_Summary_App
& "C:\Users\THONG SL\anaconda3\python.exe" -m pip install -r requirements.txt   # Anaconda đã có sẵn: bỏ qua được
copy .env.example .env                                                            # sửa nếu cần (cổng, đường dẫn)
& "C:\Users\THONG SL\anaconda3\python.exe" manage.py init-db
& "C:\Users\THONG SL\anaconda3\python.exe" manage.py create-user ten.quan.tri --role admin --full-name "Họ Tên" --set-password
```

## 2. Chạy máy chủ

```powershell
& "C:\Users\THONG SL\anaconda3\python.exe" run_server.py
```
Mở `http://<IP-máy-chủ>:<APP_PORT>` → đăng nhập. Tài liệu API tự sinh: `/api/docs`.

> Máy build hiện tại (`10.110.134.218`) dùng `APP_PORT=8765` trong `.env` vì Kaspersky trên máy này
> đã có quy tắc cho phép cổng **8765** → link: `http://10.110.134.218:8765`. Đổi cổng thì phải thêm quy tắc Kaspersky cho cổng mới.

## 3. Cập nhật dữ liệu hằng tháng

1. Chạy build như cũ: `Report_Summary_App\Core\Run_Build_Summary.py`.
   Stage 5 tự xuất snapshot vào `04.Output\Report_Summary\app_snapshot\`.
2. Máy chủ **tự nạp** bản mới trong ≤ 60 giây (hoặc Quản trị → Dữ liệu báo cáo → *Nạp bản build mới nhất*).
3. Người xem chỉ cần tải lại trang. Bản sai? Quản trị → *Dùng bản này* để quay về bản trước (giữ 12 bản).

## 4. Quản lý người dùng

- Trang **/admin → Người dùng**: tạo user (hệ thống sinh mật khẩu tạm, hiện 1 lần), cấp lại mật khẩu, khóa/mở, đổi vai trò.
- Người dùng mới **bắt buộc đổi mật khẩu** ở lần đăng nhập đầu.
- Dòng lệnh: `manage.py list-users`, `manage.py reset-password <ten>` (dùng khi quên mật khẩu quản trị).

## 5. Triển khai để MỌI wifi công ty truy cập được

Mạng công ty chia nhiều dải (máy build ở `10.110.x.x`); router chặn kết nối **vào** máy trạm từ dải khác,
nhưng các dải đều tới được **dải máy chủ `10.222.x.x`** (nơi có `\\hovmfs01`). Vì vậy:

1. **Nhờ IT** cấp 1 máy chủ (Windows) trong dải `10.222.x.x`, cài Anaconda/Python ≥ 3.11, mở cổng **TCP 8780** vào máy đó.
2. Chép thư mục `Report_Summary_App` lên máy chủ; trong `.env` đặt:
   - `SNAPSHOT_SOURCE_DIR=\\DESKTOP-LMHVA0L\...\app_snapshot` (thư mục chia sẻ từ máy build) **hoặc**
     cho build ghi thẳng ra thư mục chia sẻ trên máy chủ.
3. Cho chạy cùng Windows: Task Scheduler → *At startup* → chương trình `pythonw.exe`, đối số `run_server.py`,
   *Start in* = thư mục `Report_Summary_App`, chạy dù không đăng nhập.
4. (Khuyến nghị) IT tạo tên DNS nội bộ, vd `baocao.anphuoc.local` → thêm vào `TRUSTED_ORIGINS`.

Chạy tạm trên máy build (chỉ máy cùng dải `10.110.x.x` vào được): bước 2 ở trên là đủ.

## 6. Sao lưu & bảo trì

| Cần sao lưu | Vị trí |
|---|---|
| CSDL người dùng, phiên, nhật ký | `data\app.db` (dừng server hoặc dùng `sqlite3 app.db ".backup bak.db"`) |
| Snapshot dữ liệu | `data\snapshots\` (có thể tạo lại từ build) |
| Log | `data\logs\app.log` (xoay vòng 5 × 5 MB) |

Kiểm tra sức khỏe: `GET /api/health` → `{"status": "ok", ...}`.

## 7. Kiểm thử

```powershell
& "C:\Users\THONG SL\anaconda3\python.exe" -m pytest -q tests
```
31 test: đăng nhập/khóa sai mật khẩu, phiên, CSRF, phân quyền, tra Mã hàng, payload + ETag, nạp/quay về snapshot, watcher.

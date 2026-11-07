# HƯỚNG DẪN QUẢN TRỊ — WEB APP BÁO CÁO TỔNG HỢP AN PHƯỚC

Dành cho người quản trị (hiện tại: `Thongnhm.qlsl`). Làm theo đúng thứ tự từng mục.
Mọi lệnh chạy trong **PowerShell**. Python luôn dùng bản Anaconda:

```powershell
$PY = "C:\Users\THONG SL\anaconda3\python.exe"
```
> Mỗi lần mở cửa sổ PowerShell mới, dán dòng trên trước. Các lệnh bên dưới dùng `& $PY ...`.

---

## 0. Bức tranh tổng thể (đọc 1 lần)

```
 Dữ liệu gốc (.parquet)                 00.Data_AnPhuoc_Group\03.Data_Parquest\...
        │  ① Chạy BUILD (mỗi khi có dữ liệu mới)
        ▼
 03.Projects\Report_Summary_App\Core\Run_Build_Summary.py
        ├─► 04.Output\Report_Summary\BaoCao_TongHop.html      (file offline như cũ)
        └─► 04.Output\Report_Summary\app_snapshot\            (dữ liệu cho web)
        │  ② Web app TỰ NẠP trong ≤ 60 giây
        ▼
 03.Projects\Report_Summary_App   (máy chủ web, cổng 8765)
        │  ③ Người xem mở link, đăng nhập
        ▼
 http://10.110.134.218:8765
```

| Thứ | Nằm ở đâu |
|---|---|
| Code web app | `D:\AnPhuocGroup\AnPhuoc_Data\01.Python_Projects\03.Projects\Report_Summary_App` |
| Code tính số liệu (pipeline) | `...\03.Projects\Report_Summary_App\Core` |
| Giao diện 10 sheet | `...\03.Projects\Report_Summary_App\Template` |
| Cấu hình web (cổng, đường dẫn) | `Report_Summary_App\.env` |
| CSDL người dùng + nhật ký | `Report_Summary_App\data\app.db` |
| Log máy chủ | `Report_Summary_App\data\logs\app.log` |

---

## 1. Mở code

1. Mở **VS Code** → `File` → `Open Folder...` → chọn
   `D:\AnPhuocGroup\AnPhuoc_Data\01.Python_Projects` (cả repo, VS Code đã cấu hình sẵn Python Anaconda).
2. Mở Terminal trong VS Code: `Ctrl + `` ` (phím dấu huyền) → chọn PowerShell.
3. Bản đồ file — muốn sửa gì thì mở file nào:

| Muốn sửa | File |
|---|---|
| Cách tính số liệu (bán, tồn, tuổi tồn...) | `Report_Summary_App\Core\Steps\*.py` |
| Giao diện / bảng / KPI của 10 sheet | `Report_Summary_App\Template\Report_Engine.js`, `Report_Template.html`, `Report_Style.css` |
| Trang đăng nhập / quản trị / đổi mật khẩu | `Report_Summary_App\app\web\*.html`, `*.js`, `app.css` |
| API, phân quyền, đăng nhập | `Report_Summary_App\app\routers\*.py` |
| Cổng, thời hạn phiên, số lần nhập sai | `Report_Summary_App\.env` |

---

## 2. Bật / tắt / kiểm tra máy chủ web

### Bật
```powershell
cd "D:\AnPhuocGroup\AnPhuoc_Data\01.Python_Projects\03.Projects\Report_Summary_App"
& $PY run_server.py
```
Thấy dòng `Uvicorn running on http://0.0.0.0:8765` là xong. **Để nguyên cửa sổ này** — đóng cửa sổ = tắt web.

### Tắt
Bấm `Ctrl + C` trong cửa sổ đang chạy.

### Kiểm tra web còn sống
Mở trình duyệt: `http://localhost:8765/api/health`
- `"status":"ok"` → bình thường, kèm kỳ dữ liệu đang dùng.
- `"status":"no_data"` → web chạy nhưng chưa có dữ liệu → xem mục 4.
- Không mở được → web chưa bật.

### Link cho người khác
`http://10.110.134.218:8765` — IP này do mạng cấp, **có thể đổi**. Kiểm tra IP hiện tại:
```powershell
ipconfig | Select-String "IPv4"
```
Nếu IP đổi → gửi lại link mới cho mọi người (hoặc nhờ IT giữ cố định IP cho máy này).

> Máy khác chỉ vào được ở **cổng 8765** (Kaspersky đã có quy tắc cho cổng này) và chỉ từ dải mạng `10.110.x.x`.
> Đổi cổng trong `.env` thì phải thêm quy tắc Kaspersky cho cổng mới.

---

## 3. Quản lý người dùng (trên web)

Đăng nhập bằng tài khoản quản trị → bấm **Quản trị** trên đầu trang → tab **👥 Người dùng**.

| Việc | Cách làm |
|---|---|
| **Thêm người** | Nhập *Tên đăng nhập* (3–32 ký tự: chữ, số, `. _ -`), *Họ tên*, chọn *Vai trò* → **+ Tạo** → hiện **mật khẩu tạm** (chỉ hiện 1 lần) → gửi riêng cho người đó (Zalo/tin nhắn riêng). Lần đầu đăng nhập họ bắt buộc đặt mật khẩu mới. |
| **Quên mật khẩu** | Dòng người đó → **Cấp lại MK** → gửi mật khẩu tạm mới. Mọi phiên cũ của họ bị đăng xuất. |
| **Nghỉ việc / tạm ngưng** | **Khóa** → bị đăng xuất ngay, không đăng nhập được nữa. Không xóa để giữ lịch sử. Mở lại: **Mở khóa**. |
| **Cho làm quản trị** | **Nâng Quản trị** / **Hạ thành Người xem**. Hệ thống không cho tự khóa/tự hạ quyền mình và luôn giữ ≥ 1 quản trị. |

Vai trò: **Người xem** = chỉ xem báo cáo. **Quản trị** = xem + quản lý người dùng, dữ liệu, nhật ký.

### Quên mật khẩu QUẢN TRỊ (không vào web được)
```powershell
cd "D:\AnPhuocGroup\AnPhuoc_Data\01.Python_Projects\03.Projects\Report_Summary_App"
& $PY manage.py reset-password Thongnhm.qlsl --set-password
```
Nhập mật khẩu mới 2 lần (ký tự không hiện ra — bình thường). Lệnh này cũng mở khóa nếu bị khóa.

Lệnh khác: `& $PY manage.py list-users` (xem danh sách), `& $PY manage.py create-user <ten> --role admin` (tạo quản trị qua dòng lệnh).

---

## 4. Quy trình cập nhật số liệu (hằng tháng / khi có dữ liệu mới)

| Bước | Làm gì | Đạt khi |
|---|---|---|
| 1 | Tải dữ liệu mới như thường lệ (01.Data_Download / 02.Data_Processing) để có file parquet mới | File `System_sales_<tháng>.parquet` có ngày sửa mới |
| 2 | Chạy build (lệnh dưới) | Màn hình in `>>> VALIDATE OK` và `Snapshot Web app: ...` |
| 3 | Đợi ≤ 60 giây — web tự nạp | Quản trị → tab **🗂️ Dữ liệu báo cáo**: dòng mới nhất **Đang dùng**, đúng kỳ & giờ build |
| 4 | Mở báo cáo, kiểm tra nhanh KPI Sheet 1 | Số liệu đúng kỳ mới |
| 5 | Báo mọi người tải lại trang (F5) | — |

```powershell
cd "D:\AnPhuocGroup\AnPhuoc_Data\01.Python_Projects\03.Projects\Report_Summary_App"
& $PY Core\Run_Build_Summary.py
```

- Muốn nạp ngay không đợi: tab **Dữ liệu báo cáo** → **⟳ Nạp bản build mới nhất**.
- **Bản mới bị sai?** Tab **Dữ liệu báo cáo** → dòng bản cũ → **Dùng bản này** → mọi người quay về bản cũ ngay (giữ 12 bản gần nhất).
- Build in `LỖI` hoặc không thấy `VALIDATE OK` → **không** có dữ liệu mới lên web (web giữ bản cũ). Gửi nội dung lỗi để xử lý.

> ⚠️ Kiểm tra dữ liệu bán đã **đủ tháng** trước khi build (ví dụ T10 phải có đến 31/10). Build khi file còn thiếu ngày → số tháng đó bị thấp và YoY/MoM sai.

---

## 5. Xem ai đã làm gì

Quản trị → tab **📜 Nhật ký**: 200 hoạt động gần nhất — đăng nhập, **đăng nhập sai** (tô đỏ), xem báo cáo, tạo/khóa người dùng, nạp dữ liệu, kèm IP.
Nhiều dòng *Đăng nhập sai* liên tục từ 1 IP lạ → khóa tài khoản bị nhắm và báo IT.

---

## 6. Sửa code — làm gì sau khi sửa

| Đã sửa | Cần làm để thấy thay đổi |
|---|---|
| `Report_Summary_App\Core\...` (cách tính) | Chạy lại build (mục 4) |
| `Report_Summary_App\Template\...` (giao diện báo cáo) | Chạy lại build (để file offline cũng cập nhật) → trên web bấm `Ctrl + F5` |
| `Report_Summary_App\app\web\...` (trang đăng nhập/quản trị) | `Ctrl + F5` trên trình duyệt |
| `Report_Summary_App\app\*.py` hoặc `.env` | Tắt máy chủ (`Ctrl + C`) rồi bật lại (mục 2) |

### Chạy kiểm thử sau khi sửa code web app
```powershell
cd "D:\AnPhuocGroup\AnPhuoc_Data\01.Python_Projects\03.Projects\Report_Summary_App"
& $PY -m pytest -q tests
```
Phải ra `31 passed` (hoặc nhiều hơn nếu thêm test). Có `failed` → chưa đưa lên dùng.

### Lưu thay đổi vào git
```powershell
cd "D:\AnPhuocGroup\AnPhuoc_Data\01.Python_Projects"
git status
git add 03.Projects/Report_Summary_App 03.Projects/Report_Summary
git commit -m "Mô tả ngắn thay đổi"
```
`data\` và `.env` đã được loại khỏi git (chứa CSDL người dùng) — **không** tự thêm vào.

---

## 7. Sao lưu (mỗi tuần)

Chỉ cần sao lưu **1 file**: `Report_Summary_App\data\app.db` (người dùng, mật khẩu đã mã hóa, nhật ký).
Số liệu báo cáo không cần sao lưu — build lại là có.

```powershell
cd "D:\AnPhuocGroup\AnPhuoc_Data\01.Python_Projects\03.Projects\Report_Summary_App"
& $PY -c "import sqlite3,datetime; s=sqlite3.connect('data/app.db'); d=sqlite3.connect(f'data/app_backup_{datetime.date.today():%Y%m%d}.db'); s.backup(d); print('Đã sao lưu')"
```
Chép file `app_backup_YYYYMMDD.db` sang ổ chung/OneDrive. Khôi phục: tắt máy chủ → đổi tên bản sao lưu thành `app.db` → bật lại.

---

## 8. Xử lý sự cố nhanh

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không ai mở được link | Máy chủ chưa bật / máy đã tắt / đóng cửa sổ PowerShell | Bật lại (mục 2) |
| Mình mở được, máy khác không | IP máy đổi, hoặc máy kia ở dải mạng khác `10.110.x.x`, hoặc đổi cổng khác 8765 | Kiểm tra IP (mục 2); dải khác → cần IT |
| Báo "Chưa có dữ liệu báo cáo" | Chưa build lần nào / thư mục `app_snapshot` trống | Chạy build (mục 4) hoặc `& $PY manage.py import-snapshot` |
| Số liệu vẫn là kỳ cũ | Chưa build, build lỗi, hoặc trình duyệt giữ bản cũ | Xem tab Dữ liệu báo cáo; `Ctrl + F5` |
| "Đăng nhập sai quá nhiều lần" | Nhập sai 5 lần trong 15 phút | Đợi 15 phút, hoặc quản trị **Cấp lại MK** |
| Bật máy chủ báo lỗi `[Errno 10048]` (cổng đang được dùng) | Máy chủ cũ còn chạy ở cửa sổ khác | Tìm cửa sổ đó `Ctrl + C`, hoặc khởi động lại máy |
| Trang trắng / "Lỗi tải dữ liệu" | Trình duyệt quá cũ | Dùng Chrome/Edge/Cốc Cốc bản mới |
| Lỗi khác | — | Mở `data\logs\app.log`, xem các dòng `ERROR` cuối file |

---

## 9. Lịch việc định kỳ

| Khi nào | Việc |
|---|---|
| Mỗi sáng làm việc | Bật máy chủ (nếu máy đã tắt), mở `/api/health` kiểm tra |
| Khi có dữ liệu mới | Mục 4 |
| Mỗi tuần | Xem tab Nhật ký; sao lưu `app.db` (mục 7) |
| Khi có người nghỉ việc | Khóa tài khoản ngay (mục 3) |
| Mỗi tháng | Rà danh sách người dùng, khóa tài khoản không còn dùng |

# HƯỚNG DẪN VẬN HÀNH & CẬP NHẬT — BÁO CÁO TỔNG HỢP AN PHƯỚC

Tài liệu hướng dẫn quy trình build, kiểm tra dữ liệu và cập nhật file báo cáo tự chứa lên Google Drive.

> 📖 Chi tiết kỹ thuật (kiến trúc, cấu trúc payload, quy tắc nghiệp vụ, sơ đồ sheet): xem **`KIEN_TRUC.md`**.

---

## 1. Kiến trúc vận hành

- Báo cáo được thiết kế dưới dạng **Trình sinh Báo cáo Tĩnh (Static Report Generator)**.
- Chỉ chạy Python **lúc build** trên máy chủ có kết nối với kho dữ liệu `D:\AnPhuocGroup\AnPhuoc_Data\00.Data_AnPhuoc_Group`.
- Sản phẩm đầu ra là **1 file duy nhất**: `04_KetQua/BaoCao_TongHop/BaoCao_TongHop.html` (~13 MB, 100% tự chứa, chạy offline không cần server hay CDN).
- **File cần chạy:** chỉ `xu_ly/cap_nhat_bao_cao.py`. Nó tự gọi 5 stage. Không chạy file stage lẻ.

---

## 2. Quy trình cập nhật dữ liệu (Chủ dữ liệu)

### Bước 1: Chuẩn bị dữ liệu gốc
Khi có dữ liệu tháng mới:
- Copy các file parquet bán lẻ vào thư mục tương ứng: `D:\AnPhuocGroup\AnPhuoc_Data\00.Data_AnPhuoc_Group\03.Data_Parquest\01.System_sales\<năm>\`
- Copy các file parquet bán hợp đồng vào: `D:\AnPhuocGroup\AnPhuoc_Data\00.Data_AnPhuoc_Group\03.Data_Parquest\02.Contract_sales\<năm>\`
- Cập nhật tồn kho (nếu có): `D:\AnPhuocGroup\AnPhuoc_Data\00.Data_AnPhuoc_Group\03.Data_Parquest\03.Inventory\InventorySize.parquet`
- Cập nhật lệnh luân chuyển (nếu có): `D:\AnPhuocGroup\AnPhuoc_Data\00.Data_AnPhuoc_Group\03.Data_Parquest\07.Lenh_HHLC\<năm>\`

### Bước 2: Chạy lệnh Build (1 lệnh duy nhất)
Mở PowerShell hoặc Command Prompt tại thư mục dự án và chạy:

```powershell
# 1 lệnh cho MỌI trường hợp — kể cả vừa thêm file bán tháng mới.
# refresh_cache tự so kỳ + số dòng nguồn vs cache; có mới thì tự nạp lại.
& "C:\Users\THONG SL\anaconda3\python.exe" xu_ly\cap_nhat_bao_cao.py

# Chỉ khi muốn ÉP dựng lại cache từ đầu (nghi cache hỏng)
& "C:\Users\THONG SL\anaconda3\python.exe" xu_ly\cap_nhat_bao_cao.py --force-cache
```

> Sau khi bỏ file parquet bán tháng mới vào đúng folder năm, chạy lệnh thường là đủ.
> Màn hình sẽ in `Phát hiện dữ liệu bán thay đổi → tự động nạp lại cache` rồi `Kỳ tham chiếu mới nhất: T<mới>/<năm>`.

> [!NOTE]
> Luôn sử dụng đường dẫn đầy đủ đến Python của Anaconda (`C:\Users\THONG SL\anaconda3\python.exe`). Lệnh `python` mặc định trên một số máy Windows có thể trỏ vào stub của Microsoft Store.

### Bước 3: Kiểm tra kết quả màn hình
Tiến trình build (`xu_ly/cap_nhat_bao_cao.py`) chạy tuần tự các stage — nhãn `[STAGE n]` in ra là số hiệu module, **thứ tự chạy thực tế** là:
1. `lam_moi_cache` — nạp dữ liệu 3 năm từ parquet gốc + master data → `du_lieu_tam/cache_ban_hang.parquet` (bỏ qua nếu đã có; dùng `--force-cache` để tạo lại).
2. `tong_hop_ban` (`[STAGE 3]`) — tổng hợp Số Bán + xác định kỳ tham chiếu.
3. `tong_hop_ton` (`[STAGE 2]`) — phân loại vị trí (CH vs Kho), gán `size_profile`, kỳ PP 6 tháng, cờ bán 30/60/90.
4. `kiem_tra` (`[STAGE 4]`) — đối chiếu tổng Bán & Tồn giữa payload và parquet gốc; **dừng build** nếu lệch > 0.5%.
5. `xuat_html` (`[STAGE 5]`) — gzip + base64, nhúng vào `giao_dien/mau_bao_cao.html` → `04_KetQua/BaoCao_TongHop/BaoCao_TongHop.html`.

Kết quả đạt chuẩn:
- Màn hình hiển thị: `>>> VALIDATE OK`.
- Kích thước `04_KetQua/BaoCao_TongHop/BaoCao_TongHop.html`: khoảng **6–9 MB** (tuyệt đối < 15 MB).
- Thời gian chạy: ~25–35 giây (lâu hơn nếu có `--force-cache`).

---

## 3. Quy trình tải lên Google Drive (Giữ nguyên link chia sẻ)

Để người xem không phải đổi link báo cáo qua các lần cập nhật:

1. Mở **Google Drive** trên trình duyệt web.
2. Tìm đến file báo cáo cũ: `BaoCao_TongHop.html`.
3. Nhấp chuột phải vào file → chọn **Quản lý phiên bản** (Manage versions).
4. Bấm nút **Tải phiên bản mới lên** (Upload new version).
5. Chọn file mới vừa sinh tại: `D:\AnPhuocGroup\AnPhuoc_Data\01.Python_Projects\04_KetQua\BaoCao_TongHop\BaoCao_TongHop.html`.

> [!TIP]
> **Kết quả:** Google Drive sẽ lưu phiên bản mới đè lên phiên bản cũ. Toàn bộ người xem báo cáo thông qua đường link chia sẻ ban đầu chỉ cần tải lại (refresh) hoặc tải file về là tự động nhận số liệu mới nhất mà không cần gửi lại link mới.

---

## 4. Hướng dẫn dành cho người xem báo cáo

1. Nhấp vào đường link chia sẻ trên Google Drive và bấm **Tải xuống** (Download). *(Google Drive không render file HTML trực tiếp — đây là hành vi mặc định)*.
2. Nhấp đúp chuột vào file `BaoCao_TongHop.html` vừa tải về máy để mở bằng Google Chrome, Microsoft Edge hoặc Cốc Cốc.
3. Chờ 1–2 giây để trình duyệt giải nén dữ liệu vào bộ nhớ.
4. Sử dụng báo cáo 100% offline, không cần internet, chuyển đổi phân khúc và bộ lọc tức thì.

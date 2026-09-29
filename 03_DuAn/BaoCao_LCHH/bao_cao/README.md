# Hướng Dẫn Sử Dụng & Phương Pháp Phân Tích Báo Cáo Luân Chuyển Hàng Hóa (LCHH)

## 1. Giới Thiệu
Thư mục `lchh_analytics` chứa toàn bộ công cụ tự động phân tích và xuất Dashboard Excel cho hoạt động Luân Chuyển Hàng Hóa (LCHH).
Hệ thống được thiết kế theo góc nhìn **Chuyên gia Phân tích Dữ liệu (Data Analyst)**, tự động đọc từ nguồn `04_KetQua/BaoCao_LCHH/KQ_LCHH.parquet` và xuất ra báo cáo Excel đa chiều, trực quan hóa cao cấp.

---

## 2. Cấu Trúc Báo Cáo Excel (6 Sheets)

| STT | Tên Sheet | Nội Dung & Chỉ Số Chính |
|:---:|---|---|
| **1** | **`DASHBOARD_TONG_QUAN`** | **Executive Summary**: Thẻ KPI lớn (Tổng lệnh, Tỷ lệ nhập kho %, Tỷ lệ đúng hạn SLA %, Lệnh trễ hạn/treo, Thời gian thực hiện trung bình). **Bảng tiến độ theo Đợt báo cáo (Ngày yêu cầu `NgayChungTu_YeuCau` + Mã `Operation`)**. Biểu đồ phân bổ Donut & Bar Chart. |
| **2** | **`PHAN_TICH_HANG_HOA`** | Phân tích chi tiết theo **Thương hiệu** (An Phước, Pierre Cardin), **Nhóm báo cáo** (Áo Thun, Áo Vest, Áo Golf), **Giới tính** (Nam, Nữ) và **Top 20 Mã hàng (SKU)** luân chuyển nhiều nhất. |
| **3** | **`TUYEN_VA_CUAHANG`** | **Ma trận luân chuyển Vùng** (`Region_from` $\rightarrow$ `Region_to`), Top 15 Cửa hàng gửi (`Store_from`) nhiều nhất, Top 15 Cửa hàng nhận (`Store_to`) nhiều nhất. |
| **4** | **`TIEN_DO_VA_SLA`** | **Phân bổ Lead Time** (0-3 ngày, 4-7 ngày, 8-15 ngày, >15 ngày). **Danh sách chi tiết toàn bộ các lệnh bị Trễ hạn** để phục vụ đôn đốc xử lý. |
| **5** | **`CANH_BAO_BAT_THUONG`** | **Nguyên nhân Chưa thực hiện (Root Causes)** theo cột `ly_do`, Cảnh báo hàng **Trả kho** (`Qty_TraKho > 0`), Cảnh báo hàng **Chuyển đi tiếp** (`Qty_ChuyenDiTiep > 0`). |
| **6** | **`DU_LIEU_CHI_TIET`** | Toàn bộ 33 cột dữ liệu gốc dạng Excel Table, tích hợp bộ lọc (Filter) và cố định tiêu đề (Freeze Panes). |

---

## 3. Cách Sử Dụng & Đồng Bộ Dữ Liệu Tự Động

### Cách 1: Chạy 1-Click (Khuyên dùng)
- Click đúp chuột vào file **`CHAY_XUAT_EXCEL.bat`** (ở thư mục BaoCao_LCHH).
- Màn hình console sẽ tự động đọc dữ liệu mới nhất từ `04_KetQua/BaoCao_LCHH/KQ_LCHH.parquet`, tính toán KPI và xuất file Excel trong vòng 2-3 giây.

### Cách 2: Chạy bằng lệnh Python
```bash
"C:\Users\THONG SL\anaconda3\python.exe" bao_cao\xuat_excel_lchh.py
"C:\Users\THONG SL\anaconda3\python.exe" bao_cao\xuat_excel_hieu_suat.py
```

---

## 4. Vị Trí File Báo Cáo Excel Đầu Ra

Tất cả báo cáo Excel được lưu tự động trong thư mục:
📂 `01.Python_Projects\04_KetQua\BaoCao_LCHH\bao_cao_excel\`

1. **`BaoCao_PhanTich_LCHH_Latest.xlsx`**: File luôn chứa dữ liệu kỳ mới nhất (dùng để ghim/mở nhanh).
2. **`BaoCao_PhanTich_LCHH_YYYY_MM.xlsx`**: File lưu trữ lịch sử theo từng tháng/năm cụ thể (ví dụ: `BaoCao_PhanTich_LCHH_2026_08.xlsx`).

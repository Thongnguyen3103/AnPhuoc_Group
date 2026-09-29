# Hướng dẫn Xử lý Dữ liệu — 02_XuLyDuLieu

Tài liệu này mô tả **chức năng, nhiệm vụ và luồng chạy** của từng file Python trong phần xử lý dữ liệu, để việc bảo trì/mở rộng sau này không phải đọc lại toàn bộ code.

```
02_XuLyDuLieu/
├── CHAY_XU_LY.bat          ← menu chọn nguồn cần xử lý (chạy chay_tat_ca.py)
├── CHAY_DOANH_THU.bat      ← cập nhật DuckDB doanh thu (doanh_thu.py)
├── CHAY_XUAT_CSV.bat       ← xuất Parquet → CSV (xuat_csv_data_ap.py)
├── chay_tat_ca.py          ← điểm chạy chính: 01.Source → 02.Master / 03.Data_Parquest
├── xu_ly_theo_thang.py     ← khuôn chung MonthlySourceProcessor
├── chuyen_xls_sang_xlsx.py ← đổi .xls → .xlsx (Excel COM) trước bước HDD
├── xuat_csv_data_ap.py     ← Parquet → 05.Data_Csv (cho Power BI)
├── doanh_thu.py            ← doanh thu ngày + chỉ tiêu + bill → Report_AP.duckdb
└── nguon/                  ← mỗi file = 1 nguồn dữ liệu
```

Dùng chung từ `01.Python_Projects/dung_chung/`:

| File | Nhiệm vụ |
|---|---|
| **`cau_hinh.yaml`** + **`duong_dan.py`** | **Nơi duy nhất khai báo đường dẫn** (thư mục nguồn, Master, Parquet, DuckDB, CSV export, ổ mạng...). Code dùng `duong_dan.nguon_ban_le`, `duong_dan.master`... Muốn đổi ổ đĩa/vị trí thư mục — chỉ sửa `cau_hinh.yaml`. |
| **`doc_ghi_parquet.py`** | `load_master_table(name)` đọc 1 bảng lookup từ `02.Master/*.parquet`; `export_parquet_partitioned(df, dir_name, file_prefix)` xuất Parquet phân mảnh theo Năm/Tháng (mỗi tháng 1 file `<prefix>_<MM>.parquet`, chỉ ghi đè đúng tháng có dữ liệu mới). |
| **`ngay_thang.py`** | `parse_date(series, fmt)` — parse cột ngày có định dạng tường minh (bỏ phần giờ), cảnh báo số dòng lỗi. |
| **`quy_doi_size.py`** | `actual_size(system_size, report_item_name)` — quy đổi size hệ thống → size thực tế theo `SIZE_MAP`; `FEMALE_SIZE_MAP` riêng cho hàng Nữ/Jupe/Váy. Dùng chung cho **mọi** nguồn. |

---

## 1. Kiến trúc chung

Mọi nguồn "giao dịch theo tháng" (bán hàng, kho xuất, nhập SX, luân chuyển, trả kho...) đều theo cùng một khuôn:

```
đọc file CSV/Excel thô → merge với bảng danh mục (Master) → chuẩn hoá (size, ngày, status)
→ group theo các cột chiều (Store/Item/Size/Month...) → xuất Parquet phân mảnh theo Năm/Tháng
```

Khuôn này nằm trong `xu_ly_theo_thang.py` (class `MonthlySourceProcessor`). Nguồn mới **chỉ cần 1 file trong `nguon/`, kế thừa class này và cài 3 phương thức** `load_lookups()`, `read_files()`, `transform()`.

Hai nguồn dạng "snapshot toàn bộ" — `HDDProcessor` và `InventoryProcessor` — không kế thừa base class, nhưng có cùng interface `run()` để `chay_tat_ca.py` gọi thống nhất.

## 2. nguon/ — Từng nguồn dữ liệu

| File | Class | Input (key trong cau_hinh.yaml) | Output | Đặc điểm riêng |
|---|---|---|---|---|
| **`cap_nhat_master.py`** | `DataTrackingProcessor` | `data_tracking_excel` + DMHH mới nhất (`danh_muc_hang_hoa`) + file xếp loại CH (`xep_loai_cua_hang`) | `02.Master/{A_Region, B_Size, D_Category, C_BasicSizeChart, E_T-Shirt, F_DataTracking}.parquet` | **Làm mới bảng danh mục (Master)** — nguồn của `load_master_table()` cho mọi processor khác. Luôn full-refresh. |
| **`hang_di_duong.py`** | `HDDProcessor` | `nguon_hdd_qlkd` + `nguon_hdd_report` | `02.Master/HDD_QLKD_Tong_hop.parquet` | Gộp 2 nguồn HDD (đối chiếu Số chứng từ trùng), dò encoding linh hoạt. |
| **`ton_kho.py`** | `InventoryProcessor` | `nguon_ton_kho` + `HDD_QLKD_Tong_hop.parquet` | `03.Inventory/{InventorySize, Inventory}.parquet` | Unpivot cột `size_*` thành dòng, gộp HDD. Env `INVENTORY_KEEP_ZERO=1` để giữ dòng 0. |
| **`ban_hang.py`** | `SystemSalesProcessor`, `ContractSalesProcessor` | `nguon_ban_le`, `nguon_ban_hop_dong` | `01.System_sales/`, `02.Contract_sales/` | Trích mã CH từ `SoChungTu` (`STORE_CODE_ALIAS` cho mã cũ). Bán lẻ chỉ giữ Bán/Tặng/Đổi. |
| **`kho_xuat_cua_hang.py`** | `KhoXuatCHProcessor` | `nguon_kho_xuat_ch` | `06.KhoXuat_CH/` | Trích mã kho xuất từ `SoChungTu`, tra Region/Warehouse theo `TenCH_NHAP`. |
| **`nhap_tu_san_xuat.py`** | `NhapTuSXProcessor` | `nguon_nhap_sx` | `05.NhapSX/` | Tự khôi phục dòng bị tách do dấu phẩy dư trong cột `Noidung`. |
| **`lich_su_luan_chuyen.py`** | `HistoryLCProcessor` | `nguon_lich_su_lc` | `08.History_LC/` | Có cửa hàng gửi (`MaCH`) và nhận (`MaCH_N`). |
| **`tra_kho.py`** | `TraKhoProcessor` | `nguon_tra_kho` | `09.TraKho/` | Chỉ giữ `LyDo == "Nhập cửa hàng trả kho"`; field dư gộp về cột cuối. |
| **`lenh_luan_chuyen.py`** | `LenhLuanChuyenProcessor` | `hhlc_o_mang` (`**/*.xlsx`, ổ mạng) | `07.Lenh_HHLC/` (prefix `KQ_HHLC`) | Nguồn Excel, bỏ file tạm `~$...`, đổi tên cột qua `RENAME_MAP`. |

Output Parquet nằm dưới `03.Data_Parquest/` (key `parquet`).

**Quy ước chung:** mỗi processor có `robust_read_csv` riêng (ưu tiên `utf-16`, tự phục hồi dòng lỗi); dùng `Short_name` (MaHang bỏ 4 ký tự cuối) để tra `D_Category`; lọc bỏ `Product_type` "Bao Bì"/"Đồng Phục" và `Brand` "Dv In Theu"/"Khác" (trừ Contract_sales, KhoXuat_CH, NhapTuSX, HH_LuanChuyen).

## 3. chay_tat_ca.py — Điểm chạy chính

Chạy: double-click **`CHAY_XU_LY.bat`** (hoặc `python chay_tat_ca.py`).

- Menu checkbox (↑↓ di chuyển, Space tích, Enter chạy, Esc/HỦY thoát).
- `run_all()` chạy đúng thứ tự: Master → HDD + Tồn kho → Bán lẻ/Bán HĐ (dùng chung lookups) → Kho Xuất CH → Nhập từ SX → History_LC → Trả Kho → Lệnh Điều chuyển.
- **Phụ thuộc:** Master phải chạy **trước** mọi processor khác. HDD phải chạy trước Tồn kho nếu muốn tồn có HDD mới nhất.

## 4. Các script độc lập

| File | Nhiệm vụ |
|---|---|
| **`doanh_thu.py`** (`CHAY_DOANH_THU.bat`) | Ghi vào DuckDB `duckdb_report_ap`: (1) `process_sales_data()` — file `.xls` "DOANH THU THEO NGAY" (`doanh_thu_ngay_2026/2025`) → table `revenue`; (2) `process_target_data()` — `chi_tieu_cua_hang` → table `target`; (3) `process_sales_details()` — CSV bán chi tiết (`phan_tich_o_mang/2.System_sales`) → table `bill_sales`. Dùng bởi `03_DuAn/BaoCao_QLKD_Tuan`. |
| **`xuat_csv_data_ap.py`** (`CHAY_XUAT_CSV.bat`) | Parquet đã xử lý → CSV trong `05.Data_Csv/{01.Master, 02.Raw}`. Menu chọn bảng, retry khi file bị khoá. `03_DuAn/KiemSoat_TonKho` đọc `02.Raw/System_sales.csv` từ đây. |
| **`chuyen_xls_sang_xlsx.py`** | Convert `.xls` → `.xlsx` bằng Excel COM, chạy tự động trước bước HDD. |

## 5. Sơ đồ luồng dữ liệu

```
01_TaiDuLieu (tải web)
      │
      ▼
00.Data_AnPhuoc_Group/01.Source/*  ──►  02_XuLyDuLieu/chay_tat_ca.py
                                              │
          ┌───────────────────────────────────┼───────────────────────────┐
          ▼                                   ▼                           ▼
   02.Master/*.parquet              03.Data_Parquest/*            (xuat_csv_data_ap.py)
   (cap_nhat_master,                (ban_hang, ton_kho,            05.Data_Csv/*.csv
    hang_di_duong)                   kho_xuat, lich_su_lc...)
          │                                   │
          └──────────────┬────────────────────┘
                         ▼
                 03_DuAn/* (báo cáo)  ──►  04_KetQua/<TenDuAn>/

doanh_thu.py ──► 04.Data_Db/01.Data_DuckDB/Report_AP.duckdb ──► 03_DuAn/BaoCao_QLKD_Tuan
```

## 6. Ghi chú khi bảo trì / mở rộng

- **Đổi đường dẫn:** chỉ sửa `dung_chung/cau_hinh.yaml`. Chạy `python -m dung_chung.duong_dan` (từ thư mục `01.Python_Projects`) để kiểm tra đường dẫn nào đang không tồn tại.
- **Thêm nguồn "giao dịch theo tháng" mới:** thêm key đường dẫn vào `cau_hinh.yaml`, tạo file trong `nguon/` kế thừa `MonthlySourceProcessor` (khai `source_dir`, `output_dir_name`, `file_prefix`), rồi thêm vào `MENU` của `chay_tat_ca.py`.
- **Đổi quy tắc Size:** sửa `dung_chung/quy_doi_size.py` — áp dụng cho toàn bộ nguồn.
- **Danh mục/khu vực sai:** kiểm tra `nguon/cap_nhat_master.py` trước, vì mọi nguồn khác merge dựa trên bảng Master.
- **File CSV đọc lỗi/mất dòng:** mỗi `nguon/*.py` có `robust_read_csv` riêng — kiểm tra cột hay dính dấu phẩy (`Kieu`, `Noidung`...).

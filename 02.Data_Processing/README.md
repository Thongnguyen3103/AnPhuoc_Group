# Hướng dẫn Xử lý Dữ liệu — 02.Data_Processing

Tài liệu này mô tả **chức năng, nhiệm vụ và luồng chạy** của từng file Python trong phần xử lý dữ liệu, để việc bảo trì/mở rộng sau này không phải đọc lại toàn bộ code.

```
02.Data_Processing/
├── Run_All_Processing.bat         ← double-click để mở menu (chạy Run_All_Processing.py)
├── Run_All_Processing.py          ← điểm chạy chính: 01.Source → 02.Master / 03.Data_Parquest
├── Process_Monthly_Base.py     ← khuôn chung MonthlySourceProcessor
├── Convert_Xls_To_Xlsx.py ← đổi .xls → .xlsx (Excel COM) trước bước HDD
├── Export_Parquet_To_Csv.py     ← Parquet → 05.Data_Csv (cho Power BI)
├── Process_Revenue_To_Parquet.py           ← doanh thu ngày + chỉ tiêu + bill → 03.Data_Parquest/10.Revenue
└── Sources/                  ← mỗi file = 1 nguồn dữ liệu
```

Dùng chung từ `01.Python_Projects/00.Shared/`:

| File | Nhiệm vụ |
|---|---|
| **`00.Shared/Config_Paths.yaml`** + **`Get_Paths.py`** | **Nơi duy nhất khai báo đường dẫn** (thư mục nguồn, Master, Parquet, CSV export, ổ mạng...). Code dùng `Get_Paths.nguon_ban_le`, `Get_Paths.master`... Muốn đổi ổ đĩa/vị trí thư mục — chỉ sửa `00.Shared/Config_Paths.yaml`. |
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

Khuôn này nằm trong `Process_Monthly_Base.py` (class `MonthlySourceProcessor`). Nguồn mới **chỉ cần 1 file trong `Sources/`, kế thừa class này và cài 3 phương thức** `load_lookups()`, `read_files()`, `transform()`.

Hai nguồn dạng "snapshot toàn bộ" — `HDDProcessor` và `InventoryProcessor` — không kế thừa base class, nhưng có cùng interface `run()` để `Run_All_Processing.py` gọi thống nhất.

## 2. Sources/ — Từng nguồn dữ liệu

| File | Class | Input (key trong Config_Paths.yaml) | Output | Đặc điểm riêng |
|---|---|---|---|---|
| **`Update_Master_Tables.py`** | `DataTrackingProcessor` | `data_tracking_excel` + DMHH mới nhất (`danh_muc_hang_hoa`) + file xếp loại CH (`xep_loai_cua_hang`) | `02.Master/{A_Region, B_Size, D_Category, C_BasicSizeChart, E_T-Shirt, F_DataTracking}.parquet` | **Làm mới bảng danh mục (Master)** — nguồn của `load_master_table()` cho mọi processor khác. Luôn full-refresh. |
| **`Process_InTransit_HDD.py`** | `HDDProcessor` | `nguon_hdd_qlkd` + `nguon_hdd_report` | `02.Master/HDD_QLKD_Tong_hop.parquet` | Gộp 2 nguồn HDD (đối chiếu Số chứng từ trùng), dò encoding linh hoạt. |
| **`Process_Inventory.py`** | `InventoryProcessor` | `nguon_ton_kho` + `HDD_QLKD_Tong_hop.parquet` | `03.Inventory/{InventorySize, Inventory}.parquet` | Unpivot cột `size_*` thành dòng, gộp HDD. Env `INVENTORY_KEEP_ZERO=1` để giữ dòng 0. |
| **`Process_Sales.py`** | `SystemSalesProcessor`, `ContractSalesProcessor` | `nguon_ban_le`, `nguon_ban_hop_dong` | `01.System_sales/`, `02.Contract_sales/` | Trích mã CH từ `SoChungTu` (`STORE_CODE_ALIAS` cho mã cũ). Bán lẻ chỉ giữ Bán/Tặng/Đổi. |
| **`Process_Warehouse_To_Store.py`** | `KhoXuatCHProcessor` | `nguon_kho_xuat_ch` | `06.KhoXuat_CH/` | Trích mã kho xuất từ `SoChungTu`, tra Region/Warehouse theo `TenCH_NHAP`. |
| **`Process_Production_Receipt.py`** | `NhapTuSXProcessor` | `nguon_nhap_sx` | `05.NhapSX/` | Tự khôi phục dòng bị tách do dấu phẩy dư trong cột `Noidung`. |
| **`Process_Transfer_History.py`** | `HistoryLCProcessor` | `nguon_lich_su_lc` | `08.History_LC/` | Có cửa hàng gửi (`MaCH`) và nhận (`MaCH_N`). |
| **`Process_Return_To_Warehouse.py`** | `TraKhoProcessor` | `nguon_tra_kho` | `09.TraKho/` | Chỉ giữ `LyDo == "Nhập cửa hàng trả kho"`; field dư gộp về cột cuối. |
| **`Process_Transfer_Orders.py`** | `LenhLuanChuyenProcessor` | `hhlc_o_mang` (`**/*.xlsx`, ổ mạng) | `07.Lenh_HHLC/` (prefix `KQ_HHLC`) | Nguồn Excel, bỏ file tạm `~$...`, đổi tên cột qua `RENAME_MAP`. |
| **`Process_Transit_Receipt_HN.py`** | `NhapTrungChuyenCHNHNProcessor` | `nguon_nhap_trung_chuyen_hn` (`01.Source/07.NhapTrungChuyen_CHNHN/NTC_*.xls`, tải bằng job `qlkd_ntc`) | `04.NhapTrungChuyen_CHNHN/` (prefix `NhapTrungChuyen_CHNHN`, bảng `NhapTrungChuyen_CHNHN`) | Nhập kho trung chuyển về Kho Chi nhánh Hà Nội. Kho nhận lấy từ đuôi số chứng từ (`.../KHOHN-26-NK` → `KHOHN`); kho xuất là tên trong cột "Ghi chú" → `Kho_Xuat` + mã `MaCH_XUAT` theo `A_Region` (kho không có mã thì để trống). Không có Size/Operation; giữ `Don_gia`, `Tri_gia`. |

Output Parquet nằm dưới `03.Data_Parquest/` (key `parquet`).

**Quy ước chung:** mỗi processor có `robust_read_csv` riêng (ưu tiên `utf-16`, tự phục hồi dòng lỗi); dùng `Short_name` (MaHang bỏ 4 ký tự cuối) để tra `D_Category`; lọc bỏ `Product_type` "Bao Bì"/"Đồng Phục" và `Brand` "Dv In Theu"/"Khác" (trừ Contract_sales, KhoXuat_CH, NhapTuSX, HH_LuanChuyen).

## 3. Run_All_Processing.py — Điểm chạy chính

Chạy: double-click **`Run_All_Processing.bat`** (hoặc `python Run_All_Processing.py`).

- Menu checkbox (↑↓ di chuyển, Space tích, Enter chạy, Esc/HỦY thoát).
- `run_all()` chạy đúng thứ tự: Master → HDD + Tồn kho → Bán lẻ/Bán HĐ (dùng chung lookups) → Kho Xuất CH → Nhập từ SX → History_LC → Trả Kho → Lệnh Điều chuyển.
- **Phụ thuộc:** Master phải chạy **trước** mọi processor khác. HDD phải chạy trước Tồn kho nếu muốn tồn có HDD mới nhất.

## 4. Các script độc lập

| File | Nhiệm vụ |
|---|---|
| **`Process_Revenue_To_Parquet.py`** | Ghi Parquet vào `03.Data_Parquest/10.Revenue` (key `doanh_thu_parquet`), đọc A_Region/D_Category từ `02.Master`: (1) `process_sales_data()` — file `.xls` "DOANH THU THEO NGAY" (`doanh_thu_ngay_2026/2025`) → `Revenue.parquet`; (2) `process_target_data()` — `chi_tieu_cua_hang` → `Target.parquet`; (3) `process_sales_details()` — CSV bán chi tiết (`phan_tich_o_mang/2.System_sales`) → `Bill_sales.parquet`. Dùng bởi `03.Projects/Report_QLKD_Weekly`. |
| **`Export_Parquet_To_Csv.py`** | Parquet đã xử lý → CSV trong `05.Data_Csv/{01.Master, 02.Raw}`. Menu chọn bảng, retry khi file bị khoá. `03.Projects/Inventory_Control` đọc `02.Raw/System_sales.csv` từ đây. |
| **`Convert_Xls_To_Xlsx.py`** | Convert `.xls` → `.xlsx` bằng Excel COM, chạy tự động trước bước HDD. |

## 5. Sơ đồ luồng dữ liệu

```
01.Data_Download (tải web)
      │
      ▼
00.Data_AnPhuoc_Group/01.Source/*  ──►  02.Data_Processing/Run_All_Processing.py
                                              │
          ┌───────────────────────────────────┼───────────────────────────┐
          ▼                                   ▼                           ▼
   02.Master/*.parquet              03.Data_Parquest/*            (Export_Parquet_To_Csv.py)
   (cap_nhat_master,                (ban_hang, ton_kho,            05.Data_Csv/*.csv
    hang_di_duong)                   kho_xuat, lich_su_lc...)
          │                                   │
          └──────────────┬────────────────────┘
                         ▼
                 03.Projects/* (báo cáo)  ──►  04.Output/<TenDuAn>/

Process_Revenue_To_Parquet.py ──► 03.Data_Parquest/10.Revenue/*.parquet ──► 03.Projects/Report_QLKD_Weekly
```

## 6. Ghi chú khi bảo trì / mở rộng

- **Không dùng file `.duckdb`.** Mọi project đọc thẳng Parquet. Cần truy vấn SQL theo tên bảng thì dùng `00.Shared/Read_Write_Parquet.py`: `connect_parquet_views()` (VIEW `A_Region`, `System_sales`, `Revenue`... trỏ vào file parquet) hoặc `read_table("D_Category")`. Bảng mới → thêm 1 dòng vào `PARQUET_TABLES`.

- **Đổi đường dẫn:** chỉ sửa `00.Shared/Config_Paths.yaml`. Chạy `python -m Get_Paths` (từ thư mục `01.Python_Projects`) để kiểm tra đường dẫn nào đang không tồn tại.
- **Thêm nguồn "giao dịch theo tháng" mới:** thêm key đường dẫn vào `00.Shared/Config_Paths.yaml`, tạo file trong `Sources/` kế thừa `MonthlySourceProcessor` (khai `source_dir`, `output_dir_name`, `file_prefix`), rồi thêm vào `MENU` của `Run_All_Processing.py`.
- **Đổi quy tắc Size:** sửa `00.Shared/Convert_Size.py` — áp dụng cho toàn bộ nguồn.
- **Danh mục/khu vực sai:** kiểm tra `Sources/Update_Master_Tables.py` trước, vì mọi nguồn khác merge dựa trên bảng Master.
- **File CSV đọc lỗi/mất dòng:** mỗi `Sources/*.py` có `robust_read_csv` riêng — kiểm tra cột hay dính dấu phẩy (`Kieu`, `Noidung`...).

# Hướng dẫn Pipeline Xử lý Dữ liệu — 01.Data_Xuly

Tài liệu này mô tả **chức năng, nhiệm vụ và luồng chạy** của từng file Python trong dự án, để việc bảo trì/mở rộng sau này không phải đọc lại toàn bộ code.

Dự án gồm 3 nhóm độc lập, không dùng chung code với nhau:

```
01.Data_Xuly/
├── Report/        ← Pipeline chính: gộp dữ liệu bán/tồn/luân chuyển → Parquet
├── Revenue/        ← Doanh thu theo ngày + chỉ tiêu (DuckDB riêng)
└── Top_Seller/     ← Báo cáo Best/Slow Seller (đọc Parquet của Report/)
```

---

## 1. Report/ — Pipeline chính (nguồn dữ liệu → Parquet)

### 1.1. Kiến trúc chung

Mọi nguồn "giao dịch theo tháng" (bán hàng, kho xuất, nhập SX, luân chuyển, trả kho...) đều theo cùng một khuôn:

```
đọc file CSV/Excel thô → merge với bảng danh mục (Master) → chuẩn hoá (size, ngày, status)
→ group theo các cột chiều (Store/Item/Size/Month...) → xuất Parquet phân mảnh theo Năm/Tháng
```

Khuôn này được đóng gói trong `core/base_processor.py` (class `MonthlySourceProcessor`). Mỗi nguồn dữ liệu mới **chỉ cần viết 1 file mới trong `sources/`, kế thừa class này và cài đặt 3 phương thức** — không phải viết lại phần đọc thư mục, kiểm tra rỗng, hay xuất Parquet.

Hai nguồn không theo khuôn "giao dịch theo tháng" (mà là "snapshot toàn bộ") — `HDDProcessor` và `InventoryProcessor` — không kế thừa base class này, nhưng vẫn có cùng interface `run()` để `Run_all_data.py` gọi thống nhất.

### 1.2. core/ — Hạ tầng dùng chung

| File | Nhiệm vụ |
|---|---|
| **`core/paths.py`** | **Nơi duy nhất khai báo đường dẫn** (thư mục nguồn, Master, Parquet, CSV export...). Class `Paths`. Muốn đổi ổ đĩa/vị trí thư mục — chỉ sửa ở đây, không sửa từng file `sources/`. |
| **`core/base_processor.py`** | Class trừu tượng `MonthlySourceProcessor` (ABC). Định nghĩa khung xử lý chung: `_files()` (glob file nguồn) → `load_lookups()` → `read_files()` → `transform()` → xuất Parquet. Các processor con override 3 phương thức abstract: `load_lookups()`, `read_files()`, `transform()`. |
| **`core/parquet_io.py`** | I/O Parquet dùng chung: `load_master_table(name)` đọc 1 bảng lookup từ `02.Master/*.parquet`; `export_parquet_partitioned(df, dir_name, file_prefix)` xuất DataFrame ra Parquet, phân mảnh theo Năm/Tháng (mỗi tháng 1 file `<prefix>_<MM>.parquet`, chỉ ghi đè đúng tháng có dữ liệu mới). |
| **`core/date_utils.py`** | `parse_date(series, fmt)` — parse cột ngày dạng chuỗi có định dạng tường minh (bỏ phần giờ nếu có), cảnh báo số dòng parse lỗi. |
| **`core/size_map.py`** | `actual_size(system_size, report_item_name)` — quy đổi size hệ thống → size thực tế (S/M/L/XL/XXL/3XL/DAT1-3/OneSize) theo `SIZE_MAP`; áp dụng riêng `FEMALE_SIZE_MAP` cho hàng Nữ/Jupe/Váy vì size số (5/7/9...) chỉ có nghĩa S/M/L với nhóm này. Dùng chung cho **mọi** nguồn dữ liệu. |

**Khi thêm nguồn dữ liệu mới:** thêm đường dẫn vào `Paths`, tạo file mới trong `sources/` kế thừa `MonthlySourceProcessor`, rồi thêm 1 mục vào `MENU` trong `Run_all_data.py`.

### 1.3. sources/ — Từng nguồn dữ liệu cụ thể

| File | Class | Input | Output Parquet | Đặc điểm riêng |
|---|---|---|---|---|
| **`data_tracking.py`** | `DataTrackingProcessor` | `Data_Tracking.xlsx` + DMHH mới nhất (ổ Y:) + file xếp loại CH | `02.Master/{A_Region, B_Size, D_Category, C_BasicSizeChart, E_T-Shirt, F_DataTracking}.parquet` | **Làm mới các bảng danh mục/lookup (Master)** — nguồn cho `load_master_table()` của mọi processor khác. Luôn full-refresh, không phân mảnh theo tháng. Có logic chuẩn hoá tên category (`format_cat_text`), cập nhật xếp loại cửa hàng (`Store_rank`), phát hiện cặp SP Ngắn/Dài–Nam/Nữ (`compute_nd_pairs`), và báo cáo trùng khoá (`report_duplicates`). |
| **`hdd.py`** | `HDDProcessor` | Folder `HDD_QLKD` (csv/xlsx) + `HDD_Report` | `02.Master/HDD_QLKD_Tong_hop.parquet` | Gộp 2 nguồn HDD (đối chiếu theo Số chứng từ trùng để tránh đếm 2 lần), tra danh mục/khu vực, đọc CSV với dò encoding linh hoạt (`robust_read_csv`). Snapshot toàn bộ, **không** kế thừa `MonthlySourceProcessor`. |
| **`inventory.py`** | `InventoryProcessor` (module-level functions) | Folder tồn kho (csv/xlsx, cột `size_*`) + `HDD_QLKD_Tong_hop.parquet` | `03.Data_Parquest/03.Inventory/{InventorySize, Inventory}.parquet` | Unpivot các cột `size_25...size_FS` thành dòng (melt), gộp thêm HDD, xuất 2 bảng: có Size và không Size. Có cờ env `INVENTORY_KEEP_ZERO=1` để giữ dòng số lượng 0. Snapshot toàn bộ, không kế thừa base class. |
| **`system_sales.py`** | `SystemSalesProcessor`, `ContractSalesProcessor` | `01.System_sales/`, `02.Contract_sales/` (csv) | `01.System_sales/`, `02.Contract_sales/` (Parquet theo năm/tháng) | Xử lý **Bán lẻ** và **Bán Hợp Đồng**. Trích mã CH từ `SoChungTu` (`extract_ma_ch`, có `STORE_CODE_ALIAS` cho mã cửa hàng cũ đã đổi tên). System_sales lọc `Nội dung` chỉ giữ Bán/Tặng/Đổi; Contract_sales không filter dòng. `robust_read_csv` tự phục hồi dòng bị dư field do dấu phẩy không escape trong cột `Kieu`. |
| **`kho_xuat_ch.py`** | `KhoXuatCHProcessor` | `04.KhoXuat_CH/` (csv) | `04.KhoXuat_CH/` (Parquet) | Kho xuất ra cửa hàng. Trích mã kho xuất từ `SoChungTu` (`_extract_kho_xuat`), tra Region/Warehouse theo `TenCH_NHAP`. |
| **`nhap_tu_sx.py`** | `NhapTuSXProcessor` | `05.NhapSX/` (csv) | `05.NhapSX/` (Parquet) | Hàng nhập từ sản xuất. `robust_read_csv` tự khôi phục dòng bị tách do dấu phẩy dư trong cột `Noidung` (index cột 17). |
| **`history_lc.py`** | `HistoryLCProcessor` | `09.History_LC/` (csv) | `08.History_LC/` (Parquet) | Lịch sử luân chuyển — có cả cửa hàng gửi (`MaCH`) và nhận (`MaCH_N`), tra Region/Warehouse riêng cho từng chiều. Đọc CSV ưu tiên `utf-16`. |
| **`tra_kho.py`** | `TraKhoProcessor` | `10.TraKho/` (csv) | `09.TraKho/` (Parquet) | Trả kho — chỉ giữ dòng `LyDo == "Nhập cửa hàng trả kho"`. `_read_csv_fixing_ragged_tail` gộp field dư luôn về **cột cuối** (khác cách xử lý của `nhap_tu_sx.py`/`kho_xuat_ch.py` vốn gộp về cột `Noidung` ở giữa). |
| **`lenh_luan_chuyen.py`** | `LenhLuanChuyenProcessor` | Ổ mạng `HHLC_DIR` (`**/*.xlsx`) | `07.Lenh_HHLC/` (Parquet, prefix `KQ_HHLC`) | Lệnh điều chuyển hàng hóa — nguồn là Excel (không phải CSV) trên ổ mạng `\\hovmfs01\...`, dùng `file_glob = "**/*.xlsx"` (đệ quy) và lọc bỏ file tạm `~$...`. Đổi tên cột tiếng Việt → tiếng Anh qua `RENAME_MAP`. |

**Quy ước chung giữa các `sources/*.py`:**
- Mỗi processor có `robust_read_csv`/`robust_read_excel` riêng để tự dò encoding (ưu tiên `utf-16` cho file xuất từ hệ thống) và tự phục hồi dòng lỗi do dấu phẩy không escape.
- Đều dùng `Short_name` (MaHang bỏ 4 ký tự cuối) để tra `D_Category`, và `actual_size()` để chuẩn hoá Size.
- Đều lọc bỏ `Product_type` là "Bao Bì"/"Đồng Phục" và `Brand` là "Dv In Theu"/"Khác" (trừ `Contract_sales`, `KhoXuat_CH`, `NhapTuSX`, `HH_LuanChuyen` — không áp filter này).

### 1.4. export/ — Xuất dữ liệu ra CSV

| File | Nhiệm vụ |
|---|---|
| **`export/data_ap.py`** | Class `ExportManager`. Đọc các bảng Parquet đã xử lý (System_sales, Contract_sales, Inventory, KhoXuat_CH, NhapTuSX, các bảng Master...) bằng DuckDB, xuất ra CSV vào `05.Data_Csv/{01.Master, 02.Raw}` cho Data_ReportAP. Có menu checkbox chọn bảng cần export (`select_exports_menu`), và cơ chế retry khi file đang bị khoá (`_write_csv_with_retry`, gỡ thuộc tính hidden/readonly qua `attrib`). Chạy trực tiếp: `python export/data_ap.py` (mặc định interactive). |

### 1.5. utils/ — Công cụ hỗ trợ

| File | Nhiệm vụ |
|---|---|
| **`utils/format_excel.py`** | Class `ExcelFormatConverter`. Convert file Excel 2003 (`.xls`) → `.xlsx` bằng Excel COM (`win32com`), chạy **trước** bước xử lý HDD_QLKD (vì `HDDProcessor` chỉ đọc `.csv`/`.xlsx`). Xoá sheet rỗng trước khi lưu. Chạy trực tiếp sẽ hỏi đường dẫn thư mục qua `input()`. |

### 1.6. Run_all_data.py — Điểm chạy chính (entry point)

File điều phối toàn bộ pipeline, chạy trực tiếp bằng `python Run_all_data.py`.

**Chức năng:**
- Định nghĩa các hàm `run_*()` bọc quanh từng processor (có đo thời gian qua `timed()`).
- `run_all()` — chạy toàn bộ theo đúng thứ tự: Master refresh → HDD+Tồn kho → Bán lẻ/Bán HĐ (dùng chung lookups đã load 1 lần) → Kho Xuất CH → Nhập từ SX → History_LC → Trả Kho → Lệnh Điều chuyển.
- **Menu checkbox tương tác** (dùng `msvcrt`, chỉ chạy trên Windows): mũi tên ↑↓ di chuyển, Space tích/bỏ chọn mục cần chạy, Enter xác nhận, Esc/chọn "HỦY" để thoát không chạy gì.
- `execute(indices)` — chạy các mục đã chọn; nếu chọn "Bán lẻ" và/hoặc "Bán HĐ" cùng lúc thì load lookups (`SystemSalesProcessor().load_lookups()`) chỉ 1 lần rồi tái sử dụng cho cả 2, tránh đọc lại Parquet Master 2 lần.

**Cách chạy:**
```bash
cd Report
python Run_all_data.py
```
Dùng ↑↓/Space chọn các mục cần cập nhật, Enter để chạy, hoặc tích "Tất cả" để chạy full pipeline.

**Thứ tự phụ thuộc quan trọng:** `run_master_refresh()` (Data_Tracking) phải chạy **trước** mọi processor khác vì tất cả đều `load_master_table()` từ `02.Master/*.parquet`. `run_hdd_ton()` phải chạy trước nếu muốn `InventoryProcessor` có dữ liệu HDD mới nhất gộp vào tồn kho.

---

## 2. Revenue/ — Doanh thu theo ngày

| File | Nhiệm vụ |
|---|---|
| **`Revenue/DoanhThu.py`** | Script độc lập (không dùng `core/` của Report/), ghi kết quả vào **DuckDB** (`D:\DataBase\DuckDB\Report_AP.duckdb`) thay vì Parquet. Gồm 3 bước chạy tuần tự trong `__main__`:<br>1. **`process_sales_data()`** — đọc file `.xls` "DOANH THU THEO NGÀY MM.YYYY" từ ổ mạng `Z:\...`, map cửa hàng qua `map_regions()`/`load_a_region_mapper()` (đọc bảng `A_Region` từ DuckDB `Database_AP.duckdb`, có `manual_overrides` cho các cửa hàng đặc biệt không khớp tự động), lưu vào table **`revenue`**.<br>2. **`process_target_data()`** — đọc chỉ tiêu doanh thu từ `DOANH THU CUA HANG NAM-2026.xlsx` (các sheet `THOP01`..`THOP12`), lưu vào table **`target`**.<br>3. **`process_sales_details()`** — đọc CSV System_sales chi tiết theo bill, gộp nhóm theo ngày/cửa hàng, lưu vào table **`bill_sales`**.<br>Có `robust_read_csv()` và `parse_date()` riêng (bản sao gần giống `core/date_utils.py` của Report/, không import chung). |

**Cách chạy:**
```bash
cd Revenue
python DoanhThu.py
```
Chạy cả 3 bước liên tiếp (dòng cuối `__main__` chỉ gọi `process_sales_data()` + `process_target_data()` — `process_sales_details()` cần gọi riêng nếu cần).

---

## 3. Top_Seller/ — Báo cáo Best/Slow Seller

| File | Nhiệm vụ |
|---|---|
| **`Top_Seller/BaoCao_BanTopSaller.Slow.py`** | Đọc Parquet **`System_sales`** (do `Report/sources/system_sales.py` xuất ra, tại `03.Data_Parquest/01.System_sales/{2025,2026}/`) + `F_DataTracking.parquet`, `E_T-Shirt.parquet` từ `02.Master/`, tính báo cáo **Bán chạy (Best Seller)** hoặc **Bán chậm (Slow Seller)**. Xuất file Excel vào `07.Report/`.<br>Có 2 chế độ chạy:<br>- `python Run_Report.py` → **GUI** (Tkinter, hàm `run_gui_mode()`)<br>- `python Run_Report.py --cli` → **CLI** (hàm `run_cli_mode()`)<br>Tham số lọc: loại báo cáo, nhóm thời gian (Tháng/Quý), khu vực, lọc theo tháng KHPP (kế hoạch phân phối), năm xuất. Hàm chính `run_processing(report_type, time_grouping, region, khpp_filter, export_year, log_func)` thực hiện toàn bộ logic đọc → merge → tính toán → xuất Excel (dùng `xlsxwriter`, có retry nếu file đang mở). |

**Cách chạy:**
```bash
cd Top_Seller
python "BaoCao_BanTopSaller.Slow.py"          # GUI
python "BaoCao_BanTopSaller.Slow.py" --cli    # CLI
```

**Phụ thuộc:** Cần `Report/Run_all_data.py` đã chạy trước (ít nhất mục Master + Bán lẻ) để có đủ Parquet trong `03.Data_Parquest/01.System_sales/`.

---

## 4. Sơ đồ luồng dữ liệu tổng thể

```
                          ┌─────────────────────┐
                          │  Data_Tracking.xlsx  │
                          │  + DMHH (ổ Y:)       │
                          │  + Xếp loại CH       │
                          └──────────┬───────────┘
                                     │ data_tracking.py
                                     ▼
                     02.Master/*.parquet (A_Region, D_Category,
                     B_Size, C_BasicSizeChart, E_T-Shirt, F_DataTracking)
                                     │
              ┌──────────────────────┼───────────────────────────┐
              │ load_master_table()  │ (mọi processor dưới đều đọc từ đây)
              ▼                      ▼                           ▼
   ┌─────────────────┐   ┌────────────────────┐      ┌──────────────────────┐
   │ hdd.py           │   │ system_sales.py     │      │ kho_xuat_ch.py        │
   │ → HDD_QLKD_      │   │ nhap_tu_sx.py       │      │ history_lc.py         │
   │   Tong_hop        │   │ tra_kho.py          │      │ lenh_luan_chuyen.py   │
   │   (02.Master)     │   └──────────┬──────────┘      └───────────┬───────────┘
   └─────────┬─────────┘              │                             │
             │                        ▼                             ▼
             ▼               03.Data_Parquest/                03.Data_Parquest/
   ┌─────────────────┐       01.System_sales/                04.KhoXuat_CH/, 05.NhapSX/
   │ inventory.py      │      02.Contract_sales/              08.History_LC/, 09.TraKho/
   │ → Inventory,       │                                     07.Lenh_HHLC/
   │   InventorySize     │
   │   (03.Inventory)    │
   └─────────────────┘
             │
             ▼
   ┌──────────────────────────┐        ┌───────────────────────────┐
   │ export/data_ap.py          │        │ Top_Seller/               │
   │ → 05.Data_Csv/ (CSV)       │        │ BaoCao_BanTopSaller.py    │
   └──────────────────────────┘        │ → 07.Report/*.xlsx        │
                                        └───────────────────────────┘

   (Độc lập — không dùng Parquet trên)
   ┌──────────────────────────┐
   │ Revenue/DoanhThu.py         │
   │ → DuckDB Report_AP.duckdb    │
   │   (revenue, target,          │
   │    bill_sales)                │
   └──────────────────────────┘
```

---

## 5. Ghi chú khi bảo trì / mở rộng

- **Đổi đường dẫn:** chỉ sửa `Report/core/paths.py` (class `Paths`). File `Revenue/DoanhThu.py` và `Top_Seller/...py` khai đường dẫn riêng ngay đầu file (không dùng `Paths` chung).
- **Thêm nguồn dữ liệu "giao dịch theo tháng" mới:** tạo file trong `Report/sources/`, kế thừa `MonthlySourceProcessor`, khai `source_dir`, `output_dir_name`, `file_prefix`, cài `load_lookups()`/`read_files()`/`transform()`, rồi thêm vào `MENU` của `Run_all_data.py`.
- **Đổi quy tắc quy đổi Size:** sửa `SIZE_MAP`/`FEMALE_SIZE_MAP` trong `core/size_map.py` — áp dụng ngay cho toàn bộ nguồn dữ liệu.
- **Danh mục/khu vực sai:** kiểm tra `data_tracking.py` (nguồn của `D_Category`, `A_Region`...) — sửa lỗi lookup ở đây trước khi sửa logic từng processor riêng, vì mọi nguồn khác đều merge dựa trên các bảng này.
- **File CSV đọc lỗi/dòng bị mất:** mỗi `sources/*.py` có `robust_read_csv` riêng — kiểm tra đúng cột nào hay bị dính dấu phẩy chưa escape (`Kieu`, `Noidung`...) trước khi sửa logic gộp field.
- **`Revenue/` và `Top_Seller/`** không chia sẻ code với `Report/core/` — nếu sửa logic chung (ví dụ `parse_date`, `actual_size`) cần thiết áp dụng cho cả 3 nhóm, phải sửa từng nơi (chưa được refactor dùng chung).

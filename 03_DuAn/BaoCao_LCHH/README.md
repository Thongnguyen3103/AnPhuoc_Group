# Báo cáo Lệnh điều chuyển hàng hóa luân chuyển (LCHH)

## Cấu trúc thư mục

```
03_DuAn/BaoCao_LCHH/
  cau_hinh.yaml              - cấu hình RIÊNG của báo cáo LCHH (kỳ báo cáo, ngưỡng SLA, alias cửa hàng...)
  CHAY_TAO_DU_LIEU.bat       - chạy 2 entrypoint bên dưới (hỏi tháng)
  CHAY_XUAT_EXCEL.bat        - xuất 2 file Excel từ parquet
  tao_du_lieu_lchh.py        - entrypoint mỏng: chạy LCHHPipeline
  tao_du_lieu_hieu_suat.py   - entrypoint mỏng: chạy PerformanceAnalyzer
  xu_ly/                     - logic OOP dùng chung cho cả 2 entrypoint
    cau_hinh.py                AppConfig   - gộp cau_hinh.yaml + đường dẫn dùng chung
    tien_ich.py                hàm đọc/chuẩn hoá dữ liệu (read_many, key_norm, store_norm, ...)
    quy_trinh_lchh.py          LCHHPipeline - đọc + đối chiếu Lệnh/History/TraKho -> KQ_LCHH.parquet
    hieu_suat.py               PerformanceAnalyzer - tái sử dụng LCHHPipeline + doanh số + tồn kho
  bao_cao/                   - script xuất Excel
    xuat_excel_lchh.py
    xuat_excel_hieu_suat.py

04_KetQua/BaoCao_LCHH/       - **1 nơi duy nhất** chứa mọi kết quả
  KQ_LCHH.parquet, KQ_LCHH_HieuSuat.parquet
  bao_cao_excel/*.xlsx
```

Đường dẫn **nguồn dữ liệu gốc** (`07.Lenh_HHLC`, `08.History_LC`, `09.TraKho`, `A_Region`,
`01.System_sales`, `03.Inventory`) không khai báo trong project này — chúng được khai
báo DUY NHẤT một lần ở `01.Python_Projects/dung_chung/cau_hinh.yaml` (dùng chung cho mọi project)
và được `xu_ly/cau_hinh.py` đọc qua `dung_chung.duong_dan`. Muốn đổi vị trí
kho dữ liệu gốc (đổi ổ đĩa, đổi cấu trúc thư mục...) chỉ cần sửa **một chỗ duy nhất** ở đó.

## Chạy

**Cách 1 – tự nhập tháng khi chạy:**

```bash
"C:/Users/THONG SL/anaconda3/python.exe" tao_du_lieu_lchh.py
```

Chương trình hỏi `Nhap thang chay` → gõ `2026-09` (hoặc chỉ `9`); nhiều tháng cách nhau dấu cách; Enter để dùng `cau_hinh.yaml`.

**Cách 2 – truyền tham số:**

```bash
"C:/Users/THONG SL/anaconda3/python.exe" tao_du_lieu_lchh.py 2026-09
"C:/Users/THONG SL/anaconda3/python.exe" tao_du_lieu_lchh.py 2026-08 2026-09 2026-10
```

Kết quả luôn ghi vào **1 file cố định**: `04_KetQua/BaoCao_LCHH/KQ_LCHH.parquet`, chứa dữ liệu của (các) tháng vừa chọn — chạy lại với tháng khác thì file được ghi đè bằng tháng đó.
Tháng chưa có file lệnh `KQ_HHLC_MM` sẽ được bỏ qua.

## Nguồn dữ liệu

| Thư mục | Vai trò |
|---|---|
| `07.Lenh_HHLC` | **CHUẨN** – mỗi dòng 1 yêu cầu điều chuyển (Store_from → Store_to) |
| `08.History_LC` | Lịch sử điều chuyển **đã thực hiện** CH→CH, kèm `TrangThaiNhap` (Đã nhập kho CH / Hàng hóa đi đường) |
| `09.TraKho` | Cửa hàng **trả hàng về kho** — cấu trúc mới: mỗi dòng = 1 lần trả kho thực (cột `TrangThai` đã bỏ). `Kho_Nhan` là mã kho (KHOSALETL / KHOAP / KHOTB) |

## Quy tắc đối chiếu

- **Khóa 1 lệnh** = `Store_from` + `Store_to` + `MaHang` + `Operation` + `Size` (đã chuẩn hóa: MaHang/Operation/Size IN HOA + bỏ khoảng trắng; tên cửa hàng in thường + alias).
- **Thời gian**: chỉ tính mốc History/TraKho có `ym >= ym` của lệnh (`ym = Year*12 + Month`). Lệnh tháng 8 ⇒ chỉ soi di chuyển từ tháng 8 trở đi.
- **Đã điều chuyển**: khớp History đúng tuyến + khóa SKU.
  - `Qty_DaNhapKho` = phần `TrangThaiNhap = "Đã nhập kho CH"`
  - `Qty_DiDuong`  = phần `TrangThaiNhap = "Hàng hóa đi đường"`
- **Trả kho**: cửa hàng **NHẬN** (`Store_to`) sau khi đã nhập kho lại đem trả về kho.
  - khớp `TraKho.Store_name = Store_to` + khóa SKU (`MaHang+Operation+Size`), `ym >= ym` lệnh
  - `Qty_TraKho` = tổng `Qty_Tra` của mọi dòng khớp (cấu trúc mới: mỗi dòng đã là 1 lần trả kho thực)
  - `Qty_TraKho_vuot_nhan` = `max(Qty_TraKho − Qty_DaNhapKho, 0)` khi `Qty_DaNhapKho > 0` → trả nhiều hơn số nhận = trả luôn tồn có sẵn của chính CH

## `trang_thai_thuc_hien` (thứ tự ưu tiên)

| Trạng thái | Điều kiện |
|---|---|
| Chưa thực hiện | không khớp History và không trả kho |
| Nhận rồi trả kho | `Qty_DaNhapKho > 0` và `Qty_TraKho >= Qty_DaNhapKho` |
| Nhận rồi trả kho một phần | `Qty_DaNhapKho > 0` và `0 < Qty_TraKho < Qty_DaNhapKho` |
| Đã thực hiện | `Qty_DaNhapKho >= Qty_Lenh` |
| Thực hiện một phần | `Qty_DaNhapKho > 0` (< lệnh) hoặc chỉ khớp một phần History |
| Đang đi đường | `Qty_DiDuong > 0` và chưa nhập kho |

Lý do các lệnh "Chưa thực hiện" xem trực tiếp ở cột `ly_do` (lọc `trang_thai_thuc_hien == "Chưa thực hiện"`).

## `Danh_gia_han` — thực hiện đúng hạn?

Từ ngày ra thông báo (`NgayChungTu`) phải thực hiện trong **`han_thuc_hien_ngay`** ngày (mặc định 15, sửa ở `cau_hinh.yaml`).
History_LC và TraKho **đã có ngày** (`NgayChungTu` / `NgayChungTu_dt`) → so sánh **theo NGÀY**. Chỉ giữ 2 cột ngày:

| Cột | Nội dung |
|---|---|
| `NgayChungTu_YeuCau` | ngày chứng từ yêu cầu (ngày ra lệnh điều chuyển) |
| `Ngay_thuc_hien` | ngày nhập kho CH sớm nhất (chưa nhập → ngày History sớm nhất; rỗng nếu chưa khớp) |
| `So_ngay_thuc_hien` | số ngày từ yêu cầu đến khi thực hiện |
| `So_ngay_tre` | số ngày trễ so với hạn (= `NgayChungTu_YeuCau + N ngày`; 0 = đúng hạn) |
| `Danh_gia_han` | **Đúng hạn** · **Trễ hạn** · **Trễ hạn - chưa thực hiện** (chưa nhập & quá hạn hôm nay) · **Đang đi đường** · **Chưa tới hạn** |

Kỳ T8: Đúng hạn 1.648 · Trễ hạn 64 · Trễ hạn - chưa thực hiện 168 · Đang đi đường 12. (`So_ngay_thuc_hien` TB 5,9 ngày, tối đa 21).
Kỳ T6: Đúng hạn 7.869 · Trễ hạn 6.383 · Trễ hạn - chưa thực hiện 1.614 · Đang đi đường 1.

## Output (`04_KetQua/BaoCao_LCHH/`)

**1 file cố định**: `KQ_LCHH.parquet` – 1 dòng / 1 lệnh, **33 cột**, chứa dữ liệu tháng vừa chọn (ghi đè mỗi lần chạy).
Cột `Note` từ file Lệnh đổi tên thành `ly_do` (đặt cuối). Region đã join sẵn. Cột `Month` / `Year` cho biết dữ liệu thuộc tháng nào.

33 cột: `NgayChungTu_YeuCau, Year, Month, Quarter, Store_from, Region_from, Store_to, Region_to, MaHang, Report_item_name, Operation, Size, Brand, Product_type, Gender, Product_group, Group_Report, Qty_Lenh, Qty_DaChuyen, Qty_DaNhapKho, Qty_DiDuong, Status_list, Qty_TraKho, Qty_TraKho_vuot_nhan, Kho_Nhan_list, Qty_ChuyenDiTiep, ChuyenDiTiep_toi, trang_thai_thuc_hien, Ngay_thuc_hien, So_ngay_thuc_hien, So_ngay_tre, Danh_gia_han, ly_do`.

- **`Qty_ChuyenDiTiep`** = số lượng cửa hàng **nhận** (`Store_to`) sau đó chuyển tiếp SKU đó đi cửa hàng khác — khớp History `Store_from = Store_to` + **`MaHang + Operation + Size`** (đúng khóa của lệnh; nếu Operation/TN ghi sai thì bản thân lệnh đã sai → không tính), tháng ≥ tháng lệnh, loại self-transfer. `ChuyenDiTiep_toi` = danh sách cửa hàng đích.
- **`Qty_TraKho_vuot_nhan`** = `max(Qty_TraKho − Qty_DaNhapKho, 0)`, chỉ tính khi `Qty_DaNhapKho > 0`. > 0 nghĩa là cửa hàng nhận hàng xong **trả về kho nhiều hơn số nhận** → trả luôn cả hàng tồn có sẵn của chính nó. Kỳ T6: 374 lệnh · T8: 0.

### Region lấy từ đâu?

Từ **master khu vực chuẩn hóa** `02.Master/A_Region.parquet` (key `region` trong dung_chung/cau_hinh.yaml)
(`Store_name → Region`), map theo tên cửa hàng đã chuẩn hóa (bỏ khoảng trắng + in thường).
File Lệnh không có sẵn Region. Toàn bộ 136 cửa hàng trong lệnh T8 đều khớp A_Region (0 thiếu).

---

# 2. `tao_du_lieu_hieu_suat.py` — Hiệu suất bán sau luân chuyển

**Báo cáo độc lập** — chạy riêng, KHÔNG cần `tao_du_lieu_lchh.py` chạy trước, KHÔNG đọc `KQ_LCHH.parquet`.
Tự xử lý luân chuyển từ **data gốc** (dùng lại logic trong `tao_du_lieu_lchh.py`), rồi ghép thêm doanh số + tồn kho.
Xuất `04_KetQua/BaoCao_LCHH/KQ_LCHH_HieuSuat.parquet` — **file gọn 29 cột**, chỉ phần hiệu suất bán: định danh + **tồn trước/sau luân chuyển + bán + tồn hiện tại + đánh giá** (không kèm các số điều chuyển / trả kho / trạng thái — cái đó nằm ở `KQ_LCHH.parquet`).
**Đã lọc bỏ lệnh `trang_thai_thuc_hien = "Chưa thực hiện"`** (T8: bỏ 168 → còn 1.724 dòng). Vẫn giữ lệnh "Đang đi đường" (đã xuất, chưa nhận).

```bash
"C:/Users/THONG SL/anaconda3/python.exe" tao_du_lieu_hieu_suat.py 2026-08
"C:/Users/THONG SL/anaconda3/python.exe" tao_du_lieu_hieu_suat.py            # hỏi tháng; Enter = config
```

Chọn tháng luân chuyển `M` y hệt `tao_du_lieu_lchh.py` (tham số `YYYY-MM` / tự nhập / `periods` trong `cau_hinh.yaml`).
Sau đó **chỉ đọc** file doanh số các tháng `M … M+sales_months_ahead` (mặc định 3 → luân chuyển T8 thì đọc T8,9,10,11). Không đọc toàn bộ 2021–2026.

### Nguồn
| File | Vai trò |
|---|---|
| `01.System_sales/<năm>/System_sales_MM.parquet` | doanh số theo **tháng** (chỉ tính `Nội dung = "Bán"`) |
| `03.Inventory/InventorySize.parquet` | tồn kho **hiện tại** (snapshot, không có tháng) |

### Quy tắc
- Doanh số gán vào **cửa hàng nhận** `Store_to`, khớp `MaHang + Operation + Size`.
- Tính bán **kể từ tháng luân chuyển M**. Data bán chỉ có cấp tháng:
  `Qty_Ban_30d` = tháng M · `60d` = M..M+1 · `90d` = M..M+2 · `Qty_Ban_LuyKe` = toàn bộ tháng đọc được (M..M+`sales_months_ahead`). Ví dụ luân chuyển T8 → tính bán T8, T9, T10, T11.
  `So_thang_ban_co_DL` cho biết đã có mấy tháng dữ liệu (để biết 60d/90d đã đủ chưa).
- `Ton_hien_tai` = tồn InventorySize tại `Store_to` cho SKU đó (mọi Status).
- `Ton_hien_tai` = tồn InventorySize tại `Store_to` cho SKU đó (mọi Status).
- Tồn tại cửa hàng NHẬN, dựng ngược từ snapshot tồn hiện tại (nội bộ dùng số nhận / trả kho / chuyển tiếp từ logic `tao_du_lieu_lchh.py`):
  `raw = Ton_hien_tai − nhận + bán luỹ kế + trả kho + chuyển đi tiếp`
  - **`Ton_truoc_dieu_chuyen`** = `max(raw, 0)` — tồn CH nhận có NGAY TRƯỚC khi lô về. 0 hợp lệ (CH hết hàng → mới cần điều chuyển).
  - **`Ton_sau_dieu_chuyen`** = `Ton_truoc_dieu_chuyen + số nhận` — tồn ngay SAU khi nhận. Số nhận = `Ton_sau − Ton_truoc`.
- `Ty_le_ban_90d`, `Ty_le_ban_LuyKe` = `bán / số nhận`.
- `Danh_gia_ban`: **Không nhận** (nhận = 0) · **Chưa bán** (bán luỹ kế ≤ 0) · **Bán tốt** (bán ≥ nhận) · **Bán khá** (0.5–1) · **Bán chậm** (0–0.5).

### 29 cột (`KQ_LCHH_HieuSuat.parquet`)
Định danh: `NgayChungTu_YeuCau, Year, Month, Quarter, Store_from, Region_from, Store_to, Region_to, MaHang, Report_item_name, Operation, Size, Brand, Product_type, Gender, Product_group, Group_Report, Qty_Lenh`
Hiệu suất: `Ton_truoc_dieu_chuyen, Ton_sau_dieu_chuyen, Qty_Ban_30d, Qty_Ban_60d, Qty_Ban_90d, Qty_Ban_LuyKe, So_thang_ban_co_DL, Ton_hien_tai, Ty_le_ban_90d, Ty_le_ban_LuyKe, Danh_gia_ban`

Kỳ T8 (mới có dữ liệu bán T8): Bán tốt 95 · Chưa bán 1.617 · Không nhận 180. Số 60d/90d/luỹ kế sẽ đầy đủ dần khi có file bán T9, T10, T11.

---

## Lưu ý dữ liệu

- Nguồn được cập nhật định kỳ (`08.History_LC` T5–T8 (đã có ngày), `09.TraKho` T6–T8 (đã có ngày), `01.System_sales` 2021–2026). Code luôn lọc `ym >= tháng lệnh` nên chỉ mốc từ tháng lệnh trở đi được tính.
- Không có mã lệnh trong nguồn ⇒ 1 lệnh định danh bằng 5 khóa trên. Vì khớp theo tuyến+SKU (không phải theo từng chứng từ), `Qty_DaNhapKho` có thể nhỉnh hơn `Qty_Lenh` chút ít khi trên cùng tuyến+SKU có phát sinh điều chuyển ngoài lệnh.
- Nhiều `ly_do` dạng `25/089`, `25/108`, `xuất sai TN` ⇒ lệnh ghi sai Operation nên không khớp History (thể hiện ở nhóm "Chưa thực hiện").

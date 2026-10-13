# Report_Quarter — Báo cáo quý (lượt bill, giá trị TB bill, khung giờ mua sắm)

| File | Vai trò |
|---|---|
| `Report_Quarter.ipynb` | Notebook chính: cấu hình `KY_CHINH`, vẽ biểu đồ % đạt, xuất PNG + Excel |
| `Quarter_Bill_Data.py` | Đọc file thô `Baocao_BanHang_*.csv` → cache 1 dòng/bill theo tháng |

## Cách chạy
1. Tải file thô **Bán hàng - BC_CTBH_Size** (`01.Data_Download`) cho đủ 9 tháng: quý chính, quý trước, cùng kỳ năm trước
   (vd Q3.2026 → 04–09/2026 và 07–09/2025). File nằm ở `01.Source/01.System_sales` (hoặc thêm thư mục vào `RAW_DIRS_EXTRA`).
2. Mở `Report_Quarter.ipynb`, sửa `KY_CHINH`, Run All. Ô *Nạp dữ liệu* báo tháng nào thiếu / chưa đủ ngày.
3. Kết quả: `04.Output/Report_Quarter/<KY_CHINH>/` — PNG mục 1–5 và 3 file Excel
   (`Report_Quarter_<KY>.xlsx`, `_Nhan_hang.xlsx`, `_Phan_tich_bill.xlsx`). File Excel đang mở thì notebook
   chỉ cảnh báo và chạy tiếp; đóng file rồi chạy lại ô đó.

Mục trong notebook: 1 lượt bill · 2 giá trị TB bill · 3 khung giờ / thứ (so quý trước) ·
4 bill theo nhãn AP / PIE / FLD · 5 phân tích bill (ngày / thứ / khung giờ, TB bill tổng & từng hiệu, % bill Anamai–Bonjour).

## Vì sao không đọc Parquet System_sales
Parquet `03.Data_Parquest/01.System_sales` đã gộp theo mặt hàng/ngày nên mất `SoChungTu`, giờ bán và `Tongtien`.
Cache bill lưu tại `04.Output/Report_Quarter/Bill_Cache/<YYYY>/Bills_<MM>.parquet` (gộp theo SoChungTu, không ghi đè),
file thô đã đọc ghi trong `_Processed_Files.csv` → lần sau bỏ qua; đọc xong có thể chuyển/xoá file thô.

## Định nghĩa
- 1 bill = 1 `SoChungTu` có ≥ 1 dòng *Bán* hợp lệ (loại Bao Bì, Đồng Phục, Dv In Theu, Khác như `Process_Sales.py`); *Bán phiếu tặng* không tính.
- Mặc định loại bill `Tongtien ≤ 0` (đổi hàng bù trừ) — `BO_BILL_KHONG_TIEN`.
- Giá trị TB bill = Σ `Tongtien` / số bill (`Tongtien` = khách thực trả, đã trừ Sale %, CK VIP).
- Khung giờ/thứ: tỷ trọng % của *bình quân bill/ngày* (chuẩn hoá số ngày mỗi thứ trong quý).
- `CHI_CH_CHUNG = True` để chỉ so các cửa hàng có bán ở cả 2 kỳ.
- Nhãn: AP = An Phước, AP Ladies, Gerb Weis, Tomiya; PIE = Pierre Cardin; FLD = Anamai + Bonjour.
  Hiệu HTT gộp vào hiệu chính cùng tên. Cache có thêm số lượng / tiền từng hiệu (`SLH_*`, `TTH_*`).

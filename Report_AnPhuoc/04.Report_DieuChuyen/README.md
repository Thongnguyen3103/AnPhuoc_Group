# Báo cáo Điều chuyển Hàng hoá — hướng dẫn chạy

## 1. Cài đặt (chạy 1 lần)
Máy cần Python 3.9+ (Windows). Mở CMD/PowerShell tại thư mục chứa các file này:

```
pip install duckdb pandas openpyxl numpy
```

## 2. Cấu trúc file
```
main.py                    <- chạy file này cho đợt điều chuyển
generate_geo.py            <- (khuyến nghị chạy trước, 1 lần) tạo file toạ độ CH
dc_config.py               <- toàn bộ tham số Phụ lục C — chỉnh ở đây khi cần đổi ngưỡng
dc_data.py                 <- truy vấn DuckDB
dc_compute.py              <- công thức Mục 5 (mã/CH/size), ma trận, cờ BÁN HẾT...
dc_pipeline.py             <- ráp bảng chỉ số SKU / Cửa hàng / Size / (CH x Size)
dc_allocate.py             <- sinh lệnh điều chuyển (Mục 8/9/13/14), ghép cặp theo khoảng cách thật
dc_output.py               <- tổng hợp Sheet 3/4/5/6 (bảng nội bộ)
dc_display.py              <- đổi tên cột sang tiếng Việt hiển thị + dựng nội dung Dashboard Sheet 0
dc_writer.py               <- ghi file Excel (style dashboard: navy header, freeze panes...)
dc_geo.py                  <- geocode địa chỉ + khoảng cách Haversine (km) + ma trận khoảng cách vùng
dc_geo_data.py             <- bảng toạ độ tham chiếu theo tên phường/tỉnh
ViTri_DiaLy_CuaHang.csv    <- (tự tạo bởi generate_geo.py) toạ độ từng CH — RÀ SOÁT rồi sửa tay nếu cần
hieu_suat_ky_history.json  <- (tự tạo bởi main.py) lưu "Hiệu suất kỳ" để tính Xu hướng Lần 3
```

## 3. Chạy

**Bước 0 (khuyến nghị, chạy 1 lần trước khi dùng số liệu thật):**
```
python generate_geo.py
```
→ Tạo `ViTri_DiaLy_CuaHang.csv`, mở bằng Excel rà soát cột `Do_tin_cay`, sửa tay
Lat/Lon cho các dòng "Thấp" rồi lưu lại (xem Mục 5.1 bên dưới).

**Bước 1 — chạy báo cáo:**
```
python main.py
```
Thứ tự hộp thoại hiện ra:
1. Chọn file CSV danh sách mã cần điều chuyển (cột bắt buộc `Combined PK`).
2. **Chọn Lần điều chuyển:**
   - Nếu CSV có sẵn cột **`Dot Chuyen`** (giá trị `Lần 1`/`Lần 2`/`Lần 3`, hoặc `1`/`2`/`3`)
     — script tự đọc và áp dụng đúng theo từng dòng, KHÔNG hỏi lại.
   - Nếu CSV không có cột này, một hộp thoại hiện ra cho bạn chọn: **Tự động** (suy
     theo số tháng kể từ KHPP của từng mã — như bản trước), hoặc ép cứng **Lần 1 /
     Lần 2 / Lần 3** cho toàn bộ mã trong file. Lần 2 siết Top% còn ~một nửa (Mục
     11.2); Lần 3 dùng ma trận xu hướng (Mục 12) — cần đã chạy Lần 2 trước đó để có
     "Hiệu suất kỳ" lưu trong `hieu_suat_ky_history.json`, nếu chưa có script vẫn
     chạy được nhưng Xu hướng sẽ thiếu dữ liệu so sánh.
3. Chọn Database_AP.duckdb (nếu không thấy đúng đường dẫn D:\).
4. Chọn Vùng tham gia + tick bỏ từng cửa hàng muốn loại.
5. Chọn nơi lưu file kết quả `.xlsx`.

## 4. Cấu trúc file kết quả (7 sheet, đúng theo mẫu)
| Sheet | Nội dung |
|---|---|
| `0.Dashboard & Tham số` | Thông tin đợt chạy, bảng ngưỡng trạng thái mã, bảng nhóm hiệu suất ABCD, ma trận khoảng cách thật giữa 5 vùng (km), bảng cửa sổ size mẫu |
| `1.Tổng hợp SKU` | Mỗi mã 1 dòng: Ma Hang/Operation tách riêng, Tồn HTCH / Tồn Các Kho tách riêng, tỷ lệ bán, tốc độ bán chuẩn, trạng thái mã... |
| `2.Thông tin cửa hàng × SKU` | Mỗi mã × mỗi CH 1 dòng: địa chỉ, nhóm A/B/C/D, cờ BÁN HẾT, Định Mức Tồn & Hạn Mức Nhận (tính đúng Mục 7.1/7.2 trên TOÀN BỘ mã của CH, không riêng danh sách đang chạy), cột Đề Xuất |
| `3.Chi tiết Bán-Tồn Size` | Mỗi mã × CH × size: tồn, bán 3T, tốc độ bán size, tháng tồn size, có trong cửa sổ hay không, đề xuất xuất/nhận |
| `4.Lệnh điều chuyển chi tiết` | CH xuất → CH nhận theo từng size, khoảng cách km thật, tồn dự kiến 2 đầu sau chuyển |
| `5.Tổng hợp lệnh` | Gọn: STT – CH xuất – Mã – Size – SL – Giá trị – CH nhận – vùng – loại lệnh – khoảng cách |
| `6.Tổng hợp theo cửa hàng` | Tồn đầu kỳ / tổng xuất / tổng nhận / tồn cuối dự kiến theo từng CH |

Muốn có thêm bảng "mỗi SKU 1 dòng, liệt kê các CH nhận + SL trong 1 ô" (đã làm ở bản
trước), báo tôi — có thể thêm lại như Phần B trong Sheet 6 mà không ảnh hưởng cấu
trúc hiện tại.

## 5. Những điểm đã đơn giản hoá — CẦN BIẾT trước khi phát lệnh thật

1. **Khoảng cách địa lý — ĐÃ CÓ toạ độ ước tính, khuyến nghị rà soát trước khi dùng thật:**
   - Chạy **`python generate_geo.py`** (1 lần, hoặc mỗi khi hệ thống mở CH mới) để
     tạo file `ViTri_DiaLy_CuaHang.csv` cạnh `main.py`. File này suy toạ độ (lat/lon)
     từ chính cột "Địa chỉ" trong `A_Region`, khớp theo tên phường/quận trước
     (chính xác hơn), rồi mới rơi về tỉnh/thành phố sau sáp nhập 2025 nếu không khớp
     được cấp phường. Bảng tên địa danh nằm trong `dc_geo_data.py`.
   - Mở `ViTri_DiaLy_CuaHang.csv` bằng Excel, xem cột **`Do_tin_cay`**: dòng nào ghi
     "Thấp — cần rà soát tay" (thường do CH thiếu địa chỉ trong DB, hoặc địa danh lạ
     `dc_geo_data.py` chưa có) thì tự tra Google Maps rồi điền tay `Lat`/`Lon`. Lưu
     lại file — `main.py` sẽ tự đọc file này ở lần chạy sau, không cần chỉnh code.
   - Nếu chưa chạy `generate_geo.py`, `main.py` vẫn tự geocode xấp xỉ ngay lúc chạy
     (không lưu lại), nên vẫn ra kết quả nhưng độ chính xác thấp hơn.
   - Thuật toán ghép cặp (`dc_allocate.py`) giờ **ưu tiên khoảng cách THẬT** (Haversine,
     km) trước, đúng như bạn yêu cầu: 1 CH ở rìa Miền Tây có thể được ưu tiên nhận từ
     1 CH rìa TP.HCM gần hơn, thay vì bắt buộc lấy từ CH cùng Vùng nhưng ở xa. Nhãn
     "Nội vùng / Liên vùng" ở Sheet 4 & 5 chỉ còn mang tính MÔ TẢ (đối chiếu Mục 13 —
     đếm số lần chuyển liên vùng), không còn quyết định thứ tự chọn nguồn.
   - Muốn chính xác tuyệt đối (giao thông thực tế, không phải đường chim bay), thay
     hàm `haversine_km` trong `dc_geo.py` bằng gọi Google Distance Matrix API khi máy
     có mạng ổn định.
2. **Mùa vụ (Mục 4)**: DuckDB hiện chưa có bảng lịch mùa vụ theo danh mục, nên mọi mã
   đang được coi là "Trong mùa" (không đóng băng, không giới hạn cuối mùa). Khi có
   bảng mùa vụ, bổ sung bước lọc ngay đầu `dc_pipeline.build_all`.

**Đã sửa (trước đây là bug):** Bảng "Cửa sổ size tiêu chuẩn" ở Sheet 0 từng bị viết
cứng nên mọi Vùng ra kết quả giống hệt nhau bất kể chọn Lần nào. Giờ bảng này tính
THẬT từ dữ liệu bán 3 tháng gần nhất theo từng Vùng của danh mục phổ biến nhất trong
đợt đang chạy (dùng đúng thuật toán trượt cửa sổ Mục 6.2) — sẽ khác nhau giữa các
Vùng, và khác nhau giữa các lần chạy nếu danh mục hoặc dữ liệu bán thay đổi. Bảng
này KHÔNG phụ thuộc vào Lần 1/2/3 (nó phụ thuộc Danh mục × Vùng × Loại CH theo đúng
Mục 6, không phải theo Lần) — đây là điều đúng theo tài liệu, không phải bug.
3. **Hạn mức nhận cấp CH (Mục 7.2, Pha 1→Pha 2)**: bản đầy đủ cần "bán bình quân
   tháng toàn CH (mọi mã)" để ra định mức tồn CH, rồi cộng dồn nhu cầu mọi mã trong
   đợt để cắt giảm khi vượt hạn mức (giống sheet `07_Cắt giảm Pha2` trong file mẫu
   bạn từng có). Bản này áp van điều tiết ở mức suất chia mỗi lệnh, CHƯA cộng dồn
   chéo giữa nhiều mã cùng đợt — nếu bạn chạy nhiều mã cùng lúc và muốn chặn 1 CH
   nhận dồn dập từ nhiều mã, cần bổ sung bước Pha 2 riêng (có thể yêu cầu làm tiếp).
4. **Lần 2 / Lần 3**: script tự tính Lần theo số tháng kể từ KHPP mỗi mã, và tự lưu
   "Hiệu suất kỳ" vào `hieu_suat_ky_history.json` sau mỗi lần chạy để dùng cho Xu
   hướng ở Lần 3 (Mục 12). Nếu chưa từng chạy Lần 2 cho 1 mã mà mã đó đã đến hạn
   Lần 3, script sẽ không có số liệu Xu hướng — cần chạy đủ tuần tự.
5. **Ràng buộc "không mâu thuẫn 2 chiều"**: thuật toán phân vai trò nhận/xuất theo
   từng mã sao cho về nguyên tắc 1 CH không vừa là nơi nhận vừa là nơi xuất CÙNG
   size CÙNG mã trong 1 đợt (do Top/ma trận đã tách rạch ròi vai trò importer/exporter
   theo từng trạng thái mã). Bản hiện tại không tự kiểm tra chéo lại điều này sau khi
   ghi Excel — nếu bạn chỉnh sửa logic phân vai trò trong `dc_allocate.py`, nên tự đối
   chiếu Sheet 4 (nhóm theo `Combined PK` + `Size`, kiểm tra không CH nào xuất hiện cả
   ở cột `CH Xuất` lẫn `CH Nhận`).
6. **Pha 2 (Mục 7.2)**: hàm `dc_allocate.build_transfer_orders` hiện chỉ trả về đúng
   1 bảng lệnh chi tiết — chưa có bước cộng dồn nhu cầu nhiều mã trong cùng đợt để cắt
   giảm khi vượt hạn mức CH (xem điểm 3 phía trên). Đây là chỗ để bổ sung nếu cần.

## 6. Muốn chỉnh ngưỡng / tham số
Toàn bộ số liệu ở Phụ lục C nằm gọn trong `dc_config.py` — sửa xong chạy lại
`main.py`, không cần đụng logic tính toán ở các file khác.

## 7. ĐÍNH CHÍNH quan trọng (bản cập nhật này)

1. **Ngưỡng trạng thái mã (Mục 5.1) áp theo LẦN, không theo nhóm hàng:** 3 cột
   "mốc 6/9/12 tháng" ứng với số tháng mã đã trên kệ, tiến theo Lần điều chuyển —
   Lần 1 dùng 85/65/25, Lần 2 dùng 88/70/30, Lần 3 dùng 90/75/35. (Hàng Nhóm 2/3
   — phụ kiện, vest — đi theo Mục 10, không dùng bảng này.) Bản trước áp sai theo
   nhóm danh mục nên cả 3 Lần ra cùng ngưỡng.
2. **"Số tháng bán" = số tháng THỰC TẾ mã trên kệ** (từ Dist_plan đến hiện tại),
   tăng dần 6 → 9 → 12 qua các Lần; bản trước dùng hằng số mốc KHPP nên tốc độ
   bán chuẩn không đổi giữa các Lần.
3. **TB Bán/Tháng (HT) ≠ Tốc độ bán chuẩn (/CH):** cột đầu = Tổng bán ÷ số tháng
   bán; cột sau chia thêm số CH đã phân phối. Bản trước 2 cột trùng nhau.
4. **Sheet 1 thêm "Bán 3T Gần Nhất" và "Số Tháng Bán"** — chạy Lần 2/3 thấy được
   cả lũy kế lẫn 3 tháng gần nhất đúng yêu cầu nghiệp vụ.
5. **Lần 2 siết vai trò đúng Mục 11.2** (chỉ nhóm A + cờ BÁN HẾT được nhận, nhóm D
   xuất toàn bộ không giữ size); **Lần 3 chạy ma trận xu hướng Mục 12** (Xu hướng =
   Hiệu suất kỳ L3 ÷ L2 đã lưu; gom tối đa 5–10 điểm, còn lại rút hết). Hiệu suất kỳ
   giờ lưu ĐÚNG bản 3 tháng (không lũy kế) vào hieu_suat_ky_history.json — vì vậy
   file state cũ lưu theo bản lũy kế không dùng lại được cho Xu hướng; hãy chạy lại
   Lần 2 bằng bản này trước khi chạy Lần 3.
6. **Bảng cửa sổ size Sheet 0 áp độ lệch vùng Phụ lục B:** Miền Trung −1 bậc (thiên
   size nhỏ), Miền Tây +2/+2/+3/+4 theo loại CH (thiên size lớn), TP.HCM/Đông chuẩn.
   Cửa sổ của từng CH khi lập lệnh cũng đã thêm bậc "hồ sơ size vùng" vào chuỗi ưu
   tiên: lịch sử CH → vùng → toàn hệ thống (Mục 6.2).

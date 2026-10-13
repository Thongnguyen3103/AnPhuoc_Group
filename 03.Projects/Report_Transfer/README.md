# Báo cáo Điều chuyển Hàng hoá — hướng dẫn chạy

## 1. Cài đặt (chạy 1 lần)
Máy cần Python 3.9+ (Windows). Mở CMD/PowerShell tại thư mục chứa các file này:

```
pip install duckdb pandas openpyxl numpy
```

## 2. Cấu trúc thư mục (OOP)
```
Report_Transfer/
├── Open_Transfer_GUI.py                  <- MỞ GIAO DIỆN chạy đợt điều chuyển
├── Generate_Store_Coordinates.py         <- (chạy trước, 1 lần) tạo file toạ độ CH
│
├── Config/                               CẤU HÌNH
│   ├── Config_Parameters.py              toàn bộ tham số Phụ lục C — chỉnh ở đây khi đổi ngưỡng
│   ├── Config_Gui_Theme.py               màu + font giao diện
│   └── Paths_Transfer.py                 đường dẫn (kho Parquet, Data/, 04.Output) lấy từ 00.Shared
│
├── Core/                                 XỬ LÝ
│   ├── Load_Data_Parquet.py     class TransferDataLoader    đọc thẳng Parquet (02.Master, 03.Data_Parquest)
│   ├── Compute_Metrics.py       class MetricRules           công thức Mục 5, ma trận, cờ BÁN HẾT, cửa sổ size
│   ├── Build_Pipeline_Tables.py class PipelineTableBuilder  ráp bảng SKU / CH / Size / (CH x Size)
│   ├── Allocate_Transfers.py    class TransferAllocator     sinh lệnh điều chuyển (Mục 8/9/13/14)
│   ├── Store_Performance_State.py class PerformanceStateStore  lưu "Hiệu suất kỳ" (Xu hướng Lần 3)
│   └── Run_Transfer_Report.py   class TransferReportRunner  điều phối trọn 1 lần chạy (không cần GUI)
│
├── Geo/                                  ĐỊA LÝ
│   ├── Compute_Geo_Distance.py  class GeoLocator            geocode + khoảng cách Haversine (km)
│   └── Geo_Reference_Data.py                                bảng toạ độ tham chiếu phường/tỉnh
│
├── Output/                               KẾT XUẤT
│   ├── Summarize_Output.py      class OutputSummarizer      tổng hợp Sheet 3/4/5/6
│   ├── Format_Display.py        class DisplayFormatter      đổi tên cột hiển thị + Dashboard Sheet 0
│   └── Write_Excel_Report.py    class ExcelReportWriter     ghi file Excel 7 sheet
│
├── Gui/
│   └── Transfer_App.py          class TransferApp           cửa sổ giao diện (tkinter)
│
└── Data/                                 DỮ LIỆU CHẠY (không phải code)
    ├── ViTri_DiaLy_CuaHang.csv           toạ độ từng CH — RÀ SOÁT rồi sửa tay nếu cần
    └── lich_su_hieu_suat_ky.json         "Hiệu suất kỳ" đã lưu để tính Xu hướng Lần 3
```

Luồng chạy: `TransferApp` → `TransferReportRunner.run()` → `TransferDataLoader` →
`PipelineTableBuilder` (dùng `MetricRules`) → `TransferAllocator` → `OutputSummarizer` →
`DisplayFormatter` → `ExcelReportWriter`.

Chạy không cần giao diện (vd để test / đặt lịch):
```python
import sys; sys.path.insert(0, r"...\03.Projects\Report_Transfer")
from Core.Run_Transfer_Report import TransferReportRunner
TransferReportRunner(dict(csv_path=..., data_root=None, out_dir=..., round_choice="AUTO",
                          selected_regions=[...], excluded_stores=[], do_geocode=True)).run()
```

Dữ liệu đọc TRỰC TIẾP từ Parquet (không dùng file .duckdb) — đường dẫn lấy từ `00.Shared/Config_Paths.yaml`.
File Excel kết quả mặc định lưu vào `04.Output/Report_Transfer/`.

## 3. Chạy

**Bước 0 (khuyến nghị, chạy 1 lần trước khi dùng số liệu thật):**
```
python Generate_Store_Coordinates.py
```
→ Tạo `Data/ViTri_DiaLy_CuaHang.csv`, mở bằng Excel rà soát cột `Do_tin_cay`, sửa tay
Lat/Lon cho các dòng "Thấp" rồi lưu lại (xem Mục 5.1 bên dưới).

**Bước 1 — chạy báo cáo:**
```
python Open_Transfer_GUI.py
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
     "Hiệu suất kỳ" lưu trong `Data/lich_su_hieu_suat_ky.json`, nếu chưa có script vẫn
     chạy được nhưng Xu hướng sẽ thiếu dữ liệu so sánh.
3. Kho dữ liệu Parquet: mặc định `00.Data_AnPhuoc_Group` theo Config_Paths.yaml (chỉ đổi khi dữ liệu nằm chỗ khác).
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
| `7.DX chia từ Kho` | Đề xuất chia từ kho đi CH cho phần nhu cầu chưa đủ sau điều chuyển giữa CH |
| `8.Tồn-Chuyển-Nhận CH×Nhóm` | CH → nhóm hàng = tên sản phẩm + thuộc tính (vd "Chemise Nam Dài PIE - Màu"; Quần: "… - Form - Style") → mã điều chuyển: tồn ban đầu / chuyển / nhận từ CH / nhận từ kho / tồn cuối. Cuối mỗi nhóm 2 dòng: **Total — mã điều chuyển** (xanh) và **tồn toàn CH (nguyên giá)** (vàng, mọi mã nguyên giá cùng nhóm tại CH). Cuối sheet: TỔNG CỘNG (chỉ mã điều chuyển) |

Muốn có thêm bảng "mỗi SKU 1 dòng, liệt kê các CH nhận + SL trong 1 ô" (đã làm ở bản
trước), báo tôi — có thể thêm lại như Phần B trong Sheet 6 mà không ảnh hưởng cấu
trúc hiện tại.

## 5. Những điểm đã đơn giản hoá — CẦN BIẾT trước khi phát lệnh thật

1. **Khoảng cách địa lý — ĐÃ CÓ toạ độ ước tính, khuyến nghị rà soát trước khi dùng thật:**
   - Chạy **`python Generate_Store_Coordinates.py`** (1 lần, hoặc mỗi khi hệ thống mở CH mới) để
     tạo file `Data/ViTri_DiaLy_CuaHang.csv`. File này suy toạ độ (lat/lon)
     từ chính cột "Địa chỉ" trong `A_Region`, khớp theo tên phường/quận trước
     (chính xác hơn), rồi mới rơi về tỉnh/thành phố sau sáp nhập 2025 nếu không khớp
     được cấp phường. Bảng tên địa danh nằm trong `Geo/Geo_Reference_Data.py`.
   - Mở `ViTri_DiaLy_CuaHang.csv` bằng Excel, xem cột **`Do_tin_cay`**: dòng nào ghi
     "Thấp — cần rà soát tay" (thường do CH thiếu địa chỉ trong DB, hoặc địa danh lạ
     `Geo/Geo_Reference_Data.py` chưa có) thì tự tra Google Maps rồi điền tay `Lat`/`Lon`. Lưu
     lại file — `Open_Transfer_GUI.py` sẽ tự đọc file này ở lần chạy sau, không cần chỉnh code.
   - Nếu chưa chạy `Generate_Store_Coordinates.py`, `Open_Transfer_GUI.py` vẫn tự geocode xấp xỉ ngay lúc chạy
     (không lưu lại), nên vẫn ra kết quả nhưng độ chính xác thấp hơn.
   - Thuật toán ghép cặp (`Core/Allocate_Transfers.py`) giờ **ưu tiên khoảng cách THẬT** (Haversine,
     km) trước, đúng như bạn yêu cầu: 1 CH ở rìa Miền Tây có thể được ưu tiên nhận từ
     1 CH rìa TP.HCM gần hơn, thay vì bắt buộc lấy từ CH cùng Vùng nhưng ở xa. Nhãn
     "Nội vùng / Liên vùng" ở Sheet 4 & 5 chỉ còn mang tính MÔ TẢ (đối chiếu Mục 13 —
     đếm số lần chuyển liên vùng), không còn quyết định thứ tự chọn nguồn.
   - Muốn chính xác tuyệt đối (giao thông thực tế, không phải đường chim bay), thay
     hàm `haversine_km` trong `Geo/Compute_Geo_Distance.py` bằng gọi Google Distance Matrix API khi máy
     có mạng ổn định.
2. **Mùa vụ (Mục 4)**: Dữ liệu hiện chưa có bảng lịch mùa vụ theo danh mục, nên mọi mã
   đang được coi là "Trong mùa" (không đóng băng, không giới hạn cuối mùa). Khi có
   bảng mùa vụ, bổ sung bước lọc ngay đầu `PipelineTableBuilder.build_all`.

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
   "Hiệu suất kỳ" vào `Data/lich_su_hieu_suat_ky.json` sau mỗi lần chạy để dùng cho Xu
   hướng ở Lần 3 (Mục 12). Nếu chưa từng chạy Lần 2 cho 1 mã mà mã đó đã đến hạn
   Lần 3, script sẽ không có số liệu Xu hướng — cần chạy đủ tuần tự.
5. **Ràng buộc "không mâu thuẫn 2 chiều"**: thuật toán phân vai trò nhận/xuất theo
   từng mã sao cho về nguyên tắc 1 CH không vừa là nơi nhận vừa là nơi xuất CÙNG
   size CÙNG mã trong 1 đợt (do Top/ma trận đã tách rạch ròi vai trò importer/exporter
   theo từng trạng thái mã). Bản hiện tại không tự kiểm tra chéo lại điều này sau khi
   ghi Excel — nếu bạn chỉnh sửa logic phân vai trò trong `Core/Allocate_Transfers.py`, nên tự đối
   chiếu Sheet 4 (nhóm theo `Combined PK` + `Size`, kiểm tra không CH nào xuất hiện cả
   ở cột `CH Xuất` lẫn `CH Nhận`).
6. **Pha 2 (Mục 7.2)**: hàm `TransferAllocator.build_transfer_orders` hiện chỉ trả về đúng
   1 bảng lệnh chi tiết — chưa có bước cộng dồn nhu cầu nhiều mã trong cùng đợt để cắt
   giảm khi vượt hạn mức CH (xem điểm 3 phía trên). Đây là chỗ để bổ sung nếu cần.

## 6. Muốn chỉnh ngưỡng / tham số
Toàn bộ số liệu ở Phụ lục C nằm gọn trong `Config/Config_Parameters.py` — sửa xong chạy lại
`Open_Transfer_GUI.py`, không cần đụng logic tính toán ở các file khác.

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
   giờ lưu ĐÚNG bản 3 tháng (không lũy kế) vào Data/lich_su_hieu_suat_ky.json — vì vậy
   file state cũ lưu theo bản lũy kế không dùng lại được cho Xu hướng; hãy chạy lại
   Lần 2 bằng bản này trước khi chạy Lần 3.
6. **Bảng cửa sổ size Sheet 0 áp độ lệch vùng Phụ lục B:** Miền Trung −1 bậc (thiên
   size nhỏ), Miền Tây +2/+2/+3/+4 theo loại CH (thiên size lớn), TP.HCM/Đông chuẩn.
   Cửa sổ của từng CH khi lập lệnh cũng đã thêm bậc "hồ sơ size vùng" vào chuỗi ưu
   tiên: lịch sử CH → vùng → toàn hệ thống (Mục 6.2).

## 8. Cập nhật 2026-10 — sửa logic luân chuyển

1. **Không còn lệnh CH xuất = CH nhận; trong cùng 1 mã, mỗi CH chỉ 1 vai trò** (nhận
   ưu tiên hơn xuất). Sau mỗi lần chạy, log in phần "Kiểm tra lệnh" (tự chuyển, vừa
   xuất vừa nhận, CH không rút bị xuất, xuất vượt tồn, lô tối thiểu).
2. **Tỷ lệ bán toàn mã = 30% TỶ LỆ kỳ + 70% TỶ LỆ lũy kế** (trước đây trộn 2 số lượng
   chung một mẫu số → Lần 2/3 bị kéo thấp). Sheet 1 thêm "Tỷ lệ Bán Kỳ", "Tỷ lệ Bán Lũy Kế".
3. **Tốc độ bán chỉ tính số bán TRONG KHUNG Lần** (cùng khoảng với số tháng chia).
4. **CH không rút:** nút "🛡 CH không rút" trên GUI — CH được chọn vẫn nhận, không bị
   xuất. Lưu tại `Data/CH_khong_rut.json`. Bảo hộ tự động theo số tháng đã TẮT
   (`BAOHO_TU_DONG = False`) vì luật cũ tính theo tuổi mã, không phải tuổi CH.
5. **Lệnh dùng đúng cửa sổ size / size gãy ở Sheet 2** (cột "Nguồn Cửa Sổ": lịch sử CH →
   hồ sơ vùng → toàn HT + lệch vùng Phụ lục B).
6. **CH nhận nhiều cái/size:** nhu cầu size = tồn mục tiêu × tỷ trọng size − tồn size
   (size gãy tối thiểu 1).
7. **Gom chuyến:** ưu tiên CH nguồn đã có chuyến tới CH nhận nếu xa thêm ≤
   `GOM_CHUYEN_KM_THEM` km. Sheet 4/5 có cột "Đạt Lô Tối Thiểu" (✗ tô đỏ).
8. **Giữ 2 size LIỀN KỀ** bán tốt nhất ở CH xuất (trước là 2 size bán tốt nhất bất kỳ).
9. **Sheet 7 "DX chia từ Kho":** phần nhu cầu CH nhận chưa đủ sau điều chuyển giữa CH
   được chia từ Kho An Phước / Kho PIE / Kho Tổng hợp; Kho CN Hà Nội chỉ chia cho CH
   Hà Nội (lấy trước). Danh sách kho: `KHO_CHIA_CHUNG`, `KHO_CHIA_THEO_VUNG`.
10. **Hiệu suất kỳ không phạt CH hết hàng:** CH tồn = 0 → chia cho số tháng CÓ BÁN trong
    kỳ (không có tồn theo tháng nên dùng tháng có bán thay tháng có hàng).
11. **Hạn mức nhận theo nhóm hàng (chống dồn về 1 CH bán tốt nhất):** mỗi đợt, tổng SL
    1 CH nhận của 1 nhóm (cộng mọi mã cùng nhóm) ≤ `HAN_MUC_NHOM_THANG_BAN` (1,5) × bán
    bình quân tháng của CH ở nhóm đó (3 tháng gần nhất, mọi mã). Nhóm: Quần → Form + Style;
    Chemise / Áo Thun / Áo Golf / khác → Color_group (`NHOM_KEY_THEO_DANH_MUC`). CH chưa
    bán nhóm (hoặc hạn mức < suất chia) → mỗi mã nhận tối đa = suất chia. Sheet 2 có cột
    "Nhóm Hạn Mức", "Bán TB/Tháng Nhóm", "Hạn Mức Nhận Nhóm (đợt)". (Cột "Hạn Mức Nhận"
    cũ theo Mục 7 chỉ để tham khảo, không dùng để chặn.)
12. **Sheet 1 tách tồn HTCH:** "Tồn HTCH (trừ HN)" và "Tồn CH Hà Nội" (Tồn HTCH = tổng 2 cột).
13. **Lũy kế đã vượt ngưỡng Sắp hết → luôn "Sắp hết hàng"** (mã gần hết hàng có tỷ lệ bán kỳ
    thấp vì không còn hàng để bán, không để phần trộn 30% kỳ kéo xuống).
14. **Lần 3: số điểm gom theo lượng tồn** = tồn còn lại ÷ suất chia TB (1 bộ size), trong [1, 10].
15. **Mã gãy size** (số size bộ chính còn hàng < 50% bộ size chính): không rải đi nhiều CH — gom
    toàn bộ size còn lại về 1–2 CH bán các size đó tốt nhất trong kỳ (tồn ≤ 6 cái → 1 CH).
    Lý do lệnh "Gom mã gãy size"; Sheet 1 có cột "Số Size Chính Còn Hàng", "Mã Gãy Size".
16. **Tồn tối thiểu sau điều chuyển (mọi trạng thái mã):** mỗi CH × mã sau điều chuyển còn **0 hoặc
    ≥ 3 cái** (`TON_TOI_THIEU_SAU_DC`). CH nhận mà vẫn < 3 → huỷ lệnh nhận; CH còn 1–2 cái (kể cả
    CH không có lệnh) hoặc CH đã xuất mà còn < 3 size → rút nốt về CH đang giữ ≥ 3 (ưu tiên CH nhận),
    lý do "Rút nốt tồn lẻ (<3 cái)". CH xuất 1 phần giữ lại 3 size liền kề, mỗi size 1 cái
    (`GIU_LAI_SO_SIZE`). Chia từ kho (Sheet 7) không tạo tồn 1–2 cái. CH "Không rút" giữ nguyên.
    Log "Kiểm tra lệnh" báo số (mã, CH) còn tồn cuối 1–2 cái nếu có.
17. **Mã tồn phạm vi < 3 cái** (tổng mọi CH trong phạm vi): không gom đủ được → để nguyên, không ra
    lệnh; Sheet 1 cột "Đề Xuất Sale/Thanh Lý" đánh dấu để xử lý riêng.
18. **Chế độ GOM THEO TỒN (`CHE_DO_PHAN_BO = "GOM_THEO_TON"`, mặc định)** — 1 công thức cho mọi
    trạng thái / mọi Lần (thay top% & ma trận Mục 9; logic cũ giữ ở chế độ "THEO_TRANG_THAI"):
    - N điểm bán = tồn phạm vi ÷ (số size bộ chính × `GOM_CAI_MOI_SIZE`: Lần 1 = 1, Lần 2 = 1,5,
      Lần 3 = 2 cái/size), tối thiểu 1 — số điểm phụ thuộc lượng tồn, không fix cứng. Sheet 1 cột
      "Số Điểm Bán (N)".
    - Chọn N CH: cờ BÁN HẾT → Hiệu suất kỳ (Lần 1: 6T; Lần 2/3: 3 tháng gần nhất, không cần file
      Lần 2) → Hiệu suất CH → đang có hàng.
    - Mỗi điểm nhận tới phần chia đều (tồn ÷ N) theo tỷ trọng size bộ chính, cấp VÒNG TRÒN từng cái
      → CH top 1 không lấy quá phần chia đều.
    - Hạn mức nhóm (1,5 tháng bán, cộng dồn các mã cùng nhóm): CH đủ hạn mức → GIỮ hàng, không nhận
      thêm, nhường suất điểm bán cho CH kế tiếp; phần rút về / rút nốt ưu tiên điểm còn hạn mức.
    - CH ngoài N rút hết về N điểm (lý do "Rút về điểm bán"); vẫn áp tồn cuối 0 hoặc ≥3, mã gãy
      size, mã tồn < 3 đề xuất sale, chia từ kho.
19. **Hạn mức nhóm chặn ngay khi cấp hàng:** điểm bán hết hạn mức (cộng dồn các mã cùng nhóm) dừng nhận ở
    bước bù đủ size; phần thiếu do hết hạn mức không đẩy sang chia kho.
20. **Mọi điểm bán đã đủ hạn mức khi rút về → MỞ THÊM điểm:** CH xếp hạng kế tiếp còn hạn mức và chưa xuất
    cái nào ở mã đó trở thành điểm bán (giữ hàng đang có, nhận phần rút về) thay vì dồn vượt hạn mức.

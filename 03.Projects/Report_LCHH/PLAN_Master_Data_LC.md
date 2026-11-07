# PLAN MASTER DATA LUÂN CHUYỂN HÀNG HÓA

Quy tắc đã chốt với bạn ngày 04/11/2026. Đổi quy tắc thì cập nhật file này trước khi sửa code.

## 1. Tư duy

Báo cáo trả lời hai câu hỏi: đã luân chuyển thế nào, và hàng luân chuyển bán ra sao.
- Ba file chỉ lưu dữ liệu nền (số lượng, ngày, trạng thái). Chỉ số do báo cáo bổ sung.
- Master là nguồn duy nhất xác định hàng nào là hàng LC.
- Lưu đủ lịch sử, tháng chạy chỉ là bộ lọc.
- Cộng lại phải khớp nguồn; phần bị loại được in ra khi chạy.

```
07.Lenh_HHLC ──┐
08.History_LC ─┼─> [1] Master_MaHang_LC ──┬─> [2] Data_LuanChuyen
09.TraKho ─────┘                          └─> [3] Data_Ban_LC
01.System_sales ──────────────────────────────────^
```

Chạy: `python Build_Master_LC.py 2026-10`. Đầu ra: `04.Output/Report_LCHH/Master/`. Dữ liệu tính tới hết tháng chạy.

## 2. Quy tắc đã chốt

**Master**
1. SKU = MaHang + TNSX (cột `Operation`). Master chi tiết tới size.
2. Lần LC xác định theo tháng: tháng thứ n có lệnh của SKU trên toàn hệ thống là lần n. Lệnh cùng tháng khác ngày vẫn là một lần.

**File luân chuyển**

3. Chỉ tính lệnh trong `07.Lenh_HHLC`. History ngoài lệnh không tính.
4. Dòng Note "Hết tồn": phần chưa thực hiện coi là hủy (`Qty_Huy`).
5. Hạn thực hiện 15 ngày. Quá hạn vẫn tính nhập và đánh dấu trễ.
6. File lưu đủ lệnh, có cả tháng lệnh và tháng nhận để lọc.

**File bán luân chuyển**

7. Bán LC là bán tại đúng cửa hàng nhận, cùng SKU và size, từ ngày nhận trở đi.
8. Hàng LC bán trước, không vượt số đã nhận còn lại.
9. Tính Bán + Đổi, Status Nguyên giá + Sale. Không tính Tặng.
10. Nhóm tháng LC để riêng 6 tháng gần nhất tính cả tháng bán; cũ hơn gộp "Trên 6 tháng" (`Nhom_Thang_LC`).
11. Hàng chuyển tiếp đi cửa hàng khác không còn là bán LC ở nơi nhận sau; số lượng đó trừ khỏi lô.
12. `Data_Ban_LC` chỉ ghi bán của tháng chạy. Bán các tháng trước vẫn được tính nội bộ để biết lô còn lại bao nhiêu.

## 3. Giả định khi dựng (bạn kiểm tra lại)

- **A. Khớp size:** câu 3 chốt master tới size nên bán cũng khớp tới size. Khớp theo SKU không xét size thì số bán LC sẽ cao hơn.
- **B. Thanh lý:** không tính vào bán LC vì bạn nêu "nguyên, sale". Thanh lý và Tặng vẫn trừ khỏi lô vì hàng đã rời cửa hàng.
- **C. Trả kho:** trừ khỏi lô, theo hướng hàng LC ra trước.
- **D. Khớp History:** cùng CH gửi, CH nhận, SKU, size; gán vào lệnh gần nhất trước ngày chứng từ; không vượt `Qty_Lenh`.
- **E. Hàng đi đường:** chỉ dòng "Đã nhập kho CH" mới thành lô bán được.
- **F. Dòng bị loại:** 51 dòng CH gửi = CH nhận, 4 dòng lệnh trống TNSX (đều "Hết tồn"), và các dòng trùng hoàn toàn.

## 4. Ba file

| File | Một dòng là | Cột chính |
|---|---|---|
| `Master_MaHang_LC` | SKU × Size × Lần LC × CH nhận | `Ma_LC_ID`, `Lan_LC`, `Thang_LC`, `Ngay_Lenh`, `So_CH_Gui`, `Qty_Lenh`, `Qty_Nhan`, `Qty_DiDuong`, `Ngay_Nhan_Dau`, `Ngay_Nhan_Cuoi` + thuộc tính hàng |
| `Data_LuanChuyen` | Ngày lệnh × CH gửi × CH nhận × SKU × Size | `Lenh_ID`, `Ma_LC_ID`, `Qty_Lenh`, `Qty_DaXuat`, `Qty_DaNhap`, `Qty_DiDuong`, `Qty_ChuaThucHien`, `Qty_Huy`, `Han_Chot`, `So_Ngay_Thuc_Hien`, `Dung_Han`, `Trang_Thai`, `Ly_Do` |
| `Data_Ban_LC` | Ngày bán × CH × SKU × Size × Nội dung × Status × đợt LC | `Thang_Ban`, `Loai_Hang` (LC, Tồn sẵn), `Ma_LC_ID`, `Lan_LC`, `Thang_LC`, `Nhom_Thang_LC`, `Qty_Ban` |

`Data_Ban_LC` chỉ gồm bán trong tháng chạy của các cặp CH × SKU × Size có trong lệnh, từ tháng có lệnh đầu tiên của cặp đó.

## 5. Việc tiếp theo

Bạn hướng dẫn phần chỉ số và báo cáo Excel.

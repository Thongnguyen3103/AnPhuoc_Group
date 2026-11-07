# Báo cáo Luân chuyển hàng hóa (LCHH)

Dựng master data cho báo cáo quá trình luân chuyển và hiệu suất bán hàng luân chuyển. Quy tắc tính: xem [PLAN_Master_Data_LC.md](PLAN_Master_Data_LC.md).

## Cách chạy

```bash
python Build_Master_LC.py 2026-10
```

Không truyền tháng thì chương trình hỏi; Enter sẽ lấy `periods` trong `Config_LCHH.yaml`. Cuối lần chạy có mục đối soát, dòng `LECH` nghĩa là số liệu không khớp.

## Cấu trúc

```
03.Projects/Report_LCHH/
  Config_LCHH.yaml         cấu hình riêng (tháng chạy, hạn thực hiện, alias cửa hàng)
  Build_Master_LC.py       entrypoint
  PLAN_Master_Data_LC.md   quy tắc đã chốt
  Core/
    Load_Config.py         gộp Config_LCHH.yaml + đường dẫn dùng chung
    Common_Utils.py        đọc và chuẩn hóa dữ liệu
    Master_LC.py           MasterLCBuilder: dựng 3 file

04.Output/Report_LCHH/Master/
  Master_MaHang_LC.parquet   SKU × Size × Lần LC × Cửa hàng nhận
  Data_LuanChuyen.parquet    từng lệnh: số lượng, thời gian, tiến độ
  Data_Ban_LC.parquet        bán trong tháng chạy tại cửa hàng nhận, tách theo đợt luân chuyển
```

Nguồn dữ liệu (`07.Lenh_HHLC`, `08.History_LC`, `09.TraKho`, `A_Region`, `01.System_sales`) khai báo ở `00.Shared/Config_LCHH.yaml` và được đọc qua `Get_Paths`.

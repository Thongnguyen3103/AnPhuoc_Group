# 01.Python_Projects — Hướng dẫn sử dụng

## Cấu trúc

```
01.Python_Projects/
├── 00.Shared/                 SOURCE DÙNG CHUNG — sửa 1 nơi, mọi project dùng được
│   ├── Config_Paths.yaml         ← MỌI đường dẫn (kho dữ liệu Parquet, ổ mạng X:/Z:, 04.Output...)
│   ├── Get_Paths.py              ← đọc Config_Paths.yaml:  Get_Paths.ban_le, Get_Paths.thu_muc_ket_qua("...")
│   ├── Read_Write_Parquet.py     ← đọc bảng theo tên (connect_parquet_views / read_table), ghi Parquet năm/tháng
│   ├── Convert_Size.py           ← quy đổi size hệ thống → size thực tế
│   └── Parse_Date.py             ← parse ngày
│
├── 01.Data_Download/          Tải dữ liệu từ web QLKD / Report (Selenium)
│   ├── Open_Download_GUI.bat         mở giao diện
│   ├── Run_Download_Background.bat   chạy ngầm các mục đang tích (dùng để đặt lịch)
│   └── Edit_Download_Accounts.bat    sửa Config/Accounts.json
│
├── 02.Data_Processing/        01.Source → 02.Master / 03.Data_Parquest / CSV
│   ├── Run_All_Processing.py         menu xử lý từng nguồn
│   ├── Process_Revenue_To_Parquet.py doanh thu → 03.Data_Parquest/10.Revenue
│   ├── Export_Parquet_To_Csv.py      Parquet → 05.Data_Csv
│   ├── Sources/                      mỗi file = 1 nguồn dữ liệu (Process_Sales.py, Process_Inventory.py...)
│   └── README.md                     chi tiết từng file
│
├── 03.Projects/               Các báo cáo (chỉ ĐỌC dữ liệu đã xử lý, GHI vào 04.Output)
│   ├── Report_LCHH/              Build_Data_LCHH.bat, Export_Excel_LCHH.bat
│   ├── Report_Summary/           Run_Build_Summary.bat        (HTML tự chứa)
│   ├── Report_Transfer/          Open_Transfer_GUI.bat        (giao diện, cấu trúc OOP)
│   ├── Report_TopSeller/         Build_Best_Slow_Seller.bat   (giao diện Best/Slow Seller)
│   ├── Report_QLKD_Weekly/       Export_Weekly_QLKD.bat
│   └── Inventory_Control/        Run_Review_Web.bat           (web duyệt lệnh điều chuyển, env inventory_env)
│
├── 04.Output/                 OUTPUT DÙNG CHUNG — mỗi project 1 thư mục con cùng tên
│
└── 99.Archive/                Code cũ, repo git cũ, HocTap_PTIT (không dùng trong vận hành)
```

## Luồng dữ liệu

```
01.Data_Download ─► 00.Data_AnPhuoc_Group/01.Source ─► 02.Data_Processing ─► 02.Master, 03.Data_Parquest,
                                                                             05.Data_Csv
                                                                                    │
                                                                                    ▼
                                                                03.Projects/<Project> ─► 04.Output/<Project>
```

Thứ tự hằng tháng / hằng tuần thường là:
1. `01.Data_Download` tải file mới về `01.Source`.
2. `02.Data_Processing/Run_All_Processing.py` → chọn các nguồn vừa tải (lần đầu tháng: chạy **Master** trước).
3. Nếu cần: `Process_Revenue_To_Parquet.py` (cho Report_QLKD_Weekly), `Export_Parquet_To_Csv.py` (cho Power BI / Inventory_Control).
4. Chạy báo cáo cần dùng trong `03.Projects/`. Kết quả nằm ở `04.Output/<Project>/`.

## Đổi đường dẫn / chuyển máy

Chỉ sửa **`00.Shared/Config_Paths.yaml`** (thường chỉ dòng `data_root`). Kiểm tra nhanh:

```
cd D:\AnPhuocGroup\AnPhuoc_Data\01.Python_Projects
"%USERPROFILE%\anaconda3\python.exe" 00.Shared\Get_Paths.py
```

In ra từng đường dẫn kèm `[OK ]` / `[---]` (không tồn tại).

Các file `.bat` gọi Python qua `%USERPROFILE%\anaconda3\python.exe`, nên chạy được trên máy khác
có Anaconda cài mặc định mà không cần sửa.

## Đọc dữ liệu: chỉ Parquet

Không dùng file `.duckdb` nữa. Mọi project đọc thẳng file Parquet trong `02.Master` và `03.Data_Parquest`.
Muốn viết SQL theo tên bảng (như trước với DuckDB):

```python
from Read_Write_Parquet import connect_parquet_views, read_table
con = connect_parquet_views()                          # VIEW A_Region, System_sales, InventorySize, Revenue...
df = con.execute("SELECT * FROM A_Region").fetchdf()
df = read_table("D_Category")                           # hoặc đọc 1 bảng ra DataFrame
```

## Viết script mới

Thư mục `00.Shared` bắt đầu bằng số nên không import dạng package được — thêm nó vào `sys.path`
rồi import thẳng từng module. Ví dụ file trong `03.Projects/<Project>/`:

```python
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # 01.Python_Projects
sys.path.insert(0, os.path.join(ROOT, "00.Shared"))
import Get_Paths

df = pd.read_parquet(Get_Paths.ton_kho_size)
out_dir = Get_Paths.thu_muc_ket_qua("My_Project")     # -> 04.Output/My_Project (tự tạo)
```

Cần đường dẫn mới → thêm 1 dòng vào `Config_Paths.yaml`, **không** ghi cứng trong code.

## Quy ước đặt tên

- Thư mục và file code: tiếng Anh, viết hoa chữ cái đầu mỗi từ, dạng **`LàmGì_ỞĐâu`**
  (`Process_Inventory.py`, `Export_Excel_LCHH.py`, `Run_Build_Summary.py`).
- File `.bat` trùng tên với file `.py` mà nó chạy.
- Thư mục cấp 1 có số thứ tự (`00.` ... `99.`) để sắp xếp.
- Trong project: `Core/` xử lý, `Config/` cấu hình, `Output/` hoặc `Excel/` kết xuất,
  `Data/` dữ liệu chạy (trạng thái, toạ độ...), `Cache/` dữ liệu tạm.

## Git

Thư mục gốc là 1 repo git (`git log` để xem lịch sử). `04.Output`, `99.Archive`, dữ liệu
(`*.parquet`, `*.xlsx`, `*.csv`...), thư mục `Data/`, `Cache/` và file tài khoản **không** đưa vào git
(xem `.gitignore`). Bản sao lưu trước khi tái cấu trúc: `D:\AnPhuocGroup\AnPhuoc_Data\99_SaoLuu\`.

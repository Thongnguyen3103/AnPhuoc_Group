# 01.Python_Projects — Hướng dẫn sử dụng

## Cấu trúc

```
01.Python_Projects/
├── 00.Shared/          SOURCE DÙNG CHUNG — sửa 1 nơi, mọi project dùng được
│   ├── cau_hinh.yaml       ← MỌI đường dẫn (kho dữ liệu, DuckDB, ổ mạng X:/Z:, 04.Output...)
│   ├── Get_Paths.py        ← đọc cau_hinh.yaml:  Get_Paths.ban_le, Get_Paths.thu_muc_ket_qua("...")
│   ├── doc_ghi_parquet.py  ← đọc bảng Master, ghi Parquet phân mảnh năm/tháng
│   ├── quy_doi_size.py     ← quy đổi size hệ thống → size thực tế
│   └── ngay_thang.py       ← parse ngày
│
├── 01.Data_Download/        Tải dữ liệu từ web QLKD / Report (Selenium)
│   ├── CHAY_TOOL.bat         mở giao diện        CHAY_NGAM_TAT_CA.bat  chạy ngầm (đặt lịch)
│   └── DOI_MAT_KHAU.bat      sửa cau_hinh/tai_khoan.json
│
├── 02.Data_Processing/       01.Source → 02.Master / 03.Data_Parquest / DuckDB / CSV
│   ├── CHAY_XU_LY.bat        menu xử lý từng nguồn (chay_tat_ca.py)
│   ├── CHAY_DOANH_THU.bat    doanh thu → Report_AP.duckdb
│   ├── CHAY_XUAT_CSV.bat     Parquet → 05.Data_Csv
│   └── README.md          chi tiết từng file
│
├── 03.Projects/             Các báo cáo (chỉ ĐỌC dữ liệu đã xử lý, GHI vào 04.Output)
│   ├── Report_LCHH/          CHAY_TAO_DU_LIEU.bat, CHAY_XUAT_EXCEL.bat
│   ├── Report_Summary/       CHAY_CAP_NHAT.bat  (HTML tự chứa)
│   ├── Report_Transfer/    CHAY_BAO_CAO.bat   (giao diện)
│   ├── Report_TopSeller/     CHAY_BAO_CAO.bat   (giao diện Best/Slow Seller)
│   ├── Report_QLKD_Weekly/     CHAY_BAO_CAO_TUAN.bat
│   └── Inventory_Control/      CHAY_WEB.bat       (web duyệt lệnh điều chuyển, env inventory_env)
│
├── 04.Output/           OUTPUT DÙNG CHUNG — mỗi project 1 thư mục con cùng tên
│
└── 99.Archive/           Code cũ, repo git cũ, HocTap_PTIT (không dùng trong vận hành)
```

## Luồng dữ liệu

```
01.Data_Download ─► 00.Data_AnPhuoc_Group/01.Source ─► 02.Data_Processing ─► 02.Master, 03.Data_Parquest,
                                                                   04.Data_Db (DuckDB), 05.Data_Csv
                                                                          │
                                                                          ▼
                                                              03.Projects/<TenDuAn> ─► 04.Output/<TenDuAn>
```

Thứ tự hằng tháng / hằng tuần thường là:
1. `01.Data_Download` tải file mới về `01.Source`.
2. `02.Data_Processing/CHAY_XU_LY.bat` → chọn các nguồn vừa tải (lần đầu tháng: chạy **Master** trước).
3. Nếu cần: `CHAY_DOANH_THU.bat` (cho báo cáo tuần QLKD), `CHAY_XUAT_CSV.bat` (cho Power BI / Inventory_Control).
4. Chạy báo cáo cần dùng trong `03.Projects/`. Kết quả nằm ở `04.Output/<TenDuAn>/`.

## Đổi đường dẫn / chuyển máy

Chỉ sửa **`00.Shared/Config_Paths.yaml`** (thường chỉ dòng `goc_du_lieu`). Kiểm tra nhanh:

```
cd D:\AnPhuocGroup\AnPhuoc_Data\01.Python_Projects
"%USERPROFILE%\anaconda3\python.exe" -m Get_Paths
```

In ra từng đường dẫn kèm `[OK ]` / `[---]` (không tồn tại).

Các file `.bat` gọi Python qua `%USERPROFILE%\anaconda3\python.exe`, nên chạy được trên máy khác
có Anaconda cài mặc định mà không cần sửa.

## Viết script mới

Đặt script ở bất kỳ đâu trong `01.Python_Projects`, thêm 1 dòng trước khi import `00.Shared`
(số `dirname` = số cấp thư mục từ file lên tới `01.Python_Projects`), ví dụ file trong `03.Projects/TenDuAn/`:

```python
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import Get_Paths

df = pd.read_parquet(Get_Paths.ton_kho_size)
out_dir = Get_Paths.thu_muc_ket_qua("TenDuAn")     # -> 04.Output/TenDuAn (tự tạo)
```

Cần đường dẫn mới → thêm 1 dòng vào `cau_hinh.yaml`, **không** ghi cứng trong code.

## Quy ước đặt tên

- File code: tiếng Việt không dấu, chữ thường, gạch dưới (`ton_kho.py`).
- File chạy bằng double-click: `CHAY_....bat` (chữ HOA).
- Thư mục có số thứ tự để sắp xếp; riêng `00.Shared` không có số vì Python cần import được.
- Dữ liệu chạy của từng project (trạng thái, cache, log) nằm trong `du_lieu/` hoặc `du_lieu_tam/` của project đó.

## Git

Thư mục gốc là 1 repo git (`git log` để xem lịch sử). `04.Output`, `99.Archive`, dữ liệu
(`*.parquet`, `*.xlsx`, `*.csv`...) và file tài khoản **không** đưa vào git (xem `.gitignore`).
Bản sao lưu trước khi tái cấu trúc: `D:\AnPhuocGroup\AnPhuoc_Data\99_SaoLuu\`.

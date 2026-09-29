# 01.Python_Projects — Hướng dẫn sử dụng

## Cấu trúc

```
01.Python_Projects/
├── dung_chung/          SOURCE DÙNG CHUNG — sửa 1 nơi, mọi project dùng được
│   ├── cau_hinh.yaml       ← MỌI đường dẫn (kho dữ liệu, DuckDB, ổ mạng X:/Z:, 04_KetQua...)
│   ├── duong_dan.py        ← đọc cau_hinh.yaml:  duong_dan.ban_le, duong_dan.thu_muc_ket_qua("...")
│   ├── doc_ghi_parquet.py  ← đọc bảng Master, ghi Parquet phân mảnh năm/tháng
│   ├── quy_doi_size.py     ← quy đổi size hệ thống → size thực tế
│   └── ngay_thang.py       ← parse ngày
│
├── 01_TaiDuLieu/        Tải dữ liệu từ web QLKD / Report (Selenium)
│   ├── CHAY_TOOL.bat         mở giao diện        CHAY_NGAM_TAT_CA.bat  chạy ngầm (đặt lịch)
│   └── DOI_MAT_KHAU.bat      sửa cau_hinh/tai_khoan.json
│
├── 02_XuLyDuLieu/       01.Source → 02.Master / 03.Data_Parquest / DuckDB / CSV
│   ├── CHAY_XU_LY.bat        menu xử lý từng nguồn (chay_tat_ca.py)
│   ├── CHAY_DOANH_THU.bat    doanh thu → Report_AP.duckdb
│   ├── CHAY_XUAT_CSV.bat     Parquet → 05.Data_Csv
│   └── HUONG_DAN.md          chi tiết từng file
│
├── 03_DuAn/             Các báo cáo (chỉ ĐỌC dữ liệu đã xử lý, GHI vào 04_KetQua)
│   ├── BaoCao_LCHH/          CHAY_TAO_DU_LIEU.bat, CHAY_XUAT_EXCEL.bat
│   ├── BaoCao_TongHop/       CHAY_CAP_NHAT.bat  (HTML tự chứa)
│   ├── BaoCao_DieuChuyen/    CHAY_BAO_CAO.bat   (giao diện)
│   ├── BaoCao_TopSeller/     CHAY_BAO_CAO.bat   (giao diện Best/Slow Seller)
│   ├── BaoCao_QLKD_Tuan/     CHAY_BAO_CAO_TUAN.bat
│   └── KiemSoat_TonKho/      CHAY_WEB.bat       (web duyệt lệnh điều chuyển, env inventory_env)
│
├── 04_KetQua/           OUTPUT DÙNG CHUNG — mỗi project 1 thư mục con cùng tên
│
└── 99_LuuTru/           Code cũ, repo git cũ, HocTap_PTIT (không dùng trong vận hành)
```

## Luồng dữ liệu

```
01_TaiDuLieu ─► 00.Data_AnPhuoc_Group/01.Source ─► 02_XuLyDuLieu ─► 02.Master, 03.Data_Parquest,
                                                                   04.Data_Db (DuckDB), 05.Data_Csv
                                                                          │
                                                                          ▼
                                                              03_DuAn/<TenDuAn> ─► 04_KetQua/<TenDuAn>
```

Thứ tự hằng tháng / hằng tuần thường là:
1. `01_TaiDuLieu` tải file mới về `01.Source`.
2. `02_XuLyDuLieu/CHAY_XU_LY.bat` → chọn các nguồn vừa tải (lần đầu tháng: chạy **Master** trước).
3. Nếu cần: `CHAY_DOANH_THU.bat` (cho báo cáo tuần QLKD), `CHAY_XUAT_CSV.bat` (cho Power BI / KiemSoat_TonKho).
4. Chạy báo cáo cần dùng trong `03_DuAn/`. Kết quả nằm ở `04_KetQua/<TenDuAn>/`.

## Đổi đường dẫn / chuyển máy

Chỉ sửa **`dung_chung/cau_hinh.yaml`** (thường chỉ dòng `goc_du_lieu`). Kiểm tra nhanh:

```
cd D:\AnPhuocGroup\AnPhuoc_Data\01.Python_Projects
"%USERPROFILE%\anaconda3\python.exe" -m dung_chung.duong_dan
```

In ra từng đường dẫn kèm `[OK ]` / `[---]` (không tồn tại).

Các file `.bat` gọi Python qua `%USERPROFILE%\anaconda3\python.exe`, nên chạy được trên máy khác
có Anaconda cài mặc định mà không cần sửa.

## Viết script mới

Đặt script ở bất kỳ đâu trong `01.Python_Projects`, thêm 1 dòng trước khi import `dung_chung`
(số `dirname` = số cấp thư mục từ file lên tới `01.Python_Projects`), ví dụ file trong `03_DuAn/TenDuAn/`:

```python
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from dung_chung import duong_dan

df = pd.read_parquet(duong_dan.ton_kho_size)
out_dir = duong_dan.thu_muc_ket_qua("TenDuAn")     # -> 04_KetQua/TenDuAn (tự tạo)
```

Cần đường dẫn mới → thêm 1 dòng vào `cau_hinh.yaml`, **không** ghi cứng trong code.

## Quy ước đặt tên

- File code: tiếng Việt không dấu, chữ thường, gạch dưới (`ton_kho.py`).
- File chạy bằng double-click: `CHAY_....bat` (chữ HOA).
- Thư mục có số thứ tự để sắp xếp; riêng `dung_chung` không có số vì Python cần import được.
- Dữ liệu chạy của từng project (trạng thái, cache, log) nằm trong `du_lieu/` hoặc `du_lieu_tam/` của project đó.

## Git

Thư mục gốc là 1 repo git (`git log` để xem lịch sử). `04_KetQua`, `99_LuuTru`, dữ liệu
(`*.parquet`, `*.xlsx`, `*.csv`...) và file tài khoản **không** đưa vào git (xem `.gitignore`).
Bản sao lưu trước khi tái cấu trúc: `D:\AnPhuocGroup\AnPhuoc_Data\99_SaoLuu\`.

# Report_Summary_App — Kiến trúc Web app nội bộ Báo cáo Tổng hợp An Phước

Web app có đăng nhập, chạy trên máy chủ nội bộ, phục vụ Báo cáo Tổng hợp (Tồn & Số bán)
cho **20–30 người dùng**. Giao diện 10 sheet nằm trong `Template/` của app;
dữ liệu lấy từ máy chủ qua API thay vì nhúng trong file HTML.

## 1. Kiến trúc hệ thống

```
 ┌──────────────── Máy chạy build (hiện tại: DESKTOP-LMHVA0L) ────────────────┐
 │  00.Data_AnPhuoc_Group/*.parquet                                           │
 │        │                                                                   │
 │  Report_Summary_App/Core/Run_Build_Summary.py  (pipeline không đổi luồng)  │
 │        │  Stage 5 Render ──► BaoCao_TongHop.html   (file offline như cũ)    │
 │        └─ Export_App_Snapshot ──► 04.Output/Report_Summary/app_snapshot/   │
 │                 payload.json.gz · sku_track.json.gz · meta.json (ghi cuối) │
 └──────────────────────────────────────┬─────────────────────────────────────┘
                                        │ thư mục dùng chung / cùng máy
 ┌──────────────── Report_Summary_App (FastAPI + Uvicorn) ────────────────────┐
 │  SnapshotWatcher (thread, 60s) ─ thấy meta.json mới ─► import snapshot     │
 │                                                                            │
 │  SQLite (WAL)  data/app.db                                                 │
 │    users · sessions · snapshots · sku_track · audit_log · schema_migrations│
 │  data/snapshots/<sha>.json.gz   (payload báo cáo, giữ N bản gần nhất)      │
 │                                                                            │
 │  Routers:  /api/auth  /api/report  /api/skus  /api/admin  /api/health      │
 │  Pages:    /login  /  (báo cáo)  /account  /admin                          │
 │  Middleware: security headers · Origin check (CSRF) · GZip                 │
 └──────────────────────────────────────┬─────────────────────────────────────┘
                                        │ HTTP (LAN/wifi công ty)
                           Trình duyệt (PC / điện thoại)
        Report_Engine.js tải /api/report/payload (gzip) ─► giải nén tại client
```

**Vì sao thiết kế như vậy (cho 20–30 người):**
- **Tái dùng engine 10 sheet đã kiểm chứng.** Engine chỉ thêm 1 nhánh: khi có
  `window.REPORT_PAYLOAD_URL` thì `fetch` dữ liệu thay vì đọc Base64 nhúng.
  File HTML offline cũ vẫn chạy như trước.
- **Payload tính sẵn, phục vụ tĩnh.** Máy chủ không tính toán lúc người dùng xem:
  một file gzip ~5 MB, có `ETag`, nên lần mở sau trình duyệt nhận `304` (gần như tức thì).
  30 người xem cùng lúc chỉ là 30 lần đọc file.
- **API truy vấn thật cho những thứ cần tra nhanh** (`/api/skus`): tra Mã hàng từ
  bảng `sku_track` trong SQLite. Đây là điểm mở rộng: dần chuyển từng sheet sang API
  khi cần (VD phân quyền theo vùng/cửa hàng).
- **SQLite + SQL thuần qua lớp repository.** Đủ cho 30 người (WAL, đọc song song).
  Khi cần nhiều tiến trình/máy: thay `app/db.py` sang PostgreSQL; câu SQL là chuẩn ANSI.
- **Không phụ thuộc internet / CDN.** Mọi thư viện phục vụ từ máy chủ.

## 2. Cấu trúc file

```
Report_Summary_App/
├── ARCHITECTURE.md          # tài liệu này
├── README.md                # cài đặt, vận hành, triển khai
├── requirements.txt
├── .env.example             # cấu hình mẫu (copy thành .env)
├── run_server.py            # chạy server (uvicorn)
├── manage.py                # CLI: init-db, create-user, reset-password, list-users, import-snapshot
├── app/
│   ├── main.py              # create_app(): routers, middleware, pages, watcher
│   ├── config.py            # Settings từ biến môi trường / .env
│   ├── db.py                # kết nối SQLite + chạy migration
│   ├── migrations/001_init.sql
│   ├── security.py          # băm mật khẩu PBKDF2, token phiên, giới hạn đăng nhập sai
│   ├── deps.py              # current_user / require_admin / audit
│   ├── repositories/        # SQL thuần theo bảng: users, sessions, snapshots, skus, audit
│   ├── services/snapshots.py# import / kích hoạt / dọn snapshot + watcher
│   ├── routers/             # auth, report, skus, admin, health, pages
│   └── web/                 # login, account, admin (HTML/JS/CSS) + app_shell.js
└── tests/                   # pytest: auth, phân quyền, report, skus, admin, snapshot
```

Nguồn giao diện báo cáo nằm ngay trong app: `Report_Summary_App/Template/`.

## 3. Database schema (SQLite)

| Bảng | Cột chính | Ghi chú |
|---|---|---|
| `users` | id, username (unique, không phân biệt hoa thường), full_name, password_hash, role (`admin`/`viewer`), is_active, must_change_password, created_at, updated_at, last_login_at | Không xóa user — khóa (`is_active=0`) để giữ lịch sử |
| `sessions` | token_hash (PK, SHA-256 của token), user_id → users, created_at, expires_at, last_seen_at, ip, user_agent | Token gốc chỉ nằm trong cookie HttpOnly |
| `snapshots` | id, sha256 (unique), ref_label, ref_year, ref_month, built_at, file_name, size_bytes, sku_count, imported_at, imported_by → users, is_active | Đúng 1 bản active (unique index có điều kiện) |
| `sku_track` | (snapshot_id, mh, op) PK, brand, cat_group, group_report, item, status, price, prod_ym, age_months, ton_ch, ton_kho, ban_1m, ban_3m, ban_6m, ban_ytd, ban_all, months_since_sale | Xóa theo snapshot (ON DELETE CASCADE) |
| `audit_log` | id, at, user_id, username, action, detail, ip | login / login_failed / logout / view_report / user.* / snapshot.* |
| `schema_migrations` | version, applied_at | Migration đánh số `NNN_*.sql` |

## 4. API endpoints

Tất cả trả JSON. Phiên đăng nhập bằng cookie `ap_session` (HttpOnly, SameSite=Strict).
Yêu cầu thay đổi dữ liệu (POST/PATCH) phải là JSON và có `Origin` khớp máy chủ.

| Method | Path | Quyền | Mô tả |
|---|---|---|---|
| POST | `/api/auth/login` | — | `{username, password}` → đặt cookie; sai 5 lần/15 phút → 429 |
| POST | `/api/auth/logout` | user | Hủy phiên |
| GET | `/api/auth/me` | user | Thông tin người đang đăng nhập |
| POST | `/api/auth/change-password` | user | `{current_password, new_password}` (≥ 8 ký tự), hủy các phiên khác |
| GET | `/api/report/meta` | user | Snapshot đang dùng (kỳ, thời điểm build, dung lượng) |
| GET | `/api/report/payload` | user | Payload gzip của báo cáo, `ETag` + `304` |
| GET | `/api/skus` | user | Tra Mã hàng: `q, brand, cat_group, group_report, item, status, sort, order, limit (≤500), offset` |
| GET | `/api/skus/facets` | user | Danh sách giá trị lọc (brand, nhóm hàng, nhóm BC, tên hàng) |
| GET | `/api/skus/{ma_hang}` | user | Mọi lô của 1 mã hàng |
| GET | `/api/admin/users` | admin | Danh sách user |
| POST | `/api/admin/users` | admin | Tạo user → trả **mật khẩu tạm 1 lần** |
| PATCH | `/api/admin/users/{id}` | admin | Đổi tên / vai trò / khóa–mở |
| POST | `/api/admin/users/{id}/reset-password` | admin | Mật khẩu tạm mới, hủy mọi phiên của user |
| GET | `/api/admin/snapshots` | admin | Lịch sử snapshot |
| POST | `/api/admin/snapshots/import` | admin | Nạp ngay bản build mới nhất |
| POST | `/api/admin/snapshots/{id}/activate` | admin | Quay về / chuyển sang 1 snapshot |
| GET | `/api/admin/audit` | admin | Nhật ký hoạt động (mới nhất trước) |
| GET | `/api/health` | — | Trạng thái DB + snapshot (cho giám sát) |

## 5. Kiến trúc UI

| Trang | Nội dung |
|---|---|
| `/login` | Form đăng nhập (thương hiệu An Phước: navy `#1a365d`, vàng `#c5a059`) |
| `/` | Báo cáo 10 sheet (template gốc) + `app_shell.js` gắn chip người dùng vào header: tên · Đổi mật khẩu · Quản trị · Đăng xuất |
| `/account` | Đổi mật khẩu (bắt buộc ở lần đăng nhập đầu) |
| `/admin` | 3 tab: Người dùng · Dữ liệu (snapshot) · Nhật ký |

Trang chưa đăng nhập → chuyển `/login`; phiên hết hạn khi đang xem → API trả 401 → chuyển `/login`.

## 6. Bảo mật

- Mật khẩu: PBKDF2-SHA256, 390.000 vòng, salt riêng; so sánh thời gian hằng.
- Phiên: token ngẫu nhiên 256-bit, DB chỉ lưu SHA-256; hết hạn sau `SESSION_HOURS` (trượt theo hoạt động).
- CSRF: cookie SameSite=Strict + bắt buộc JSON + kiểm `Origin`.
- Header: CSP (chỉ `'self'`), `X-Frame-Options: DENY`, `X-Content-Type-Options`, `Referrer-Policy`.
- Giới hạn đăng nhập sai theo (IP, username). Mọi thao tác quản trị ghi `audit_log`.
- Chạy HTTP trong LAN; khi có chứng chỉ nội bộ đặt `COOKIE_SECURE=true` sau reverse proxy HTTPS.

## 7. Lộ trình mở rộng

1. Phân quyền theo vùng/cửa hàng: thêm bảng `user_scopes`, chuyển sheet Cửa hàng sang API có lọc theo scope.
2. PostgreSQL + nhiều worker khi > 100 người dùng đồng thời.
3. SSO với Active Directory `anphuoc.local` (LDAP) thay mật khẩu riêng.
4. Lên lịch build tự động (Task Scheduler) → watcher tự nạp, không thao tác tay.

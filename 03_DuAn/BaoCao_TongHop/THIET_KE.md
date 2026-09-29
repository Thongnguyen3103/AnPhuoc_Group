# THIẾT KẾ HỆ THỐNG — BÁO CÁO TỔNG HỢP (TỒN & SỐ BÁN) AN PHƯỚC



> ⚠️ **TÀI LIỆU LỊCH SỬ (bản thiết kế mục tiêu, 09/09/2026).** Hệ thống đã tiến hoá nhiều so với bản này
> (cấu trúc `ov`, tên/nội dung 8 sheet, "Kỳ xem", SKU = MaHang+Operation…). **Bản đúng hiện tại là `ARCHITECTURE.md`.**
> Giữ file này để tham khảo ý tưởng gốc (phân khúc §6, phân tích chuyên sâu §13–14 chưa làm hết).

> Ngày: 09/09/2026.



---



## 0. Bối cảnh & 3 ràng buộc



| Ràng buộc thực tế | Hệ quả thiết kế |

|:---|:---|

| File báo cáo **gửi cho người khác xem**, họ không cài gì | 1 file `.html` tự chứa 100%, không CDN, không server, mở bằng double-click |

| Chỉ **chủ dữ liệu** cập nhật số liệu | Dữ liệu gốc không rời máy chủ dữ liệu; chỉ **số liệu đã tổng hợp** được nhúng |

| File xem để trên **Google Drive** | Kích thước < 15 MB để tải nhanh; giữ **cùng 1 link** qua các lần cập nhật bằng "Quản lý phiên bản" của Drive |



**Nguyên tắc cốt lõi:** tách hẳn **"vỏ" (shell)** — template + CSS + engine JS viết tay một lần — khỏi

**"ruột" (payload)** — khối dữ liệu tổng hợp đã nén, sinh lại mỗi lần build. File 278 MB hiện nay

là do nhồi cả dữ liệu thô + Plotly (2 lần) + JSON không nén vào cùng một tài liệu.



---



## 1. Kiến trúc tổng thể



Đây là **trình sinh báo cáo tĩnh** (static report generator), **không phải** web app:



```

D:\00.Data_AnPhuoc_Group   (chỉ trên máy chủ dữ liệu — parquet gốc ~4.7M dòng)

        │

        ▼   python backend/Update_Baocao_TongHop.py        (1 lệnh duy nhất)

┌────────────────────────────────────────────────────────────┐

│ [1] refresh_cache  → database/cache_sales.parquet           │

│ [2] aggregate_ton  → dict tổng hợp Tồn  (đã GROUP BY)       │

│ [3] aggregate_ban  → dict tổng hợp Bán  (overview + top-N)  │

│ [4] validate       → đối chiếu tổng số với nguồn            │

│ [5] render         → gzip(JSON) → base64 → chèn vào shell   │

└────────────────────────────────────────────────────────────┘

        │

        ▼

dist/BaoCao_TongHop.html   (~8–12 MB, tự chứa, offline 100%)

        │

        ▼   chủ dữ liệu upload (thay phiên bản, giữ nguyên link)

Google Drive ──chia sẻ link──► Người nhận: tải về → mở bằng Chrome

        (giải nén trong Web Worker → Array.filter → Plotly render)

```



Không có server lúc người dùng xem. Mọi thao tác lọc do **engine JavaScript** chạy trong trình

duyệt (`Array.filter` trên payload đã nhúng).



---



## 2. Cấu trúc thư mục



```

BaoCao_TongHop/

├── backend/

│   ├── Update_Baocao_TongHop.py                 # ★ orchestrator: refresh → aggregate → validate → render

│   ├── stages/

│   │   ├── refresh_cache.py     # đọc D:\00.Data_AnPhuoc_Group → cache_sales.parquet

│   │   ├── aggregate_ton.py     # parquet → payload Tồn (columnar + dict encoding)

│   │   ├── aggregate_ban.py     # parquet → payload Bán (overview + top-N sản phẩm)

│   │   └── validate.py          # so tổng Qty payload ↔ nguồn; fail nếu lệch > ngưỡng

│   └── render.py                # gzip+base64 payload, chèn vào shell/template.html

├── shell/                       # "VỎ" — viết tay, KHÔNG phải output build

│   ├── template.html            # khung 2 tab + 1 placeholder <script id="payload">

│   ├── style.css                # 1 design system, scope sẵn #tab-ton / #tab-ban

│   ├── engine.js                # 1 engine: renderTon() + renderBan(); KHÔNG shim document

│   ├── segments.js              # khai báo phân khúc báo cáo (business sửa được)

│   └── vendor/

│       └── plotly-basic.min.js  # ~1 MB (bar/pie/scatter) thay full 3.6 MB

├── database/

│   └── cache_sales.parquet      # trung gian — .gitignore

├── dist/

│   └── BaoCao_TongHop.html      # ★ FILE DUY NHẤT upload lên Drive

├── DESIGN.md                    # tài liệu này

└── OPERATIONS.md                # quy trình vận hành

```



**Xóa khỏi dự án hiện tại:**

`build_report.py` (ghép file bằng regex), `build_standalone_html.py`,

`frontend/static/js/app.js` + `frontend/static/css/style.css` (mã chết, mô tả API không có thật),

`frontend/static/ton_report_template.html` (đang là output build cũ bị nhiễm bẩn — dòng 13

`,#app-ban{...}` selector cụt, dòng 1626–1627 lặp listener), `tom-select.*` (vendor nhưng

không nạp), `server.py` (chỉ rebuild Bán từ cache cũ, không refresh dữ liệu sống).



---



## 3. Thiết kế file HTML xuất ra



```html

<!doctype html><html lang="vi"><head>

  <meta charset="utf-8">

  <style> /* shell/style.css nhúng thẳng, ~30 KB — 1 design system */ </style>

</head><body>



  <div id="tabbar">… Tồn | Bán …</div>



  <div id="tab-ton">

    <div class="seg-bar">…thanh phân khúc…</div>

    <div class="filter-bar">…bộ lọc tự do…</div>

    <div class="kpi-row">…8 thẻ…</div>

    <div class="views">…biểu đồ / bảng…</div>

  </div>

  <div id="tab-ban" hidden> …cấu trúc tương tự… </div>



  <script id="payload" type="application/octet-stream">BASE64_GZIP_JSON</script>

  <script> /* plotly-basic.min.js — nhúng 1 LẦN */ </script>

  <script> /* shell/engine.js + shell/segments.js */ </script>

</body></html>

```



### Ngân sách kích thước



| Thành phần | Mục tiêu |

|:---|---:|

| Shell HTML + CSS | ~30 KB |

| Plotly basic (bar/pie/scatter) | ~1 MB |

| engine.js + segments.js | ~45 KB |

| Payload Tồn — tổng hợp, columnar, gzip+base64 | 3–5 MB |

| Payload Bán — overview + top 2.000 mã hàng | 3–6 MB |

| **Tổng file** | **~8–12 MB** |



### Chiến lược ép kích thước (278 MB → ~10 MB)



1. **Chỉ nhúng số liệu đã tổng hợp**, không dòng thô. Overview `GROUP BY` theo mọi chiều lọc;

   bảng chi tiết sản phẩm giữ **top 2.000 mã hàng** theo tổng Qty, phần đuôi gom "Khác".

2. **Columnar** thay array-of-arrays: mỗi cột là 1 mảng đồng nhất (`years:[…], qty:[…]`) →

   gzip nén tốt hơn nhiều so với `[[2026,7,"AB",…],…]`.

3. **Dictionary encoding** mọi chuỗi + **làm tròn số**.

4. **gzip + base64, giải nén trong trình duyệt** bằng `DecompressionStream('gzip')`.

   (Code này đã có sẵn trong `standalone_engine.js` nhưng là mã chết — payload không bao giờ

   chứa `prod_gz`. Chỉ cần nối lại đúng.)

5. **Plotly basic bundle** (~1 MB) thay full (~3.6 MB), nhúng **1 lần** (hiện nhúng 2 lần).

6. **Parse payload trong Web Worker** để tab không treo khi mở.



---



## 4. Hai báo cáo trong một file — làm đúng cách



Bỏ cách "ghép 2 HTML rời bằng regex + `document` giả" của `build_report.py`.



- **1 file `style.css`**, selector đặt tiền tố **ngay khi viết**: `#tab-ton .card`, `#tab-ban .card`.

  Không cần hàm `scope_css` bằng regex (hàm hiện tại còn không xử lý `@media`).

- **1 file `engine.js`** export `renderTon(data.ton)` và `renderBan(data.ban)`.

  `switchTab()` chỉ bật/tắt thuộc tính `hidden` và gọi render lần đầu (lazy).

- **Không** có shim `var document = {…}` → Plotly, sự kiện, `createElementNS` chạy bình thường.

- Hai payload dùng **chung bảng `dict`** → tiết kiệm dung lượng.



Nếu về sau Tồn và Bán khác nhau quá nhiều → tách `BaoCao_Ton.html` / `BaoCao_SoBan.html` +

1 trang `index.html` chọn báo cáo. Vẫn sạch hơn regex-merge.



---



## 5. Payload — cấu trúc dữ liệu nhúng



```jsonc

{

  "v": 3,

  "built": "2026-09-08T14:25",

  "ref": { "year": 2026, "month": 7, "label": "T7/2026" },   // TÍNH ĐỘNG từ tháng mới nhất

  "dict": ["...", "..."],                                     // bảng chuỗi dùng chung



  "ton": {

    "cols": ["y","m","st","rg","wh","br","gr","status","pt","pg","form","style","attr","cn","cg","qty"],

    "data": [ [/* cột y */], [/* cột m */], ... ]              // COLUMNAR: mảng song song

  },



  "ban": {

    "ov":   { "cols": [...], "data": [...] },                 // overview đã GROUP BY

    "prod": { "cols": [...], "data": [...] },                 // top 2.000 mã hàng

    "meta": { "<mahang_idx>": [op, item, cg, ct, form, style, attr, price, lc_label, lc_stcount] }

  }

}

```



**Bắt buộc:** thêm cột `Product_group` (`pg`) vào GROUP BY của cả `ton` và `ban.ov`

(hiện `build_standalone_html.py` không có) — cần cho phân khúc "Golf", "Phụ kiện da",

"Quần áo còn lại". Cardinality thấp (23 giá trị) và tương quan mạnh với `Group_Report` →

số tổ hợp tăng không đáng kể.



### Chiều & trường phái sinh bổ sung cho phân tích chuyên sâu (§13–§14)



| Trường | Nguồn | Dùng cho |

|:---|:---|:---|

| `pg` — Product_group | có sẵn, thêm vào GROUP BY | phân khúc + lát cắt tồn |

| `price_type` — *Loại giá bán* (phái sinh) | `SalesSource='Contract' ⇒ 'Hợp đồng'`, ngược lại lấy `Status` (Nguyên giá / Sale / Thanh lý) | §13.2 |

| `region_kind` — *Khu vực CH* vs *Kho* (phái sinh, chỉ Tồn) | phân loại giá trị cột `Region` của InventorySize (xem §14.1) | §14.1–14.2 |

| `size_profile` — *khóa bộ cặp size* (phái sinh, chỉ Tồn) | tra theo `Report_item_name` từ tập size đã chuẩn hóa | §14.3 |

| `dist_y`, `dist_m` — *kỳ phân phối* (phái sinh, chỉ Tồn) | parse `Dist_plan` (`T09.2024` / `T9.2023`…), giá trị chữ → `null` | §14.5 |

| `sold_30/60/90` — *cờ đã bán trong N ngày* (chỉ Tồn, cấp mã hàng) | từ dữ liệu bán theo mã (cửa sổ lăn, không phải theo tháng lịch) | §14.5 |

| `active_stores` — bảng phụ `[year][month][region] → số CH có Qty>0` | tính khi aggregate `ban` | §13 (mẫu số TB/CH) |



Bảng phụ `ban.active_stores` rất nhỏ (3 năm × 12 tháng × 6 khu vực) — nhúng nguyên, không nén riêng.



---



## 6. Phân khúc báo cáo (Segments)



### 6.1. Khái niệm



Một **thanh chọn phân khúc** ở đầu mỗi tab, **nằm trên** bộ lọc tự do. Chọn 1 phân khúc = áp

một **bộ lọc nền khóa sẵn**; KPI/biểu đồ/bảng tính lại trong phạm vi đó. Bộ lọc tự do

(Khu vực, Cửa hàng, Tháng…) vẫn hoạt động **chồng lên** phân khúc đang chọn.



```

┌─ PHÂN KHÚC:  [Toàn bộ] [●Nhóm chủ đạo] [Golf] [Phụ kiện da] [Quần áo còn lại] [Anamai·Bonjour]

├─ Bộ lọc tự do:  Năm ▾  Tháng ▾  Khu vực ▾  Cửa hàng ▾ …

├─ 8 thẻ KPI  (đã tính theo phân khúc + bộ lọc)

└─ Biểu đồ / bảng   (tiêu đề tự thêm hậu tố: "… — Nhóm chủ đạo")

```



Mỗi tab (Tồn / Bán) có thanh phân khúc riêng, trạng thái độc lập. Có chip

**"Đang xem: Nhóm chủ đạo ✕"** cạnh tiêu đề để quay về "Toàn bộ".



### 6.2. Định nghĩa 5 phân khúc (theo giá trị THẬT trong `cache_sales.parquet`)



| # | Phân khúc | Điều kiện | Qty toàn kỳ |

|:--|:---|:---|---:|

| 1 | **Nhóm chủ đạo** | `Group_Report ∈ {Chemise, Áo Thun, Quần Tây}` | ~3.661.000 |

| 2 | **Golf** | `Product_group = 'Golf'`  *(≡ `Report_item_name` chứa "golf" — trùng khớp tuyệt đối: 114.845 qty / 241 mã hàng, lệch 0)* | ~114.845 |

| 3 | **Phụ kiện da** | `Product_group = 'Phụ Kiện Da'` | ~155.600 |

| 4 | **Quần áo còn lại** | `Product_group ∈ {Áo, Quần, Váy, Vest Bộ, Fashion, Đồ Mặc Nhà, Bộ}` **VÀ** không thuộc #1/#2/#3 | phần dư |

| 5 | **Anamai · Bonjour** | `Brand ∈ {Hiệu Anamai, Hiệu Bonjour}` | ~381.000 |



### 6.3. Hai quy tắc



**a) Loại Anamai/Bonjour khỏi phân khúc #1–#4** (`brand_exclude`) — để "xem riêng" đúng nghĩa;

Anamai/Bonjour chỉ hiện khi chọn phân khúc #5.



**b) Ưu tiên "first-match-wins"** để #4 đúng nghĩa "còn lại":



```

Anamai/Bonjour  → cắt theo Brand, độc lập (nút riêng)

Nhóm sản phẩm, xét theo thứ tự:  #1 chủ đạo → #2 Golf → #3 phụ kiện da → #4 còn lại

```



### 6.5. Đã chốt



- **Loại Anamai/Bonjour khỏi #1–#4: CÓ** (`brand_exclude` như trong `segments.js`).

- **Đồ lót / áo ngực / quần lót / seamless:** phần lớn thuộc hai hiệu **Anamai / Bonjour**

  (là hai nhãn đồ lót của An Phước) → đã nằm trọn ở phân khúc #5, và bị `brand_exclude`

  loại khỏi #1–#4. Phần đồ lót mang hiệu "Hiệu An Phước"/khác còn sót lại **không thuộc**

  5 phân khúc → gộp vào phân khúc phụ **"Khác"** (phần dư của "Toàn bộ"), không cần cấu hình thêm.

- 5 phân khúc + "Toàn bộ" + "Khác" ⇒ phủ 100%.



### 6.4. Khai báo — `shell/segments.js` (sửa được, không đụng engine)



```js

const SEGMENTS = [

  { id:'all',  label:'Toàn bộ', base:{} },



  { id:'core', label:'Nhóm chủ đạo — Chemise · Áo Thun · Quần Tây', default:true,

    base:{ group_report:['Chemise','Áo Thun','Quần Tây'],

           brand_exclude:['Hiệu Anamai','Hiệu Bonjour'] } },



  { id:'golf', label:'Golf',

    base:{ product_group:['Golf'],                 // ≡ report_item_name_contains:'golf'

           brand_exclude:['Hiệu Anamai','Hiệu Bonjour'] } },



  { id:'leather', label:'Phụ kiện da',

    base:{ product_group:['Phụ Kiện Da'],

           brand_exclude:['Hiệu Anamai','Hiệu Bonjour'] } },



  { id:'apparel_rest', label:'Quần áo còn lại',

    base:{ product_group:['Áo','Quần','Váy','Vest Bộ','Fashion','Đồ Mặc Nhà','Bộ'],

           group_report_exclude:['Chemise','Áo Thun','Quần Tây'],

           product_group_exclude:['Golf','Phụ Kiện Da'],

           brand_exclude:['Hiệu Anamai','Hiệu Bonjour'] } },



  { id:'anamai_bonjour', label:'Anamai · Bonjour',

    base:{ brand:['Hiệu Anamai','Hiệu Bonjour'] } },

];

```



Engine chỉ cần `applySegment(rows, seg.base)` chạy **trước** `filterRows(rows, freeFilters)` —

cùng cơ chế `Array.filter`, hỗ trợ `*_exclude` và (tùy chọn) `report_item_name_contains`.



---



## 7. `Update_Baocao_TongHop.py` — các stage



| Stage | Nhiệm vụ | Chống lỗi |

|:---|:---|:---|

| `refresh_cache` | DuckDB đọc System_sales + Contract_sales (N năm gần nhất, tính từ `MAX(Year)`) `LEFT JOIN` F_DataTracking theo `MaHang=item_code AND Operation=Operation` | Log số dòng join hụt + danh sách `MaHang` không khớp |

| `aggregate_ban` | overview GROUP BY **+ `Product_group` + `price_type`** (§5); giữ `st`, `br`, `reg`, `nr` để phục vụ §13; sinh bảng phụ `active_stores`; product giữ top 2.000 mã + "Khác" | — |

| `aggregate_ton` | đọc InventorySize + F_DataTracking + HHLC; phân loại `region_kind` (§14.1); tra `size_profile` (§14.3); chuẩn hóa `Dist_plan → dist_y/dist_m` (§14.5); tính `sold_30/60/90` theo mã; GROUP BY theo mọi chiều lọc **+ `Product_group`**; encode columnar + dict | Log mã hàng không map được `size_profile` / `Dist_plan` |

| `validate` | So `SUM(Qty)` theo Year/SalesSource (bán) và `SUM(Qty_TonKho)` theo Brand/Region (tồn) giữa payload và parquet nguồn | **Dừng build** nếu lệch > 0,5% |

| `render` | `json → gzip → base64`, chèn vào `shell/template.html` qua **1 placeholder literal** | Không regex đổi tên hàm, không scope CSS động |



### Bỏ hardcode kỳ tham chiếu



`build_data.py` hiện có `REF_YEAR, REF_MONTH = 2026, 7` và các list `ym1/ym3/ym6/ym9`,

nhãn `"T7/2026"` **cứng**. Thiết kế mới: tính kỳ tham chiếu và mọi cửa sổ lũy kế

3/6/9 tháng **động** từ tháng có dữ liệu mới nhất; sinh nhãn tự động.



---



## 8. Quy trình cập nhật (chủ dữ liệu)



```bash

# 1. Bỏ file parquet mới vào D:\00.Data_AnPhuoc_Group\...\<năm>\

# 2. Build (1 lệnh — tự làm mới từ dữ liệu sống, tự dò kỳ mới nhất)

"%USERPROFILE%\anaconda3\python.exe" backend\build.py

#    → kiểm tra dòng "VALIDATE OK — lệch 0.02%" và kích thước file

# 3. Google Drive → chuột phải file cũ → "Quản lý phiên bản" →

#    "Tải phiên bản mới lên" → chọn dist/BaoCao_TongHop.html

#    → LINK CHIA SẺ KHÔNG ĐỔI; người nhận luôn lấy bản mới nhất

```



- Header file hiển thị `Dữ liệu cập nhật: 08/09/2026 14:25 — kỳ T7/2026`.

- `build.py` in checklist + cảnh báo nếu file > 20 MB.

- `python` mặc định trên máy là Microsoft Store stub — **luôn** dùng đường dẫn Anaconda đầy đủ.



---



## 9. Quy trình xem (người nhận)



1. Mở link Drive → bấm **Tải xuống** (Drive không render HTML — đây là hành vi bình thường;

   file ~10 MB tải vài giây).

2. Double-click file → mở bằng trình duyệt → loading ~1–2 giây (giải nén) → dashboard.

3. Hoạt động **100% offline**: lọc, đổi phân khúc, đổi tab tức thì, không cần internet/Python.



> Tùy chọn nếu muốn xem thẳng không tải: đẩy `dist/` lên **Cloudflare Pages / Netlify Drop /

> GitHub Pages** (miễn phí, kéo-thả) → 1 URL mở thẳng trong trình duyệt. Vẫn giữ bản trên Drive

> làm lưu trữ. Không bắt buộc.



---



## 10. Khả năng lọc — giải thích



"Tổng hợp" **không** làm mất khả năng lọc. Nó là `GROUP BY` theo **tất cả** chiều muốn lọc.



| Lọc được thoải mái (nằm trong GROUP BY) | Không lọc được |

|:---|:---|

| Năm, Tháng, Nguồn bán, Giao dịch, Khu vực, Cửa hàng, Status, Brand, **Product_group**, Nhóm BC, Tên hàng BC, Color tone, Color group, Form, Style, Attribute — **kết hợp tự do, chọn nhiều giá trị** | Chiều không đưa vào GROUP BY (vd Size, Gender, Warehouse nếu bỏ) |

| 5 phân khúc + mọi bộ lọc tự do chồng lên nhau | Chi tiết dưới mức tổng hợp: từng hóa đơn, từng ngày, từng dòng thô |

| Top mã hàng, cơ cấu nhóm, so sánh 3 năm | Mã hàng ngoài top 2.000 → nằm trong "Khác" ở *bảng chi tiết* (biểu đồ tổng quan vẫn tính đủ) |



Nút vặn cân bằng: thêm 1 chiều vào GROUP BY → lọc được theo chiều đó nhưng file to hơn.

Kích thước phụ thuộc **số tổ hợp thực sự xuất hiện trong dữ liệu**, không phải tích Descartes.



---



## 11. Bug cần sửa kèm theo (độc lập kiến trúc)



| # | Vị trí | Lỗi |

|:--|:---|:---|

| 1 | `standalone_engine.js:158` | Filter `sub_brand` lấy từ `getUniqueValues(7)` = cột **Brand**, không phải sub-brand. Sửa đúng cột hoặc bỏ filter. |

| 2 | `renderYoYDetailTable` / `renderProductDetailTable` | "Sức Bán TB/Tháng" chia `params.months.length || 1`. Chọn năm không chọn tháng → chia 1 → "TB tháng" = tổng cả năm. Phải chia **số tháng thực có dữ liệu**. |

| 3 | `server.py` | Chỉ chạy `build_standalone_html.py`, không refresh cache/Tồn. Dùng `'python'` (Store stub). `host=0.0.0.0` không auth. → thay bằng gọi `build.py`, `sys.executable`, `127.0.0.1` + token, hoặc bỏ hẳn (quy trình build thủ công đã đủ). |

| 4 | `build_data.py:146-148` | `gz_prod_b64` được tính, in size, **không đưa vào payload** → nén vô ích, ship mảng lớn nhất không nén. Nối lại hoặc xóa. |

| 5 | `build_data.py:53` | `REF_YEAR, REF_MONTH = 2026, 7` + windows hardcode → báo cáo sai kỳ khi có dữ liệu mới. Tính động. |

| 6 | file gộp | Plotly nhúng 2 lần. Nhúng 1 lần. |



---



## 12. Lộ trình triển khai



| GĐ | Việc | Kết quả |

|:--|:---|:---|

| 1 | Dựng `shell/` sạch (template + 1 CSS + 1 engine), tách 2 tab đúng cách, không shim | Vỏ tái dùng được |

| 2 | `aggregate_*` columnar + `Product_group` + `render.py` nối lại đường gzip | File < 15 MB, mở không treo |

| 3 | `build.py` orchestrator + bỏ hardcode kỳ + `validate.py` | 1 lệnh, số liệu tin được |

| 4 | `segments.js` + `applySegment()` + thanh nút phân khúc trên HTML | 5 phân khúc hoạt động |

| 5 | Sửa bug mục 11 (sub_brand, TB/tháng, server) | Số đúng |

| 6 | **Số Bán chuyên sâu (§13):** bộ chỉ số thời gian chuẩn, ma trận brand×khu vực, loại giá bán, top 20 CH, top 5 CH theo khu vực×brand, số bán theo loại hàng + khu vực bán chạy theo TB/CH active | Tab Bán đủ phân tích |

| 7 | **Số Tồn chuyên sâu (§14):** tách khu vực/kho, tồn theo brand/khu vực/kho + tỉ trọng, drill tên hàng→mã hàng, size theo `size_profile`, kết nối HHLC, phân loại hàng mới PP 6 tháng, cờ bán 30/60/90 ngày, lát cắt theo thuộc tính/tên hàng/CH | Tab Tồn đủ phân tích |

| 8 | Viết `OPERATIONS.md` theo quy trình thật + Drive versioning; xóa file chết | Tài liệu khớp code |



---



## 13. Phân tích chuyên sâu — SỐ BÁN



### 13.0. Bộ chỉ số thời gian chuẩn (BCTG) — dùng lại ở mọi bảng số bán



Với kỳ hiện tại = **tháng T / năm N** (N = năm mới nhất có dữ liệu, T = tháng mới nhất của N):



| Cột | Định nghĩa |

|:---|:---|

| **Tháng hiện tại** | Qty tháng T / năm N |

| **Tháng trước (MoM)** | Qty tháng T‑1 (nếu T=1 → T12/N‑1); kèm `% thay đổi` |

| **Cùng kỳ N‑1** | Qty tháng T / năm N‑1; kèm `% YoY` |

| **Cùng kỳ N‑2** | Qty tháng T / năm N‑2; kèm `% YoY` |

| **Lũy kế hiện tại (YTD)** | Σ Qty tháng 1..T / năm N |

| **YTD cùng kỳ N‑1** | Σ Qty tháng 1..T / năm N‑1; kèm `% YoY` |

| **YTD cùng kỳ N‑2** | Σ Qty tháng 1..T / năm N‑2; kèm `% YoY` |



Hiện `N=2026 ⇒ N‑1=2025, N‑2=2024` (cache 3 năm). Nếu một năm không có trong cache → hiển thị `—`.

Mọi bảng ở §13.1, §13.3–13.5 đều có đủ 7 cột này (thu gọn được bằng nút "MTD / YTD").



### 13.0b. Quy tắc "cửa hàng đang mở" (dùng chung)



- **Cửa hàng đóng cửa** = Qty tháng hiện tại (T/N) = 0 → **loại khỏi**:

  - mẫu số khi tính **bán trung bình / cửa hàng**;

  - bảng xếp hạng "bán ít nhất" (mặc định; có toggle *"gồm CH đóng cửa"*).

- **Khu vực bán chạy** = xếp theo **Qty ÷ số CH đang mở của khu vực**, KHÔNG theo tổng Qty

  (số CH mỗi khu vực rất lệch: TP.HCM 68, Hà Nội 46, Miền Tây 30, Miền Trung‑TN 30, Miền Đông 12).

- Engine đọc từ bảng phụ `ban.active_stores[N][T][region]`; có thể tự tính lại client‑side khi có

  bộ lọc thu hẹp (đếm `distinct st` có Qty>0 trong phạm vi hiện tại).



### 13.1. Ma trận **Brand × Khu vực**



- **Brand chính (5):** Hiệu An Phước · Hiệu An Phước Ladies · Hiệu Pierre Cardin · Hiệu Anamai · Hiệu Bonjour

  (các hiệu khác gộp "Khác").

- **Khu vực chính (5):** TP. HCM · Miền Tây · Miền Đông · Miền Trung - TN · Hà Nội

  (**loại `Event`** khỏi phân tích khu vực; vẫn xem được ở "Toàn bộ").

- Bảng chéo: hàng = Brand, cột = Khu vực, ô = **Qty tháng hiện tại + %YoY (N‑1)**; có dòng/cột **Tổng**.

- Chế độ xem phụ: ô = **bán TB/CH đang mở** (so sánh khu vực công bằng).

- Bấm 1 ô → mở BCTG đầy đủ (7 cột) cho cặp (brand, khu vực) đó.



### 13.2. Loại giá bán (Status) — xem riêng biệt



Trường phái sinh `price_type` (4 giá trị):



| Giá trị | Nguồn |

|:---|:---|

| **Nguyên giá** | `Status = 'Nguyên giá'` |

| **Sale** | `Status = 'Sale'` |

| **Thanh lý** | `Status = 'Thanh lý'` |

| **Hợp đồng** | `SalesSource = 'Contract'` (đè lên Status — bán hộ/hợp đồng) |



Bộ lọc chọn‑nhiều, mặc định **tất cả**; mỗi giá trị có thể xem tách (KPI + cơ cấu %).

*(Lưu ý: `"Nội dung"` = Bán / Tặng / Đổi / Hợp đồng là chiều **Giao dịch** riêng — "số bán" mặc định

chỉ lấy `Bán`; `Đổi` mang dấu âm.)*



### 13.3. Top 20 cửa hàng toàn hệ thống



- **Top 20 bán nhiều nhất** và **Top 20 bán ít nhất** (2 bảng / 2 biểu đồ thanh ngang).

- Sắp theo **Qty tháng hiện tại** (đổi được sang YTD).

- Mỗi dòng kèm BCTG rút gọn (MoM %, YoY %, TB/tháng) + Khu vực + Brand chủ đạo của CH.

- "Bán ít nhất": áp §13.0b (bỏ CH đóng cửa, có toggle).



### 13.4. Top 5 cửa hàng theo **Khu vực × Brand**



- Với mỗi cặp (khu vực chính, brand chính) → **5 CH bán chạy nhất** tháng hiện tại.

- Trình bày: bảng nhóm (gộp theo khu vực, trong mỗi khu vực xổ 5 brand × 5 CH) hoặc lưới small‑multiples.

- Mỗi CH: Qty tháng hiện tại + %YoY + hạng trong khu vực.



### 13.5. Số bán theo **loại hàng** (Group_Report → Report_item_name → Mã hàng)



- Bảng phân cấp, mỗi dòng có **BCTG đầy đủ (7 cột)**.

- Cột **"Khu vực bán chạy tháng này"** = khu vực có **bán TB/CH đang mở** cao nhất (§13.0b),

  hiển thị tên khu vực + chỉ số TB/CH (không phải tổng).

- Drill: `Group_Report` → `Report_item_name` → `Mã hàng` (kèm đủ thuộc tính như §14.3).

- Áp được phân khúc (§6) và mọi bộ lọc tự do.



---



## 14. Phân tích chuyên sâu — SỐ TỒN



> Tồn là **ảnh chụp tại thời điểm build**, không có lịch sử tháng → **không áp BCTG** của §13.

> "Chiều thời gian" của tồn = kỳ phân phối (§14.5) + cờ đã bán 30/60/90 ngày (§14.5).



### 14.1. Tách **Khu vực cửa hàng** vs **Kho** (xử lý ở pipeline)



Trong `InventorySize.parquet`, cột `Region` **trộn lẫn** khu vực bán và kho. Pipeline phải sinh

`region_kind`:



| `region_kind` | Giá trị `Region` |

|:---|:---|

| **Cửa hàng** | TP. HCM · Miền Tây · Miền Trung - TN · Hà Nội · Miền Đông · Event |

| **Kho** | Kho Tổng hợp · Kho AP · Kho PIE · Kho CNHN · Kho TB3 đồ lót · Kho KDTT · Kho Nội Bộ AP · Kho Sửa Chữa · KDND |



- **Kho chính (5)** để hiển thị mặc định: **Kho AP · Kho PIE · Kho TB3 đồ lót · Kho CNHN · Kho Tổng hợp**

  (phần kho còn lại gộp "Kho khác"). *(Người dùng gọi "Kho CHNH" = `Kho CNHN`; "Kho TB3" = `Kho TB3 đồ lót`.)*

- Cột `Warehouse` gốc (`HTCH` / `Kho Tổng` / `KDND`) hầu như vô nghĩa → **không dùng** làm chiều chính.



### 14.2. Tồn — tổng quan (kèm tỉ trọng %)



| Bảng | Chiều | Cột |

|:---|:---|:---|

| Tồn theo **Brand chính** | 5 brand + "Khác" | Qty tồn · % tổng · số mã hàng |

| Tồn theo **Khu vực CH** | 5 khu vực (+ Event) | Qty tồn · % tổng |

| Tồn theo **Kho chính** | 5 kho + "Kho khác" | Qty tồn · % tổng |



Cho phép cắt chéo brand × (khu vực/kho). Áp phân khúc §6.



### 14.3. Tồn theo **tên hàng** → drill **mã hàng** + Size



**Phân cấp:** `Group_Report` → `Report_item_name` → `Mã hàng`.



**Cấp mã hàng — đủ thuộc tính** (từ F_DataTracking join):

`Operation, Gender, Product_type, Composition, Color_tone, Color_group, Norm_Color_Group,

Form, Style, Attribute, Price, Sub_Brand, Dist_plan, Tháng/Năm sản xuất`, cùng Qty tồn tổng

và Qty tồn theo từng cửa hàng.



**Size — quy tắc "bộ cặp size" (`size_profile`):**



- Mỗi `Report_item_name` được gán 1 `size_profile` = khóa suy từ tập size đã chuẩn hóa

  (vd *sơ mi nam*: `37–46 + DAT` ; *áo nữ chữ*: `S–3XL + DAT` ; *áo ngực*: hệ 27 size…).

- **Hiển thị hàng "Tổng size":**

  - phạm vi đang xem chỉ chứa **1 `size_profile`** → hiện 1 hàng **Tổng size** (cộng dồn theo size).

  - phạm vi chứa **nhiều `size_profile`** (vd chọn cả `Group_Report = Chemise` gồm cả nam số lẫn nữ chữ)

    → **ẩn** hàng Tổng size, thay bằng **một hàng Tổng cho mỗi profile** (hoặc chỉ hiện khi drill sâu hơn).

- Ví dụ người dùng nêu:

  - chọn `Chemise` (nhiều profile) → **không** hiện dãy size tổng.

  - chọn `Chemise Nam Ngắn AP` (1 profile) → hiện **Tổng size** (37, 38, …, 46, DAT, OneSize).

- Cấp mã hàng luôn xem được size chi tiết (theo CH và tổng mã).



### 14.4. Kết nối **Lệnh luân chuyển (HHLC)**



- Nguồn: `D:\00.Data_AnPhuoc_Group\03.Data_Parquest\07.Lenh_HHLC\<năm>\*.parquet`

  (đã dùng trong `build_data.py`: `lc_map` / `lc_dict`).

- Ở cấp **mã hàng / cửa hàng**: badge **"🔄 vừa nhập LC (T8/2026)"** khi kỳ nhập LC gần nhất

  trùng/kề kỳ báo cáo; kèm số CH nhận trong kỳ đó.

- Bộ lọc nhanh: *"Chỉ hàng vừa luân chuyển về"*.

- Bảng con: danh sách lệnh LC gần nhất của mã đang xem (kỳ nhập, CH nhận, số lượng, ghi chú).



### 14.5. Phân loại **hàng mới phân phối** (cửa sổ 6 tháng) + cờ đã bán



Kỳ hiện tại = tháng **M** / năm **Y** (theo ngày build).



| Nhóm | Điều kiện `Dist_plan` (chuẩn hóa → `dist_y`, `dist_m`) | Ý nghĩa |

|:---|:---|:---|

| **Mới ra CH — chưa đánh giá** | `dist` = M/Y (và M+1 nếu có) | vừa lên kệ, chưa đủ thời gian bán |

| **Hàng mới PP (đánh giá được)** | `dist` ∈ [M‑6/Y … M‑1/Y] (vd M=9 → tháng 3‑8) | đã bán 1–6 tháng — theo dõi hiệu quả |

| **Hàng cũ** | `dist` cũ hơn M‑6 | ngoài cửa sổ đánh giá |

| **Không theo cửa sổ** | `Dist_plan` là chữ: `H.Đồng, Thanh Lý, Không Xác Định, Chưa PP, HANG TANG, Áo Mẫu…` hoặc rỗng | tách riêng, không xếp nhóm |



- **Chuẩn hóa `Dist_plan`:** parse `T?<m>.<yyyy>` — chấp nhận cả `T09.2024` và `T9.2023`;

  giá trị không parse được → `dist_y/dist_m = null` → nhóm "Không theo cửa sổ". Log ở build.

- Cửa sổ (6 tháng) **tính động** theo M; hiển thị nhãn kỳ rõ ràng ("Hàng mới PP: T3–T8/2026").



**Cấp mã hàng — cờ đã bán:** `sold_30`, `sold_60`, `sold_90` (mã có phát sinh bán trong

30/60/90 ngày gần nhất tính từ ngày build — **cửa sổ lăn theo ngày**, không phải theo tháng lịch).

Dùng để lọc "hàng tồn nhưng **không** bán 90 ngày" (ứ đọng) hay "mới PP **đã** bán 30 ngày" (bắt nhịp tốt).

*(Nếu dữ liệu bán chỉ có mức tháng, tạm dùng cửa sổ tháng gần đúng `s1/s3` như `build_data.py` — ghi rõ trong tooltip.)*



### 14.6. Báo cáo tồn theo **lát cắt** (song song với §13.5)



Cùng một khối tồn, xoay theo:



- **Theo thuộc tính:** `Norm_Color_Group` / `Color_tone` / `Form` / `Style` / `Attribute` / `Sub_Brand`.

- **Theo tên hàng:** `Group_Report` / `Report_item_name` (drill mã hàng).

- **Theo cửa hàng:** xếp hạng CH theo Qty tồn; tồn TB/CH theo khu vực.

- **Theo khu vực / kho:** như §14.2.

- **Theo kỳ phân phối:** nhóm §14.5.



Mỗi lát cắt hiển thị Qty tồn + % tổng + số mã hàng; áp phân khúc §6 và bộ lọc tự do.



---



## Phụ lục A — Giá trị danh mục thật (từ `cache_sales.parquet`, để đánh dấu mapping)



### `Group_Report` (40 giá trị)

```

Chemise 2.170.662 | Áo Thun 1.052.617 | Quần Tây 438.211 | Đồ Lót 257.612 |

Quần Short 172.723 | Quần Kaki 164.143 | Quần Lót 133.499 | Vớ 130.917 |

Quần Jean 118.423 | Caravat 107.022 | Áo Ngực 99.830 | Quần Golf 84.899 |

Áo Khoác 72.331 | Dây Nịt 58.369 | Khác 51.003 | Seamless 48.398 | Váy 47.843 |

Fashion 43.472 | Đồ Mặc Nhà 33.070 | Ví 29.848 | Giày, Dép 29.005 | Áo Golf 28.151 |

Quần Vest 20.254 | Đồ Ngủ 18.556 | Khăn, Nơ, Nón 18.044 | Áo Vest 17.497 |

Nút, Kẹp, Logo 9.762 | Túi 5.134 | Bao Bì 4.784 | Áo Lót 4.626 | Áo Khác 3.433 |

Basic 2.612 | Vali 2.485 | Thanh Lý 2.469 | Balô, Cặp 1.864 | Phụ Kiện Golf 1.795 |

Áo 1.494 | Phụ Kiện 114 | Đồng Phục 110 | Đồ Bơi 83

```



### `Product_group` (23 giá trị)

```

Áo 3.205.156 | Quần 893.500 | Phụ Kiện Vải 286.921 | Đồ Lót 262.238 |

Phụ Kiện Da 155.624 | Quần Lót 133.499 | Golf 114.845 | Áo Ngực 99.830 |

Hợp Đồng 95.381 | Seamless 48.398 | Váy 47.684 | Fashion 43.472 | Vest Bộ 37.910 |

Đồ Mặc Nhà 33.070 | Đồ Ngủ 18.556 | Bao Bì 4.784 | Basic 2.612 | Đồng Giá 2.469 |

Bộ 898 | Phụ Kiện 114 | Đồng Phục 110 | Đồ Bơi 83 | Phụ Kiện Khác 10

```



### `Brand` (10 giá trị)

```

Hiệu An Phước 2.912.040 | Hiệu Pierre Cardin 1.611.988 | Hiệu An Phước Ladies 574.587 |

Hiệu Bonjour 248.026 | Hiệu Anamai 133.102 | Khác 4.784 | Thanh Lý 2.469 |

Hiệu Gerb Weis 96 | Hiệu Tomiya 67 | Hiệu An Phước HTT 5

```



### `Product_type` (8 giá trị)

```

Thông Thường 4.926.401 | Thanh Lý 329.057 | Thanh Lý (ĐG) 121.029 | Hợp Đồng 95.381 |

Thanh Lý (NB) 10.397 | Bao Bì 4.784 | Đồng Phục 110 | Hàng Thông Tin 5

```



### `Region` (6 giá trị) — kèm số cửa hàng có bán 2026

```

TP. HCM  qty 2.124.291  (68 CH)   | Miền Tây        qty 1.193.362  (30 CH)

Miền Trung - TN  qty 855.839  (30 CH) | Hà Nội       qty 606.666  (46 CH)

Miền Đông  qty 384.947  (12 CH)   | Event           qty 322.059  (26 CH)  ← loại khỏi phân tích khu vực

```



### `Status` (3 giá trị) → ánh xạ `price_type`

```

Nguyên giá 4.613.138 | Thanh lý 460.483 | Sale 413.543

+ "Hợp đồng" (phái sinh) = SalesSource/Sales_Type = 'Contract'  → 430.325

```



### `Sales_Type` / `"Nội dung"` (chiều Giao dịch)

```

Sales_Type:  Retail 5.056.839 | Contract 430.325

"Nội dung":  Bán 5.409.597 | (Hợp đồng/None) 430.325 | Tặng 147.434 | Đổi -500.192

```



### `Dist_plan` — định dạng & giá trị đặc biệt

```

Định dạng kỳ:  T09.2024 , T02.2026 …  (lẫn cả T9.2023 , T6.2022 — phải parse linh hoạt)

Giá trị chữ (không có kỳ):  H.Đồng · Thanh Lý · Thanh lý · Không Xác Định · Chưa PP ·

                            HANG TANG · HANG THONG TIN · Hàng B · Hàng SC · Áo Mẫu · Quần Mẫu · None

```



### Phạm vi dữ liệu bán trong cache hiện tại

```

2024: T1–T12   |   2025: T1–T12   |   2026: T1–T8   (N=2026, N-1=2025, N-2=2024)

```



*Báo cáo Tồn hiện đã lọc bỏ `Bao Bì` và `Đồng Phục` — giữ nguyên quy tắc này ở cả hai báo cáo.*



---



## Phụ lục B — `InventorySize.parquet` (nguồn Số Tồn)



**Cột:** `Warehouse, Region, Store_name, Brand, System_item_name, Report_item_name, Mahang,

Operation, Size, Qty_TonKho, Status, Product_type, Gender, Product_group, Group_Report`

→ **không có** Color/Form/Style/Price/Sub_Brand/Dist_plan ⇒ phải `LEFT JOIN F_DataTracking`

theo `Mahang + Operation` (như `build_data.py`).



### `Region` trong InventorySize (15 giá trị — trộn khu vực & kho)

```

CỬA HÀNG:  TP. HCM 922.102 | Miền Tây 541.351 | Miền Trung - TN 453.065 | Hà Nội 399.773 |

           Miền Đông 197.734 | Event 74.326

KHO:       Kho Tổng hợp 402.009 | Kho AP 342.991 | Kho PIE 338.560 | Kho CNHN 213.049 |

           Kho TB3 đồ lót 69.411 | Kho KDTT 6.294 | Kho Nội Bộ AP 717 | Kho Sửa Chữa 2 | KDND 1

```

→ 5 **kho chính**: Kho AP · Kho PIE · Kho TB3 đồ lót · Kho CNHN · Kho Tổng hợp.



### `Warehouse` trong InventorySize (gần như vô dụng)

```

HTCH 2.588.351 | Kho Tổng 1.373.033 | KDND 1

```



### `Brand` trong InventorySize

```

Hiệu An Phước 1.268.747 | Hiệu Pierre Cardin 1.232.373 | Khác 770.961 |

Hiệu An Phước Ladies 315.901 | Hiệu Bonjour 211.485 | Hiệu Anamai 159.902 |

Hiệu Gerb Weis 1.974 | Thanh Lý 36 | Hiệu An Phước HTT 5 | Hiệu Pierre Cardin HTT 1

```

*(Lưu ý "Khác" = 770k tồn chưa gắn hiệu — cần rà lại mapping ở bước join.)*



---



## Phụ lục C — Ví dụ `size_profile` (Group_Report = Chemise)



```

Chemise Nam Ngắn/Dài AP · PIE   → 37,38,39,40,41,42,43,44,45,46,DAT1,DAT2,DAT3,OneSize   (14) — hệ "sơ mi nam số"

Chemise Nữ Dài AP               → S,M,L,XL,XXL,3XL,DAT1,DAT2                              (8)  — hệ "nữ chữ"

Chemise Nữ Ngắn AP · PIE        → S,M,L,XL,XXL,3XL,DAT1                                   (7)  — hệ "nữ chữ"

```

→ `Group_Report = Chemise` gộp ≥2 hệ ⇒ **ẩn Tổng size**. Chọn 1 `Report_item_name` ⇒ **hiện Tổng size**.

Nhóm high‑cardinality khác: Áo Ngực 27 size, Quần Vest/Tây/Kaki 21 size.

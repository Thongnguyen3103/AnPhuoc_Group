# KIẾN TRÚC & THAM CHIẾU KỸ THUẬT — BÁO CÁO TỔNG HỢP (TỒN & SỐ BÁN) AN PHƯỚC

> **Tài liệu "as-built"** — mô tả đúng hệ thống hiện tại (sau các vòng chỉnh sửa).
> Cập nhật: 10/09/2026. Nếu lệch với `DESIGN.md` (bản thiết kế mục tiêu, viết trước) thì **tài liệu này đúng**.

---

## 0. Tóm tắt 30 giây

- Đây là **trình sinh báo cáo tĩnh** (static report generator), **không phải web app**.
- Chạy Python **1 lần lúc build** trên máy có kết nối kho dữ liệu `D:\AnPhuocGroup\AnPhuoc_Data\00.Data_AnPhuoc_Group`.
- Kết quả: **1 file duy nhất** `04.Output/Report_Summary/BaoCao_TongHop.html` (~13 MB, tự chứa 100%, chạy offline, không CDN/server).
- Người xem: tải file từ Google Drive → mở bằng Chrome/Edge/Cốc Cốc → mọi thao tác lọc chạy bằng JavaScript trong trình duyệt.

### Lệnh chạy duy nhất

```powershell
# Dùng cho MỌI trường hợp — kể cả khi vừa thêm/sửa file parquet bán.
# Stage 1 tự phát hiện dữ liệu bán mới (so kỳ + số dòng nguồn vs cache) và tự nạp lại.
& "C:\Users\THONG SL\anaconda3\python.exe" Core\Run_Build_Summary.py

# Chỉ dùng khi muốn ÉP tạo lại cache từ đầu (nghi ngờ cache hỏng)
& "C:\Users\THONG SL\anaconda3\python.exe" Core\Run_Build_Summary.py --force-cache
```

> Luôn dùng đường dẫn đầy đủ tới Python Anaconda. Lệnh `python` trần trên Windows có thể trỏ vào stub Microsoft Store.
>
> **Có số bán tháng mới?** Bỏ file parquet vào đúng folder năm (`…\01.System_sales\<năm>\`, `…\02.Contract_sales\<năm>\`) rồi chạy lệnh thường — kỳ báo cáo tự nhảy sang tháng mới nhất.

---

## 1. Cây thư mục hiện tại (đã dọn rác)

```
Report_Summary/
├── ARCHITECTURE.md          ← tài liệu này (as-built)
├── DESIGN.md                ← bản thiết kế mục tiêu (viết trước, tham khảo lịch sử)
├── README.md            ← quy trình vận hành / upload Drive
├── requirements.txt         ← pandas, pyarrow, duckdb
│
├── Core/                 ← CODE PYTHON — chỉ chạy lúc build
│   ├── Run_Build_Summary.py ← ★ ORCHESTRATOR: chạy 5 stage tuần tự (đổi tên từ build.py)
│   ├── Render_Html_Output.py            ← Stage 5: gzip+base64 payload, nhúng vào shell → dist/
│   └── Steps/
│       ├── Refresh_Sales_Cache.py ← Stage 1: đọc parquet gốc → Cache/Sales_Cache.parquet
│       ├── Aggregate_Sales.py ← Stage 3: tổng hợp SỐ BÁN (chạy trước aggregate_ton)
│       ├── Aggregate_Inventory.py ← Stage 2: tổng hợp SỐ TỒN + metadata SKU
│       └── Validate_Payload.py      ← Stage 4: đối chiếu tổng Qty payload ↔ nguồn (dừng nếu lệch > 0.5%)
│
├── Template/                   ← "VỎ" — viết tay, KHÔNG phải output build
│   ├── Report_Template.html        ← khung 2 Phần × 4 Sheet + placeholder <!-- PAYLOAD_PLACEHOLDER -->
│   ├── Report_Style.css            ← 1 design system
│   ├── Report_Engine.js            ← ★ toàn bộ logic render (2738 dòng)
│   ├── Report_Segments.js          ← khai báo 6 phân khúc — ⚠️ HIỆN CHƯA ĐƯỢC ENGINE DÙNG (xem §8)
│   └── vendor/
│       └── plotly-basic.min.js  ← ~1 MB (bar/pie/scatter)
│
├── database/
│   └── Sales_Cache.parquet  ← TRUNG GIAN (~110 MB). Không commit. Xoá cũng được — build sau tự dựng lại.
│
└── dist/
    └── BaoCao_TongHop.html  ← ★ FILE DUY NHẤT UPLOAD LÊN DRIVE
```

**File cần chạy code:** chỉ `Core/Run_Build_Summary.py`. Nó tự import và gọi 5 module trong `Core/Steps/` + `Core/Render_Html_Output.py`. Không chạy các file stage lẻ trực tiếp (chúng có `if __name__ == '__main__'` chỉ để test nhanh).

**Đã xoá (rác):** `Core/__pycache__/`, `Core/Steps/__pycache__/`, `build.log`, và trước đó: `frontend/` (bản FastAPI/standalone cũ), `Core/build_cache.py`, `Core/build_data.py`, `Core/data_full.db`.

---

## 2. Nguồn dữ liệu (chỉ có trên máy build)

| Nguồn | Đường dẫn | Dùng cho |
|:---|:---|:---|
| System_sales | `D:\AnPhuocGroup\AnPhuoc_Data\00.Data_AnPhuoc_Group\03.Data_Parquest\01.System_sales\<năm>\*.parquet` | số bán lẻ |
| Contract_sales | `…\02.Contract_sales\<năm>\*.parquet` | số bán hợp đồng |
| InventorySize | `…\03.Inventory\InventorySize.parquet` | số tồn (ảnh chụp) |
| F_DataTracking | `…\02.Master\F_DataTracking.parquet` | thuộc tính SKU (join theo `item_code + Operation`) |
| A_Region | `…\02.Master\A_Region.parquet` | Store_rank, FLD |
| Lệnh HHLC | `…\07.Lenh_HHLC\<năm>\*.parquet` | cờ "vừa luân chuyển về" |

`Refresh_Sales_Cache.py` gộp System_sales + Contract_sales (N năm gần nhất, tính từ `MAX(Year)` = 3) và `LEFT JOIN` F_DataTracking + A_Region → `Cache/Sales_Cache.parquet`.

> **Đã kiểm toán join:** `F_DataTracking` là **1:1 tuyệt đối** trên `(item_code, Operation)`; `A_Region` 1:1 trên `Store_name`. `Sales_Cache.parquet` có `SUM(Qty_Ban)` = nguồn thô y hệt (lệch 0). Không có double-count.

---

## 3. Pipeline build — 5 stage (`Core/Run_Build_Summary.py`)

Nhãn `[STAGE n]` in ra là **số hiệu module**, không phải thứ tự chạy. Thứ tự chạy thực tế:

| # | Module | Input | Output (biến trong bộ nhớ) | Logic chính |
|:--|:---|:---|:---|:---|
| 1 | `refresh_cache.run(force)` | parquet gốc | `Cache/Sales_Cache.parquet` | Đọc 3 năm gần nhất. **Tự phát hiện:** so `MAX(Year*100+Month)` + tổng số dòng nguồn ↔ cache; nguồn mới hơn / khác → tự nạp lại, bằng nhau → bỏ qua. `--force-cache` = ép nạp lại. |
| 2 | `aggregate_ban.run()` | cache_sales | `ban_payload`, `shared_dict`, `ref_year`, `ref_month` | Xác định kỳ tham chiếu = (Year, Month) mới nhất. Tổng hợp overview + top-N. |
| 3 | `aggregate_ton.run(shared_dict, ref_year, ref_month)` | InventorySize + F_DataTracking + HHLC + cache_sales | `ton_payload`, `shared_dict` | Phân loại vị trí, size_profile, tuổi PP, cờ bán; metadata SKU. |
| 4 | `validate.run(ton_payload, ban_payload)` | payload + parquet nguồn | — (raise nếu lệch) | So `SUM(Qty)` payload ↔ nguồn. **Dừng build nếu lệch > 0.5%.** |
| 5 | `render.run(...)` | payload + `Template/*` | `04.Output/Report_Summary/BaoCao_TongHop.html` | `json → gzip(level 9) → base64` → chèn vào `Report_Template.html` qua 1 placeholder literal; nhúng thẳng CSS/plotly/segments/engine. |

**`shared_dict`** = bảng chuỗi dùng chung (`{'list': [...], 'map': {...}}`). Mọi giá trị chuỗi trong payload được thay bằng **chỉ số** vào `shared_dict['list']` (dictionary encoding) → gzip nén rất tốt.

### Loại trừ áp dụng ở MỌI stage
- Bỏ nhóm hàng chứa `"bao bì"` hoặc `"đồng phục"` (LIKE, không phân biệt hoa thường).
- `Region = 'Event'` bị loại khỏi các phân tích khu vực / xếp hạng cửa hàng (vẫn tính trong tổng "Toàn HT").

---

## 4. CẤU TRÚC PAYLOAD NHÚNG (JSON)

Thẻ `<script id="payload">` chứa `base64(gzip(JSON))`. Engine giải nén bằng `DecompressionStream('gzip')`.

```jsonc
{
  "v": 3,
  "built": "10/09/2026 09:38",              // thời điểm build
  "ref": { "year": 2026, "month": 8, "label": "T8/2026" },  // kỳ tham chiếu (động)
  "dict": ["…", "…"],                        // bảng chuỗi dùng chung
  "ban": { … },
  "ton": { … }
}
```

### 4.1. `ban` — SỐ BÁN

| Key | Kiểu | Ý nghĩa |
|:---|:---|:---|
| `ov` | columnar | Overview đã GROUP BY. **9 cột** (xem dưới). Nguồn tính lại cho Sheet 1/2/3. |
| `top_fullprice_brand_item` | `{ period: { brand: { item: [sku…] } } }` | Top 5 mã Nguyên giá theo Brand × Tên hàng, **theo từng kỳ** (`period` ∈ `'ytd'`, `'1'`..`'12'`). Mỗi sku = `{mahang, form, style, cg, price, qty}`. Dùng Sheet 2. |
| `top_fullprice_store_brand_item` | `{ store: { brand: { item: [sku…] } } }` | Top 5 mã Nguyên giá theo Cửa hàng × Brand × Tên hàng (năm hiện tại). Dùng Sheet 3. |
| `attr_sales` | columnar | Lát cắt thuộc tính bán đa năm. **11 cột** (xem dưới). Dùng Sheet 4. |
| `active_stores` | `{ "year": { "month": { region: count } } }` | Số CH có Qty>0. **⚠️ Engine hiện chưa dùng** (dành cho phân tích TB/CH tương lai). |
| `return_analysis` | `{ brand, group_report, top_stores, top_items }` | Phân tích đổi trả. **⚠️ Engine hiện chưa dùng** (dành cho sheet Đổi trả tương lai). |

**`ban.ov.cols`** (9): mọi giá trị trừ `y/m/qty` là **chỉ số DICT**.

| idx | tên | giá trị |
|:--:|:---|:---|
| 0 | `y` | năm (int) |
| 1 | `m` | tháng 1–12 (int) |
| 2 | `src` | `'Lẻ'` \| `'HĐ'` (SalesSource) |
| 3 | `txn_type` | `'Bán'` \| `'Đổi'` \| `'Tặng'` … (cột "Nội dung") |
| 4 | `price_type` | `'Nguyên giá'` \| `'Sale'` \| `'Thanh lý'` \| `'Hợp đồng'` (Contract đè lên Status) |
| 5 | `st` | Store_name |
| 6 | `rg` | Region |
| 7 | `br` | 5 brand chính (An Phước Nữ → "Hiệu An Phước Ladies") hoặc `'Khác'` |
| 8 | `qty` | `SUM(Qty_Ban)` (int, **Đổi mang dấu âm**) |

**`ban.attr_sales.cols`** (11): `m` thêm ở cuối để giữ index cũ.

| idx | tên | | idx | tên |
|:--:|:---|---|:--:|:---|
| 0 | `y` (int) | | 6 | `form` |
| 1 | `rg` | | 7 | `style` |
| 2 | `br` | | 8 | `cat_group` (6 nhóm hàng) |
| 3 | `gr` (Group_Report) | | 9 | `qty` (int) |
| 4 | `item` (Report_item_name) | | 10 | `m` (int, tháng) |
| 5 | `cg` (Color_group) | | | |

### 4.2. `ton` — SỐ TỒN

| Key | Kiểu | Ý nghĩa |
|:---|:---|:---|
| `cols` / `data` | columnar | Overview tồn đã GROUP BY. **18 cột** (xem dưới). |
| `product_meta` | `{ "MaHang§Operation": [13 phần tử] }` | Metadata **cấp SKU** (1 SKU = MaHang + Operation). Xem map dưới. |
| `store_product_sizes` | columnar | Bán & Tồn tới từng Size của từng (Cửa hàng, SKU). **5 cột**. Nguồn dựng `STORE_DATA_MAP` client-side. |
| `warehouse_skus` | `{ kho_chính: { item: [sku…] } }` | SKU tồn tại 5 kho chính. sku = `{mh, op, key, qty, sizes:{size:qty}}`. Dùng Sheet 2. |
| `sizes` | `{ dict_idx(item): [[dict_idx(size), qty], …] }` | Tổng size theo Tên hàng (mọi vị trí). Dùng "Dãy size tổng". |
| `brand_counts` | `{ brand: { item_count, sku_count } }` | `item_count` = số Report_item_name khác nhau; `sku_count` = số **(MaHang, Operation)** khác nhau. |
| `item_attributes` | `{ item: { forms, styles, colors, sub_brands: {value: qty} } }` | **⚠️ Engine hiện chưa dùng.** |

**`ton.cols`** (18): `has_lc/qty` là int, `y` không có; còn lại là chỉ số DICT.

| idx | tên | giá trị |
|:--:|:---|:---|
| 0 | `rk` | `'CH'` \| `'KHO'` |
| 1 | `rg` | Region gốc (trộn khu vực CH + tên kho) |
| 2 | `wh` | KHO → 1 trong 5 kho chính hoặc `'Kho khác'`; CH → `'Cửa hàng'` |
| 3 | `br` | 5 brand chính + `'Khác'` |
| 4 | `pg` | Product_group |
| 5 | `gr` | Group_Report |
| 6 | `item` | Report_item_name |
| 7 | `cg` | Color_group |
| 8 | `form` | |
| 9 | `style` | |
| 10 | `attr` | Attribute |
| 11 | `dist_cat` | `prep` \| `new_dist` \| `pp_6m` \| `pp_1y` \| `pp_2y` \| `pp_over_2y` \| `special` |
| 12 | `sold_cat` | `sold_30` \| `sold_60` \| `sold_90` \| `not_sold_90` |
| 13 | `has_lc` | 0 \| 1 (int) — mã vừa nhận Lệnh luân chuyển |
| 14 | `size_prof` | khoá bộ cặp size (bra / chemise_men / women_alpha / pants_numeric / alpha / other) |
| 15 | `status` | `'Nguyên giá'` \| `'Sale'` \| `'Thanh lý'` |
| 16 | `qty` | `SUM(Qty_TonKho)` (int) |
| 17 | `catg` | 6 nhóm hàng (xem §5.6) |

**`ton.product_meta["MaHang§Operation"]`** — 14 phần tử:

| idx | nội dung | kiểu |
|:--:|:---|:---|
| 0 | tên hàng (Report_item_name) | dict idx |
| 1 | Group_Report | dict idx |
| 2 | brand (đã map) | dict idx |
| 3 | Form | dict idx |
| 4 | Style | dict idx |
| 5 | Color_group | dict idx |
| 6 | **Đơn giá** | **float** (Price) |
| 7 | cờ bán (`sold_30`…`not_sold_90`) — **theo MaHang** | dict idx |
| 8 | Dist_plan gốc (vd `T09.2024`, `Thanh lý`) | dict idx |
| 9 | nhóm tuổi PP (`prep`…`special`) | dict idx |
| 10 | cờ LC (0/1) — **theo MaHang** | int |
| 11 | Status | dict idx |
| 12 | nhóm hàng (6 cat_group) | dict idx |
| 13 | **Operation** | dict idx |

> Vì key gồm cả Operation, các thuộc tính 3/4/5/6/8/9/11 là **chính xác từng SKU** (F_DataTracking 1:1 trên `item_code+Operation`), không cần "(nhiều)".

**`ton.store_product_sizes.cols`** (5):

| idx | tên | giá trị |
|:--:|:---|:---|
| 0 | `st` | Store_name (đã loại 9 kho có tên) |
| 1 | `sku` | chuỗi `"MaHang§Operation"` (dict idx) |
| 2 | `sz` | Size |
| 3 | `ban` | Qty_Ban năm hiện tại (int) |
| 4 | `ton` | Qty_TonKho (int) |

---

## 5. QUY TẮC NGHIỆP VỤ

### 5.1. SKU = MaHang + Operation
1 MaHang có thể nhiều Operation với thuộc tính khác nhau (Form/Style/Màu/Giá/Kỳ PP…). Số liệu **không bị double** (mọi tổng hợp là GROUP BY SUM), nhưng để hiển thị đúng thuộc tính, các bảng **cấp SKU** dùng khoá `MaHang§Operation`:
- **Sheet 4 Tồn** (bảng SKU chi tiết), **Sheet 2 Tồn** (cây phân cấp — dòng con), **Sheet 3 Tồn** (Top bán chậm — dòng con), **modal Soi Size**.
- **Cách hiển thị "theo cặp":** sắp `(Tên hàng → MaHang → Operation)` sao cho **mọi Operation của 1 MaHang đứng liền nhau**, in MaHang ở dòng đầu nhóm + đường kẻ ngăn, các dòng còn lại chỉ có `Op xxx`.
- `brand_counts."Số Mã hàng"` = số `(MaHang, Operation)` phân biệt (~11.711).

### 5.2. 5 Brand chính
`Hiệu An Phước` · `Hiệu Pierre Cardin` · `Hiệu An Phước Ladies` · `Hiệu Bonjour` · `Hiệu Anamai`. Còn lại → `'Khác'`.
**Map Ladies:** `Brand = 'Hiệu An Phước' AND Gender = 'Nữ'` → `'Hiệu An Phước Ladies'`.

### 5.3. 5 Khu vực chính (bỏ Event khỏi phân tích khu vực)
`TP. HCM` · `Miền Tây` · `Miền Đông` · `Miền Trung - TN` · `Hà Nội`. (`Event` chỉ hiện ở tổng "Toàn HT".)

### 5.4. 5 Kho chính
`Kho AP` · `Kho PIE` · `Kho TB3 đồ lót` · `Kho CNHN` · `Kho Tổng hợp`. Kho khác → `'Kho khác'`.
Trong `InventorySize.Region` trộn lẫn khu vực CH và kho → pipeline sinh `rk` (`'CH'`/`'KHO'`).

### 5.5. `price_type` (loại giá bán)
`Nguyên giá` · `Sale` · `Thanh lý` (từ `Status`) + `Hợp đồng` (khi `SalesSource = 'Contract'`, đè lên Status).
*Sheet 1: bộ lọc "Nguồn bán" chỉ còn `Bán Lẻ` / `Tất cả`; bộ lọc "Loại giá" không còn `Hợp đồng` — vì các bảng Sheet 1 là số bán lẻ, chọn HĐ sẽ ra 0. Thẻ "SL Bán Hợp đồng" luôn hiện độc lập.*

### 5.6. 6 nhóm hàng (`cat_group` / `catg`) — Bước 1 của Sheet 4
Công thức CASE (khớp giữa `aggregate_ban.attr_sql` và `aggregate_ton.classify_cat_group`), xét theo thứ tự:
1. `Nhóm Golf` — `Group_Report` hoặc `Report_item_name` chứa "golf"
2. `Nhóm Đồ da` — `Group_Report` hoặc `Product_group` chứa "da"
3. `Nhóm Phụ kiện khác` — `Group_Report` chứa: phụ kiện / cà vạt / khăn / nón / tất / vớ
4. `Nhóm Anamai / Bonjour` — `Brand ∈ {Hiệu Anamai, Hiệu Bonjour}` hoặc `Group_Report` chứa "đồ lót" / "nội y"
5. `Nhóm chủ đạo` — `Group_Report ∈ {Chemise, Áo Thun, Quần Tây, Quần Kaki, Quần Short, Áo Khoác, Suit}`
6. `Nhóm Quần áo khác` — còn lại

### 5.7. Tuổi phân phối (`dist_cat`) — parse `Dist_plan`
Kỳ hiện tại = tháng M / năm Y (theo ngày build). `diff = (Y-year)*12 + (M-month)`:
| `dist_cat` | điều kiện | | `dist_cat` | điều kiện |
|:---|:---|---|:---|:---|
| `prep` | diff < 0 (KHPP tương lai) | | `pp_1y` | 12 ≤ diff ≤ 23 |
| `new_dist` | 0 ≤ diff ≤ 5 (mới PP) | | `pp_2y` | 24 ≤ diff ≤ 35 |
| `pp_6m` | 6 ≤ diff ≤ 11 | | `pp_over_2y` | diff ≥ 36 |
| `special` | `Dist_plan` là chữ (H.Đồng, Thanh Lý, Chưa PP…) hoặc rỗng / không parse được | | | |

### 5.8. Cờ bán gần đây (`sold_cat`) — theo MaHang
Từ `cache_sales`: `sold_30` (bán tháng M), `sold_60` (bán từ M-1), `sold_90` (bán từ M-2), `not_sold_90` (không). *(Xấp xỉ theo tháng lịch, không phải cửa sổ lăn theo ngày.)*

### 5.9. "Kỳ xem" (Sheet 2/3/4 Số Bán)
Control `[Lũy kế đến T{ref}] [Theo tháng ▾]`. Mặc định **Lũy kế** = cộng T1..T{ref_month} năm hiện tại. **Theo tháng** = đúng 1 tháng. Logic ở `Report_Engine.js`: object `PERIODS` + `setPeriodMode/setPeriodMonth/periodMonthsFor/periodLastMonth/periodLabelFor`. MoM = tháng cuối kỳ vs tháng liền trước; YoY = cùng cửa sổ năm trước.

---

## 6. FRONTEND — 2 Phần × 4 Sheet

`Report_Template.html`: `#btn-part-ban` / `#btn-part-ton` → `#sec-{part}-sheet{1..4}`. `switchSheet()` ẩn/hiện section và gọi hàm render.

### PHẦN 1 — SỐ BÁN

| Sheet | Section | Hàm render chính | Đọc payload | Nội dung |
|:--|:--|:--|:--|:--|
| 1. Tổng quan HTCH & Brand | `sec-ban-sheet1` | `renderBanSheet1`, `renderBan1TrendChart` | `ban.ov` | Lọc năm/tháng/nguồn/loại giá. 8 thẻ KPI (**thẻ MoM/YoY hiển thị SỐ LƯỢNG kỳ đối chiếu**, % + chênh lệch ở dòng phụ). Bảng 5 brand. Biểu đồ 3 năm. Ma trận Khu vực × Brand (Qty / TB-CH). |
| 2. Phân tích Bán chạy | `sec-ban-sheet2` | `renderBanSheet2` → `…TopStores` + `…TopStoresByRegion` + `…TopSkusByItem` | `ban.ov` (tính lại), `ban.top_fullprice_brand_item[kỳ]` | Control **Kỳ xem**. Top 20 / Bottom 20 CH Nguyên giá (bottom loại Event + CH đóng cửa). Top 5 CH theo Khu vực × Brand. Top 5 mã theo Brand × Tên hàng — **accordion** (bấm mới xổ 5 mã). |
| 3. Cấp Cửa hàng & Khu vực | `sec-ban-sheet3` | `renderBanSheet3`, `renderBan3TrendChart`, `renderBan3TopSkus` | `ban.ov` (tính lại KPI/hạng/bảng brand), `ban.top_fullprice_store_brand_item` | Lọc Khu vực / Cửa hàng + control **Kỳ xem**. KPI (Tổng/Nguyên giá/Sale/Thanh lý/**HĐ**/Đổi). Bảng 5 brand **MoM/YoY tính thật**. Thứ hạng KV & Toàn HT (tính lại theo kỳ). Biểu đồ 3 năm. Top 5 mã tại CH — **gộp theo Brand → Tên hàng (accordion 2 cấp)**. |
| 4. Chi tiết Thuộc tính | `sec-ban-sheet4` | `renderBanSheet4`, `renderAttrComparison` | `ban.attr_sales` | **Bước 1**: 6 nhóm hàng (`setBan4CatGroup`). Bước 2–5: cascade Khu vực → Brand → Nhóm BC → Tên hàng. **Bước 6**: chọn thuộc tính soi (Form/Style/Màu). Control **Kỳ xem** (lọc cả 3 cột năm — 3 năm gần nhất, tính động). |

### PHẦN 2 — SỐ TỒN

| Sheet | Section | Hàm render chính | Đọc payload | Nội dung |
|:--|:--|:--|:--|:--|
| 1. Tồn kho Tổng hợp | `sec-ton-sheet1` | `renderTonSheet1`, `renderTon1LocationTable`, `renderTon1Matrix` | `ton.data`, `ton.brand_counts` | 6 thẻ KPI (tổng / NG / Sale / TL / tại CH / tại Kho). Bảng 5 brand (**Số Tên hàng / Số SKU = MaHang+Operation**). Bảng vị trí: 5 khu vực CH + dòng "KHO TỔNG" bấm bung 5 kho. Ma trận Khu vực × Brand (lọc theo trạng thái giá). |
| 2. Tồn Kho Tổng (5 kho) | `sec-ton-sheet2` | `renderTonSheet2`, `renderTonSheet2Hierarchy` | `ton.data`, `ton.warehouse_skus`, `ton.product_meta`, `ton.sizes` | 4 KPI + 5 card kho. Cây phân cấp: **Tên hàng** (Nhóm BC · Brand · `N mã · N SKU` · Tổng tồn · Dãy size tổng) → bấm bung → **SKU (MaHang · Op)** theo cặp, thuộc tính từ `product_meta[MaHang§Op]`, cột Kỳ PP = `dist_plan_raw` + badge nhóm tuổi. Chỉ 5 kho chính. |
| 3. Tồn kho HTCH | `sec-ton-sheet3` | `renderTonSheet3`, `renderTon3Age`, `renderTon3SlowMoving` | `ton.data` (region/all) hoặc `STORE_DATA_MAP` + `product_meta` (per-store) | Lọc Khu vực → Cửa hàng (danh sách CH lọc theo khu vực qua `ban.ov`). 5 KPI. Cơ cấu 6 nấc tuổi tồn. Bảng 5 brand. **Top mã bán chậm tồn cao** — gộp `Brand · Tên hàng` (`N mã · N CH`) → bấm "Xem mã hàng" → chi tiết **SKU (MaHang · Op)** theo cặp + Cửa hàng + Kiến nghị. |
| 4. Chi tiết Tồn & Gãy Size | `sec-ton-sheet4` | `renderTonSheet4`, `renderTon4SummaryTable`, `openSizeModal` | `STORE_DATA_MAP` + `product_meta` + `ton.data` (summary) | **Bước 1**: 6 nhóm hàng (`setTon4CatGroup`, có nút "Tất cả nhóm"). 8 bộ lọc (Khu vực/CH/Trạng thái/Brand/Nhóm BC/Tên hàng/Cảnh báo bán/Tuổi tồn) + ô tìm kiếm. Bảng tổng hợp Brand–Tên hàng (đồng bộ theo CH/Khu vực). Bảng SKU chi tiết **theo cặp MaHang · Op** (chỉ SKU còn tồn), có nút **🔍 Soi Size** → modal đối soát Bán/Tồn từng size + cảnh báo **đứt size** (bán > 0 nhưng tồn = 0). |

### Helper quan trọng trong `Report_Engine.js`
| Hàm | Vai trò |
|:---|:---|
| `switchPart` / `switchSheet` | điều hướng 2 Phần × 4 Sheet |
| `buildStore360Index()` | dựng `STORE_DATA_MAP` từ `ton.store_product_sizes` (1 lần, lazy). `items` khoá theo `MaHang§Operation`, lưu kèm `{mh, op}`. |
| `splitSku(key)` | tách `"MaHang§Operation"` → `[mh, op]` |
| `dictIndex(s)` / `DICT_MAP` | tra ngược DICT (Map, thay `DICT.indexOf` O(n)) |
| `PERIODS`, `setPeriodMode`, `setPeriodMonth`, `periodMonthsFor`, `periodLastMonth`, `periodLabelFor` | "Kỳ xem" cho Sheet 2/3/4 |
| `scanBanStorePeriod(k)` | quét `ban.ov` 1 lượt → chỉ số theo cửa hàng cho kỳ đang chọn (Sheet 2/3) |
| `fmtNum`, `fmtPct`, `getBadgePct`, `metaPriceStr`, `emptyRow` | định dạng hiển thị |
| `classify_cat_group` (Python, `Aggregate_Inventory.py`) | phân 6 nhóm hàng — phải giữ khớp với CASE trong `aggregate_ban.attr_sql` |

---

## 7. Deploy lên Google Drive (giữ nguyên link)

1. Mở **Google Drive** trên web.
2. Chuột phải file `BaoCao_TongHop.html` cũ → **Quản lý phiên bản** (Manage versions).
3. **Tải phiên bản mới lên** → chọn `D:\AnPhuocGroup\AnPhuoc_Data\01.Python_Projects\04.Output\Report_Summary\BaoCao_TongHop.html`.
4. Link chia sẻ **không đổi**; người nhận tải lại là có số mới.

Người xem: tải file về → double-click mở bằng trình duyệt → chờ 1–2 giây giải nén → dùng 100% offline.

---

## 8. Điểm đã biết / nợ kỹ thuật

| # | Vấn đề | Ghi chú |
|:--|:---|:---|
| 1 | **`Template/Report_Segments.js` được nhúng nhưng KHÔNG dùng** (`SEGMENTS` = 0 tham chiếu trong engine). | ~2 KB JS chết mỗi build. Hoặc nối `applySegment()` theo `DESIGN.md §6`, hoặc bỏ dòng nhúng trong `Render_Html_Output.py`. |
| 2 | **Payload thừa (tính nhưng frontend chưa đọc):** `ban.active_stores`, `ban.return_analysis`, `ton.item_attributes`. | Giữ lại làm sẵn cho các sheet tương lai (TB/CH, Đổi trả, drill thuộc tính). Bỏ nếu cần giảm dung lượng. |
| 3 | **File `dist` ~13 MB**, vượt mục tiêu "< 15 MB để tải nhanh" của DESIGN nhưng vẫn < 15. Chi phối: `store_product_sizes` (~1,97M dòng) + `attr_sales` (có chiều tháng) + `ban.ov`. | Nếu cần nhẹ hơn: giảm `store_product_sizes` (chỉ dòng cần đối soát size), hoặc bỏ chiều tháng của `attr_sales`. |
| 4 | **`STORE_DATA_MAP` lẫn một số "kho" vào danh sách cửa hàng** (vd "Kho Chi nhánh Hà Nội", "Kho Tổng hợp (NG-S-TL)"). SQL `store_product_sizes` chỉ loại 9 tên kho cố định. | Chỉ ảnh hưởng Sheet 3/4 Tồn (dòng chi tiết). Mở rộng danh sách loại trừ hoặc lọc `Store_name NOT LIKE 'Kho %'`. |
| 5 | **`DESIGN.md` đã lỗi thời** ở nhiều chỗ (mô tả 8 sheet khác tên, thanh phân khúc, cấu trúc `ov` 16 cột…). | Tài liệu này (`ARCHITECTURE.md`) là bản đúng. `README.md` vẫn dùng được. |
| 6 | `Sales_Cache.parquet` ~110 MB nằm trong `database/`. | Là trung gian. Stage 1 tự dựng lại khi nguồn thay đổi hoặc khi file không tồn tại (~1–2 phút). Xoá tay cũng không sao. |

---

## 9. Lịch sử thay đổi lớn (tóm tắt)

- **Dựng lại kiến trúc sạch:** bỏ `frontend/` (FastAPI/standalone cũ), `build_cache.py`, `build_data.py`. Pipeline 5 stage + payload columnar + dict encoding.
- **Số Bán:** thêm `price_type`/`txn_type` vào `ov`; sửa xếp hạng cửa hàng (gom theo Store, `arg_max` khu vực, chỉ giao dịch "Bán"); sửa `store_metrics.hd` (`SalesSource='Contract'`); thẻ HĐ/Đổi tính độc lập bộ lọc; bỏ option "Hợp đồng" gây trắng Sheet 1; thẻ MoM/YoY hiển thị số lượng.
- **Kỳ xem:** Sheet 2/3/4 có control Lũy kế / Theo tháng. `attr_sales` +cột `m`; `top_fullprice_brand_item` theo từng kỳ. Sheet 2/3 tính lại trực tiếp từ `ov` (bỏ 3 bảng pre-agg). `ov` rút còn 9 cột (bỏ `rk/pg/gr/item` không dùng) → 577k → 89k dòng.
- **Accordion:** Sheet 2 & Sheet 3 các bảng "Top 5 mã theo tên hàng" thu gọn, bấm mới xổ; Sheet 3 gộp thêm cấp Brand.
- **Số Tồn:** thêm cột `catg` (6 nhóm hàng) + Bước 1 cho Sheet 4 Tồn; cây phân cấp Sheet 2 & Top bán chậm Sheet 3 sửa cấu trúc, cột Kỳ PP dùng `dist_plan_raw`; Sheet 4 chỉ lấy mã còn tồn; đồng bộ bảng tổng hợp theo cửa hàng.
- **SKU = MaHang + Operation (Option B):** `product_meta` khoá `MaHang§Operation`, `store_product_sizes` gộp cột `sku`, `warehouse_skus` khoá theo SKU, `brand_counts.sku_count` = distinct (MaHang, Operation). Hiển thị "theo cặp": mọi Operation của 1 MaHang liền nhau rồi mới sang MaHang khác. Modal Soi Size drill đúng SKU.
- **Đổi tên** `build.py` → `Run_Build_Summary.py`.
- **Tự phát hiện dữ liệu bán mới:** `Refresh_Sales_Cache` so kỳ + số dòng nguồn ↔ cache, tự nạp lại khi cần → không cần `--force-cache` khi thêm tháng.
- **Bỏ HARDCODE năm ở frontend:** `Report_Engine.js` + `Report_Template.html` không còn `2024/2025/2026` cố định. Mọi năm/nhãn/dropdown/biểu đồ/bảng so sánh lấy từ `refYearsList()` = `[ref.year, ref.year-1, ref.year-2]`. Có năm 2027 → **chỉ cần thả parquet + chạy build**, không sửa code.

---
*Đối chiếu dữ liệu: mỗi lần build, Stage 4 VALIDATE phải in `>>> VALIDATE OK` với lệch Bán & Tồn = 0.0000%.*

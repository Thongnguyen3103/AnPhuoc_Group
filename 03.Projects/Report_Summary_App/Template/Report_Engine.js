/**
 * ENGINE.JS — TRÌNH ĐIỀU KHIỂN BÁO CÁO TỔNG HỢP AN PHƯỚC
 * Kiến trúc 2 Phần Chính & 8 Sheet Chuyên Sâu:
 * - PHẦN 1: SỐ BÁN (4 Sheets)
 *   + Sheet 1: Tổng quan HTCH & Brand
 *   + Sheet 2: Phân tích Bán chạy
 *   + Sheet 3: Cấp Cửa hàng & Khu vực
 *   + Sheet 4: Chi tiết Thuộc tính theo 6 nhóm hàng
 * - PHẦN 2: SỐ TỒN (4 Sheets)
 *   + Sheet 1: Tồn kho Tổng hợp
 *   + Sheet 2: Tồn Kho Tổng (5 kho)
 *   + Sheet 3: Tồn kho HTCH
 *   + Sheet 4: Chi tiết Tồn & Gãy Size
 * Offline 100%, DecompressionStream client-side, zero CDN.
 */

// =============================================================================
// GLOBAL STATE & CONSTANTS
// =============================================================================
let APP_DATA = null;
let DICT = [];
let CURRENT_PART = 'ban';
let CURRENT_SHEET = 'sheet1';

const BRAND_MAIN_5 = ['Hiệu An Phước', 'Hiệu Pierre Cardin', 'Hiệu An Phước Ladies', 'Hiệu Bonjour', 'Hiệu Anamai'];
const REGION_MAIN_5 = ['TP. HCM', 'Miền Tây', 'Miền Đông', 'Miền Trung - TN', 'Hà Nội'];
const WAREHOUSE_MAIN_5 = ['Kho AP', 'Kho PIE', 'Kho TB3 đồ lót', 'Kho CNHN', 'Kho Tổng hợp'];

// Nhãn nhóm tuổi phân phối (mã dist_cat -> chữ)
const DIST_LABELS = {
  prep: 'Chuẩn bị PP',
  new_dist: 'Mới PP (0-5th)',
  pp_6m: 'PP 6 tháng',
  pp_1y: 'PP 1 năm',
  pp_2y: 'PP 2 năm',
  pp_over_2y: 'PP > 2 năm',
  special: 'Không theo cửa sổ'
};

let STORE_DATA_MAP = null; // { store_name: { salesTotal, stockTotal, items: { mh: { ban, ton, sizes: { sz: { ban, ton } } } } } }
let DICT_MAP = null;       // Map<chuỗi, index> — tra ngược DICT nhanh (thay DICT.indexOf O(n))
let CURRENT_BAN1_MATRIX_MODE = 'qty'; // 'qty' | 'avg'
let CURRENT_BAN4_CAT_GROUP = 'Nhóm chủ đạo';
let CURRENT_TON4_CAT_GROUP = 'all'; // Sheet 4 Tồn — lọc theo nhóm hàng ('all' | 'Nhóm chủ đạo' | ...)
let TON1_KHO_EXPANDED = false;

// =============================================================================
// HELPER FORMATTERS
// =============================================================================
function fmtNum(n) {
  if (n === null || n === undefined || isNaN(n)) return '0';
  return Math.round(n).toLocaleString('vi-VN');
}

// Tra ngược 1 chuỗi -> index trong DICT (build 1 lần, dùng lại)
function dictIndex(s) {
  if (!DICT_MAP) {
    DICT_MAP = new Map();
    for (let i = 0; i < DICT.length; i++) {
      if (!DICT_MAP.has(DICT[i])) DICT_MAP.set(DICT[i], i);
    }
  }
  const v = DICT_MAP.get(s);
  return v === undefined ? -1 : v;
}

// Đơn giá cấp Mã hàng: -1 = các Operation có nhiều giá khác nhau (xem Option C)
function metaPriceStr(price) {
  if (price === undefined || price === null) return '—';
  if (price < 0) return '(nhiều giá)';
  return fmtNum(price) + 'đ';
}

// Dòng thông báo "không có dữ liệu" dùng chung cho tbody/khối
function emptyRow(colspan, msg) {
  return `<tr><td colspan="${colspan}" style="text-align: center; padding: 22px; color: var(--text-muted); font-size: 13px;">${msg || 'Không có dữ liệu phù hợp với bộ lọc hiện tại.'}</td></tr>`;
}

// 3 năm gần nhất theo kỳ tham chiếu: [năm hiện tại, năm-1, năm-2]. KHÔNG hardcode.
function refYearsList() {
  const y = APP_DATA.ref.year;
  return [y, y - 1, y - 2];
}
function yy(y) { return "'" + String(y).slice(-2); }   // 2027 -> '27

// =============================================================================
// "KỲ XEM" — dùng chung cho Sheet 2 / 3 / 4 Số Bán
//   mode 'ytd'   -> lũy kế T1..T{ref.month} của năm hiện tại
//   mode 'month' -> đúng 1 tháng đã chọn
// =============================================================================
const PERIODS = {
  ban2: { mode: 'ytd', month: null, _render: null },
  ban3: { mode: 'ytd', month: null, _render: null },
  ban4: { mode: 'ytd', month: null, _render: null }
};
function periodMonthsFor(k) {
  const p = PERIODS[k], rm = APP_DATA.ref.month;
  return (p.mode === 'month' && p.month) ? [p.month] : Array.from({ length: rm }, (_, i) => i + 1);
}
function periodLastMonth(k) {
  const p = PERIODS[k];
  return (p.mode === 'month' && p.month) ? p.month : APP_DATA.ref.month;
}
function periodLabelFor(k) {
  const p = PERIODS[k];
  return (p.mode === 'month' && p.month)
    ? `Tháng ${p.month}/${APP_DATA.ref.year}`
    : `Lũy kế T1–T${APP_DATA.ref.month}/${APP_DATA.ref.year}`;
}
function initPeriodControl(k, renderFn) {
  PERIODS[k]._render = renderFn;
  const sel = document.getElementById(`${k}-period-month-sel`);
  if (sel && !sel.options.length) {
    for (let m = 1; m <= APP_DATA.ref.month; m++) {
      const o = document.createElement('option');
      o.value = m; o.textContent = `Tháng ${m}`;
      if (m === APP_DATA.ref.month) o.selected = true;
      sel.appendChild(o);
    }
  }
}
function setPeriodMode(k, mode) {
  const p = PERIODS[k];
  p.mode = mode;
  const btnY = document.getElementById(`${k}-period-ytd`);
  const btnM = document.getElementById(`${k}-period-month`);
  const sel = document.getElementById(`${k}-period-month-sel`);
  if (btnY) btnY.classList.toggle('active', mode === 'ytd');
  if (btnM) btnM.classList.toggle('active', mode === 'month');
  if (sel) sel.disabled = (mode !== 'month');
  if (mode === 'month' && !p.month && sel) p.month = parseInt(sel.value) || APP_DATA.ref.month;
  if (p._render) p._render();
}
function setPeriodMonth(k) {
  const p = PERIODS[k];
  const sel = document.getElementById(`${k}-period-month-sel`);
  p.month = parseInt(sel.value);
  p.mode = 'month';
  const btnY = document.getElementById(`${k}-period-ytd`);
  const btnM = document.getElementById(`${k}-period-month`);
  if (btnY) btnY.classList.remove('active');
  if (btnM) btnM.classList.add('active');
  if (sel) sel.disabled = false;
  if (p._render) p._render();
}

function fmtPct(p, showPlus = true) {
  if (p === null || p === undefined || isNaN(p)) return '—';
  const sign = p > 0 && showPlus ? '+' : '';
  return `${sign}${p.toFixed(1)}%`;
}

function getBadgePct(p) {
  if (p === null || p === undefined || isNaN(p)) {
    return `<span class="tag-badge tag-neutral">—</span>`;
  }
  if (p > 0) {
    return `<span class="tag-badge tag-up">+${p.toFixed(1)}%</span>`;
  } else if (p < 0) {
    return `<span class="tag-badge tag-down">${p.toFixed(1)}%</span>`;
  }
  return `<span class="tag-badge tag-neutral">0.0%</span>`;
}

// =============================================================================
// BOOTSTRAP & GZIP DECOMPRESSION
// =============================================================================
document.addEventListener('DOMContentLoaded', async () => {
  try {
    let bytes;
    if (window.REPORT_PAYLOAD_URL) {
      // Chế độ Web app (Report_Summary_App): tải payload gzip từ máy chủ
      document.getElementById('loading-text').textContent = 'Đang tải dữ liệu từ máy chủ...';
      const res = await fetch(window.REPORT_PAYLOAD_URL, { credentials: 'same-origin' });
      if (res.status === 401) { window.location.href = '/login'; return; }
      if (!res.ok) throw new Error(`Máy chủ trả lỗi ${res.status}`);
      bytes = new Uint8Array(await res.arrayBuffer());
      document.getElementById('loading-text').textContent = 'Đang giải nén dữ liệu báo cáo...';
    } else {
    const payloadEl = document.getElementById('payload');
    if (!payloadEl) throw new Error('Không tìm thấy thẻ payload!');

    const b64Data = payloadEl.textContent.trim();
    if (!b64Data) throw new Error('Dữ liệu payload trống!');

    document.getElementById('loading-text').textContent = 'Đang giải nén dữ liệu báo cáo...';

    const binStr = atob(b64Data);
    const len = binStr.length;
    bytes = new Uint8Array(len);
    for (let i = 0; i < len; i++) {
      bytes[i] = binStr.charCodeAt(i);
    }
    }

    let jsonStr = '';
    if (typeof DecompressionStream !== 'undefined') {
      const ds = new DecompressionStream('gzip');
      const writer = ds.writable.getWriter();
      writer.write(bytes);
      writer.close();
      const response = new Response(ds.readable);
      jsonStr = await response.text();
    } else {
      throw new Error('Trình duyệt không hỗ trợ DecompressionStream.');
    }

    document.getElementById('loading-text').textContent = 'Đang khởi tạo các module báo cáo...';
    APP_DATA = JSON.parse(jsonStr);
    DICT = APP_DATA.dict;

    // Metadata
    document.getElementById('badge-ref-date').textContent = `📅 Kỳ báo cáo: ${APP_DATA.ref.label}`;
    document.getElementById('badge-build-time').textContent = `🕒 Dữ liệu: ${APP_DATA.built}`;

    // Khởi tạo các bộ lọc chung
    initFilterOptions();

    // Mặc định mở Phần 1: Số Bán - Sheet 1
    switchPart('ban');

    // Ẩn loading overlay
    const overlay = document.getElementById('loading-overlay');
    overlay.style.opacity = '0';
    setTimeout(() => { overlay.style.display = 'none'; }, 300);

  } catch (err) {
    console.error('Khởi động thất bại:', err);
    document.getElementById('loading-text').textContent = `Lỗi tải dữ liệu: ${err.message}`;
    document.getElementById('loading-text').style.color = '#ef4444';
  }
});

// =============================================================================
// NAVIGATION CONTROLLER: 2 PARTS & 8 SHEETS
// =============================================================================
function switchPart(partId) {
  CURRENT_PART = partId;

  // Cập nhật nút phần chính
  document.querySelectorAll('.part-btn').forEach(b => b.classList.remove('active'));
  const btn = document.getElementById(`btn-part-${partId}`);
  if (btn) btn.classList.add('active');

  // Toggle subnav
  const navBan = document.getElementById('sheet-nav-ban');
  const navTon = document.getElementById('sheet-nav-ton');
  if (partId === 'ban') {
    navBan.style.display = 'flex';
    navTon.style.display = 'none';
  } else {
    navBan.style.display = 'none';
    navTon.style.display = 'flex';
  }

  // Mặc định chuyển về sheet 1 của part đó
  switchSheet(partId, 'sheet1');
}

function switchSheet(partId, sheetId) {
  CURRENT_PART = partId;
  CURRENT_SHEET = sheetId;

  // Cập nhật nút sheet active
  const navEl = document.getElementById(`sheet-nav-${partId}`);
  if (navEl) {
    navEl.querySelectorAll('.sheet-btn').forEach(b => b.classList.remove('active'));
    const sBtn = document.getElementById(`btn-${partId}-${sheetId}`);
    if (sBtn) sBtn.classList.add('active');
  }

  // Ẩn tất cả 8 section
  const allSections = [
    'sec-ban-sheet1', 'sec-ban-sheet2', 'sec-ban-sheet3', 'sec-ban-sheet4',
    'sec-ton-sheet1', 'sec-ton-sheet2', 'sec-ton-sheet3', 'sec-ton-sheet4',
    'sec-ton-sheet5', 'sec-ton-sheet6'
  ];
  allSections.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.hidden = true;
  });

  // Hiện section mục tiêu
  const targetSec = document.getElementById(`sec-${partId}-${sheetId}`);
  if (targetSec) targetSec.hidden = false;

  // Trigger render tương ứng
  if (partId === 'ban') {
    if (sheetId === 'sheet1') renderBanSheet1();
    else if (sheetId === 'sheet2') renderBanSheet2();
    else if (sheetId === 'sheet3') renderBanSheet3();
    else if (sheetId === 'sheet4') renderBanSheet4();
  } else {
    if (sheetId === 'sheet1') renderTonSheet1();
    else if (sheetId === 'sheet2') renderTonSheet2();
    else if (sheetId === 'sheet3') renderTonSheet3();
    else if (sheetId === 'sheet4') renderTonSheet4();
    else if (sheetId === 'sheet5') renderTonSheet5();
    else if (sheetId === 'sheet6') renderTonSheet6();
  }
}

// =============================================================================
// PRE-INDEXING STORE & SKU LOOKUP (LAZY LOAD)
// =============================================================================
// 1 SKU = MaHang + Operation. Khóa dùng chung: "MaHang§Operation".
const PM_SEP = '§';
function splitSku(key) {
  const i = key.indexOf(PM_SEP);
  return i < 0 ? [key, ''] : [key.slice(0, i), key.slice(i + 1)];
}

function buildStore360Index() {
  if (STORE_DATA_MAP) return;
  STORE_DATA_MAP = {};

  const stSizes = APP_DATA.ton.store_product_sizes;
  if (stSizes && stSizes.fmt === 'rle2') { buildStore360IndexRle2(stSizes); return; }
  if (!stSizes || !stSizes.data) return;

  // cols: ['st','sku','sz','ban','ton'] ('sku' = "MaHang§Operation"); payload cũ dùng 'mh'
  const cols = stSizes.cols || ['st', 'mh', 'sz', 'ban', 'ton'];
  const colSt = stSizes.data[0];
  const colKey = stSizes.data[1];
  const colSz = stSizes.data[2];
  const colBan = stSizes.data[3];
  const colTon = stSizes.data[4];
  const n = colSt.length;

  for (let i = 0; i < n; i++) {
    const st = DICT[colSt[i]];
    const key = DICT[colKey[i]];
    const [mh, op] = splitSku(key);
    const sz = DICT[colSz[i]];
    const b = colBan[i];
    const t = colTon[i];

    let store = STORE_DATA_MAP[st];
    if (!store) store = STORE_DATA_MAP[st] = { salesTotal: 0, stockTotal: 0, items: {} };
    store.salesTotal += b;
    store.stockTotal += t;

    let it = store.items[key];
    if (!it) it = store.items[key] = { mh, op, ban: 0, ton: 0, sizes: {} };
    it.ban += b;
    it.ton += t;
    it.sizes[sz] = { ban: b, ton: t };
  }
}

// Giải nén store_product_sizes dạng 'rle2' (xem pack_store_sizes trong Aggregate_Inventory.py)
function buildStore360IndexRle2(p) {
  const szNames = p.szs.map(i => DICT[i]);
  let g = 0, row = 0;
  for (let s = 0; s < p.stores.length; s++) {
    const st = DICT[p.stores[s]];
    const store = STORE_DATA_MAP[st] = { salesTotal: 0, stockTotal: 0, items: {} };
    let skuPos = 0;
    for (let k = 0; k < p.slen[s]; k++, g++) {
      skuPos += p.dsku[g];
      const key = DICT[p.skus[skuPos]];
      const [mh, op] = splitSku(key);
      const it = store.items[key] = { mh, op, ban: 0, ton: 0, sizes: {} };
      for (let r = 0; r < p.glen[g]; r++, row++) {
        const b = p.ban[row], t = p.ton[row];
        it.ban += b;
        it.ton += t;
        it.sizes[szNames[p.sz[row]]] = { ban: b, ton: t };
      }
      store.salesTotal += it.ban;
      store.stockTotal += it.ton;
    }
  }
}

// =============================================================================
// FILTER INITIALIZATION
// =============================================================================
function initFilterOptions() {
  // Ban Sheet 1 Months
  const ban1Month = document.getElementById('ban1-f-month');
  if (ban1Month) {
    ban1Month.innerHTML = '<option value="all">Tất cả các tháng</option>';
    for (let m = 1; m <= 12; m++) {
      const opt = document.createElement('option');
      opt.value = m;
      opt.textContent = `Tháng ${m}`;
      if (m === APP_DATA.ref.month) opt.selected = true;
      ban1Month.appendChild(opt);
    }
  }

  // Năm báo cáo (Sheet 1) — 3 năm gần nhất theo kỳ tham chiếu, KHÔNG hardcode
  const ban1Year = document.getElementById('ban1-f-year');
  if (ban1Year) {
    ban1Year.innerHTML = '';
    refYearsList().forEach((y, idx) => {
      const opt = document.createElement('option');
      opt.value = y;
      opt.textContent = y;
      if (idx === 0) opt.selected = true;
      ban1Year.appendChild(opt);
    });
  }

  // Populate Store dropdowns
  buildStore360Index();
  const allStores = Object.keys(STORE_DATA_MAP || {}).sort((a, b) => a.localeCompare(b, 'vi'));

  populateStoreDropdown('ban3-f-store', allStores);
  populateStoreDropdown('ton3-f-store', allStores);
  populateStoreDropdown('ton4-f-store', allStores);
  populateQlkdDropdown('ban3-f-qlkd', allStores);
  populateQlkdDropdown('ton3-f-qlkd', allStores);

  // Populate Brands & Groups for cascading
  const brands = BRAND_MAIN_5.concat(['Khác']);
  ['ban4-f-brand', 'ton4-f-brand'].forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      el.innerHTML = '<option value="all">Tất cả Brand</option>';
      brands.forEach(b => el.innerHTML += `<option value="${b}">${b}</option>`);
    }
  });

  // Control "Kỳ xem" cho Sheet 2 / 3 / 4
  initPeriodControl('ban2', renderBanSheet2);
  initPeriodControl('ban3', renderBanSheet3);
  initPeriodControl('ban4', renderBanSheet4);

  // Khởi tạo các cấp lọc con (Group & Item)
  if (typeof onBan4BrandChange === 'function') onBan4BrandChange();
  if (typeof onTon4BrandChange === 'function') onTon4BrandChange();
}

function populateStoreDropdown(elemId, storeList) {
  const el = document.getElementById(elemId);
  if (!el) return;
  el.innerHTML = '<option value="all">Toàn khu vực (Tất cả CH)</option>';
  storeList.forEach(st => {
    const opt = document.createElement('option');
    opt.value = st;
    opt.textContent = st;
    el.appendChild(opt);
  });
}


// =============================================================================
// =============================================================================
// PHẦN 1: SỐ BÁN
// =============================================================================
// =============================================================================

// -----------------------------------------------------------------------------
// SHEET 1.1: TỔNG QUAN HTCH & BRAND
// -----------------------------------------------------------------------------
function setBan1MatrixMode(mode) {
  CURRENT_BAN1_MATRIX_MODE = mode;
  document.getElementById('ban1-matrix-mode-qty').classList.toggle('active', mode === 'qty');
  document.getElementById('ban1-matrix-mode-avg').classList.toggle('active', mode === 'avg');
  renderBanSheet1();
}

function resetBanSheet1Filters() {
  document.getElementById('ban1-f-year').value = String(APP_DATA.ref.year);
  document.getElementById('ban1-f-month').value = APP_DATA.ref.month;
  document.getElementById('ban1-f-src').value = 'Lẻ';
  document.getElementById('ban1-f-price').value = 'all';
  renderBanSheet1();
}

function renderBanSheet1() {
  const ov = APP_DATA.ban.ov;
  const nRows = ov.data[0].length;

  const selYear = parseInt(document.getElementById('ban1-f-year').value);
  const selMonthVal = document.getElementById('ban1-f-month').value;
  const selMonth = selMonthVal === 'all' ? null : parseInt(selMonthVal);
  // Nguồn bán: 'Lẻ' -> giao diện Bán lẻ; 'HĐ' -> giao diện Bán Hợp đồng riêng (không gộp chung).
  let fSrc = document.getElementById('ban1-f-src').value;
  let fPrice = document.getElementById('ban1-f-price').value;
  if (fSrc !== 'HĐ') fSrc = 'Lẻ';
  if (fPrice === 'Hợp đồng') fPrice = 'all';
  const isHd = fSrc === 'HĐ';
  document.getElementById('ban1-view-le').hidden = isHd;
  document.getElementById('ban1-view-hd').hidden = !isHd;
  document.getElementById('ban1-fg-price').style.display = isHd ? 'none' : '';
  if (isHd) { renderBan1Contract(selYear, selMonth); return; }

  const refY = APP_DATA.ref.year;
  const refM = selMonth !== null ? selMonth : APP_DATA.ref.month;

  let curRetailQty = 0;
  let prevRetailQty = 0;
  let yoy25RetailQty = 0;
  let yoy24RetailQty = 0;
  let ytdRetailQty = 0;
  let ytd25RetailQty = 0;
  let hdQty = 0;
  let retQty = 0;
  let ngRetailQty = 0;   // bán lẻ Nguyên giá trong kỳ — mẫu số Tỷ lệ Đổi trả
  let totalRetailBase = 0;

  const brandStats = {};
  BRAND_MAIN_5.forEach(b => {
    brandStats[b] = { cur: 0, prev: 0, y25: 0, y24: 0, ytd: 0, ret: 0, ng: 0 };
  });
  brandStats['Khác'] = { cur: 0, prev: 0, y25: 0, y24: 0, ytd: 0, ret: 0, ng: 0 };

  const matrixQty = {};
  const matrixStores = {};
  BRAND_MAIN_5.forEach(b => {
    matrixQty[b] = { 'TP. HCM': 0, 'Miền Tây': 0, 'Miền Đông': 0, 'Miền Trung - TN': 0, 'Hà Nội': 0, 'Event': 0, total5: 0, totalHT: 0 };
    matrixStores[b] = { 'TP. HCM': new Set(), 'Miền Tây': new Set(), 'Miền Đông': new Set(), 'Miền Trung - TN': new Set(), 'Hà Nội': new Set(), 'Event': new Set() };
  });

  const YRS = refYearsList();            // [Y0=hiện tại, Y1=-1, Y2=-2]
  const trendMonthly = {};
  YRS.forEach(y => { trendMonthly[y] = Array(12).fill(0); });

  const colY = ov.data[0];
  const colM = ov.data[1];
  const colSrc = ov.data[2];
  const colTxn = ov.data[3];
  const colPrice = ov.data[4];
  const colSt = ov.data[5];
  const colRg = ov.data[6];
  const colBr = ov.data[7];
  const colQty = ov.data[8];

  for (let i = 0; i < nRows; i++) {
    const yr = colY[i];
    const mo = colM[i];
    const src = DICT[colSrc[i]];
    const txn = DICT[colTxn[i]];
    const prc = DICT[colPrice[i]];
    const st = DICT[colSt[i]];
    const rg = DICT[colRg[i]];
    const br = DICT[colBr[i]];
    const qty = colQty[i];

    const brKey = BRAND_MAIN_5.includes(br) ? br : 'Khác';

    // Trend chart (bán lẻ các năm)
    if (src === 'Lẻ' && txn === 'Bán' && (fPrice === 'all' || prc === fPrice)) {
      if (trendMonthly[yr] && mo >= 1 && mo <= 12) {
        trendMonthly[yr][mo - 1] += qty;
      }
    }

    // Đổi trả: chỉ tính hàng NGUYÊN GIÁ bán lẻ — tỷ lệ = SL đổi NG ÷ SL bán lẻ NG.
    // KHÔNG phụ thuộc bộ lọc "Loại giá". (Qty đổi trong dữ liệu là số âm -> lấy trị tuyệt đối.)
    if (yr === selYear && (selMonth === null || mo === selMonth) && src === 'Lẻ' && prc === 'Nguyên giá') {
      if (txn === 'Đổi') {
        retQty += Math.abs(qty);
        if (brandStats[brKey]) brandStats[brKey].ret += Math.abs(qty);
      } else if (txn === 'Bán') {
        ngRetailQty += qty;
        if (brandStats[brKey]) brandStats[brKey].ng += qty;
      }
    }

    if (fSrc !== 'all' && src !== fSrc) continue;
    if (fPrice !== 'all' && prc !== fPrice) continue;

    // Chỉ tính bán lẻ cho KPI & Brand table chính
    if (src === 'Lẻ' && txn === 'Bán') {
      totalRetailBase += qty;

      // Tháng này
      if (yr === selYear && (selMonth === null || mo === selMonth)) {
        curRetailQty += qty;
        if (brandStats[brKey]) brandStats[brKey].cur += qty;

        // Ma trận Khu vực x Brand
        if (matrixQty[brKey]) {
          if (matrixQty[brKey][rg] !== undefined) {
            matrixQty[brKey][rg] += qty;
            matrixStores[brKey][rg].add(st);
            if (rg !== 'Event') matrixQty[brKey].total5 += qty;
          }
          matrixQty[brKey].totalHT += qty;
        }
      }

      // Tháng trước
      const prevM = (refM === 1) ? 12 : (refM - 1);
      const prevY = (refM === 1) ? (selYear - 1) : selYear;
      if (yr === prevY && mo === prevM) {
        prevRetailQty += qty;
        if (brandStats[brKey]) brandStats[brKey].prev += qty;
      }

      // Cùng kỳ năm -1
      if (yr === YRS[1] && (selMonth === null || mo === selMonth)) {
        yoy25RetailQty += qty;
        if (brandStats[brKey]) brandStats[brKey].y25 += qty;
      }

      // Cùng kỳ năm -2
      if (yr === YRS[2] && (selMonth === null || mo === selMonth)) {
        yoy24RetailQty += qty;
        if (brandStats[brKey]) brandStats[brKey].y24 += qty;
      }

      // Lũy kế YTD
      if (yr === selYear && mo <= refM) {
        ytdRetailQty += qty;
        if (brandStats[brKey]) brandStats[brKey].ytd += qty;
      }
      if (yr === YRS[1] && mo <= refM) {
        ytd25RetailQty += qty;
      }
    }
  }

  // 1. KPI Cards
  const momPct = prevRetailQty > 0 ? ((curRetailQty - prevRetailQty) / prevRetailQty * 100) : null;
  const momDiff = curRetailQty - prevRetailQty;
  const yoy25Pct = yoy25RetailQty > 0 ? ((curRetailQty - yoy25RetailQty) / yoy25RetailQty * 100) : null;
  const yoy25Diff = curRetailQty - yoy25RetailQty;
  const yoy24Pct = yoy24RetailQty > 0 ? ((curRetailQty - yoy24RetailQty) / yoy24RetailQty * 100) : null;
  const yoy24Diff = curRetailQty - yoy24RetailQty;
  const ytdYoyPct = ytd25RetailQty > 0 ? ((ytdRetailQty - ytd25RetailQty) / ytd25RetailQty * 100) : null;
  const returnRate = ngRetailQty > 0 ? (retQty / ngRetailQty * 100) : 0;

  document.getElementById('ban1-kpi-cur-qty').textContent = fmtNum(curRetailQty);
  document.getElementById('ban1-kpi-cur-sub').textContent = selMonth ? `Tháng ${selMonth}/${selYear}` : `Cả năm ${selYear}`;

  // Nhãn động theo 3 năm gần nhất
  const _l25 = document.getElementById('ban1-lbl-yoy25');
  if (_l25) _l25.textContent = `Cùng kỳ ${YRS[1]} (YoY${yy(YRS[1])})`;
  const _l24 = document.getElementById('ban1-lbl-yoy24');
  if (_l24) _l24.textContent = `Cùng kỳ ${YRS[2]} (YoY${yy(YRS[2])})`;

  // 3 thẻ so sánh: hiển thị SỐ LƯỢNG kỳ đối chiếu làm giá trị chính (đồng bộ các thẻ khác),
  // % thay đổi + chênh lệch đưa xuống dòng phụ.
  const cmpSub = (pct, diff) => `${getBadgePct(pct)} <span style="margin-left:4px;">${diff >= 0 ? '+' : ''}${fmtNum(diff)} sp</span>`;

  document.getElementById('ban1-kpi-mom-rate').textContent = fmtNum(prevRetailQty);
  document.getElementById('ban1-kpi-mom-diff').innerHTML = cmpSub(momPct, momDiff);

  document.getElementById('ban1-kpi-yoy25-rate').textContent = fmtNum(yoy25RetailQty);
  document.getElementById('ban1-kpi-yoy25-diff').innerHTML = cmpSub(yoy25Pct, yoy25Diff);

  document.getElementById('ban1-kpi-yoy24-rate').textContent = fmtNum(yoy24RetailQty);
  document.getElementById('ban1-kpi-yoy24-diff').innerHTML = cmpSub(yoy24Pct, yoy24Diff);

  document.getElementById('ban1-kpi-ytd-qty').textContent = fmtNum(ytdRetailQty);
  document.getElementById('ban1-kpi-ytd-yoy').textContent = `YoY${yy(YRS[1])}: ${fmtPct(ytdYoyPct)}`;

  document.getElementById('ban1-kpi-ret-qty').textContent = fmtNum(retQty);
  document.getElementById('ban1-kpi-ret-rate').textContent = `${returnRate.toFixed(1)}%`;
  const _retSub = document.getElementById('ban1-kpi-ret-sub');
  if (_retSub) _retSub.textContent = `${fmtNum(retQty)} đổi ÷ ${fmtNum(ngRetailQty)} bán NG`;

  // 2. Bảng 5 Brand chính
  const tbodyBrands = document.getElementById('ban1-table-brands-tbody');
  tbodyBrands.innerHTML = '';

  const brandsList = BRAND_MAIN_5.concat(['Khác']);
  brandsList.forEach(b => {
    const s = brandStats[b];
    const bMom = s.prev > 0 ? ((s.cur - s.prev) / s.prev * 100) : null;
    const bY25 = s.y25 > 0 ? ((s.cur - s.y25) / s.y25 * 100) : null;
    const bY24 = s.y24 > 0 ? ((s.cur - s.y24) / s.y24 * 100) : null;
    const bShare = curRetailQty > 0 ? (s.cur / curRetailQty * 100) : 0;
    const bRetRate = s.ng > 0 ? (s.ret / s.ng * 100) : 0;

    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><strong>${b}</strong></td>
      <td><strong>${fmtNum(s.cur)}</strong></td>
      <td>${fmtNum(s.prev)}</td>
      <td>${getBadgePct(bMom)}</td>
      <td>${fmtNum(s.y25)}</td>
      <td>${getBadgePct(bY25)}</td>
      <td>${fmtNum(s.y24)}</td>
      <td>${getBadgePct(bY24)}</td>
      <td><strong>${fmtNum(s.ytd)}</strong></td>
      <td>${bShare.toFixed(1)}%</td>
      <td class="ban1-ret-col">${fmtNum(s.ng)}</td>
      <td class="ban1-ret-col">${fmtNum(s.ret)}</td>
      <td class="ban1-ret-col"><span class="tag-badge ${bRetRate > 5 ? 'tag-down' : 'tag-neutral'}">${bRetRate.toFixed(1)}%</span></td>
    `;
    tbodyBrands.appendChild(tr);
  });

  // Xem số bán Sale / Thanh lý: không hiển thị Đổi trả & Tỷ lệ đổi (chỉ có nghĩa với hàng Nguyên giá)
  const showRet = fPrice === 'all' || fPrice === 'Nguyên giá';
  document.querySelectorAll('#ban1-view-le .ban1-ret-col').forEach(el => { el.style.display = showRet ? '' : 'none'; });

  // 3. Biểu đồ Tăng trưởng 3 năm
  renderBan1TrendChart(trendMonthly, YRS);

  // Bán lẻ theo QLKD
  renderBan1Qlkd(selYear, selMonth, fPrice);

  // 4. Ma trận Khu vực x Brand
  const tbodyMatrix = document.getElementById('ban1-table-matrix-tbody');
  tbodyMatrix.innerHTML = '';

  BRAND_MAIN_5.forEach(b => {
    const mq = matrixQty[b];
    const ms = matrixStores[b];

    const getVal = (rg) => {
      if (CURRENT_BAN1_MATRIX_MODE === 'avg') {
        const count = ms[rg] ? ms[rg].size : 0;
        return count > 0 ? (mq[rg] / count).toFixed(0) : '0';
      }
      return fmtNum(mq[rg]);
    };

    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><strong>${b}</strong></td>
      <td>${getVal('TP. HCM')}</td>
      <td>${getVal('Miền Tây')}</td>
      <td>${getVal('Miền Đông')}</td>
      <td>${getVal('Miền Trung - TN')}</td>
      <td>${getVal('Hà Nội')}</td>
      <td><strong>${fmtNum(mq.total5)}</strong></td>
      <td><strong>${fmtNum(mq.totalHT)}</strong></td>
    `;
    tbodyMatrix.appendChild(tr);
  });
}

// -----------------------------------------------------------------------------
// SHEET 1.1 — BÁN LẺ THEO QLKD (cửa hàng 5 khu vực, bỏ Event). Theo Năm/Tháng & Loại giá đang chọn.
// Đổi trả: chỉ hàng Nguyên giá (SL đổi NG ÷ SL bán lẻ NG) — không phụ thuộc Loại giá.
// -----------------------------------------------------------------------------
function renderBan1Qlkd(selYear, selMonth, fPrice) {
  const tb = document.getElementById('ban1-qlkd-tbody');
  if (!tb) return;
  const ov = APP_DATA.ban.ov;
  const cY = ov.data[0], cM = ov.data[1], cSrc = ov.data[2], cTxn = ov.data[3],
        cPr = ov.data[4], cSt = ov.data[5], cRg = ov.data[6], cQ = ov.data[8];
  const QM = APP_DATA.ban.store_qlkd || {};
  const YRS = refYearsList();
  const refM = selMonth !== null ? selMonth : APP_DATA.ref.month;
  const prevM = refM === 1 ? 12 : refM - 1;
  const prevY = refM === 1 ? selYear - 1 : selYear;
  const inMonth = (mo) => selMonth === null || mo === selMonth;
  const iLe = dictIndex('Lẻ'), iBan = dictIndex('Bán'), iDoi = dictIndex('Đổi'), iNG = dictIndex('Nguyên giá');
  const iPr = fPrice === 'all' ? -1 : dictIndex(fPrice);
  const iEv = dictIndex('Event');
  const Q = {};
  const get = (k) => Q[k] || (Q[k] = { rgs: new Set(), sts: new Set(), cur: 0, prev: 0, y1: 0, ytd: 0, ytd1: 0, ret: 0, ng: 0 });

  for (let i = 0; i < cY.length; i++) {
    if (cSrc[i] !== iLe || cRg[i] === iEv) continue;
    const yr = cY[i], mo = cM[i], q = cQ[i], st = DICT[cSt[i]];
    const k = QM[st] || QLKD_NONE;
    if (yr === selYear && inMonth(mo) && cPr[i] === iNG) {
      if (cTxn[i] === iDoi) get(k).ret += Math.abs(q);
      else if (cTxn[i] === iBan) get(k).ng += q;
    }
    if (cTxn[i] !== iBan || (iPr !== -1 && cPr[i] !== iPr)) continue;
    const a = get(k);
    if (yr === selYear && inMonth(mo)) { a.cur += q; a.sts.add(st); a.rgs.add(DICT[cRg[i]]); }
    if (yr === prevY && mo === prevM) a.prev += q;
    if (yr === YRS[1] && inMonth(mo)) a.y1 += q;
    if (yr === selYear && mo <= refM) a.ytd += q;
    if (yr === YRS[1] && mo <= refM) a.ytd1 += q;
  }

  const keys = Object.keys(Q).filter(k => Q[k].cur || Q[k].ytd).sort((a, b) => Q[b].cur - Q[a].cur);
  const T = { cur: 0, prev: 0, y1: 0, ytd: 0, ytd1: 0, ret: 0, ng: 0, n: 0 };
  keys.forEach(k => { ['cur', 'prev', 'y1', 'ytd', 'ytd1', 'ret', 'ng'].forEach(f => { T[f] += Q[k][f]; }); T.n += Q[k].sts.size; });
  const ch = (a, b) => (b > 0 ? (a - b) / b * 100 : null);
  const rate = (a, b) => (b > 0 ? a / b * 100 : 0).toFixed(1) + '%';
  const cells = (a, n) => `<td>${fmtNum(n)}</td><td><strong>${fmtNum(a.cur)}</strong></td><td>${fmtNum(a.prev)}</td>
    <td>${getBadgePct(ch(a.cur, a.prev))}</td><td>${fmtNum(a.y1)}</td><td>${getBadgePct(ch(a.cur, a.y1))}</td>
    <td><strong>${fmtNum(a.ytd)}</strong></td><td>${getBadgePct(ch(a.ytd, a.ytd1))}</td><td>${fmtNum(a.ret)}</td>
    <td>${rate(a.ret, a.ng)}</td><td>${rate(a.cur, T.cur)}</td>`;
  const rows = keys.map(k => {
    const a = Q[k];
    const rgTxt = REGION_MAIN_5.filter(r => a.rgs.has(r)).join(', ') || '—';
    return `<tr ${qlkdRowAttrs('ban', k)}><td><strong>${k}</strong></td><td>${rgTxt}</td>${cells(a, a.sts.size)}</tr>`;
  });
  if (rows.length) rows.push(`<tr style="background:#f8fafc;font-weight:700;"><td>Tổng</td><td></td>${cells(T, T.n)}</tr>`);
  tb.innerHTML = rows.length ? rows.join('') : emptyRow(13);
  const th = document.getElementById('ban1-qlkd-th-y1');
  if (th) th.textContent = `Cùng kỳ ${YRS[1]}`;
  const sub = document.getElementById('ban1-qlkd-sub');
  if (sub) sub.textContent = `${selMonth ? 'Tháng ' + selMonth + '/' + selYear : 'Cả năm ' + selYear}` +
    `${fPrice !== 'all' ? ' · ' + fPrice : ''} · CH 5 khu vực (bỏ Event) · bấm 1 QLKD để mở Sheet 3 xem từng cửa hàng`;
}

function renderBan1TrendChart(trendMonthly, YRS, elId) {
  const [Y0, Y1, Y2] = YRS || refYearsList();
  const chartEl = document.getElementById(elId || 'ban1-chart-trend');
  const months = ['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8', 'T9', 'T10', 'T11', 'T12'];

  const data = [
    {
      x: months,
      y: trendMonthly[Y2],
      name: 'Năm ' + Y2,
      type: 'scatter',
      mode: 'lines+markers',
      line: { color: '#94a3b8', width: 2, dash: 'dot' }
    },
    {
      x: months,
      y: trendMonthly[Y1],
      name: 'Năm ' + Y1,
      type: 'scatter',
      mode: 'lines+markers',
      line: { color: '#2563eb', width: 2.5 }
    },
    {
      x: months.slice(0, APP_DATA.ref.month),
      y: trendMonthly[Y0].slice(0, APP_DATA.ref.month),
      name: 'Năm ' + Y0,
      type: 'scatter',
      mode: 'lines+markers',
      line: { color: '#c5a059', width: 3.5 }
    }
  ];

  const layout = {
    margin: { t: 20, r: 20, b: 40, l: 50 },
    yaxis: { title: 'Số lượng bán (sp)' },
    plot_bgcolor: '#fdfdfd',
    legend: { orientation: 'h', y: 1.15 }
  };

  Plotly.newPlot(chartEl, data, layout, { responsive: true, displayModeBar: false });
}

// -----------------------------------------------------------------------------
// SHEET 1.1 — GIAO DIỆN BÁN HỢP ĐỒNG (Nguồn bán = HĐ)
// Chỉ đọc dòng src='HĐ' & Giao dịch='Bán'; bán lẻ chỉ dùng làm mẫu số "Tỷ trọng HĐ".
// -----------------------------------------------------------------------------
function renderBan1Contract(selYear, selMonth) {
  const ov = APP_DATA.ban.ov;
  const cY = ov.data[0], cM = ov.data[1], cSrc = ov.data[2], cTxn = ov.data[3],
        cSt = ov.data[5], cRg = ov.data[6], cBr = ov.data[7], cQ = ov.data[8];
  const n = cY.length;
  const YRS = refYearsList();
  const refM = selMonth !== null ? selMonth : APP_DATA.ref.month;
  const prevM = refM === 1 ? 12 : refM - 1;
  const prevY = refM === 1 ? selYear - 1 : selYear;
  const inMonth = (mo) => selMonth === null || mo === selMonth;
  const iHd = dictIndex('HĐ'), iLe = dictIndex('Lẻ'), iBan = dictIndex('Bán');

  const blank = () => ({ cur: 0, prev: 0, y1: 0, y2: 0, ytd: 0, ytd1: 0 });
  const tot = blank();
  let retailCur = 0;
  const byBr = {};
  BRAND_MAIN_5.concat(['Khác']).forEach(b => { byBr[b] = blank(); });
  const byRg = {};
  const rgStores = {};
  const bySt = {};
  const byQ = {};      // Bán HĐ theo QLKD
  const qSts = {};     // QLKD -> cửa hàng có HĐ trong kỳ
  const QM = APP_DATA.ban.store_qlkd || {};
  const trend = {};
  YRS.forEach(y => { trend[y] = Array(12).fill(0); });

  for (let i = 0; i < n; i++) {
    if (cTxn[i] !== iBan) continue;
    const yr = cY[i], mo = cM[i], q = cQ[i];
    if (cSrc[i] === iLe) {
      if (yr === selYear && inMonth(mo)) retailCur += q;
      continue;
    }
    if (cSrc[i] !== iHd) continue;
    const br = DICT[cBr[i]];
    const brKey = BRAND_MAIN_5.includes(br) ? br : 'Khác';
    const rg = DICT[cRg[i]] || '(Không rõ)';
    const st = DICT[cSt[i]] || '(Không rõ)';
    if (!byRg[rg]) { byRg[rg] = blank(); rgStores[rg] = new Set(); }
    if (!bySt[st]) bySt[st] = { st, rg, cur: 0, y1: 0, ytd: 0 };
    const qk = QM[st] || QLKD_NONE;
    if (!byQ[qk]) { byQ[qk] = blank(); byQ[qk].rgs = new Set(); qSts[qk] = new Set(); }
    const targets = [tot, byBr[brKey], byRg[rg], byQ[qk]];
    const addAll = (k) => targets.forEach(o => { o[k] += q; });

    if (trend[yr] && mo >= 1 && mo <= 12) trend[yr][mo - 1] += q;
    if (yr === selYear && inMonth(mo)) {
      addAll('cur');
      bySt[st].cur += q;
      if (q > 0) { rgStores[rg].add(st); qSts[qk].add(st); byQ[qk].rgs.add(rg); }
    }
    if (yr === prevY && mo === prevM) addAll('prev');
    if (yr === YRS[1] && inMonth(mo)) { addAll('y1'); bySt[st].y1 += q; }
    if (yr === YRS[2] && inMonth(mo)) addAll('y2');
    if (yr === selYear && mo <= refM) { addAll('ytd'); bySt[st].ytd += q; }
    if (yr === YRS[1] && mo <= refM) addAll('ytd1');
  }

  const pct = (a, b) => b > 0 ? (a - b) / b * 100 : null;
  const cmpSub = (a, b) => `${getBadgePct(pct(a, b))} <span style="margin-left:4px;">${a - b >= 0 ? '+' : ''}${fmtNum(a - b)} sp</span>`;
  const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
  const setH = (id, v) => { const el = document.getElementById(id); if (el) el.innerHTML = v; };
  const share = (v) => tot.cur > 0 ? (v / tot.cur * 100).toFixed(1) + '%' : '0.0%';

  // 1. KPI
  set('ban1hd-kpi-cur', fmtNum(tot.cur));
  set('ban1hd-kpi-cur-sub', selMonth ? `Tháng ${selMonth}/${selYear}` : `Cả năm ${selYear}`);
  set('ban1hd-kpi-mom', fmtNum(tot.prev));
  setH('ban1hd-kpi-mom-sub', cmpSub(tot.cur, tot.prev));
  set('ban1hd-lbl-y1', `Cùng kỳ ${YRS[1]} (YoY${yy(YRS[1])})`);
  set('ban1hd-kpi-y1', fmtNum(tot.y1));
  setH('ban1hd-kpi-y1-sub', cmpSub(tot.cur, tot.y1));
  set('ban1hd-lbl-y2', `Cùng kỳ ${YRS[2]} (YoY${yy(YRS[2])})`);
  set('ban1hd-kpi-y2', fmtNum(tot.y2));
  setH('ban1hd-kpi-y2-sub', cmpSub(tot.cur, tot.y2));
  set('ban1hd-kpi-ytd', fmtNum(tot.ytd));
  set('ban1hd-kpi-ytd-sub', `YoY${yy(YRS[1])}: ${fmtPct(pct(tot.ytd, tot.ytd1))}`);
  set('ban1hd-kpi-nst', fmtNum(Object.values(bySt).filter(s => s.cur > 0).length));
  const allCur = tot.cur + retailCur;
  set('ban1hd-kpi-share', allCur > 0 ? (tot.cur / allCur * 100).toFixed(1) + '%' : '0.0%');

  // 2. Bảng Thương hiệu
  set('ban1hd-th-y1', `Cùng kỳ ${yy(YRS[1])}`);
  set('ban1hd-th-y2', `Cùng kỳ ${yy(YRS[2])}`);
  const brRow = (label, s, shareTxt, style) => `<tr${style || ''}><td><strong>${label}</strong></td>
      <td><strong>${fmtNum(s.cur)}</strong></td><td>${fmtNum(s.prev)}</td><td>${getBadgePct(pct(s.cur, s.prev))}</td>
      <td>${fmtNum(s.y1)}</td><td>${getBadgePct(pct(s.cur, s.y1))}</td>
      <td>${fmtNum(s.y2)}</td><td>${getBadgePct(pct(s.cur, s.y2))}</td>
      <td><strong>${fmtNum(s.ytd)}</strong></td><td>${shareTxt}</td></tr>`;
  // Chỉ hiện thương hiệu có phát sinh HĐ — HĐ không có Anamai / Bonjour / Khác thì ẩn luôn
  const hasHd = (b) => { const s = byBr[b]; return s.cur || s.prev || s.y1 || s.y2 || s.ytd || s.ytd1; };
  const brRows = BRAND_MAIN_5.concat(['Khác']).filter(hasHd).map(b => brRow(b, byBr[b], share(byBr[b].cur)));
  brRows.push(brRow('Tổng HĐ', tot, '100%', ' style="background:#f8fafc;"'));
  setH('ban1hd-brands-tbody', brRows.join(''));

  // 3. Biểu đồ 3 năm
  renderBan1TrendChart(trend, YRS, 'ban1hd-chart-trend');

  // 4. Khu vực
  const rgOrder = REGION_MAIN_5.filter(r => byRg[r])
    .concat(Object.keys(byRg).filter(r => !REGION_MAIN_5.includes(r)));
  const rgRows = rgOrder.map(r => {
    const s = byRg[r];
    return `<tr><td><strong>${r}</strong></td><td><strong>${fmtNum(s.cur)}</strong></td><td>${fmtNum(s.prev)}</td>
      <td>${getBadgePct(pct(s.cur, s.prev))}</td><td>${fmtNum(s.y1)}</td><td>${getBadgePct(pct(s.cur, s.y1))}</td>
      <td>${fmtNum(s.ytd)}</td><td>${fmtNum(rgStores[r].size)}</td><td>${share(s.cur)}</td></tr>`;
  });
  setH('ban1hd-region-tbody', rgRows.length ? rgRows.join('') : emptyRow(9, 'Không có bán Hợp đồng trong kỳ.'));

  // 5a. Bán HĐ theo QLKD
  const qKeys = Object.keys(byQ).filter(k => byQ[k].cur || byQ[k].ytd).sort((a, b) => byQ[b].cur - byQ[a].cur);
  let qN = 0;
  const qCells = (s, n) => `<td>${fmtNum(n)}</td><td><strong>${fmtNum(s.cur)}</strong></td><td>${fmtNum(s.prev)}</td>
      <td>${getBadgePct(pct(s.cur, s.prev))}</td><td>${fmtNum(s.y1)}</td><td>${getBadgePct(pct(s.cur, s.y1))}</td>
      <td><strong>${fmtNum(s.ytd)}</strong></td><td>${getBadgePct(pct(s.ytd, s.ytd1))}</td><td>${share(s.cur)}</td>`;
  const qRows = qKeys.map(k => {
    const s = byQ[k];
    qN += qSts[k].size;
    const rgTxt = REGION_MAIN_5.filter(r => s.rgs.has(r)).join(', ') || '—';
    return `<tr ${qlkdRowAttrs('ban', k)}><td><strong>${k}</strong></td><td>${rgTxt}</td>${qCells(s, qSts[k].size)}</tr>`;
  });
  if (qRows.length) qRows.push(`<tr style="background:#f8fafc;font-weight:700;"><td>Tổng HĐ</td><td></td>${qCells(tot, qN)}</tr>`);
  setH('ban1hd-qlkd-tbody', qRows.length ? qRows.join('') : emptyRow(11, 'Không có bán Hợp đồng trong kỳ.'));
  set('ban1hd-qlkd-th-y1', `Cùng kỳ ${YRS[1]}`);

  // 5. Cửa hàng phát sinh HĐ
  const stList = Object.values(bySt).filter(s => s.cur !== 0 || s.ytd !== 0)
    .sort((a, b) => b.cur - a.cur || b.ytd - a.ytd);
  const stRows = stList.map((s, k) => `<tr><td>${k + 1}</td><td><strong>${s.st}</strong></td><td>${s.rg}</td>
      <td><strong>${fmtNum(s.cur)}</strong></td><td>${fmtNum(s.y1)}</td><td>${getBadgePct(pct(s.cur, s.y1))}</td>
      <td>${fmtNum(s.ytd)}</td><td>${share(s.cur)}</td></tr>`);
  setH('ban1hd-stores-tbody', stRows.length ? stRows.join('') : emptyRow(8, 'Không có cửa hàng phát sinh HĐ trong kỳ.'));
}

// -----------------------------------------------------------------------------
// SHEET 1.2: PHÂN TÍCH BÁN CHẠY
// -----------------------------------------------------------------------------
// Quét ban.ov 1 lần -> chỉ số theo cửa hàng cho KỲ đang chọn (Sheet 2 & Sheet 3)
function scanBanStorePeriod(k) {
  const ov = APP_DATA.ban.ov;
  const cY = ov.data[0], cM = ov.data[1], cSrc = ov.data[2], cTxn = ov.data[3],
        cPr = ov.data[4], cSt = ov.data[5], cRg = ov.data[6], cQ = ov.data[8];
  const n = cY.length;
  const refY = APP_DATA.ref.year;
  const inWin = new Array(13).fill(false);
  periodMonthsFor(k).forEach(m => inWin[m] = true);
  const lastM = periodLastMonth(k);
  const prevM = lastM > 1 ? lastM - 1 : 0;

  const S = {};
  for (let i = 0; i < n; i++) {
    const yr = cY[i];
    if (yr !== refY && yr !== refY - 1) continue;
    const rg = DICT[cRg[i]];
    if (rg === 'Event') continue;
    const st = DICT[cSt[i]];
    let o = S[st];
    if (!o) o = S[st] = { rg, total: 0, fp: 0, sale: 0, tl: 0, hd: 0, ret: 0,
                          lastFp: 0, prevFp: 0, lastTotal: 0, prevTotal: 0, yoyFp: 0, yoyTotal: 0 };
    const m = cM[i], q = cQ[i];
    const src = DICT[cSrc[i]], txn = DICT[cTxn[i]], pr = DICT[cPr[i]];
    const retail = src === 'Lẻ' && txn === 'Bán';
    if (yr === refY) {
      if (inWin[m]) {
        if (retail) {
          o.total += q;
          if (pr === 'Nguyên giá') o.fp += q;
          else if (pr === 'Sale') o.sale += q;
          else if (pr === 'Thanh lý') o.tl += q;
        }
        if (src === 'HĐ' && txn === 'Bán') o.hd += q;
        if (txn === 'Đổi') o.ret += q;
      }
      if (retail && m === lastM) { o.lastTotal += q; if (pr === 'Nguyên giá') o.lastFp += q; }
      if (retail && prevM && m === prevM) { o.prevTotal += q; if (pr === 'Nguyên giá') o.prevFp += q; }
    } else if (inWin[m] && retail) {
      o.yoyTotal += q;
      if (pr === 'Nguyên giá') o.yoyFp += q;
    }
  }
  return S;
}

function renderBanSheet2() {
  renderBanSheet2TopStores();
  renderBanSheet2TopStoresByRegion();
  renderBanSheet2TopSkusByItem();
}

function renderBanSheet2TopStores() {
  const includeClosed = document.getElementById('ban2-toggle-closed')?.checked || false;
  const S = scanBanStorePeriod('ban2');
  const rows = Object.entries(S).map(([st, o]) => ({
    st, rg: o.rg,
    qty: o.fp,
    cur: o.lastFp,
    mom: o.prevFp > 0 ? ((o.lastFp - o.prevFp) / o.prevFp * 100) : null,
    yoy: o.yoyFp > 0 ? ((o.fp - o.yoyFp) / o.yoyFp * 100) : null
  })).filter(r => r.qty > 0 || r.cur > 0);
  rows.sort((a, b) => b.qty - a.qty);

  const top20 = rows.slice(0, 20);
  const openRows = includeClosed ? rows : rows.filter(r => (r.cur || 0) > 0);
  const bot20 = openRows.slice(-20).reverse();
  const lbl = periodLabelFor('ban2');

  const paint = (tbodyId, list, danger) => {
    const tb = document.getElementById(tbodyId);
    tb.innerHTML = '';
    if (!list.length) { tb.innerHTML = emptyRow(6, `Không có cửa hàng bán nguyên giá trong kỳ (${lbl}).`); return; }
    list.forEach((s, idx) => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td><span class="tag-badge ${danger ? 'tag-down' : (idx < 3 ? 'tag-gold' : 'tag-neutral')}">#${idx + 1}</span></td>
        <td><strong>${s.st}</strong></td>
        <td>${s.rg || 'HTCH'}</td>
        <td><strong style="color: var(--${danger ? 'danger' : 'primary'});">${fmtNum(s.qty)}</strong></td>
        <td>${getBadgePct(s.mom)}</td>
        <td>${getBadgePct(s.yoy)}</td>`;
      tb.appendChild(tr);
    });
  };
  paint('ban2-table-top20-tbody', top20, false);
  paint('ban2-table-bot20-tbody', bot20, true);
}

function renderBanSheet2TopStoresByRegion() {
  const container = document.getElementById('ban2-top5-region-container');
  if (!container) return;
  container.innerHTML = '';
  const selBrand = document.getElementById('ban2-select-brand').value;

  const ov = APP_DATA.ban.ov;
  const cY = ov.data[0], cM = ov.data[1], cSrc = ov.data[2], cTxn = ov.data[3],
        cPr = ov.data[4], cSt = ov.data[5], cRg = ov.data[6], cBr = ov.data[7], cQ = ov.data[8];
  const n = cY.length;
  const refY = APP_DATA.ref.year;
  const inWin = new Array(13).fill(false);
  periodMonthsFor('ban2').forEach(m => inWin[m] = true);

  const map = {};
  for (let i = 0; i < n; i++) {
    if (cY[i] !== refY || !inWin[cM[i]]) continue;
    if (DICT[cSrc[i]] !== 'Lẻ' || DICT[cTxn[i]] !== 'Bán' || DICT[cPr[i]] !== 'Nguyên giá') continue;
    const rg = DICT[cRg[i]];
    if (REGION_MAIN_5.indexOf(rg) === -1) continue;
    if (DICT[cBr[i]] !== selBrand) continue;
    const st = DICT[cSt[i]];
    (map[rg] = map[rg] || {})[st] = (map[rg][st] || 0) + cQ[i];
  }

  REGION_MAIN_5.forEach(rg => {
    const items = Object.entries(map[rg] || {}).map(([st, qty]) => ({ st, qty }))
      .sort((a, b) => b.qty - a.qty).slice(0, 5);
    const listHtml = items.length
      ? items.map((st, idx) => `
          <div style="display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px dashed var(--border);">
            <div style="display:flex;align-items:center;gap:6px;">
              <span class="tag-badge ${idx === 0 ? 'tag-gold' : 'tag-neutral'}">#${idx + 1}</span>
              <strong style="font-size:12px;">${st.st}</strong>
            </div>
            <span style="font-weight:bold;color:var(--primary);">${fmtNum(st.qty)}</span>
          </div>`).join('')
      : '<div style="color:var(--text-muted);font-size:12px;padding:10px;">Chưa có dữ liệu trong kỳ.</div>';
    const card = document.createElement('div');
    card.className = 'view-card';
    card.style.margin = '0';
    card.style.borderTop = '3px solid var(--primary)';
    card.innerHTML = `
      <div class="view-header" style="padding:10px 14px;background:#f8fafc;">
        <strong style="color:var(--primary);">${rg}</strong>
        <span class="tag-badge tag-gold">Top 5 CH</span>
      </div>
      <div class="view-body" style="padding:10px 14px;">${listHtml}</div>`;
    container.appendChild(card);
  });
}

function renderBanSheet2TopSkusByItem() {
  const container = document.getElementById('ban2-top5-skus-container');
  if (!container) return;
  container.innerHTML = '';
  container.style.display = 'block';

  const selBrand = document.getElementById('ban2-skus-brand').value;
  const searchKw = (document.getElementById('ban2-skus-search').value || '').trim().toLowerCase();

  const p = PERIODS.ban2;
  const pkey = (p.mode === 'month' && p.month) ? String(p.month) : 'ytd';
  const src = APP_DATA.ban.top_fullprice_brand_item || {};
  const byBrand = src[pkey] || src['ytd'] || {};
  const itemsMap = byBrand[selBrand] || {};

  const itemNames = Object.keys(itemsMap).filter(it => !searchKw || it.toLowerCase().includes(searchKw)).sort();
  if (!itemNames.length) {
    container.innerHTML = `<div style="color:var(--text-muted);font-size:13px;padding:20px;text-align:center;">Không có tên hàng khớp (kỳ: ${periodLabelFor('ban2')}).</div>`;
    return;
  }

  itemNames.forEach((itName, ai) => {
    const skus = (itemsMap[itName] || []).slice(0, 5);
    const sum = skus.reduce((a, s) => a + (s.qty || 0), 0);
    const detailId = `ban2-topsku-${ai}`;

    const head = document.createElement('div');
    head.className = 'clickable-row';
    head.style.cssText = 'display:flex;justify-content:space-between;align-items:center;gap:8px;padding:8px 12px;border:1px solid var(--border);border-left:4px solid var(--accent);border-radius:6px;margin-bottom:6px;cursor:pointer;background:#fafaf9;';
    head.onclick = () => {
      const d = document.getElementById(detailId);
      if (!d) return;
      const show = d.style.display === 'none';
      d.style.display = show ? 'block' : 'none';
      const ic = head.querySelector('.expand-icon');
      if (ic) ic.textContent = show ? '▼' : '▶';
    };
    head.innerHTML = `
      <div style="display:flex;align-items:center;gap:6px;min-width:0;">
        <span class="expand-icon" style="color:var(--primary);">▶</span>
        <strong style="color:var(--primary);font-size:12px;">👕 ${itName}</strong>
        <span style="font-size:11px;color:var(--text-muted);">· ${selBrand}</span>
      </div>
      <span class="tag-badge tag-gold">Top 5: ${fmtNum(sum)} sp</span>`;
    container.appendChild(head);

    const detail = document.createElement('div');
    detail.id = detailId;
    detail.style.cssText = 'display:none;padding:6px 12px 12px 12px;border:1px solid var(--border);border-top:none;border-radius:0 0 6px 6px;margin:-6px 0 8px 0;background:#ffffff;';
    detail.innerHTML = skus.length
      ? skus.map((s, idx) => `
          <div style="display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px dashed var(--border);">
            <div>
              <div style="display:flex;align-items:center;gap:6px;">
                <span class="tag-badge ${idx === 0 ? 'tag-gold' : 'tag-neutral'}">#${idx + 1}</span>
                <strong style="color:var(--primary);font-size:12px;">${s.mahang}</strong>
              </div>
              <div style="font-size:11px;color:var(--text-muted);margin-top:2px;">Màu: ${s.cg || '—'} · Giá: ${fmtNum(s.price)}đ</div>
            </div>
            <div style="text-align:right;">
              <strong style="color:var(--accent-dark);font-size:13px;">${fmtNum(s.qty)}</strong>
              <span style="display:block;font-size:10px;color:var(--text-muted);">sp nguyên giá</span>
            </div>
          </div>`).join('')
      : '<div style="color:var(--text-muted);font-size:12px;padding:6px 0;">Không có mã hàng.</div>';
    container.appendChild(detail);
  });
}

// -----------------------------------------------------------------------------
// SHEET 1.3: CẤP CỬA HÀNG & KHU VỰC
// -----------------------------------------------------------------------------
// -----------------------------------------------------------------------------
// QLKD (người quản lý kinh doanh) — dùng chung Sheet 3 Bán & Sheet 3 Tồn
// APP_DATA.ban.store_qlkd = { Store_name: 'linhdtc' | 'CN Hà Nội' | ... } (từ A_Region)
// -----------------------------------------------------------------------------
const QLKD_NONE = '(Chưa gán QLKD)';
function qlkdOf(st) {
  const m = (APP_DATA.ban && APP_DATA.ban.store_qlkd) || {};
  return m[st] || QLKD_NONE;
}
function sortQlkd(list) {
  return list.sort((a, b) => (a === QLKD_NONE) - (b === QLKD_NONE) || a.localeCompare(b, 'vi'));
}
// Điền dropdown QLKD theo danh sách cửa hàng đang trong phạm vi; giữ lựa chọn cũ nếu còn hợp lệ
function populateQlkdDropdown(elId, stores) {
  const el = document.getElementById(elId);
  if (!el) return 'all';
  const cur = el.value;
  const list = sortQlkd(Array.from(new Set(stores.map(qlkdOf))));
  el.innerHTML = '<option value="all">Tất cả QLKD</option>' + list.map(q => `<option value="${q}">${q}</option>`).join('');
  el.value = list.includes(cur) ? cur : 'all';
  return el.value;
}
// Mở Sheet 3 (Bán / Tồn) và lọc theo 1 QLKD
function goQlkd(part, q) {
  const pfx = part === 'ban' ? 'ban3' : 'ton3';
  switchPart(part);
  switchSheet(part, 'sheet3');
  document.getElementById(pfx + '-f-region').value = 'all';
  document.getElementById(pfx + '-f-store').value = 'all';
  const onChange = part === 'ban' ? onBan3RegionChange : onTon3RegionChange;
  onChange();                                    // điền lại dropdown QLKD theo phạm vi "Tất cả khu vực"
  document.getElementById(pfx + '-f-qlkd').value = q;
  onChange();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}
function qlkdRowAttrs(part, q) {
  return `class="clickable-row" style="cursor:pointer;" title="Mở Sheet 3 xem cửa hàng của ${q}" onclick="goQlkd('${part}', '${q.replace(/'/g, "\\'")}')"`;
}
// Bấm 1 cửa hàng trong danh sách QLKD (Sheet 3) -> chọn cửa hàng đó; bấm lại -> bỏ chọn
function pickQlkdStore(pfx, st) {
  const el = document.getElementById(pfx + '-f-store');
  el.value = el.value === st ? 'all' : st;
  if (pfx === 'ban3') renderBanSheet3(); else renderTonSheet3();
}
function qlkdStoreRowAttrs(pfx, st, selSt) {
  const on = selSt === st;
  return `class="clickable-row" style="cursor:pointer;${on ? 'background:#fef3c7;font-weight:600;' : ''}" onclick="pickQlkdStore('${pfx}', '${st.replace(/'/g, "\\'")}')"`;
}

function onBan3RegionChange() {
  const selRg = document.getElementById('ban3-f-region').value;
  buildStore360Index();

  const ov = APP_DATA.ban.ov;
  const colSt = ov.data[5];
  const colRg = ov.data[6];
  const n = colSt.length;

  const storesInReg = new Set();
  for (let i = 0; i < n; i++) {
    const st = DICT[colSt[i]];
    const rg = DICT[colRg[i]];
    if (selRg === 'all' || rg === selRg) {
      storesInReg.add(st);
    }
  }

  const sortedStores = Array.from(storesInReg).sort((a, b) => a.localeCompare(b, 'vi'));
  const selQ = populateQlkdDropdown('ban3-f-qlkd', sortedStores);
  populateStoreDropdown('ban3-f-store', sortedStores.filter(st => selQ === 'all' || qlkdOf(st) === selQ));
  renderBanSheet3();
}

function resetBanSheet3Filters() {
  document.getElementById('ban3-f-region').value = 'all';
  document.getElementById('ban3-f-store').value = 'all';
  document.getElementById('ban3-f-qlkd').value = 'all';
  PERIODS.ban3.mode = 'ytd';
  PERIODS.ban3.month = null;
  const y = document.getElementById('ban3-period-ytd'), mo = document.getElementById('ban3-period-month'), sel = document.getElementById('ban3-period-month-sel');
  if (y) y.classList.add('active');
  if (mo) mo.classList.remove('active');
  if (sel) { sel.disabled = true; sel.value = String(APP_DATA.ref.month); }
  onBan3RegionChange();
}

function renderBanSheet3() {
  const selRg = document.getElementById('ban3-f-region').value;
  const selSt = document.getElementById('ban3-f-store').value;
  const selQ = document.getElementById('ban3-f-qlkd').value;
  const QM = APP_DATA.ban.store_qlkd || {};
  const QS = {};   // danh sách cửa hàng của QLKD đang chọn: { Store_name: chỉ số kỳ xem }

  const ov = APP_DATA.ban.ov;
  const cY = ov.data[0], cM = ov.data[1], cSrc = ov.data[2], cTxn = ov.data[3],
        cPr = ov.data[4], cSt = ov.data[5], cRg = ov.data[6], cBr = ov.data[7], cQ = ov.data[8];
  const n = cY.length;
  const refY = APP_DATA.ref.year;
  const inWin = new Array(13).fill(false);
  periodMonthsFor('ban3').forEach(m => inWin[m] = true);
  const lastM = periodLastMonth('ban3');
  const prevM = lastM > 1 ? lastM - 1 : 0;

  let totalSales = 0, fpSales = 0, saleSales = 0, tlSales = 0, hdSales = 0, retSales = 0;
  const B = {};
  BRAND_MAIN_5.forEach(b => B[b] = { win: 0, last: 0, prev: 0, yoy: 0 });
  B['Khác'] = { win: 0, last: 0, prev: 0, yoy: 0 };
  const YRS = refYearsList();
  const trend = {};
  YRS.forEach(y => { trend[y] = Array(12).fill(0); });
  const allStoreWin = {}; // xếp hạng: tổng bán lẻ theo kỳ của MỌI cửa hàng (bỏ Event)

  for (let i = 0; i < n; i++) {
    const yr = cY[i], m = cM[i], q = cQ[i];
    const src = DICT[cSrc[i]], txn = DICT[cTxn[i]], pr = DICT[cPr[i]];
    const st = DICT[cSt[i]], rg = DICT[cRg[i]], br = DICT[cBr[i]];
    const retail = src === 'Lẻ' && txn === 'Bán';
    const hdBan = src === 'HĐ' && txn === 'Bán';

    if (rg !== 'Event' && retail && yr === refY && inWin[m]) {
      let a = allStoreWin[st];
      if (!a) a = allStoreWin[st] = { rg, total: 0 };
      a.total += q;
    }

    const qk = QM[st] || QLKD_NONE;
    if (selQ !== 'all' && qk === selQ && (selRg === 'all' || rg === selRg) && (yr === refY || yr === refY - 1) && inWin[m]) {
      let a = QS[st];
      if (!a) a = QS[st] = { rg, total: 0, fp: 0, sale: 0, tl: 0, hd: 0, ret: 0, ng: 0, yoy: 0 };
      if (rg !== 'Event') a.rg = rg;
      if (yr === refY) {
        if (retail) {
          a.total += q;
          if (pr === 'Nguyên giá') { a.fp += q; a.ng += q; } else if (pr === 'Sale') a.sale += q; else if (pr === 'Thanh lý') a.tl += q;
        }
        if (hdBan) a.hd += q;
        if (txn === 'Đổi' && src === 'Lẻ' && pr === 'Nguyên giá') a.ret += Math.abs(q);
      } else if (retail) a.yoy += q;
    }

    if ((selRg === 'all' || rg === selRg) && (selSt === 'all' || st === selSt) && (selQ === 'all' || qk === selQ)) {
      if (retail && trend[yr] && m >= 1 && m <= 12) trend[yr][m - 1] += q;
      const bo = B[br] || B['Khác'];
      if (yr === refY) {
        if (inWin[m]) {
          if (retail) {
            totalSales += q;
            if (pr === 'Nguyên giá') fpSales += q;
            else if (pr === 'Sale') saleSales += q;
            else if (pr === 'Thanh lý') tlSales += q;
            bo.win += q;
          }
          if (hdBan) hdSales += q;
          if (txn === 'Đổi') retSales += q;
        }
        if (retail && m === lastM) bo.last += q;
        if (retail && prevM && m === prevM) bo.prev += q;
      } else if (yr === refY - 1 && inWin[m] && retail) {
        bo.yoy += q;
      }
    }
  }

  const pct = (a, b) => (b > 0 ? (a / b * 100) : 0);
  const lbl = periodLabelFor('ban3');

  document.getElementById('ban3-kpi-sales').textContent = fmtNum(totalSales);
  document.getElementById('ban3-kpi-sales-sub').textContent =
    `${selSt !== 'all' ? selSt : (selQ !== 'all' ? 'QLKD ' + selQ : (selRg !== 'all' ? selRg : 'Toàn hệ thống'))} · ${lbl}`;

  // Cửa hàng thuộc QLKD đang chọn: dòng Tổng + từng cửa hàng
  const qCard = document.getElementById('ban3-qlkd-card');
  if (qCard) {
    qCard.hidden = selQ === 'all';
    if (selQ !== 'all') {
      const keys = Object.keys(QS).filter(k => QS[k].total || QS[k].hd || QS[k].yoy)
        .sort((a, b) => QS[b].total - QS[a].total);
      const T = { total: 0, fp: 0, sale: 0, tl: 0, hd: 0, ret: 0, ng: 0, yoy: 0 };
      keys.forEach(k => Object.keys(T).forEach(f => { T[f] += QS[k][f]; }));
      const yoyOf = a => (a.yoy > 0 ? (a.total - a.yoy) / a.yoy * 100 : null);
      const cells = a => `<td><strong>${fmtNum(a.total)}</strong></td><td>${fmtNum(a.fp)}</td><td>${fmtNum(a.sale)}</td>
        <td>${fmtNum(a.tl)}</td><td>${fmtNum(a.hd)}</td><td>${fmtNum(a.ret)}</td><td>${pct(a.ret, a.ng).toFixed(1)}%</td>
        <td>${getBadgePct(yoyOf(a))}</td><td>${pct(a.total, T.total).toFixed(1)}%</td>`;
      const rows = [`<tr style="background:#f8fafc;font-weight:700;"><td></td><td>TỔNG ${selQ}</td><td>${fmtNum(keys.length)} CH</td>${cells(T)}</tr>`]
        .concat(keys.map((k, n) => `<tr ${qlkdStoreRowAttrs('ban3', k, selSt)}><td>${n + 1}</td><td><strong>${k}</strong></td><td>${QS[k].rg}</td>${cells(QS[k])}</tr>`));
      document.getElementById('ban3-qlkd-tbody').innerHTML = keys.length ? rows.join('') : emptyRow(12);
      document.getElementById('ban3-qlkd-title').textContent = `Cửa hàng thuộc QLKD: ${selQ}`;
      document.getElementById('ban3-qlkd-sub').textContent =
        `Bán lẻ ${lbl}${selRg !== 'all' ? ' · ' + selRg : ''} · YoY so cùng kỳ ${refY - 1} · bấm 1 cửa hàng để xem riêng cửa hàng đó`;
    }
  }
  document.getElementById('ban3-kpi-fp').textContent = fmtNum(fpSales);
  document.getElementById('ban3-kpi-fp-rate').textContent = `${pct(fpSales, totalSales).toFixed(1)}% tổng bán`;
  document.getElementById('ban3-kpi-sale').textContent = fmtNum(saleSales);
  document.getElementById('ban3-kpi-sale-rate').textContent = `${pct(saleSales, totalSales).toFixed(1)}% tổng bán`;
  document.getElementById('ban3-kpi-tl').textContent = fmtNum(tlSales);
  document.getElementById('ban3-kpi-tl-rate').textContent = `${pct(tlSales, totalSales).toFixed(1)}% tổng bán`;
  document.getElementById('ban3-kpi-hd').textContent = fmtNum(hdSales);
  document.getElementById('ban3-kpi-hd-rate').textContent = `${pct(hdSales, totalSales).toFixed(1)}% tổng bán`;
  document.getElementById('ban3-kpi-ret').textContent = fmtNum(retSales);
  document.getElementById('ban3-kpi-ret-rate').textContent = `Tỷ lệ: ${pct(retSales, totalSales).toFixed(1)}%`;

  let rankRgStr = '#—', rankRgSub = selRg !== 'all' ? `Khu vực: ${selRg}` : 'Chọn 1 cửa hàng để xem hạng';
  let rankSysStr = '#—', rankSysSub = 'Chọn 1 cửa hàng để xem hạng';
  if (selSt !== 'all' && allStoreWin[selSt]) {
    const myRg = allStoreWin[selSt].rg;
    const myTotal = allStoreWin[selSt].total;
    const arr = Object.values(allStoreWin);
    const rgArr = arr.filter(a => a.rg === myRg);
    rankSysStr = `#${arr.filter(a => a.total > myTotal).length + 1}`;
    rankSysSub = `Trên ${arr.length} CH toàn HTCH · ${lbl}`;
    rankRgStr = `#${rgArr.filter(a => a.total > myTotal).length + 1}`;
    rankRgSub = `Trên ${rgArr.length} CH (${myRg}) · ${lbl}`;
  }
  document.getElementById('ban3-kpi-rank-region').textContent = rankRgStr;
  document.getElementById('ban3-kpi-rank-region-sub').textContent = rankRgSub;
  document.getElementById('ban3-kpi-rank-sys').textContent = rankSysStr;
  document.getElementById('ban3-kpi-rank-sys-sub').textContent = rankSysSub;

  // Bảng 5 Brand chính — theo kỳ, MoM/YoY tính thật
  const tb = document.getElementById('ban3-table-brands-tbody');
  tb.innerHTML = '';
  BRAND_MAIN_5.forEach(b => {
    const s = B[b];
    const mom = s.prev > 0 ? ((s.last - s.prev) / s.prev * 100) : null;
    const yoy = s.yoy > 0 ? ((s.win - s.yoy) / s.yoy * 100) : null;
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><strong>${b}</strong></td>
      <td><strong>${fmtNum(s.win)}</strong></td>
      <td>${(totalSales > 0 ? s.win / totalSales * 100 : 0).toFixed(1)}%</td>
      <td>${getBadgePct(mom)}</td>
      <td>${getBadgePct(yoy)}</td>`;
    tb.appendChild(tr);
  });

  renderBan3TrendChart(trend, YRS);
  renderBan3TopSkus(selSt, selRg);
}

function renderBan3TrendChart(monthlyTrend, YRS) {
  const [Y0, Y1, Y2] = YRS || refYearsList();
  const chartEl = document.getElementById('ban3-chart-trend');
  const months = ['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8', 'T9', 'T10', 'T11', 'T12'];

  const data = [
    { x: months, y: monthlyTrend[Y2], name: String(Y2), type: 'scatter', mode: 'lines+markers', line: { color: '#94a3b8' } },
    { x: months, y: monthlyTrend[Y1], name: String(Y1), type: 'scatter', mode: 'lines+markers', line: { color: '#2563eb' } },
    { x: months.slice(0, APP_DATA.ref.month), y: monthlyTrend[Y0].slice(0, APP_DATA.ref.month), name: String(Y0), type: 'scatter', mode: 'lines+markers', line: { color: '#c5a059', width: 3 } }
  ];

  const layout = {
    margin: { t: 20, r: 20, b: 35, l: 45 },
    yaxis: { title: 'Số bán (sp)' },
    plot_bgcolor: '#fdfdfd',
    legend: { orientation: 'h', y: 1.15 }
  };

  Plotly.newPlot(chartEl, data, layout, { responsive: true, displayModeBar: false });
}

function renderBan3TopSkus(selSt, selRg) {
  const container = document.getElementById('ban3-top-skus-container');
  if (!container) return;
  container.innerHTML = '';

  const topStItem = APP_DATA.ban.top_fullprice_store_brand_item || {};

  // Bảng này là "theo từng Cửa hàng" — cần chọn 1 CH cụ thể mới có nghĩa
  if (!selSt || selSt === 'all') {
    container.innerHTML = '<div style="grid-column: 1/-1; color: var(--text-muted); font-size: 13px; padding: 20px; text-align: center;">Chọn 1 cửa hàng cụ thể ở bộ lọc phía trên để xem Top 5 mã bán chạy nguyên giá theo từng tên hàng của cửa hàng đó.</div>';
    return;
  }

  const storeItems = topStItem[selSt];
  const brands = storeItems ? Object.keys(storeItems) : [];
  if (brands.length === 0) {
    container.innerHTML = '<div style="grid-column: 1/-1; color: var(--text-muted); font-size: 13px; padding: 20px;">Cửa hàng này chưa có dữ liệu bán nguyên giá theo tên hàng.</div>';
    return;
  }

  // Chia theo BRAND: mỗi brand là 1 section bung/thu; trong đó là các Tên hàng (accordion) -> 5 mã
  container.style.display = 'block';
  let acc = 0;
  // giữ thứ tự brand chính trước
  const orderedBrands = BRAND_MAIN_5.filter(b => brands.includes(b)).concat(brands.filter(b => !BRAND_MAIN_5.includes(b)));

  orderedBrands.forEach(br => {
    const itemsMap = storeItems[br] || {};
    const itemNames = Object.keys(itemsMap).sort();
    if (!itemNames.length) return;
    const brandSecId = `ban3-topsku-brand-${acc}`;

    const brandHead = document.createElement('div');
    brandHead.className = 'clickable-row';
    brandHead.style.cssText = 'display:flex;justify-content:space-between;align-items:center;gap:8px;padding:9px 12px;border:1px solid var(--border);border-left:4px solid var(--primary);border-radius:6px;margin:10px 0 4px 0;cursor:pointer;background:#eef2f7;';
    brandHead.onclick = () => {
      const sec = document.getElementById(brandSecId);
      if (!sec) return;
      const show = sec.style.display === 'none';
      sec.style.display = show ? 'block' : 'none';
      const ic = brandHead.querySelector('.expand-icon');
      if (ic) ic.textContent = show ? '▼' : '▶';
    };
    brandHead.innerHTML = `
      <div style="display:flex;align-items:center;gap:6px;">
        <span class="expand-icon" style="color:var(--primary);">▼</span>
        <strong style="color:var(--primary);font-size:13px;">${br}</strong>
      </div>
      <span class="tag-badge tag-neutral">${fmtNum(itemNames.length)} tên hàng</span>`;
    container.appendChild(brandHead);

    const brandSec = document.createElement('div');
    brandSec.id = brandSecId;
    brandSec.style.cssText = 'display:block;padding-left:8px;';
    container.appendChild(brandSec);

    itemNames.forEach(itName => {
      const top5 = (itemsMap[itName] || []).slice(0, 5);
      const sumQty = top5.reduce((a, s) => a + (s.qty || 0), 0);
      const detailId = `ban3-topsku-${acc++}`;

      const head = document.createElement('div');
      head.className = 'clickable-row';
      head.style.cssText = 'display:flex;justify-content:space-between;align-items:center;gap:8px;padding:7px 12px;border:1px solid var(--border);border-left:3px solid var(--accent);border-radius:6px;margin-bottom:5px;cursor:pointer;background:#f8fafc;';
      head.onclick = () => {
        const d = document.getElementById(detailId);
        if (!d) return;
        const show = d.style.display === 'none';
        d.style.display = show ? 'block' : 'none';
        const ic = head.querySelector('.expand-icon');
        if (ic) ic.textContent = show ? '▼' : '▶';
      };
      head.innerHTML = `
        <div style="display:flex;align-items:center;gap:6px;min-width:0;">
          <span class="expand-icon" style="color:var(--primary);">▶</span>
          <strong style="color:var(--primary);font-size:12px;">${itName}</strong>
        </div>
        <span class="tag-badge tag-gold">Top 5: ${fmtNum(sumQty)} sp</span>`;
      brandSec.appendChild(head);

      const detail = document.createElement('div');
      detail.id = detailId;
      detail.style.cssText = 'display:none;padding:6px 12px 12px 12px;border:1px solid var(--border);border-top:none;border-radius:0 0 6px 6px;margin:-5px 0 8px 0;background:#ffffff;';
      detail.innerHTML = top5.length
        ? top5.map((s, idx) => `
            <div style="display:flex;justify-content:space-between;align-items:center;padding:5px 0;border-bottom:1px dashed var(--border);">
              <div style="display:flex;align-items:center;gap:6px;">
                <span class="tag-badge ${idx === 0 ? 'tag-gold' : 'tag-neutral'}">#${idx + 1}</span>
                <strong style="color:var(--primary);font-size:12px;">${s.mahang}</strong>
                <span style="font-size:11px;color:var(--text-muted);">${s.form || ''}${s.cg ? ' · ' + s.cg : ''}</span>
              </div>
              <span style="font-weight:bold;color:var(--accent-dark);">${fmtNum(s.qty)}</span>
            </div>`).join('')
        : '<div style="color:var(--text-muted);font-size:12px;padding:6px 0;">Không có mã hàng.</div>';
      brandSec.appendChild(detail);
    });
  });

  if (acc === 0) {
    container.innerHTML = '<div style="color: var(--text-muted); font-size: 13px; padding: 20px; text-align:center;">Cửa hàng này chưa có dữ liệu bán nguyên giá theo tên hàng.</div>';
  }
}

// -----------------------------------------------------------------------------
// SHEET 1.4: CHI TIẾT THUỘC TÍNH THEO 6 NHÓM HÀNG
// -----------------------------------------------------------------------------
function setBan4CatGroup(catGroup) {
  CURRENT_BAN4_CAT_GROUP = catGroup;
  document.querySelectorAll('#ban4-cat-group-list .seg-btn').forEach(b => {
    b.classList.toggle('active', b.textContent.trim() === catGroup);
  });
  onBan4BrandChange();
}

function onBan4BrandChange() {
  const fBr = document.getElementById('ban4-f-brand').value;
  const attrData = APP_DATA.ban.attr_sales;

  // Lọc danh sách nhóm BC có trong brand này & catGroup này
  const groups = new Set();
  if (attrData && attrData.data) {
    const colBr = attrData.data[2];
    const colGr = attrData.data[3];
    const colCgGroup = attrData.data[8];
    const n = colBr.length;
    for (let i = 0; i < n; i++) {
      if (DICT[colCgGroup[i]] !== CURRENT_BAN4_CAT_GROUP) continue;
      if (fBr !== 'all' && DICT[colBr[i]] !== fBr) continue;
      groups.add(DICT[colGr[i]]);
    }
  }

  const grEl = document.getElementById('ban4-f-group');
  if (grEl) {
    grEl.innerHTML = '<option value="all">Tất cả Nhóm</option>';
    Array.from(groups).sort().forEach(g => {
      grEl.innerHTML += `<option value="${g}">${g}</option>`;
    });
  }

  onBan4GroupChange();
}

function onBan4GroupChange() {
  const fBr = document.getElementById('ban4-f-brand').value;
  const fGr = document.getElementById('ban4-f-group').value;
  const attrData = APP_DATA.ban.attr_sales;

  // Lọc danh sách tên hàng (Report_item_name)
  const items = new Set();
  if (attrData && attrData.data) {
    const colBr = attrData.data[2];
    const colGr = attrData.data[3];
    const colIt = attrData.data[4];
    const colCgGroup = attrData.data[8];
    const n = colBr.length;
    for (let i = 0; i < n; i++) {
      if (DICT[colCgGroup[i]] !== CURRENT_BAN4_CAT_GROUP) continue;
      if (fBr !== 'all' && DICT[colBr[i]] !== fBr) continue;
      if (fGr !== 'all' && DICT[colGr[i]] !== fGr) continue;
      items.add(DICT[colIt[i]]);
    }
  }

  const itEl = document.getElementById('ban4-f-item');
  if (itEl) {
    itEl.innerHTML = '<option value="all">Tất cả Tên hàng</option>';
    Array.from(items).sort().forEach(it => {
      itEl.innerHTML += `<option value="${it}">${it}</option>`;
    });
  }

  renderBanSheet4();
}

function setBan4AttrView(viewType) {
  // Update buttons
  const btns = ['ban4-btn-view-all', 'ban4-btn-view-form', 'ban4-btn-view-style', 'ban4-btn-view-color'];
  btns.forEach(id => {
    const b = document.getElementById(id);
    if (b) b.classList.remove('active');
  });
  const curBtn = document.getElementById(`ban4-btn-view-${viewType}`);
  if (curBtn) curBtn.classList.add('active');

  // Toggle view cards
  const cardForm = document.getElementById('ban4-card-form');
  const cardStyle = document.getElementById('ban4-card-style');
  const cardColor = document.getElementById('ban4-card-color');

  if (cardForm) cardForm.style.display = (viewType === 'all' || viewType === 'form') ? 'block' : 'none';
  if (cardStyle) cardStyle.style.display = (viewType === 'all' || viewType === 'style') ? 'block' : 'none';
  if (cardColor) cardColor.style.display = (viewType === 'all' || viewType === 'color') ? 'block' : 'none';
}

function resetBanSheet4Filters() {
  document.getElementById('ban4-f-region').value = 'all';
  document.getElementById('ban4-f-brand').value = 'all';
  PERIODS.ban4.mode = 'ytd';
  PERIODS.ban4.month = null;
  const y = document.getElementById('ban4-period-ytd'), mo = document.getElementById('ban4-period-month'), sel = document.getElementById('ban4-period-month-sel');
  if (y) y.classList.add('active');
  if (mo) mo.classList.remove('active');
  if (sel) { sel.disabled = true; sel.value = String(APP_DATA.ref.month); }
  setBan4AttrView('all');
  onBan4BrandChange();
}

function renderBanSheet4() {
  const fRg = document.getElementById('ban4-f-region').value;
  const fBr = document.getElementById('ban4-f-brand').value;
  const fGr = document.getElementById('ban4-f-group').value;
  const fIt = document.getElementById('ban4-f-item').value;

  const attrData = APP_DATA.ban.attr_sales;
  if (!attrData || !attrData.data) return;

  const colYr = attrData.data[0];
  const colRg = attrData.data[1];
  const colBr = attrData.data[2];
  const colGr = attrData.data[3];
  const colIt = attrData.data[4];
  const colCg = attrData.data[5];
  const colForm = attrData.data[6];
  const colStyle = attrData.data[7];
  const colCgGroup = attrData.data[8];
  const colQty = attrData.data[9];
  const colM = attrData.data[10]; // tháng (có thể undefined ở payload cũ)
  const n = colYr.length;

  // Kỳ xem: giới hạn các tháng được cộng vào 3 cột năm (Y0 / Y1 / Y2)
  const YRS = refYearsList();
  const [Y0, Y1, Y2] = YRS;
  const inWin = new Array(13).fill(false);
  periodMonthsFor('ban4').forEach(m => inWin[m] = true);
  const zero3 = () => ({ [Y0]: 0, [Y1]: 0, [Y2]: 0 });

  const formStats = {};
  const styleStats = {};
  const colorStats = {};

  for (let i = 0; i < n; i++) {
    const yr = colYr[i];
    if (colM && !inWin[colM[i]]) continue;
    const rg = DICT[colRg[i]];
    const br = DICT[colBr[i]];
    const gr = DICT[colGr[i]];
    const it = DICT[colIt[i]];
    const cg = DICT[colCg[i]] || 'Khác';
    const form = DICT[colForm[i]] || 'Khác';
    const style = DICT[colStyle[i]] || 'Khác';
    const catG = DICT[colCgGroup[i]];
    const qty = colQty[i];

    if (catG !== CURRENT_BAN4_CAT_GROUP) continue;
    if (fRg !== 'all' && rg !== fRg) continue;
    if (fBr !== 'all' && br !== fBr) continue;
    if (fGr !== 'all' && gr !== fGr) continue;
    if (fIt !== 'all' && it !== fIt) continue;

    if (!formStats[form]) formStats[form] = zero3();
    if (formStats[form][yr] !== undefined) formStats[form][yr] += qty;

    if (!styleStats[style]) styleStats[style] = zero3();
    if (styleStats[style][yr] !== undefined) styleStats[style][yr] += qty;

    if (!colorStats[cg]) colorStats[cg] = zero3();
    if (colorStats[cg][yr] !== undefined) colorStats[cg][yr] += qty;
  }

  renderAttrComparison('ban4-table-form-tbody', 'ban4-chart-form', formStats, YRS);
  renderAttrComparison('ban4-table-style-tbody', 'ban4-chart-style', styleStats, YRS);
  renderAttrComparison('ban4-table-color-tbody', 'ban4-chart-color', colorStats, YRS);
}

function renderAttrComparison(tbodyId, chartId, statsMap, YRS) {
  const [Y0, Y1, Y2] = YRS || refYearsList();
  const tbody = document.getElementById(tbodyId);
  tbody.innerHTML = '';

  // Đổi tiêu đề 3 cột năm cho khớp kỳ hiện tại
  const table = tbody.closest('table');
  if (table) {
    const ths = table.querySelectorAll('thead th');
    if (ths.length >= 4) { ths[1].textContent = Y0; ths[2].textContent = Y1; ths[3].textContent = Y2; }
  }

  const sortedKeys = Object.keys(statsMap).sort((a, b) => statsMap[b][Y0] - statsMap[a][Y0]).slice(0, 10);

  sortedKeys.forEach(k => {
    const s = statsMap[k];
    const yoy = s[Y1] > 0 ? ((s[Y0] - s[Y1]) / s[Y1] * 100) : null;
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><strong>${k}</strong></td>
      <td><strong>${fmtNum(s[Y0])}</strong></td>
      <td>${fmtNum(s[Y1])}</td>
      <td>${fmtNum(s[Y2])}</td>
      <td>${getBadgePct(yoy)}</td>
    `;
    tbody.appendChild(tr);
  });

  // Mini Bar Chart (Y0 vs Y1)
  const chartEl = document.getElementById(chartId);
  const top5 = sortedKeys.slice(0, 5);
  const vals26 = top5.map(k => statsMap[k][Y0]);
  const vals25 = top5.map(k => statsMap[k][Y1]);

  const data = [
    { x: top5, y: vals26, name: String(Y0), type: 'bar', marker: { color: '#1a365d' } },
    { x: top5, y: vals25, name: String(Y1), type: 'bar', marker: { color: '#cbd5e1' } }
  ];

  const layout = {
    barmode: 'group',
    margin: { t: 10, r: 10, b: 35, l: 40 },
    xaxis: { tickfont: { size: 10 } },
    yaxis: { tickfont: { size: 10 } },
    plot_bgcolor: '#f8fafc',
    legend: { orientation: 'h', y: 1.2 }
  };

  Plotly.newPlot(chartEl, data, layout, { responsive: true, displayModeBar: false });
}


// =============================================================================
// =============================================================================
// PHẦN 2: SỐ TỒN
// =============================================================================
// =============================================================================

// -----------------------------------------------------------------------------
// SHEET 2.1: TỒN KHO TỔNG HỢP
// -----------------------------------------------------------------------------
function renderTonSheet1() {
  const ton = APP_DATA.ton;
  const nRows = ton.data[0].length;

  let totalQty = 0;
  let fpQty = 0;
  let saleQty = 0;
  let tlQty = 0;
  let chQty = 0;
  let khoQty = 0;

  const brandStats = {};
  BRAND_MAIN_5.forEach(b => {
    brandStats[b] = { fp: 0, sale: 0, tl: 0, total: 0 };
  });
  brandStats['Khác'] = { fp: 0, sale: 0, tl: 0, total: 0 };

  const locStats = {};
  const regList = REGION_MAIN_5.concat(['Event', 'Kho AP', 'Kho PIE', 'Kho TB3 đồ lót', 'Kho CNHN', 'Kho Tổng hợp', 'Kho khác']);
  regList.forEach(r => {
    locStats[r] = { fp: 0, sale: 0, tl: 0, total: 0 };
  });

  const colRk = ton.data[0];
  const colRg = ton.data[1];
  const colWh = ton.data[2];
  const colBr = ton.data[3];
  const colStatus = ton.data[15];
  const colQty = ton.data[16];

  for (let i = 0; i < nRows; i++) {
    const rk = DICT[colRk[i]];
    const rg = DICT[colRg[i]];
    const wh = DICT[colWh[i]];
    const br = DICT[colBr[i]];
    const status = DICT[colStatus[i]] || 'Nguyên giá';
    const qty = colQty[i];

    totalQty += qty;
    if (status === 'Nguyên giá') fpQty += qty;
    else if (status === 'Sale') saleQty += qty;
    else if (status === 'Thanh lý') tlQty += qty;

    if (rk === 'CH') chQty += qty;
    else khoQty += qty;

    // Brand
    const brKey = BRAND_MAIN_5.includes(br) ? br : 'Khác';
    if (brandStats[brKey]) {
      if (status === 'Nguyên giá') brandStats[brKey].fp += qty;
      else if (status === 'Sale') brandStats[brKey].sale += qty;
      else if (status === 'Thanh lý') brandStats[brKey].tl += qty;
      brandStats[brKey].total += qty;
    }

    // Location
    const locKey = rk === 'CH' ? rg : wh;
    if (locStats[locKey]) {
      if (status === 'Nguyên giá') locStats[locKey].fp += qty;
      else if (status === 'Sale') locStats[locKey].sale += qty;
      else if (status === 'Thanh lý') locStats[locKey].tl += qty;
      locStats[locKey].total += qty;
    }
  }

  // KPIs
  document.getElementById('ton1-kpi-total').textContent = fmtNum(totalQty);
  document.getElementById('ton1-kpi-fp').textContent = fmtNum(fpQty);
  document.getElementById('ton1-kpi-fp-rate').textContent = totalQty > 0 ? `${(fpQty / totalQty * 100).toFixed(1)}% tổng tồn` : '0%';
  document.getElementById('ton1-kpi-sale').textContent = fmtNum(saleQty);
  document.getElementById('ton1-kpi-sale-rate').textContent = totalQty > 0 ? `${(saleQty / totalQty * 100).toFixed(1)}% tổng tồn` : '0%';
  document.getElementById('ton1-kpi-tl').textContent = fmtNum(tlQty);
  document.getElementById('ton1-kpi-tl-rate').textContent = totalQty > 0 ? `${(tlQty / totalQty * 100).toFixed(1)}% tổng tồn` : '0%';
  document.getElementById('ton1-kpi-ch').textContent = fmtNum(chQty);
  document.getElementById('ton1-kpi-ch-rate').textContent = totalQty > 0 ? `${(chQty / totalQty * 100).toFixed(1)}% tổng tồn` : '0%';
  document.getElementById('ton1-kpi-kho').textContent = fmtNum(khoQty);
  document.getElementById('ton1-kpi-kho-rate').textContent = totalQty > 0 ? `${(khoQty / totalQty * 100).toFixed(1)}% tổng tồn` : '0%';

  // 5 Brand Table
  const tbodyBrands = document.getElementById('ton1-table-brands-tbody');
  tbodyBrands.innerHTML = '';
  // brand_counts[b] = { item_count: số Tên hàng (Report_item_name) khác nhau,
  //                     sku_count : số Mã hàng (MaHang / SKU) khác nhau }
  const brandCounts = APP_DATA.ton.brand_counts || {};

  BRAND_MAIN_5.concat(['Khác']).forEach(b => {
    const s = brandStats[b];
    const share = totalQty > 0 ? (s.total / totalQty * 100) : 0;
    const bInfo = brandCounts[b] || {};
    const itemCnt = (bInfo.item_count !== undefined && bInfo.item_count !== null) ? fmtNum(bInfo.item_count) : '—';
    const skuCnt = (bInfo.sku_count !== undefined && bInfo.sku_count !== null) ? fmtNum(bInfo.sku_count) : '—';
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><strong>${b}</strong></td>
      <td><strong>${fmtNum(s.fp)}</strong></td>
      <td>${fmtNum(s.sale)}</td>
      <td>${fmtNum(s.tl)}</td>
      <td><strong>${fmtNum(s.total)}</strong></td>
      <td>${share.toFixed(1)}%</td>
      <td><span class="tag-badge tag-neutral" title="Số Tên hàng (Report_item_name)">${itemCnt}</span></td>
      <td><span class="tag-badge tag-info" title="Số SKU = MaHang + Operation">${skuCnt}</span></td>
    `;
    tbodyBrands.appendChild(tr);
  });

  // Location Table (with Kho tổng expandable)
  renderTon1LocationTable(locStats, totalQty);
  renderTon1Qlkd();

  // Matrix Region x Brand
  renderTon1Matrix();
}

function renderTon1LocationTable(locStats, totalQty) {
  const tbody = document.getElementById('ton1-table-locations-tbody');
  tbody.innerHTML = '';

  // 1. Render các khu vực CH
  REGION_MAIN_5.concat(['Event']).forEach(rg => {
    const s = locStats[rg] || { fp: 0, sale: 0, tl: 0, total: 0 };
    const share = totalQty > 0 ? (s.total / totalQty * 100) : 0;
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><strong>${rg}</strong></td>
      <td>${fmtNum(s.fp)}</td>
      <td>${fmtNum(s.sale)}</td>
      <td>${fmtNum(s.tl)}</td>
      <td><strong>${fmtNum(s.total)}</strong></td>
      <td>${share.toFixed(1)}%</td>
    `;
    tbody.appendChild(tr);
  });

  // 2. Gom tổng Kho
  let khoFp = 0, khoSale = 0, khoTl = 0, khoTot = 0;
  WAREHOUSE_MAIN_5.forEach(wh => {
    const s = locStats[wh] || { fp: 0, sale: 0, tl: 0, total: 0 };
    khoFp += s.fp;
    khoSale += s.sale;
    khoTl += s.tl;
    khoTot += s.total;
  });
  const khoShare = totalQty > 0 ? (khoTot / totalQty * 100) : 0;

  // Dòng Tổng Kho (Clickable)
  const trKho = document.createElement('tr');
  trKho.className = 'clickable-row';
  trKho.style.background = '#fef3c7';
  trKho.style.fontWeight = 'bold';
  trKho.onclick = () => {
    TON1_KHO_EXPANDED = !TON1_KHO_EXPANDED;
    renderTonSheet1();
  };
  trKho.innerHTML = `
    <td><span>${TON1_KHO_EXPANDED ? '▼' : '▶'} 📦 KHO TỔNG (Bấm để xem 5 kho)</span></td>
    <td>${fmtNum(khoFp)}</td>
    <td>${fmtNum(khoSale)}</td>
    <td>${fmtNum(khoTl)}</td>
    <td><strong>${fmtNum(khoTot)}</strong></td>
    <td>${khoShare.toFixed(1)}%</td>
  `;
  tbody.appendChild(trKho);

  // Các dòng con của 5 kho
  if (TON1_KHO_EXPANDED) {
    WAREHOUSE_MAIN_5.forEach(wh => {
      const s = locStats[wh] || { fp: 0, sale: 0, tl: 0, total: 0 };
      const share = totalQty > 0 ? (s.total / totalQty * 100) : 0;
      const trWh = document.createElement('tr');
      trWh.style.background = '#fffbeb';
      trWh.innerHTML = `
        <td style="padding-left: 28px;">↳ <em>${wh}</em></td>
        <td>${fmtNum(s.fp)}</td>
        <td>${fmtNum(s.sale)}</td>
        <td>${fmtNum(s.tl)}</td>
        <td><strong>${fmtNum(s.total)}</strong></td>
        <td>${share.toFixed(1)}%</td>
      `;
      tbody.appendChild(trWh);
    });
  }
}

function renderTon1Matrix() {
  const selStatus = document.getElementById('ton1-matrix-status').value;
  const ton = APP_DATA.ton;
  const nRows = ton.data[0].length;

  const matrix = {};
  BRAND_MAIN_5.forEach(b => {
    matrix[b] = { 'TP. HCM': 0, 'Miền Tây': 0, 'Miền Đông': 0, 'Miền Trung - TN': 0, 'Hà Nội': 0, 'Kho Tổng': 0, total: 0 };
  });

  const colRk = ton.data[0];
  const colRg = ton.data[1];
  const colWh = ton.data[2];
  const colBr = ton.data[3];
  const colStatus = ton.data[15];
  const colQty = ton.data[16];

  for (let i = 0; i < nRows; i++) {
    const rk = DICT[colRk[i]];
    const rg = DICT[colRg[i]];
    const wh = DICT[colWh[i]];
    const br = DICT[colBr[i]];
    const st = DICT[colStatus[i]] || 'Nguyên giá';
    const qty = colQty[i];

    if (selStatus !== 'all' && st !== selStatus) continue;
    if (!matrix[br]) continue;

    if (rk === 'CH') {
      if (matrix[br][rg] !== undefined) {
        matrix[br][rg] += qty;
      }
    } else {
      matrix[br]['Kho Tổng'] += qty;
    }
    matrix[br].total += qty;
  }

  const tbody = document.getElementById('ton1-table-matrix-tbody');
  tbody.innerHTML = '';
  BRAND_MAIN_5.forEach(b => {
    const m = matrix[b];
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><strong>${b}</strong></td>
      <td>${fmtNum(m['TP. HCM'])}</td>
      <td>${fmtNum(m['Miền Tây'])}</td>
      <td>${fmtNum(m['Miền Đông'])}</td>
      <td>${fmtNum(m['Miền Trung - TN'])}</td>
      <td>${fmtNum(m['Hà Nội'])}</td>
      <td>${fmtNum(m['Kho Tổng'])}</td>
      <td><strong>${fmtNum(m.total)}</strong></td>
    `;
    tbody.appendChild(tr);
  });
}

// -----------------------------------------------------------------------------
// SHEET 2.2: TỒN KHO TỔNG (5 KHO)
// -----------------------------------------------------------------------------
function renderTonSheet2() {
  const ton = APP_DATA.ton;
  const nRows = ton.data[0].length;

  let totalKho = 0;
  let prepQty = 0;
  let newQty = 0;
  let oldQty = 0;

  const whCards = {};
  WAREHOUSE_MAIN_5.forEach(wh => {
    whCards[wh] = { total: 0, prep: 0, newD: 0, old: 0 };
  });

  const colRk = ton.data[0];
  const colWh = ton.data[2];
  const colDist = ton.data[11];
  const colQty = ton.data[16];

  for (let i = 0; i < nRows; i++) {
    const rk = DICT[colRk[i]];
    const wh = DICT[colWh[i]];
    const dist = DICT[colDist[i]];
    const qty = colQty[i];

    if (rk !== 'KHO') continue;

    totalKho += qty;
    if (dist === 'prep') prepQty += qty;
    else if (dist === 'new_dist') newQty += qty;
    else if (['pp_6m', 'pp_1y', 'pp_2y', 'pp_over_2y'].includes(dist)) oldQty += qty;

    if (whCards[wh]) {
      whCards[wh].total += qty;
      if (dist === 'prep') whCards[wh].prep += qty;
      else if (dist === 'new_dist') whCards[wh].newD += qty;
      else if (['pp_6m', 'pp_1y', 'pp_2y', 'pp_over_2y'].includes(dist)) whCards[wh].old += qty;
    }
  }

  // KPIs
  document.getElementById('ton2-kpi-total').textContent = fmtNum(totalKho);
  document.getElementById('ton2-kpi-prep').textContent = fmtNum(prepQty);
  document.getElementById('ton2-kpi-new').textContent = fmtNum(newQty);
  document.getElementById('ton2-kpi-old').textContent = fmtNum(oldQty);

  // 5 Central Warehouse Cards
  const container = document.getElementById('ton2-central-warehouses-grid');
  container.innerHTML = '';
  WAREHOUSE_MAIN_5.forEach(wh => {
    const w = whCards[wh];
    const card = document.createElement('div');
    card.className = 'view-card';
    card.style.margin = '0';
    card.style.borderTop = '3px solid var(--primary)';
    card.innerHTML = `
      <div class="view-header" style="padding: 10px 14px; background: #f8fafc;">
        <strong style="color: var(--primary);">${wh}</strong>
        <span class="tag-badge tag-gold">${fmtNum(w.total)} sp</span>
      </div>
      <div class="view-body" style="padding: 10px 14px; font-size: 12px; line-height: 1.8;">
        <div>Chưa PP: <strong>${fmtNum(w.prep)}</strong> sp</div>
        <div>Mới PP (&lt;6th): <strong>${fmtNum(w.newD)}</strong> sp</div>
        <div>Hàng cũ (&gt;6th): <strong>${fmtNum(w.old)}</strong> sp</div>
      </div>
    `;
    container.appendChild(card);
  });

  // Hierarchy Table
  renderTonSheet2Hierarchy();
}

function renderTonSheet2Hierarchy() {
  const selWh = document.getElementById('ton2-f-wh').value;
  const searchKw = (document.getElementById('ton2-search').value || '').trim().toLowerCase();

  const ton = APP_DATA.ton;
  const nRows = ton.data[0].length;

  // Tổng tồn kho theo Tên hàng (br/gr ổn định theo tên hàng — lấy giá trị đầu tiên gặp)
  const itemSummary = {};

  const colRk = ton.data[0];
  const colWh = ton.data[2];
  const colBr = ton.data[3];
  const colGr = ton.data[5];
  const colItem = ton.data[6];
  const colQty = ton.data[16];

  for (let i = 0; i < nRows; i++) {
    if (DICT[colRk[i]] !== 'KHO') continue;
    const wh = DICT[colWh[i]];
    if (WAREHOUSE_MAIN_5.indexOf(wh) === -1) continue;   // chỉ 5 kho tổng
    if (selWh !== 'all' && wh !== selWh) continue;

    const it = DICT[colItem[i]];
    const gr = DICT[colGr[i]];
    if (searchKw && !it.toLowerCase().includes(searchKw) && !gr.toLowerCase().includes(searchKw)) continue;

    if (!itemSummary[it]) itemSummary[it] = { gr, br: DICT[colBr[i]], qty: 0 };
    itemSummary[it].qty += colQty[i];
  }

  const tbody = document.getElementById('ton2-table-hierarchy-tbody');
  tbody.innerHTML = '';
  const whSkus = APP_DATA.ton.warehouse_skus || {};

  const sortedItems = Object.keys(itemSummary).sort((a, b) => itemSummary[b].qty - itemSummary[a].qty).slice(0, 100);
  if (sortedItems.length === 0) {
    tbody.innerHTML = emptyRow(6, 'Không có tồn kho tại kho tổng khớp bộ lọc.');
    return;
  }

  // Gom SKU (MaHang§Operation) của 1 tên hàng theo phạm vi kho đang chọn
  const skFallbackKey = (sk) => sk.key || (sk.op ? (sk.mh + PM_SEP + sk.op) : sk.mh);
  const skusForItem = (it) => {
    let arr;
    if (selWh !== 'all') {
      arr = (whSkus[selWh] && whSkus[selWh][it]) ? whSkus[selWh][it].slice() : [];
    } else {
      const combined = {};
      WAREHOUSE_MAIN_5.forEach(w => {
        if (!(whSkus[w] && whSkus[w][it])) return;
        whSkus[w][it].forEach(sk => {
          const k = skFallbackKey(sk);
          if (!combined[k]) {
            combined[k] = { ...sk, key: k, sizes: { ...sk.sizes } };
          } else {
            combined[k].qty += sk.qty;
            for (const [sz, q] of Object.entries(sk.sizes)) {
              combined[k].sizes[sz] = (combined[k].sizes[sz] || 0) + q;
            }
          }
        });
      });
      arr = Object.values(combined);
    }
    // Xếp theo cặp: cùng MaHang liền nhau (mọi Operation), rồi mới sang MaHang khác
    return arr.sort((a, b) =>
      (a.mh || '').localeCompare(b.mh || '') || (a.op || '').localeCompare(b.op || '') || b.qty - a.qty);
  };

  sortedItems.forEach((it, idx) => {
    const info = itemSummary[it];
    const skus = skusForItem(it);

    // Dãy size tổng của tên hàng (chỉ tồn kho tổng, cộng từ các mã)
    const sizeAgg = {};
    skus.forEach(sk => {
      for (const [sz, q] of Object.entries(sk.sizes)) sizeAgg[sz] = (sizeAgg[sz] || 0) + q;
    });
    const sizesHtml = Object.entries(sizeAgg)
      .filter(([, q]) => q > 0)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8)
      .map(([sz, q]) => `<span class="size-badge">${sz}: <span class="size-val">${q}</span></span>`)
      .join('');

    const detailId = `ton2-detail-${idx}`;

    const tr = document.createElement('tr');
    tr.className = 'clickable-row';
    tr.style.cursor = 'pointer';
    tr.title = 'Bấm để bung xem chi tiết các mã hàng (SKU) và dãy size';
    tr.onclick = () => {
      const dEl = document.getElementById(detailId);
      if (!dEl) return;
      const show = dEl.style.display === 'none';
      dEl.style.display = show ? 'table-row' : 'none';
      const iconEl = tr.querySelector('.expand-icon');
      if (iconEl) iconEl.textContent = show ? '▼' : '▶';
    };
    const nMh = new Set(skus.map(s => s.mh)).size;
    tr.innerHTML = `
      <td><span class="expand-icon" style="margin-right: 5px; color: var(--primary);">▶</span><strong>${it}</strong></td>
      <td>${info.gr || '—'}</td>
      <td>${info.br || '—'}</td>
      <td><span class="tag-badge tag-info">${fmtNum(nMh)} mã</span> <span style="font-size:10px;color:var(--text-muted);">· ${fmtNum(skus.length)} SKU</span></td>
      <td><strong style="color: var(--primary);">${fmtNum(info.qty)}</strong></td>
      <td>${sizesHtml || '—'}</td>
    `;
    tbody.appendChild(tr);

    const trDetail = document.createElement('tr');
    trDetail.id = detailId;
    trDetail.style.display = 'none';
    trDetail.style.background = '#f8fafc';

    let subTableHtml;
    if (skus.length === 0) {
      subTableHtml = '<div style="padding: 10px; color: var(--text-muted); font-size: 12px;">Không có chi tiết mã hàng tại 5 kho tổng cho tên hàng này.</div>';
    } else {
      const prodMeta = APP_DATA.ton.product_meta || {};
      let prevMh2 = null;
      const rowsHtml = skus.slice(0, 50).map(sk => {
        const sizeBadges = Object.entries(sk.sizes)
          .filter(([, q]) => q > 0)
          .sort((a, b) => b[1] - a[1])
          .map(([sz, q]) => `<span class="size-badge">${sz}: <span class="size-val">${q}</span></span>`)
          .join('');
        // Thuộc tính đọc từ product_meta theo đúng SKU = MaHang§Operation
        const m = prodMeta[skFallbackKey(sk)] || [];
        const form = m[3] !== undefined ? DICT[m[3]] : '—';
        const style = m[4] !== undefined ? DICT[m[4]] : '—';
        const cg = m[5] !== undefined ? DICT[m[5]] : '—';
        const distCat = m[9] !== undefined ? DICT[m[9]] : '';
        const status = m[11] !== undefined ? DICT[m[11]] : '—';
        let raw = m[8] !== undefined ? DICT[m[8]] : '—';
        if (!raw) raw = '—';
        const firstOfMh = sk.mh !== prevMh2;
        prevMh2 = sk.mh;
        return `
          <tr style="font-size: 11px; background: #ffffff;${firstOfMh ? 'border-top:2px solid var(--border);' : ''}">
            <td>${firstOfMh ? `<strong>${sk.mh}</strong>` : ''}<div style="font-size:10px;color:var(--text-muted);">Op ${sk.op || '—'}</div></td>
            <td>${form || '—'} / ${style || '—'}</td>
            <td>${cg || '—'}</td>
            <td>${raw} <span class="tag-badge tag-info">${DIST_LABELS[distCat] || distCat || '—'}</span></td>
            <td>${status || '—'}</td>
            <td><strong style="color: var(--danger);">${fmtNum(sk.qty)}</strong></td>
            <td>${sizeBadges || '—'}</td>
          </tr>`;
      }).join('');

      subTableHtml = `
        <div style="padding: 10px 14px; background: #f1f5f9; border-left: 4px solid var(--primary); margin: 6px 0;">
          <div style="margin-bottom: 6px; font-weight: bold; color: var(--primary); font-size: 12px;">
            📋 SKU (MaHang · Operation) tại kho tổng cho [ ${it} ] — tối đa 50 dòng:
          </div>
          <table class="data-table" style="background: #ffffff; border: 1px solid var(--border); font-size: 11px;">
            <thead>
              <tr style="background: #e2e8f0;">
                <th>Mã hàng (SKU)</th>
                <th>Form / Style</th>
                <th>Màu sắc</th>
                <th>Kỳ PP (Dist_plan)</th>
                <th>Trạng thái</th>
                <th>Số tồn kho</th>
                <th>Dãy Size tại kho</th>
              </tr>
            </thead>
            <tbody>${rowsHtml}</tbody>
          </table>
        </div>`;
    }

    trDetail.innerHTML = `<td colspan="6" style="padding: 0 10px;">${subTableHtml}</td>`;
    tbody.appendChild(trDetail);
  });
}

// -----------------------------------------------------------------------------
// SHEET 2.3: TỒN KHO HTCH
// -----------------------------------------------------------------------------
function onTon3RegionChange() {
  const selRg = document.getElementById('ton3-f-region').value;
  buildStore360Index();

  // Phạm vi cửa hàng theo khu vực: tra cặp Store_name × Region từ ban.ov,
  // chỉ giữ các cửa hàng thực sự có dữ liệu tồn (STORE_DATA_MAP)
  const ov = APP_DATA.ban.ov;
  let storesInReg = new Set();
  if (ov && ov.data) {
    const colSt = ov.data[5];
    const colRg = ov.data[6];
    const n = colSt.length;
    for (let i = 0; i < n; i++) {
      const st = DICT[colSt[i]];
      const rg = DICT[colRg[i]];
      if ((selRg === 'all' || rg === selRg) && STORE_DATA_MAP && STORE_DATA_MAP[st]) {
        storesInReg.add(st);
      }
    }
  } else {
    storesInReg = new Set(Object.keys(STORE_DATA_MAP || {}));
  }

  ton3StoreList(selRg, 'all').forEach(st => storesInReg.add(st));   // + CH mới chưa có bán (vd Aeon Huế)
  const sortedTon3 = Array.from(storesInReg).sort((a, b) => a.localeCompare(b, 'vi'));
  const selQ = populateQlkdDropdown('ton3-f-qlkd', sortedTon3);
  populateStoreDropdown('ton3-f-store', sortedTon3.filter(st => selQ === 'all' || qlkdOf(st) === selQ));
  renderTonSheet3();
}

function resetTonSheet3Filters() {
  document.getElementById('ton3-f-region').value = 'all';
  document.getElementById('ton3-f-store').value = 'all';
  document.getElementById('ton3-f-qlkd').value = 'all';
  onTon3RegionChange();
}

// Khu vực của từng điểm bán (tra từ ban.ov). Kho (Kho Tổng hợp, Kho KDTT...) không có khu vực.
let STORE_REGION_MAP = null;
function storeRegionMap() {
  if (STORE_REGION_MAP) return STORE_REGION_MAP;
  STORE_REGION_MAP = {};
  const ov = APP_DATA.ban.ov;
  const cSt = ov.data[5], cRg = ov.data[6];
  for (let i = 0; i < cSt.length; i++) {
    const st = DICT[cSt[i]], rg = DICT[cRg[i]];
    // CH có cả dòng Event (hội chợ gắn tên CH) -> giữ khu vực chính, không để Event đè lên
    if (!STORE_REGION_MAP[st] || (STORE_REGION_MAP[st] === 'Event' && rg !== 'Event')) STORE_REGION_MAP[st] = rg;
  }
  // CH mới chưa phát sinh bán (vd Aeon Huế): lấy khu vực theo danh mục A_Region
  const master = APP_DATA.ban.store_region || {};
  for (const [st, rg] of Object.entries(master)) {
    if (!STORE_REGION_MAP[st] && STORE_DATA_MAP && STORE_DATA_MAP[st]) STORE_REGION_MAP[st] = rg;
  }
  return STORE_REGION_MAP;
}

// Cửa hàng có dữ liệu tồn thuộc khu vực (+ QLKD). Chỉ cửa hàng có khu vực -> loại các kho.
function ton3StoreList(selRg, selQ) {
  buildStore360Index();
  const srm = storeRegionMap();
  const okRg = (rg) => REGION_MAIN_5.includes(rg) || rg === 'Event';
  const stores = Object.keys(STORE_DATA_MAP || {}).filter(st => okRg(srm[st]) && (selRg === 'all' || srm[st] === selRg));
  return selQ && selQ !== 'all' ? stores.filter(st => qlkdOf(st) === selQ) : stores;
}

// Tồn theo trạng thái của từng cửa hàng (tính 1 lần, dùng lại)
let TON3_STORE_SUM = null;
function ton3StoreSums() {
  if (TON3_STORE_SUM) return TON3_STORE_SUM;
  buildStore360Index();
  const prodMeta = APP_DATA.ton.product_meta || {};
  TON3_STORE_SUM = {};
  for (const [st, info] of Object.entries(STORE_DATA_MAP || {})) {
    const a = { total: 0, fp: 0, sale: 0, tl: 0, newq: 0 };
    for (const [sku, it] of Object.entries(info.items)) {
      const q = it.ton;
      if (q <= 0) continue;
      const meta = prodMeta[sku] || [];
      const status = meta[11] !== undefined ? DICT[meta[11]] : 'Nguyên giá';
      const dist = meta[9] !== undefined ? DICT[meta[9]] : 'new_dist';
      a.total += q;
      if (status === 'Nguyên giá') a.fp += q; else if (status === 'Sale') a.sale += q; else if (status === 'Thanh lý') a.tl += q;
      if (dist === 'new_dist') a.newq += q;
    }
    TON3_STORE_SUM[st] = a;
  }
  return TON3_STORE_SUM;
}

// Tồn theo QLKD (Sheet 1 Tồn) — cửa hàng 5 khu vực, bỏ Event & kho
function renderTon1Qlkd() {
  const tb = document.getElementById('ton1-qlkd-tbody');
  if (!tb) return;
  const sums = ton3StoreSums();
  const stRg = storeRegionMap();
  const Q = {};
  ton3StoreList('all', 'all').forEach(st => {
    const s = sums[st];
    if (!s || s.total <= 0 || stRg[st] === 'Event') return;
    const k = qlkdOf(st);
    const a = Q[k] || (Q[k] = { rgs: new Set(), n: 0, total: 0, fp: 0, sale: 0, tl: 0, newq: 0 });
    a.n += 1; a.rgs.add(stRg[st]);
    ['total', 'fp', 'sale', 'tl', 'newq'].forEach(f => { a[f] += s[f]; });
  });
  const keys = Object.keys(Q).sort((a, b) => Q[b].total - Q[a].total);
  const grand = keys.reduce((t, k) => t + Q[k].total, 0);
  const pc = (a, b) => (b > 0 ? a / b * 100 : 0).toFixed(1) + '%';
  const T = { n: 0, total: 0, fp: 0, sale: 0, tl: 0, newq: 0 };
  const rows = keys.map(k => {
    const a = Q[k];
    Object.keys(T).forEach(f => { T[f] += a[f]; });
    const rgTxt = REGION_MAIN_5.filter(r => a.rgs.has(r)).join(', ') || '—';
    return `<tr ${qlkdRowAttrs('ton', k)}><td><strong>${k}</strong></td><td>${rgTxt}</td><td>${fmtNum(a.n)}</td>
      <td><strong>${fmtNum(a.total)}</strong></td><td>${fmtNum(a.fp)}</td><td>${fmtNum(a.sale)}</td><td>${fmtNum(a.tl)}</td>
      <td>${fmtNum(a.newq)}</td><td>${pc(a.fp, a.total)}</td><td>${fmtNum(a.n ? a.total / a.n : 0)}</td><td>${pc(a.total, grand)}</td></tr>`;
  });
  if (rows.length) {
    rows.push(`<tr style="background:#f8fafc;font-weight:700;"><td>Tổng</td><td></td><td>${fmtNum(T.n)}</td><td>${fmtNum(T.total)}</td>
      <td>${fmtNum(T.fp)}</td><td>${fmtNum(T.sale)}</td><td>${fmtNum(T.tl)}</td><td>${fmtNum(T.newq)}</td>
      <td>${pc(T.fp, T.total)}</td><td>${fmtNum(T.n ? T.total / T.n : 0)}</td><td>100%</td></tr>`);
  }
  tb.innerHTML = rows.length ? rows.join('') : emptyRow(11);
}

// Sheet 3 Tồn: tổng + từng cửa hàng của QLKD đang chọn (ẩn khi "Tất cả QLKD")
function renderTon3Qlkd(selRg, selQ, selSt) {
  const card = document.getElementById('ton3-qlkd-card');
  if (!card) return;
  card.hidden = selQ === 'all';
  if (selQ === 'all') return;
  const sums = ton3StoreSums();
  const stRg = storeRegionMap();
  const list = ton3StoreList(selRg, selQ).filter(st => sums[st] && sums[st].total > 0)
    .sort((a, b) => sums[b].total - sums[a].total);
  const T = { total: 0, fp: 0, sale: 0, tl: 0, newq: 0 };
  list.forEach(st => Object.keys(T).forEach(f => { T[f] += sums[st][f]; }));
  const pc = (a, b) => (b > 0 ? a / b * 100 : 0).toFixed(1) + '%';
  const cells = a => `<td><strong>${fmtNum(a.total)}</strong></td><td>${fmtNum(a.fp)}</td><td>${fmtNum(a.sale)}</td>
    <td>${fmtNum(a.tl)}</td><td>${fmtNum(a.newq)}</td><td>${pc(a.fp, a.total)}</td><td>${pc(a.total, T.total)}</td>`;
  const rows = [`<tr style="background:#f8fafc;font-weight:700;"><td></td><td>TỔNG ${selQ}</td><td>${fmtNum(list.length)} CH</td>${cells(T)}</tr>`]
    .concat(list.map((st, n) => `<tr ${qlkdStoreRowAttrs('ton3', st, selSt)}><td>${n + 1}</td><td><strong>${st}</strong></td><td>${stRg[st] || '—'}</td>${cells(sums[st])}</tr>`));
  document.getElementById('ton3-qlkd-tbody').innerHTML = list.length ? rows.join('') : emptyRow(10);
  document.getElementById('ton3-qlkd-title').textContent = `Cửa hàng thuộc QLKD: ${selQ}`;
  document.getElementById('ton3-qlkd-sub').textContent =
    `Tồn hiện tại${selRg !== 'all' ? ' · ' + selRg : ''} · bấm 1 cửa hàng để xem riêng cửa hàng đó`;
}

function renderTonSheet3() {
  const selRg = document.getElementById('ton3-f-region').value;
  const selSt = document.getElementById('ton3-f-store').value;
  const selQ = document.getElementById('ton3-f-qlkd').value;

  const ton = APP_DATA.ton;
  const nRows = ton.data[0].length;

  let totalQty = 0;
  let fpQty = 0;
  let saleQty = 0;
  let tlQty = 0;
  let newQty = 0;

  const ageBrackets = {
    'prep': { label: 'Chuẩn bị PP', qty: 0 },
    'new_dist': { label: 'Mới PP (0-5th)', qty: 0 },
    'pp_6m': { label: 'PP 6 tháng', qty: 0 },
    'pp_1y': { label: 'PP 1 năm', qty: 0 },
    'pp_2y': { label: 'PP 2 năm', qty: 0 },
    'pp_over_2y': { label: 'PP > 2 năm', qty: 0 }
  };

  const brandStats = {};
  BRAND_MAIN_5.forEach(b => {
    brandStats[b] = { fp: 0, sale: 0, tl: 0, total: 0 };
  });

  const colRk = ton.data[0];
  const colRg = ton.data[1];
  const colBr = ton.data[3];
  const colDist = ton.data[11];
  const colStatus = ton.data[15];
  const colQty = ton.data[16];

  buildStore360Index();
  const oneStore = selSt !== 'all' && STORE_DATA_MAP && STORE_DATA_MAP[selSt];
  const ton3Stores = oneStore ? [selSt] : (selQ !== 'all' ? ton3StoreList(selRg, selQ) : null);
  if (ton3Stores) {
    // TÍNH CHÍNH XÁC THEO CỬA HÀNG ĐƯỢC CHỌN / CÁC CỬA HÀNG CỦA QLKD ĐƯỢC CHỌN
    const prodMeta = APP_DATA.ton.product_meta || {};

    for (const stName of ton3Stores) {
    const stInfo = STORE_DATA_MAP[stName];
    for (const [sku, itData] of Object.entries(stInfo.items)) {
      const qty = itData.ton;
      if (qty <= 0) continue;

      const meta = prodMeta[sku] || [];
      const br = meta[2] !== undefined ? DICT[meta[2]] : 'Khác';
      const dist = meta[9] !== undefined ? DICT[meta[9]] : 'new_dist';
      const status = meta[11] !== undefined ? DICT[meta[11]] : 'Nguyên giá';

      totalQty += qty;
      if (status === 'Nguyên giá') fpQty += qty;
      else if (status === 'Sale') saleQty += qty;
      else if (status === 'Thanh lý') tlQty += qty;

      if (dist === 'new_dist') newQty += qty;

      if (ageBrackets[dist]) {
        ageBrackets[dist].qty += qty;
      }

      if (brandStats[br]) {
        if (status === 'Nguyên giá') brandStats[br].fp += qty;
        else if (status === 'Sale') brandStats[br].sale += qty;
        else if (status === 'Thanh lý') brandStats[br].tl += qty;
        brandStats[br].total += qty;
      }
    }
    }
  } else {
    // TÍNH THEO TOÀN HỆ THỐNG HOẶC KHU VỰC
    for (let i = 0; i < nRows; i++) {
      const rk = DICT[colRk[i]];
      const rg = DICT[colRg[i]];
      const br = DICT[colBr[i]];
      const dist = DICT[colDist[i]];
      const status = DICT[colStatus[i]] || 'Nguyên giá';
      const qty = colQty[i];

      if (rk !== 'CH') continue;
      if (selRg !== 'all' && rg !== selRg) continue;

      totalQty += qty;
      if (status === 'Nguyên giá') fpQty += qty;
      else if (status === 'Sale') saleQty += qty;
      else if (status === 'Thanh lý') tlQty += qty;

      if (dist === 'new_dist') newQty += qty;

      if (ageBrackets[dist]) {
        ageBrackets[dist].qty += qty;
      }

      if (brandStats[br]) {
        if (status === 'Nguyên giá') brandStats[br].fp += qty;
        else if (status === 'Sale') brandStats[br].sale += qty;
        else if (status === 'Thanh lý') brandStats[br].tl += qty;
        brandStats[br].total += qty;
      }
    }
  }

  // KPIs
  document.getElementById('ton3-kpi-total').textContent = fmtNum(totalQty);
  document.getElementById('ton3-kpi-fp').textContent = fmtNum(fpQty);
  document.getElementById('ton3-kpi-fp-rate').textContent = totalQty > 0 ? `${(fpQty / totalQty * 100).toFixed(1)}% tổng tồn` : '0%';
  document.getElementById('ton3-kpi-sale').textContent = fmtNum(saleQty);
  document.getElementById('ton3-kpi-sale-rate').textContent = totalQty > 0 ? `${(saleQty / totalQty * 100).toFixed(1)}% tổng tồn` : '0%';
  document.getElementById('ton3-kpi-tl').textContent = fmtNum(tlQty);
  document.getElementById('ton3-kpi-tl-rate').textContent = totalQty > 0 ? `${(tlQty / totalQty * 100).toFixed(1)}% tổng tồn` : '0%';
  document.getElementById('ton3-kpi-new').textContent = fmtNum(newQty);
  document.getElementById('ton3-kpi-new-rate').textContent = totalQty > 0 ? `${(newQty / totalQty * 100).toFixed(1)}% tổng tồn` : '0%';

  // Age Breakdown Chart & Table
  renderTon3Age(ageBrackets, totalQty);

  // 5 Brand Table
  const tbodyBrands = document.getElementById('ton3-table-brands-tbody');
  tbodyBrands.innerHTML = '';
  BRAND_MAIN_5.forEach(b => {
    const s = brandStats[b];
    const share = totalQty > 0 ? (s.total / totalQty * 100) : 0;
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><strong>${b}</strong></td>
      <td>${fmtNum(s.fp)}</td>
      <td>${fmtNum(s.sale)}</td>
      <td>${fmtNum(s.tl)}</td>
      <td><strong>${fmtNum(s.total)}</strong></td>
      <td>${share.toFixed(1)}%</td>
    `;
    tbodyBrands.appendChild(tr);
  });

  // Cửa hàng thuộc QLKD đang chọn
  renderTon3Qlkd(selRg, selQ, selSt);

  // Top 10 Bán chậm tồn cao nguyên giá
  renderTon3SlowMoving(selSt, (!oneStore && selQ !== 'all') ? ton3Stores : null);
}

function renderTon3Age(ageBrackets, totalQty) {
  const tbody = document.getElementById('ton3-table-age-tbody');
  tbody.innerHTML = '';

  const labels = [];
  const vals = [];

  for (const [k, v] of Object.entries(ageBrackets)) {
    labels.push(v.label);
    vals.push(v.qty);
    const share = totalQty > 0 ? (v.qty / totalQty * 100) : 0;

    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><strong>${v.label}</strong></td>
      <td><strong>${fmtNum(v.qty)}</strong></td>
      <td>${share.toFixed(1)}%</td>
    `;
    tbody.appendChild(tr);
  }

  const chartEl = document.getElementById('ton3-chart-age');
  const data = [{
    x: labels,
    y: vals,
    type: 'bar',
    marker: { color: ['#0284c7', '#16a34a', '#eab308', '#f97316', '#ef4444', '#7f1d1d'] }
  }];

  const layout = {
    margin: { t: 15, r: 15, b: 40, l: 45 },
    yaxis: { title: 'Số lượng (sp)' },
    plot_bgcolor: '#f8fafc'
  };

  Plotly.newPlot(chartEl, data, layout, { responsive: true, displayModeBar: false });
}

function ton3SlowRecBadge(ton) {
  if (ton > 15) return '<span class="badge-rec" style="background:#fee2e2; color:#991b1b; border-color:#fca5a5;">Điều chuyển về Kho / Kích cầu</span>';
  if (ton > 8) return '<span class="badge-rec">Trưng bày lại trung tâm kệ</span>';
  return '<span class="badge-rec">Điều chuyển sang CH bán tốt</span>';
}

function renderTon3SlowMoving(selSt, storeList) {
  const tbody = document.getElementById('ton3-table-slow-tbody');
  tbody.innerHTML = '';

  buildStore360Index();
  const prodMeta = APP_DATA.ton.product_meta || {};

  const targetStores = (selSt && selSt !== 'all') ? [selSt] : (storeList || Object.keys(STORE_DATA_MAP || {}));

  // Gom theo (Brand, Tên hàng) — mỗi nhóm chứa các mã ứ đọng chi tiết
  const groups = {};
  targetStores.forEach(st => {
    const stInfo = STORE_DATA_MAP[st];
    if (!stInfo) return;
    for (const [sku, itData] of Object.entries(stInfo.items)) {
      if ((itData.ton || 0) <= 5) continue;
      const meta = prodMeta[sku] || [];
      const status = meta[11] !== undefined ? DICT[meta[11]] : 'Nguyên giá';
      const soldFlag = meta[7] !== undefined ? DICT[meta[7]] : 'not_sold_90';
      if (status !== 'Nguyên giá') continue;
      if (!(soldFlag === 'not_sold_90' || itData.ban === 0)) continue;

      const mh = itData.mh || splitSku(sku)[0];
      const op = itData.op || splitSku(sku)[1];
      const br = meta[2] !== undefined ? DICT[meta[2]] : '—';
      const name = meta[0] !== undefined ? DICT[meta[0]] : '—';
      const gkey = `${br}__${name}`;
      if (!groups[gkey]) groups[gkey] = { br, name, tonSum: 0, banSum: 0, mhSet: new Set(), stSet: new Set(), rows: [] };
      groups[gkey].tonSum += itData.ton;
      groups[gkey].banSum += itData.ban;
      groups[gkey].mhSet.add(mh);
      groups[gkey].stSet.add(st);
      groups[gkey].rows.push({
        mh, op, st,
        gr: meta[1] !== undefined ? DICT[meta[1]] : '—',
        form: meta[3] !== undefined ? DICT[meta[3]] : '—',
        style: meta[4] !== undefined ? DICT[meta[4]] : '—',
        color: meta[5] !== undefined ? DICT[meta[5]] : '—',
        price: (meta[6] !== undefined ? meta[6] : 0),
        ton: itData.ton,
        ban: itData.ban
      });
    }
  });

  const topGroups = Object.values(groups).sort((a, b) => b.tonSum - a.tonSum).slice(0, 12);
  if (topGroups.length === 0) {
    tbody.innerHTML = emptyRow(7, 'Không phát hiện mã hàng ứ đọng nguyên giá cao trong phạm vi đang chọn.');
    return;
  }

  topGroups.forEach((g, idx) => {
    const detailId = `ton3-slow-detail-${idx}`;
    // Xếp theo cặp: cùng MaHang đứng liền nhau (mọi Operation), rồi mới sang MaHang khác
    g.rows.sort((a, b) =>
      a.mh.localeCompare(b.mh) || a.op.localeCompare(b.op) || b.ton - a.ton);

    const tr = document.createElement('tr');
    tr.className = 'clickable-row';
    tr.style.cursor = 'pointer';
    tr.title = 'Bấm để xem chi tiết từng mã hàng';
    tr.onclick = () => {
      const dEl = document.getElementById(detailId);
      if (!dEl) return;
      const show = dEl.style.display === 'none';
      dEl.style.display = show ? 'table-row' : 'none';
      const iconEl = tr.querySelector('.expand-icon');
      if (iconEl) iconEl.textContent = show ? '▼' : '▶';
    };
    tr.innerHTML = `
      <td>${idx + 1}</td>
      <td>${g.br}</td>
      <td><span class="expand-icon" style="margin-right: 5px; color: var(--primary);">▶</span><strong>${g.name}</strong></td>
      <td><span class="tag-badge tag-down">${fmtNum(g.mhSet.size)} mã</span> <span style="font-size:10px;color:var(--text-muted);">· ${fmtNum(g.stSet.size)} CH</span></td>
      <td><strong style="color: var(--danger); font-size: 13px;">${fmtNum(g.tonSum)}</strong></td>
      <td>${fmtNum(g.banSum)}</td>
      <td style="text-align: center;"><button class="filter-btn-apply" style="padding: 3px 10px; font-size: 11px;">Xem mã hàng</button></td>
    `;
    tbody.appendChild(tr);

    let prevMh = null;
    const rowsHtml = g.rows.slice(0, 50).map(r => {
      const firstOfMh = r.mh !== prevMh;
      prevMh = r.mh;
      return `
      <tr style="font-size: 11px; background: #ffffff;${firstOfMh ? 'border-top:2px solid var(--border);' : ''}">
        <td>${firstOfMh ? `<strong>${r.mh}</strong>` : ''}<div style="font-size:10px;color:var(--text-muted);">Op ${r.op || '—'}</div></td>
        <td>${r.st}</td>
        <td>${r.gr} · ${r.form} · ${r.color}</td>
        <td>${metaPriceStr(r.price)}</td>
        <td><strong style="color: var(--danger);">${fmtNum(r.ton)}</strong></td>
        <td>${fmtNum(r.ban)}</td>
        <td>${ton3SlowRecBadge(r.ton)}</td>
      </tr>`;
    }).join('');

    const trDetail = document.createElement('tr');
    trDetail.id = detailId;
    trDetail.style.display = 'none';
    trDetail.style.background = '#f8fafc';
    trDetail.innerHTML = `
      <td colspan="7" style="padding: 0 10px;">
        <div style="padding: 10px 14px; background: #f1f5f9; border-left: 4px solid var(--danger); margin: 6px 0;">
          <div style="margin-bottom: 6px; font-weight: bold; color: var(--danger); font-size: 12px;">
            📋 SKU (MaHang · Operation) ứ đọng của [ ${g.name} ] — tối đa 50 dòng tồn nhiều nhất:
          </div>
          <table class="data-table" style="background: #ffffff; border: 1px solid var(--border); font-size: 11px;">
            <thead>
              <tr style="background: #e2e8f0;">
                <th>Mã hàng</th>
                <th>Cửa hàng</th>
                <th>Nhóm / Form / Màu</th>
                <th>Đơn giá</th>
                <th>Tồn NG</th>
                <th>Đã bán ${APP_DATA.ref.year}</th>
                <th>Kiến nghị hành động</th>
              </tr>
            </thead>
            <tbody>${rowsHtml}</tbody>
          </table>
        </div>
      </td>
    `;
    tbody.appendChild(trDetail);
  });
}

// -----------------------------------------------------------------------------
// SHEET 2.4: CHI TIẾT TỒN KHO & GÃY SIZE
// -----------------------------------------------------------------------------

// Nhóm hàng của 1 mã (product_meta[..][12]); '' nếu payload cũ chưa có
function ton4MetaCatGroup(meta) {
  return (meta && meta[12] !== undefined) ? DICT[meta[12]] : '';
}
function ton4CatGroupOk(catg) {
  return CURRENT_TON4_CAT_GROUP === 'all' || catg === CURRENT_TON4_CAT_GROUP;
}

function setTon4CatGroup(cg) {
  CURRENT_TON4_CAT_GROUP = cg;
  document.querySelectorAll('#ton4-cat-group-list .seg-btn').forEach(b => {
    const label = cg === 'all' ? 'Tất cả nhóm' : cg;
    b.classList.toggle('active', b.textContent.trim() === label);
  });
  onTon4BrandChange();  // cascade: brand -> group -> item -> render
}

function onTon4RegionChange() {
  const selRg = document.getElementById('ton4-f-region').value;
  buildStore360Index();

  const ov = APP_DATA.ban.ov;
  let storesInReg = new Set();
  if (ov && ov.data) {
    const colSt = ov.data[5];
    const colRg = ov.data[6];
    const n = colSt.length;
    for (let i = 0; i < n; i++) {
      const st = DICT[colSt[i]];
      const rg = DICT[colRg[i]];
      if (selRg === 'all' || rg === selRg) {
        if (STORE_DATA_MAP && STORE_DATA_MAP[st]) {
          storesInReg.add(st);
        }
      }
    }
  } else {
    storesInReg = new Set(Object.keys(STORE_DATA_MAP || {}));
  }

  const allStores = Array.from(storesInReg).sort((a, b) => a.localeCompare(b, 'vi'));
  populateStoreDropdown('ton4-f-store', allStores);
  renderTonSheet4();
}

function onTon4BrandChange() {
  const selBr = document.getElementById('ton4-f-brand').value;
  const prodMeta = APP_DATA.ton.product_meta || {};

  const groups = new Set();
  for (const meta of Object.values(prodMeta)) {
    if (!ton4CatGroupOk(ton4MetaCatGroup(meta))) continue;
    const br = meta[2] !== undefined ? DICT[meta[2]] : '—';
    const gr = meta[1] !== undefined ? DICT[meta[1]] : '—';
    if (selBr === 'all' || br === selBr) {
      groups.add(gr);
    }
  }

  const grEl = document.getElementById('ton4-f-group');
  if (grEl) {
    grEl.innerHTML = '<option value="all">Tất cả Nhóm</option>';
    Array.from(groups).sort().forEach(g => {
      grEl.innerHTML += `<option value="${g}">${g}</option>`;
    });
  }

  onTon4GroupChange();
}

function onTon4GroupChange() {
  const selBr = document.getElementById('ton4-f-brand').value;
  const selGr = document.getElementById('ton4-f-group').value;
  const prodMeta = APP_DATA.ton.product_meta || {};

  const items = new Set();
  for (const meta of Object.values(prodMeta)) {
    if (!ton4CatGroupOk(ton4MetaCatGroup(meta))) continue;
    const br = meta[2] !== undefined ? DICT[meta[2]] : '—';
    const gr = meta[1] !== undefined ? DICT[meta[1]] : '—';
    const it = meta[0] !== undefined ? DICT[meta[0]] : '—';
    if (selBr !== 'all' && br !== selBr) continue;
    if (selGr !== 'all' && gr !== selGr) continue;
    items.add(it);
  }

  const itEl = document.getElementById('ton4-f-item');
  if (itEl) {
    itEl.innerHTML = '<option value="all">Tất cả Tên hàng</option>';
    Array.from(items).sort().forEach(it => {
      itEl.innerHTML += `<option value="${it}">${it}</option>`;
    });
  }

  renderTonSheet4();
}

function resetTonSheet4Filters() {
  document.getElementById('ton4-f-region').value = 'all';
  document.getElementById('ton4-f-store').value = 'all';
  document.getElementById('ton4-f-status').value = 'all';
  document.getElementById('ton4-f-brand').value = 'all';
  document.getElementById('ton4-f-sold').value = 'all';
  document.getElementById('ton4-f-dist').value = 'all';
  document.getElementById('ton4-search-sku').value = '';
  CURRENT_TON4_CAT_GROUP = 'all';
  document.querySelectorAll('#ton4-cat-group-list .seg-btn').forEach(b => {
    b.classList.toggle('active', b.textContent.trim() === 'Tất cả nhóm');
  });
  onTon4RegionChange();
  onTon4BrandChange();
}

function renderTonSheet4() {
  buildStore360Index();

  const selRg = document.getElementById('ton4-f-region').value;
  const selSt = document.getElementById('ton4-f-store').value;
  const selStatus = document.getElementById('ton4-f-status').value;
  const selBr = document.getElementById('ton4-f-brand').value;
  const selGr = document.getElementById('ton4-f-group').value;
  const selIt = document.getElementById('ton4-f-item').value;
  const selSold = document.getElementById('ton4-f-sold').value;
  const selDist = document.getElementById('ton4-f-dist').value;
  const searchKw = (document.getElementById('ton4-search-sku').value || '').trim().toLowerCase();

  const ton = APP_DATA.ton;
  const nRows = ton.data[0].length;
  const prodMeta = APP_DATA.ton.product_meta || {};

  // 1. Bảng tổng hợp Brand × Tên hàng — đồng bộ theo Cửa hàng / Khu vực đang chọn
  const summaryCard = document.getElementById('ton4-summary-card');
  if (!searchKw && selIt === 'all') {
    summaryCard.style.display = 'block';
    renderTon4SummaryTable(selRg, selStatus, selBr, selGr, selSt);
  } else {
    summaryCard.style.display = 'none';
  }

  // 2. Danh sách cửa hàng cần soi chi tiết SKU
  //    - Chọn 1 CH cụ thể  -> đúng CH đó
  //    - Còn lại           -> toàn bộ CH trong danh sách (đã được lọc theo Khu vực)
  let targetStores = [];
  if (selSt && selSt !== 'all') {
    targetStores = [selSt];
  } else {
    const storeSelect = document.getElementById('ton4-f-store');
    targetStores = Array.from(storeSelect.options).map(o => o.value).filter(v => v !== 'all');
  }

  let skuList = [];
  targetStores.forEach(st => {
    const stInfo = STORE_DATA_MAP[st];
    if (!stInfo) return;

    for (const [sku, itData] of Object.entries(stInfo.items)) {
      // Chỉ lấy SKU CÒN TỒN
      if ((itData.ton || 0) <= 0) continue;

      const meta = prodMeta[sku] || [];
      const mh = itData.mh || splitSku(sku)[0];
      const op = itData.op || splitSku(sku)[1];
      const itName = meta[0] !== undefined ? DICT[meta[0]] : '—';
      const gr = meta[1] !== undefined ? DICT[meta[1]] : '—';
      const br = meta[2] !== undefined ? DICT[meta[2]] : '—';
      const form = meta[3] !== undefined ? DICT[meta[3]] : '—';
      const style = meta[4] !== undefined ? DICT[meta[4]] : '—';
      const color = meta[5] !== undefined ? DICT[meta[5]] : '—';
      const price = (meta[6] !== undefined ? meta[6] : 0);
      const soldFlag = meta[7] !== undefined ? DICT[meta[7]] : 'not_sold_90';
      const dist = meta[9] !== undefined ? DICT[meta[9]] : 'new_dist';
      const hasLc = meta[10] || 0;
      const status = meta[11] !== undefined ? DICT[meta[11]] : 'Nguyên giá';

      if (!ton4CatGroupOk(ton4MetaCatGroup(meta))) continue;
      if (selStatus !== 'all' && status !== selStatus) continue;
      if (selBr !== 'all' && br !== selBr) continue;
      if (selGr !== 'all' && gr !== selGr) continue;
      if (selIt !== 'all' && itName !== selIt) continue;
      if (selSold !== 'all' && soldFlag !== selSold) continue;
      if (selDist !== 'all' && dist !== selDist) continue;

      if (searchKw) {
        const match = mh.toLowerCase().includes(searchKw) ||
                      op.toLowerCase().includes(searchKw) ||
                      itName.toLowerCase().includes(searchKw) ||
                      color.toLowerCase().includes(searchKw);
        if (!match) continue;
      }

      skuList.push({
        mh, op, st, itName, gr, br, form, style, color, price, status, dist, soldFlag, hasLc,
        ton: itData.ton,
        ban: itData.ban,
        sizes: itData.sizes
      });
    }
  });

  // Xếp theo cặp: cùng Tên hàng -> cùng MaHang liền nhau (mọi Operation) -> mới sang MaHang khác
  skuList.sort((a, b) =>
    a.itName.localeCompare(b.itName, 'vi') ||
    a.mh.localeCompare(b.mh) ||
    a.op.localeCompare(b.op) ||
    b.ton - a.ton);
  document.getElementById('ton4-result-count').textContent = `${fmtNum(skuList.length)} sản phẩm`;

  // Render SKU detail table with subtotals per Item
  const tbody = document.getElementById('ton4-table-skus-tbody');
  tbody.innerHTML = '';

  if (skuList.length === 0) {
    tbody.innerHTML = emptyRow(15, 'Không có mã hàng CÒN TỒN khớp điều kiện lọc.');
    return;
  }

  let curItemName = null;
  let itemSubtotalTon = 0;
  let itemSubtotalBan = 0;

  const flushSubtotal = () => {
    if (curItemName) {
      const trSub = document.createElement('tr');
      trSub.style.background = '#f1f5f9';
      trSub.style.fontWeight = 'bold';
      trSub.innerHTML = `
        <td colspan="11" style="text-align: right; color: var(--primary);">TỔNG CỘNG CHO [ ${curItemName} ]:</td>
        <td style="color: var(--primary);">${fmtNum(itemSubtotalTon)}</td>
        <td style="color: var(--primary);">${fmtNum(itemSubtotalBan)}</td>
        <td colspan="2"></td>
      `;
      tbody.appendChild(trSub);
    }
  };

  const displayLimit = 200;
  let prevMh4 = null;
  skuList.slice(0, displayLimit).forEach(s => {
    if (s.itName !== curItemName) {
      flushSubtotal();
      curItemName = s.itName;
      itemSubtotalTon = 0;
      itemSubtotalBan = 0;
      prevMh4 = null;
    }
    const firstOfMh = s.mh !== prevMh4;
    prevMh4 = s.mh;

    itemSubtotalTon += s.ton;
    itemSubtotalBan += s.ban;

    let soldBadge = '<span class="tag-badge tag-neutral">Bình thường</span>';
    if (s.soldFlag === 'sold_30') soldBadge = '<span class="tag-badge tag-up">⚡ Bán ≤30d</span>';
    else if (s.soldFlag === 'sold_60') soldBadge = '<span class="tag-badge tag-info">Bán 31-60d</span>';
    else if (s.soldFlag === 'sold_90') soldBadge = '<span class="tag-badge tag-gold">Bán 61-90d</span>';
    else if (s.soldFlag === 'not_sold_90') soldBadge = '<span class="tag-badge tag-down">⚠️ Ứ đọng &gt;90d</span>';

    const lcBadge = s.hasLc === 1 ? '<span class="tag-badge tag-gold">🔄 Vừa nhận LC (4th)</span>' : '—';

    // Dãy size — chỉ size còn tồn
    const sizeKeys = Object.keys(s.sizes).filter(sz => (s.sizes[sz].ton || 0) > 0).slice(0, 6);
    const sizesHtml = sizeKeys.map(sz => `<span class="size-badge">${sz}: <span class="size-val">${s.sizes[sz].ton}</span></span>`).join('');

    const tr = document.createElement('tr');
    if (firstOfMh) tr.style.borderTop = '2px solid var(--border)';
    tr.innerHTML = `
      <td>${firstOfMh ? `<strong>${s.mh}</strong>` : ''}<div style="font-size:10px;color:var(--text-muted);">Op ${s.op || '—'}</div></td>
      <td>${s.itName}</td>
      <td>${s.gr}</td>
      <td>${s.br}</td>
      <td>${s.form} / ${s.style}</td>
      <td>${s.color}</td>
      <td>${metaPriceStr(s.price)}</td>
      <td><span class="tag-badge ${s.status === 'Nguyên giá' ? 'tag-up' : 'tag-neutral'}">${s.status}</span></td>
      <td>${s.dist}</td>
      <td>${soldBadge}</td>
      <td>${lcBadge}</td>
      <td><strong style="color: var(--danger);">${fmtNum(s.ton)}</strong></td>
      <td><strong style="color: var(--primary);">${fmtNum(s.ban)}</strong></td>
      <td>${sizesHtml || '—'}</td>
      <td style="text-align: center;">
        <button class="filter-btn-apply" style="padding: 3px 8px; font-size: 11px; background: var(--primary);" onclick="openSizeModal('${s.mh}', '${s.st}', '${s.op}')">
          🔍 Soi Size
        </button>
      </td>
    `;
    tbody.appendChild(tr);
  });

  flushSubtotal();
}

function renderTon4SummaryTable(selRg, selStatus, selBr, selGr, selSt) {
  const tbody = document.getElementById('ton4-table-summary-tbody');
  tbody.innerHTML = '';

  const itemGroupMap = {};

  if (selSt && selSt !== 'all') {
    // Đồng bộ đúng cửa hàng đang chọn — tính từ tồn cấp mã hàng của CH đó
    buildStore360Index();
    const stInfo = STORE_DATA_MAP[selSt];
    const prodMeta = APP_DATA.ton.product_meta || {};
    if (stInfo) {
      for (const [sku, itData] of Object.entries(stInfo.items)) {
        if ((itData.ton || 0) <= 0) continue;
        const meta = prodMeta[sku] || [];
        if (!ton4CatGroupOk(ton4MetaCatGroup(meta))) continue;
        const it = meta[0] !== undefined ? DICT[meta[0]] : '—';
        const gr = meta[1] !== undefined ? DICT[meta[1]] : '—';
        const br = meta[2] !== undefined ? DICT[meta[2]] : '—';
        const status = meta[11] !== undefined ? DICT[meta[11]] : 'Nguyên giá';
        if (selStatus !== 'all' && status !== selStatus) continue;
        if (selBr !== 'all' && br !== selBr) continue;
        if (selGr !== 'all' && gr !== selGr) continue;
        const key = `${br}__${gr}__${it}`;
        if (!itemGroupMap[key]) itemGroupMap[key] = { br, gr, it, qty: 0 };
        itemGroupMap[key].qty += itData.ton;
      }
    }
  } else {
    // Toàn hệ thống / theo khu vực — chỉ lấy tồn tại Cửa hàng (rk = 'CH')
    const ton = APP_DATA.ton;
    const nRows = ton.data[0].length;
    const colRk = ton.data[0];
    const colRg = ton.data[1];
    const colBr = ton.data[3];
    const colGr = ton.data[5];
    const colItem = ton.data[6];
    const colStatus = ton.data[15];
    const colQty = ton.data[16];
    const colCatg = ton.data[17]; // nhóm hàng Sheet 4 (có thể undefined ở payload cũ)

    for (let i = 0; i < nRows; i++) {
      const rk = DICT[colRk[i]];
      const rg = DICT[colRg[i]];
      const br = DICT[colBr[i]];
      const gr = DICT[colGr[i]];
      const it = DICT[colItem[i]];
      const status = DICT[colStatus[i]] || 'Nguyên giá';
      const qty = colQty[i];
      const catg = colCatg ? (DICT[colCatg[i]] || '') : '';

      if (rk !== 'CH') continue;
      if (!ton4CatGroupOk(catg)) continue;
      if (selRg !== 'all' && rg !== selRg) continue;
      if (selStatus !== 'all' && status !== selStatus) continue;
      if (selBr !== 'all' && br !== selBr) continue;
      if (selGr !== 'all' && gr !== selGr) continue;

      const key = `${br}__${gr}__${it}`;
      if (!itemGroupMap[key]) itemGroupMap[key] = { br, gr, it, qty: 0 };
      itemGroupMap[key].qty += qty;
    }
  }

  const sortedKeys = Object.keys(itemGroupMap).sort((a, b) => itemGroupMap[b].qty - itemGroupMap[a].qty).slice(0, 30);
  if (sortedKeys.length === 0) {
    tbody.innerHTML = emptyRow(5, 'Không có tồn kho tại cửa hàng khớp bộ lọc hiện tại.');
    return;
  }
  sortedKeys.forEach(k => {
    const item = itemGroupMap[k];
    const itIdx = dictIndex(item.it);

    let sizesHtml = '';
    if (itIdx !== -1 && APP_DATA.ton.sizes[itIdx]) {
      const sizesArr = APP_DATA.ton.sizes[itIdx].sort((a, b) => b[1] - a[1]).slice(0, 6);
      sizesHtml = sizesArr.map(s => `<span class="size-badge">${DICT[s[0]]}: <span class="size-val">${s[1]}</span></span>`).join('');
    }

    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><strong>${item.br}</strong></td>
      <td>${item.gr}</td>
      <td><strong>${item.it}</strong></td>
      <td><strong>${fmtNum(item.qty)}</strong></td>
      <td>${sizesHtml || '—'}</td>
    `;
    tbody.appendChild(tr);
  });
}

// =============================================================================
// MODAL ĐỐI SOÁT SIZE CHI TIẾT & CẢNH BÁO GÃY SIZE
// =============================================================================
function openSizeModal(mahang, storeName, operation) {
  buildStore360Index();
  const st = storeName || Object.keys(STORE_DATA_MAP || {})[0];
  const stInfo = STORE_DATA_MAP[st];
  if (!stInfo) return;
  const sku = (operation !== undefined && operation !== '') ? (mahang + PM_SEP + operation) : mahang;
  const itData = stInfo.items[sku] || stInfo.items[mahang];
  if (!itData) return;

  const prodMeta = APP_DATA.ton.product_meta || {};
  const meta = prodMeta[sku] || prodMeta[mahang] || [];

  const itemName = meta[0] !== undefined ? DICT[meta[0]] : '—';
  const gr = meta[1] !== undefined ? DICT[meta[1]] : '—';
  const br = meta[2] !== undefined ? DICT[meta[2]] : '—';
  const form = meta[3] !== undefined ? DICT[meta[3]] : '—';
  const color = meta[5] !== undefined ? DICT[meta[5]] : '—';
  const price = (meta[6] !== undefined ? meta[6] : 0);

  document.getElementById('size-modal-title').textContent =
    `ĐỐI SOÁT KÍCH CỠ (SIZE): ${mahang}${operation ? ' · Op ' + operation : ''} — TẠI ${st}`;
  document.getElementById('size-modal-meta').innerHTML = `
    <strong>Thương hiệu:</strong> ${br} | <strong>Tên sản phẩm:</strong> ${itemName} |
    <strong>Nhóm:</strong> ${gr} | <strong>Form:</strong> ${form} | <strong>Màu:</strong> ${color} |
    <strong>Đơn giá:</strong> ${metaPriceStr(price)} |
    <strong>Tổng Bán:</strong> <span style="color: var(--primary); font-weight: bold;">${fmtNum(itData.ban)} sp</span> | 
    <strong>Tổng Tồn:</strong> <span style="color: var(--danger); font-weight: bold;">${fmtNum(itData.ton)} sp</span>
  `;

  // Sắp xếp size theo quy chuẩn
  const sizeKeys = Object.keys(itData.sizes);
  const sizeRank = { 'XS': 1, 'S': 2, 'M': 3, 'L': 4, 'XL': 5, '2XL': 6, 'XXL': 6, '3XL': 7, 'XXXL': 7, '4XL': 8, 'F': 9 };
  sizeKeys.sort((a, b) => {
    const numA = parseFloat(a);
    const numB = parseFloat(b);
    if (!isNaN(numA) && !isNaN(numB)) return numA - numB;
    const rankA = sizeRank[a.toUpperCase()] || 99;
    const rankB = sizeRank[b.toUpperCase()] || 99;
    if (rankA !== rankB) return rankA - rankB;
    return a.localeCompare(b);
  });

  // Thead
  const thead = document.getElementById('size-modal-thead');
  thead.innerHTML = `
    <tr>
      <th style="min-width: 140px;">Chỉ số đối soát</th>
      ${sizeKeys.map(sz => `<th style="text-align: center; min-width: 50px; background: #e2e8f0; color: #1e293b;">${sz}</th>`).join('')}
      <th style="text-align: center; background: #cbd5e1;">Tổng</th>
    </tr>
  `;

  // Tbody
  const tbody = document.getElementById('size-modal-tbody');
  tbody.innerHTML = '';

  let rowBanHtml = `<td><strong>🛒 Số lượng ĐÃ BÁN</strong></td>`;
  let rowTonHtml = `<td><strong>📦 Số lượng CÒN TỒN</strong></td>`;
  let rowStatusHtml = `<td><strong>⚠️ Đánh giá Gãy Size</strong></td>`;

  let totalBan = 0;
  let totalTon = 0;
  let brokenSizes = [];

  sizeKeys.forEach(sz => {
    const b = itData.sizes[sz].ban;
    const t = itData.sizes[sz].ton;
    totalBan += b;
    totalTon += t;

    rowBanHtml += `<td style="text-align: center; font-weight: bold; color: ${b > 0 ? 'var(--primary)' : '#94a3b8'};">${b}</td>`;
    rowTonHtml += `<td style="text-align: center; font-weight: bold; color: ${t === 0 ? 'var(--danger)' : '#1e293b'};">${t}</td>`;

    if (b > 0 && t === 0) {
      brokenSizes.push(sz);
      rowStatusHtml += `<td style="text-align: center;"><span class="tag-badge tag-down">ĐỨT SIZE</span></td>`;
    } else if (b === 0 && t > 5) {
      rowStatusHtml += `<td style="text-align: center;"><span class="tag-badge tag-gold">ỒN TỒN</span></td>`;
    } else {
      rowStatusHtml += `<td style="text-align: center; color: #16a34a;">✓ OK</td>`;
    }
  });

  rowBanHtml += `<td style="text-align: center; font-weight: bold; background: #f1f5f9;">${fmtNum(totalBan)}</td>`;
  rowTonHtml += `<td style="text-align: center; font-weight: bold; background: #f1f5f9;">${fmtNum(totalTon)}</td>`;
  rowStatusHtml += `<td style="text-align: center; background: #f1f5f9;">—</td>`;

  const tr1 = document.createElement('tr'); tr1.innerHTML = rowBanHtml;
  const tr2 = document.createElement('tr'); tr2.innerHTML = rowTonHtml;
  const tr3 = document.createElement('tr'); tr3.innerHTML = rowStatusHtml;

  tbody.appendChild(tr1);
  tbody.appendChild(tr2);
  tbody.appendChild(tr3);

  // Alerts & Gợi ý điều chuyển
  const alertsEl = document.getElementById('size-modal-alerts');
  if (brokenSizes.length > 0) {
    alertsEl.innerHTML = `
      <div style="background: #fef2f2; border-left: 4px solid #ef4444; padding: 12px 16px; border-radius: 6px; font-size: 13px; color: #991b1b; line-height: 1.6;">
        🚨 <strong>CẢNH BÁO GÃY SIZE / ĐỨT SIZE:</strong> Cửa hàng đã bán rất chạy các kích cỡ <strong>[ ${brokenSizes.join(', ')} ]</strong> nhưng hiện tại tồn kho đã về 0!<br>
        💡 <strong>Kiến nghị điều phối:</strong> Cần ưu tiên luân chuyển gấp các size <strong>[ ${brokenSizes.join(', ')} ]</strong> từ Kho Tổng hoặc từ các cửa hàng đang có dư thừa size này về điểm bán <strong>${st}</strong> để tránh mất doanh thu khách hàng có nhu cầu.
      </div>
    `;
  } else {
    alertsEl.innerHTML = `
      <div style="background: #f0fdf4; border-left: 4px solid #22c55e; padding: 12px 16px; border-radius: 6px; font-size: 13px; color: #166534;">
        ✅ <strong>CƠ CẤU SIZE CÂN ĐỐI:</strong> Không phát hiện tình trạng gãy size / đứt size nghiêm trọng đối với sản phẩm này tại cửa hàng.
      </div>
    `;
  }

  document.getElementById('size-modal').style.display = 'flex';
}

function closeSizeModal() {
  document.getElementById('size-modal').style.display = 'none';
}


// =============================================================================
// TỒN SHEET 5 & 6: THEO DÕI MÃ HÀNG · TUỔI TỒN · SỐ THÁNG ĐÁP ỨNG
// Nguồn: APP_DATA.ton.sku_track (Aggregate_Stock_Tracking.py) — 1 dòng / SKU
// =============================================================================
const AGE_BUCKETS = [
  { k: 'a0', label: '0–6 th', min: 0, max: 6 },
  { k: 'a1', label: '7–12 th', min: 7, max: 12 },
  { k: 'a2', label: '13–24 th', min: 13, max: 24 },
  { k: 'a3', label: '25–36 th', min: 25, max: 36 },
  { k: 'a4', label: '> 36 th', min: 37, max: Infinity },
  { k: 'na', label: 'Chưa rõ', min: -1, max: -1 }
];
const HEALTH_LIST = ['Thiếu hàng', 'Khỏe', 'Dư', 'Ứ đọng', 'Không bán 3T'];
const HEALTH_CLASS = { 'Thiếu hàng': 'tag-info', 'Khỏe': 'tag-up', 'Dư': 'tag-gold', 'Ứ đọng': 'tag-down', 'Không bán 3T': 'tag-down', 'Hết hàng': 'tag-neutral' };
const CAT_GROUP_ORDER = ['Nhóm chủ đạo', 'Nhóm Golf', 'Nhóm Đồ da', 'Nhóm Phụ kiện khác', 'Nhóm Quần áo khác', 'Nhóm Anamai / Bonjour'];

let SKU_TRACK = null;
let TON5_SORT = { col: 'ton', dir: -1 };
let TON6_EXPANDED = {};

function ageBucketOf(age) {
  if (age < 0) return 'na';
  for (const b of AGE_BUCKETS) if (b.k !== 'na' && age >= b.min && age <= b.max) return b.k;
  return 'na';
}

function healthOf(ton, avg3) {
  if (ton <= 0) return 'Hết hàng';
  if (avg3 <= 0) return 'Không bán 3T';
  const mos = ton / avg3;
  if (mos < 1) return 'Thiếu hàng';
  if (mos <= 6) return 'Khỏe';
  if (mos <= 12) return 'Dư';
  return 'Ứ đọng';
}

function getSkuTrack() {
  if (SKU_TRACK) return SKU_TRACK;
  SKU_TRACK = [];
  const p = APP_DATA.ton.sku_track;
  if (!p) return SKU_TRACK;
  const c = {};
  p.cols.forEach((name, i) => { c[name] = p.data[i]; });
  const n = c.key.length;
  for (let i = 0; i < n; i++) {
    const [mh, op] = splitSku(DICT[c.key[i]]);
    const tonCh = c.ton_ch[i], tonKho = c.ton_kho[i];
    const ton = tonCh + tonKho;
    const avg3 = c.b3[i] / 3;
    const prod = c.prod[i];
    const b6 = c.b6[i];
    SKU_TRACK.push({
      mh, op, br: DICT[c.br[i]], catg: DICT[c.catg[i]], gr: DICT[c.gr[i]], item: DICT[c.item[i]],
      status: DICT[c.status[i]], price: c.price[i], prod,
      prodLabel: prod ? `${String(prod % 100).padStart(2, '0')}/${Math.floor(prod / 100)}` : '—',
      age: c.age[i], ageB: ageBucketOf(c.age[i]),
      tonCh, tonKho, ton, b1: c.b1[i], b3: c.b3[i], b6, bytd: c.bytd[i], ball: c.ball[i],
      nosale: c.nosale[i], avg3,
      mos: ton > 0 ? (avg3 > 0 ? ton / avg3 : Infinity) : 0,
      st6: (Math.max(b6, 0) + ton) > 0 ? Math.max(b6, 0) / (Math.max(b6, 0) + ton) * 100 : NaN,
      health: healthOf(ton, avg3)
    });
  }
  return SKU_TRACK;
}

function fmtMos(m) {
  if (m === Infinity) return '∞';
  if (m === null || m === undefined || isNaN(m)) return '—';
  return m.toFixed(1);
}

function mosBadge(m, ton) {
  if (ton <= 0) return '<span class="tag-badge tag-neutral">Hết</span>';
  const h = m === Infinity ? 'Không bán 3T' : (m < 1 ? 'Thiếu hàng' : m <= 6 ? 'Khỏe' : m <= 12 ? 'Dư' : 'Ứ đọng');
  return `<span class="tag-badge ${HEALTH_CLASS[h]}" title="${h}">${fmtMos(m)}</span>`;
}

function fillSelect(id, values, allLabel, keep) {
  const el = document.getElementById(id);
  if (!el) return;
  const prev = keep ? el.value : 'all';
  el.innerHTML = `<option value="all">${allLabel}</option>` + values.map(v => `<option value="${v}">${v}</option>`).join('');
  el.value = values.includes(prev) ? prev : 'all';
}

function uniqSorted(rows, f, order) {
  const s = [...new Set(rows.map(r => r[f]).filter(v => v !== ''))];
  if (order) return order.filter(v => s.includes(v)).concat(s.filter(v => !order.includes(v)).sort((a, b) => a.localeCompare(b, 'vi')));
  return s.sort((a, b) => a.localeCompare(b, 'vi'));
}

// Tổng hợp chỉ số cho 1 tập SKU. scope: 'all' | 'ch' | 'kho'
function aggSku(rows, scope = 'all') {
  const a = { n: 0, nStock: 0, ton: 0, tonCh: 0, tonKho: 0, b1: 0, b3: 0, b6: 0, bytd: 0, ball: 0, val: 0, ageQ: 0, ageKnownTon: 0, old12: 0, dead: 0, buckets: {}, health: {} };
  AGE_BUCKETS.forEach(b => { a.buckets[b.k] = 0; });
  HEALTH_LIST.forEach(h => { a.health[h] = 0; });
  for (const r of rows) {
    const ton = scope === 'ch' ? r.tonCh : scope === 'kho' ? r.tonKho : r.ton;
    a.n++;
    if (ton > 0) a.nStock++;
    a.ton += ton; a.tonCh += r.tonCh; a.tonKho += r.tonKho;
    a.b1 += r.b1; a.b3 += r.b3; a.b6 += r.b6; a.bytd += r.bytd; a.ball += r.ball;
    a.val += ton * r.price;
    a.buckets[r.ageB] += ton;
    if (r.age >= 0) { a.ageQ += r.age * ton; a.ageKnownTon += ton; }
    if (r.age > 12) a.old12 += ton;
    if (ton > 0 && r.b3 <= 0) a.dead += ton;
    const h = healthOf(ton, r.avg3);
    if (h !== 'Hết hàng') a.health[h] += ton;
  }
  const refM = APP_DATA.ref.month;
  a.avg3 = a.b3 / 3;
  a.mos = a.ton > 0 ? (a.avg3 > 0 ? a.ton / a.avg3 : Infinity) : 0;
  a.ageAvg = a.ageKnownTon > 0 ? a.ageQ / a.ageKnownTon : NaN;
  a.st6 = (a.b6 + a.ton) > 0 ? a.b6 / (a.b6 + a.ton) * 100 : NaN;
  a.turn = a.ton > 0 ? (a.bytd / refM * 12) / a.ton : NaN;
  return a;
}

function setText(id, v) { const el = document.getElementById(id); if (el) el.textContent = v; }
function pctOf(x, t) { return t > 0 ? x / t * 100 : NaN; }
function jsq(s) { return String(s).replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/"/g, '&quot;'); }

// -----------------------------------------------------------------------------
// SHEET 5 — THEO DÕI MÃ HÀNG
// -----------------------------------------------------------------------------
const TON5_COLS = [
  { k: 'mh', label: 'Mã hàng', left: true },
  { k: 'op', label: 'Lô', left: true },
  { k: 'item', label: 'Tên hàng', left: true },
  { k: 'br', label: 'Thương hiệu', left: true },
  { k: 'status', label: 'Trạng thái', left: true },
  { k: 'price', label: 'Đơn giá' },
  { k: 'prod', label: 'Tháng SX' },
  { k: 'age', label: 'Tuổi tồn (th)' },
  { k: 'tonCh', label: 'Tồn CH' },
  { k: 'tonKho', label: 'Tồn Kho' },
  { k: 'ton', label: 'Tồn hiện tại' },
  { k: 'b1', label: 'Bán tháng' },
  { k: 'b3', label: 'Bán 3T' },
  { k: 'b6', label: 'Bán 6T' },
  { k: 'bytd', label: 'Lũy kế năm' },
  { k: 'ball', label: 'Lũy kế từ 2024' },
  { k: 'st6', label: 'Bán hết 6T' },
  { k: 'mos', label: 'Đáp ứng (th)' },
  { k: 'nosale', label: 'Tháng chưa bán' }
];

function ensureTon5Init() {
  if (document.getElementById('ton5-f-br').options.length) return;
  const rows = getSkuTrack();
  fillSelect('ton5-f-br', uniqSorted(rows, 'br', BRAND_MAIN_5.concat(['Khác'])), 'Tất cả Thương hiệu');
  const ageEl = document.getElementById('ton5-f-age');
  ageEl.innerHTML = '<option value="all">Tất cả tuổi tồn</option>' + AGE_BUCKETS.map(b => `<option value="${b.k}">${b.label}</option>`).join('');
  fillSelect('ton5-f-health', HEALTH_LIST.concat(['Hết hàng']), 'Tất cả');
  onTon5Cascade('br', true);
  const m = APP_DATA.ref.month, y = APP_DATA.ref.year;
  setText('ton5-kpi-b1-label', `Bán trong tháng T${m}/${y}`);
  TON5_COLS.find(c => c.k === 'b1').label = `Bán T${m}`;
  TON5_COLS.find(c => c.k === 'bytd').label = `Lũy kế ${y}`;
}

function onTon5Cascade(level, silent) {
  const rows = getSkuTrack();
  const br = document.getElementById('ton5-f-br').value;
  const r1 = br === 'all' ? rows : rows.filter(r => r.br === br);
  if (level === 'br') fillSelect('ton5-f-catg', uniqSorted(r1, 'catg', CAT_GROUP_ORDER), 'Tất cả Nhóm hàng', true);
  const catg = document.getElementById('ton5-f-catg').value;
  const r2 = catg === 'all' ? r1 : r1.filter(r => r.catg === catg);
  if (level === 'br' || level === 'catg') fillSelect('ton5-f-gr', uniqSorted(r2, 'gr'), 'Tất cả Nhóm BC', true);
  const gr = document.getElementById('ton5-f-gr').value;
  const r3 = gr === 'all' ? r2 : r2.filter(r => r.gr === gr);
  fillSelect('ton5-f-item', uniqSorted(r3, 'item'), 'Tất cả Tên hàng', true);
  if (!silent) renderTonSheet5();
}

function resetTonSheet5() {
  ['ton5-f-br', 'ton5-f-catg', 'ton5-f-gr', 'ton5-f-item', 'ton5-f-status', 'ton5-f-age', 'ton5-f-health'].forEach(id => { document.getElementById(id).value = 'all'; });
  document.getElementById('ton5-search').value = '';
  onTon5Cascade('br');
}

function sortTon5(k) {
  TON5_SORT = TON5_SORT.col === k ? { col: k, dir: -TON5_SORT.dir } : { col: k, dir: TON5_COLS.find(c => c.k === k).left ? 1 : -1 };
  renderTonSheet5();
}

function ton5Filtered() {
  const rows = getSkuTrack();
  const q = document.getElementById('ton5-search').value.trim().toLowerCase();
  if (q) return rows.filter(r => (r.mh + ' ' + r.op).toLowerCase().includes(q));
  const v = id => document.getElementById(id).value;
  const br = v('ton5-f-br'), catg = v('ton5-f-catg'), gr = v('ton5-f-gr'), item = v('ton5-f-item');
  const st = v('ton5-f-status'), age = v('ton5-f-age'), hl = v('ton5-f-health');
  return rows.filter(r =>
    (br === 'all' || r.br === br) && (catg === 'all' || r.catg === catg) &&
    (gr === 'all' || r.gr === gr) && (item === 'all' || r.item === item) &&
    (st === 'all' || r.status === st) && (age === 'all' || r.ageB === age) &&
    (hl === 'all' || r.health === hl));
}

function renderTonSheet5() {
  if (!APP_DATA.ton.sku_track) return;
  ensureTon5Init();
  const rows = ton5Filtered();
  const a = aggSku(rows);
  const y = APP_DATA.ref.year;

  setText('ton5-count', `${fmtNum(rows.length)} mã hàng`);
  setText('ton5-kpi-ton', fmtNum(a.ton));
  setText('ton5-kpi-ton-sub', `CH ${fmtNum(a.tonCh)} · Kho ${fmtNum(a.tonKho)}`);
  setText('ton5-kpi-b1', fmtNum(a.b1));
  setText('ton5-kpi-b3', fmtNum(a.b3));
  setText('ton5-kpi-b3-sub', `BQ ${fmtNum(a.b3 / 3)} sp/tháng`);
  setText('ton5-kpi-b6', fmtNum(a.b6));
  setText('ton5-kpi-b6-sub', `BQ ${fmtNum(a.b6 / 6)} sp/tháng`);
  setText('ton5-kpi-ytd', fmtNum(a.bytd));
  setText('ton5-kpi-ytd-sub', `Năm ${y} · Lũy kế từ 2024: ${fmtNum(a.ball)}`);
  setText('ton5-kpi-mos', fmtMos(a.mos) + (a.mos === Infinity ? '' : ' th'));
  setText('ton5-kpi-age', isNaN(a.ageAvg) ? '—' : a.ageAvg.toFixed(1) + ' th');

  const { col, dir } = TON5_SORT;
  const sorted = rows.slice().sort((p, q) => {
    let x = p[col], z = q[col];
    if (typeof x === 'string') return x.localeCompare(z, 'vi') * dir;
    if (isNaN(x)) x = -Infinity;
    if (isNaN(z)) z = -Infinity;
    return (x === z ? 0 : x > z ? 1 : -1) * dir;
  });

  document.getElementById('ton5-thead').innerHTML = TON5_COLS.map(c =>
    `<th onclick="sortTon5('${c.k}')" style="cursor: pointer;${c.left ? ' text-align: left;' : ''}">${c.label}${col === c.k ? (dir > 0 ? ' ▲' : ' ▼') : ''}</th>`).join('');

  const LIMIT = 1000;
  const body = sorted.slice(0, LIMIT).map(r => `<tr>
      <td style="font-weight: 700;">${r.mh}</td>
      <td style="text-align: left;">${r.op}</td>
      <td style="text-align: left; font-family: inherit;">${r.item}</td>
      <td style="text-align: left; font-family: inherit;">${r.br}</td>
      <td style="text-align: left; font-family: inherit;">${r.status}</td>
      <td>${r.price ? fmtNum(r.price) : '—'}</td>
      <td>${r.prodLabel}</td>
      <td>${r.age < 0 ? '—' : r.age}</td>
      <td>${fmtNum(r.tonCh)}</td>
      <td>${fmtNum(r.tonKho)}</td>
      <td style="font-weight: 700;">${fmtNum(r.ton)}</td>
      <td>${fmtNum(r.b1)}</td>
      <td>${fmtNum(r.b3)}</td>
      <td>${fmtNum(r.b6)}</td>
      <td>${fmtNum(r.bytd)}</td>
      <td>${fmtNum(r.ball)}</td>
      <td>${fmtPct(r.st6, false)}</td>
      <td>${mosBadge(r.mos, r.ton)}</td>
      <td>${r.nosale < 0 ? '<span class="tag-badge tag-down">Chưa bán</span>' : r.nosale}</td>
    </tr>`).join('');
  const total = `<tr class="row-total">
      <td>TỔNG (${fmtNum(rows.length)} mã)</td><td></td><td></td><td></td><td></td><td></td><td></td>
      <td>${isNaN(a.ageAvg) ? '—' : a.ageAvg.toFixed(1)}</td>
      <td>${fmtNum(a.tonCh)}</td><td>${fmtNum(a.tonKho)}</td><td>${fmtNum(a.ton)}</td>
      <td>${fmtNum(a.b1)}</td><td>${fmtNum(a.b3)}</td><td>${fmtNum(a.b6)}</td>
      <td>${fmtNum(a.bytd)}</td><td>${fmtNum(a.ball)}</td>
      <td>${fmtPct(a.st6, false)}</td><td>${fmtMos(a.mos)}</td><td></td>
    </tr>`;
  document.getElementById('ton5-tbody').innerHTML = rows.length ? total + body : emptyRow(TON5_COLS.length);
  setText('ton5-note', rows.length > LIMIT
    ? `Đang hiển thị ${fmtNum(LIMIT)}/${fmtNum(rows.length)} mã theo thứ tự sắp xếp — chọn thêm bộ lọc hoặc tìm mã để thu hẹp. Dòng TỔNG tính trên toàn bộ ${fmtNum(rows.length)} mã.`
    : 'Tuổi tồn = số tháng từ tháng sản xuất đến kỳ báo cáo. "Tháng chưa bán" = số tháng kể từ lần bán lẻ gần nhất (0 = có bán trong tháng).');
}

function openTon5Sku(mh) {
  switchSheet('ton', 'sheet5');
  document.getElementById('ton5-search').value = mh;
  renderTonSheet5();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// -----------------------------------------------------------------------------
// SHEET 6 — TUỔI TỒN & SỐ THÁNG ĐÁP ỨNG THEO NHÓM HÀNG
// -----------------------------------------------------------------------------
function toggleTon6(catg) {
  TON6_EXPANDED[catg] = !TON6_EXPANDED[catg];
  renderTonSheet6();
}

function ton6Row(label, a, totalTon, opts = {}) {
  const bk = AGE_BUCKETS.map(b => {
    const q = a.buckets[b.k];
    const p = pctOf(q, a.ton);
    const hot = (b.k === 'a3' || b.k === 'a4') && p >= 20 ? ' style="color: var(--danger); font-weight: 700;"' : '';
    return `<td title="${fmtNum(q)} sp"${hot}>${q ? fmtPct(p, false) : '—'}</td>`;
  }).join('');
  const pad = opts.child ? 'padding-left: 30px; font-weight: 400;' : 'font-weight: 700;';
  return `<tr class="${opts.cls || ''}"${opts.onclick ? ` onclick="${opts.onclick}" style="cursor: pointer;"` : ''}>
    <td style="${pad} font-family: inherit;">${label}</td>
    <td>${fmtNum(a.nStock)}</td>
    <td style="font-weight: 700;">${fmtNum(a.ton)}</td>
    <td>${fmtPct(pctOf(a.ton, totalTon), false)}</td>
    <td>${fmtNum(a.val / 1e6)}</td>
    <td>${isNaN(a.ageAvg) ? '—' : a.ageAvg.toFixed(1)}</td>
    ${bk}
    <td>${fmtNum(a.avg3)}</td>
    <td>${mosBadge(a.mos, a.ton)}</td>
    <td>${fmtPct(a.st6, false)}</td>
    <td>${isNaN(a.turn) ? '—' : a.turn.toFixed(2)}</td>
    <td>${fmtPct(pctOf(a.dead, a.ton), false)}</td>
  </tr>`;
}

function renderTonSheet6() {
  if (!APP_DATA.ton.sku_track) return;
  const all = getSkuTrack();
  const brEl = document.getElementById('ton6-f-br');
  if (!brEl.options.length) fillSelect('ton6-f-br', uniqSorted(all, 'br', BRAND_MAIN_5.concat(['Khác'])), 'Tất cả Thương hiệu');
  document.querySelectorAll('.ton6-ref').forEach(el => { el.textContent = APP_DATA.ref.label; });

  const br = brEl.value;
  const st = document.getElementById('ton6-f-status').value;
  const scope = document.getElementById('ton6-f-scope').value;
  const rows = all.filter(r => (br === 'all' || r.br === br) && (st === 'all' || r.status === st));
  const tonOf = r => scope === 'ch' ? r.tonCh : scope === 'kho' ? r.tonKho : r.ton;
  const a = aggSku(rows, scope);

  setText('ton6-kpi-ton', fmtNum(a.ton));
  setText('ton6-kpi-ton-sub', `${fmtNum(a.nStock)} mã có tồn`);
  setText('ton6-kpi-val', (a.val / 1e9).toLocaleString('vi-VN', { maximumFractionDigits: 1 }));
  setText('ton6-kpi-age', isNaN(a.ageAvg) ? '—' : a.ageAvg.toFixed(1));
  setText('ton6-kpi-age-sub', `tháng · ${fmtPct(pctOf(a.buckets.na, a.ton), false)} tồn chưa rõ tháng SX`);
  setText('ton6-kpi-mos', fmtMos(a.mos));
  setText('ton6-kpi-mos-sub', `tháng · BQ bán ${fmtNum(a.avg3)} sp/tháng (3T)`);
  setText('ton6-kpi-st', fmtPct(a.st6, false));
  setText('ton6-kpi-turn', isNaN(a.turn) ? '—' : a.turn.toFixed(2) + ' lần');
  setText('ton6-kpi-old', fmtNum(a.old12));
  setText('ton6-kpi-old-sub', `${fmtPct(pctOf(a.old12, a.ton), false)} tổng tồn`);
  setText('ton6-kpi-dead', fmtNum(a.dead));
  setText('ton6-kpi-dead-sub', `${fmtPct(pctOf(a.dead, a.ton), false)} tổng tồn`);

  // Bảng 1: Nhóm hàng -> Nhóm BC
  const groups = uniqSorted(rows, 'catg', CAT_GROUP_ORDER);
  let html = '';
  for (const g of groups) {
    const gRows = rows.filter(r => r.catg === g);
    const ga = aggSku(gRows, scope);
    if (ga.ton <= 0 && ga.b3 <= 0) continue;
    const open = !!TON6_EXPANDED[g];
    html += ton6Row(`${open ? '▾' : '▸'} ${g}`, ga, a.ton, { onclick: `toggleTon6('${jsq(g)}')` });
    if (open) {
      uniqSorted(gRows, 'gr')
        .map(gr => ({ gr, agg: aggSku(gRows.filter(r => r.gr === gr), scope) }))
        .filter(x => x.agg.ton > 0 || x.agg.b3 > 0)
        .sort((p, q) => q.agg.ton - p.agg.ton)
        .forEach(x => { html += ton6Row(x.gr || '(Không có Nhóm BC)', x.agg, a.ton, { child: true }); });
    }
  }
  html += ton6Row('TỔNG', a, a.ton, { cls: 'row-total' });
  document.getElementById('ton6-groups-tbody').innerHTML = html;

  // Bảng 2: Sức khỏe tồn theo Nhóm hàng
  document.getElementById('ton6-health-thead').innerHTML = '<th>Nhóm hàng</th>' + HEALTH_LIST.map(h => `<th>${h}</th>`).join('');
  const hRow = (label, ag, cls) => `<tr class="${cls || ''}"><td style="font-family: inherit; font-weight: 700;">${label}</td>` +
    HEALTH_LIST.map(h => `<td>${ag.health[h] ? fmtNum(ag.health[h]) + ` <span style="color: var(--text-muted); font-size: 11px;">(${fmtPct(pctOf(ag.health[h], ag.ton), false)})</span>` : '—'}</td>`).join('') + '</tr>';
  document.getElementById('ton6-health-tbody').innerHTML =
    groups.map(g => ({ g, ag: aggSku(rows.filter(r => r.catg === g), scope) })).filter(x => x.ag.ton > 0)
      .map(x => hRow(x.g, x.ag)).join('') + hRow('TỔNG', a, 'row-total');

  // Bảng 3: Tuổi tồn × Thương hiệu
  document.getElementById('ton6-agebr-thead').innerHTML = '<th>Thương hiệu</th>' + AGE_BUCKETS.map(b => `<th>${b.label}</th>`).join('') + '<th>Tổng</th><th>Tuổi BQ</th>';
  const brands = uniqSorted(rows, 'br', BRAND_MAIN_5.concat(['Khác']));
  const abRow = (label, ag, cls) => `<tr class="${cls || ''}"><td style="font-family: inherit; font-weight: 700;">${label}</td>` +
    AGE_BUCKETS.map(b => `<td title="${fmtPct(pctOf(ag.buckets[b.k], ag.ton), false)}">${ag.buckets[b.k] ? fmtNum(ag.buckets[b.k]) : '—'}</td>`).join('') +
    `<td style="font-weight: 700;">${fmtNum(ag.ton)}</td><td>${isNaN(ag.ageAvg) ? '—' : ag.ageAvg.toFixed(1)}</td></tr>`;
  document.getElementById('ton6-agebr-tbody').innerHTML =
    brands.map(b => ({ b, ag: aggSku(rows.filter(r => r.br === b), scope) })).filter(x => x.ag.ton > 0)
      .map(x => abRow(x.b, x.ag)).join('') + abRow('TỔNG', a, 'row-total');

  // Bảng 4: Top 30 mã cần xử lý (Ứ đọng / Không bán 3T), theo giá trị tồn
  const risk = rows.map(r => ({ r, ton: tonOf(r) }))
    .filter(x => x.ton > 0 && ['Ứ đọng', 'Không bán 3T'].includes(healthOf(x.ton, x.r.avg3)))
    .sort((p, q) => q.ton * q.r.price - p.ton * p.r.price || q.ton - p.ton)
    .slice(0, 30);
  document.getElementById('ton6-risk-tbody').innerHTML = risk.length ? risk.map(({ r, ton }) => {
    const mos = r.avg3 > 0 ? ton / r.avg3 : Infinity;
    return `<tr onclick="openTon5Sku('${jsq(r.mh)}')" style="cursor: pointer;" title="Mở ở Sheet 5">
      <td style="font-weight: 700;">${r.mh}</td>
      <td style="text-align: left;">${r.op}</td>
      <td style="text-align: left; font-family: inherit;">${r.item}</td>
      <td style="text-align: left; font-family: inherit;">${r.br}</td>
      <td>${r.prodLabel}</td>
      <td>${r.age < 0 ? '—' : r.age}</td>
      <td style="font-weight: 700;">${fmtNum(ton)}</td>
      <td>${fmtNum(ton * r.price / 1e6)}</td>
      <td>${fmtNum(r.b3)}</td>
      <td>${mosBadge(mos, ton)}</td>
      <td>${r.nosale < 0 ? '<span class="tag-badge tag-down">Chưa bán</span>' : r.nosale}</td>
    </tr>`;
  }).join('') : emptyRow(11, 'Không có mã ứ đọng trong phạm vi đang chọn.');
}

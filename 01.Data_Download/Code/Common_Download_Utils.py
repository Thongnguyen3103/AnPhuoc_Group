"""
Phần dùng chung cho mọi báo cáo: đường dẫn, đọc/ghi cấu hình, log, mở Firefox,
chọn ô trên trang, điền ngày, bấm xuất và chờ file tải về.
"""
import datetime as dt
import difflib
import json
import logging
import re
import shutil
import sys
import threading
import time
import unicodedata
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import (
    NoAlertPresentException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait

# ----------------------------------------------------------------------------- đường dẫn
ROOT = Path(__file__).resolve().parent.parent   # 01.Data_Download (Code/ nam ben trong; Config/, Data/ o ngoai)
CONFIG_DIR = ROOT / "Config"
DATA_DIR = ROOT / "Data"
LOG_DIR = DATA_DIR / "logs"
DEBUG_DIR = DATA_DIR / "debug"
TMP_DOWNLOAD_DIR = DATA_DIR / "_tmp_download"
SETTINGS_FILE = CONFIG_DIR / "Settings.json"
ACCOUNTS_FILE = CONFIG_DIR / "Accounts.json"
EMPTY_CACHE_FILE = DATA_DIR / "empty_cache.json"


def load_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        if default is not None:
            return default
        raise


def save_json(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


SETTINGS = load_json(SETTINGS_FILE)
ACCOUNTS = load_json(ACCOUNTS_FILE)


def output_dir():
    return Path(SETTINGS.get("output_dir") or (Path.home() / "Downloads"))


log = logging.getLogger("tool")


def setup_logging():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(threadName)-6s | %(levelname)-7s | %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(LOG_DIR / f"{dt.date.today():%Y-%m-%d}.log", encoding="utf-8"),
        ],
    )


class NoDataError(Exception):
    """Báo cáo không có dữ liệu -> bỏ qua, không phải lỗi."""


class Job:
    """Một lượt tải: `run(driver)` điền form + xuất file, trả về đường dẫn file."""

    def __init__(self, group, stem, run, cacheable=False):
        self.group, self.stem, self.run, self.cacheable = group, stem, run, cacheable


def months_back_range(months, today=None):
    """Từ ngày 1 của tháng cách đây `months` tháng đến hôm nay."""
    today = today or dt.date.today()
    y, m = today.year, today.month - int(months)
    while m <= 0:
        m += 12
        y -= 1
    return dt.date(y, m, 1), today


# ----------------------------------------------------------------------------- helpers
def norm(text):
    return " ".join(unicodedata.normalize("NFC", text or "").lower().split())


def safe_filename(name):
    return re.sub(r'[<>:"/\\|?*]+', "-", name).strip(" .")


def month_range(today=None):
    """Từ ngày 1 của tháng đến hôm qua (nếu hôm nay là ngày 1 -> lấy trọn tháng trước)."""
    to = (today or dt.date.today()) - dt.timedelta(days=1)
    return to.replace(day=1), to


def prev_month_range(today=None):
    """Trọn tháng trước: ngày 1 -> ngày cuối tháng."""
    to = (today or dt.date.today()).replace(day=1) - dt.timedelta(days=1)
    return to.replace(day=1), to


def yesterday(today=None):
    return (today or dt.date.today()) - dt.timedelta(days=1)


JS_IDLE = """
    if (document.readyState !== 'complete') return false;
    try {
        if (window.Sys && Sys.WebForms && Sys.WebForms.PageRequestManager) {
            var p = Sys.WebForms.PageRequestManager.getInstance();
            if (p && p.get_isInAsyncPostBack()) return false;
        }
    } catch (e) {}
    try { if (window.jQuery && jQuery.active > 0) return false; } catch (e) {}
    return true;
"""


def wait_idle(driver, timeout=180):
    time.sleep(0.3)
    WebDriverWait(driver, timeout).until(lambda d: d.execute_script(JS_IDLE))
    time.sleep(0.3)


def mark_page(driver):
    driver.execute_script("window.__apMarker = true;")


def wait_after_action(driver, reload_wait=3):
    """Sau khi chọn/bấm: nếu trang postback (tải lại) thì chờ tải xong."""
    end = time.time() + reload_wait
    while time.time() < end:
        try:
            if not driver.execute_script("return window.__apMarker === true;"):
                break
        except WebDriverException:
            pass
        time.sleep(0.3)
    wait_idle(driver)


def dump_debug(driver, tag):
    DEBUG_DIR.mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    base = DEBUG_DIR / f"{stamp}_{threading.current_thread().name}_{safe_filename(tag)[:60]}"
    try:
        base.with_suffix(".html").write_text(driver.page_source, encoding="utf-8")
        driver.save_screenshot(str(base.with_suffix(".png")))
        log.info("    Đã lưu debug: %s.html / .png", base)
    except WebDriverException as e:
        log.warning("    Không lưu được debug: %s", e)


def dismiss_alert(driver):
    try:
        alert = driver.switch_to.alert
        text = alert.text
        alert.accept()
        return text
    except NoAlertPresentException:
        return None


# ----------------------------------------------------------------------------- browser
def create_driver(dl_dir):
    dl_dir.mkdir(parents=True, exist_ok=True)
    opts = Options()
    if SETTINGS.get("headless"):
        opts.add_argument("-headless")
    mime = ",".join([
        "text/csv", "text/comma-separated-values", "application/csv", "text/plain",
        "application/octet-stream", "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/download", "application/force-download", "application/zip",
    ])
    prefs = {
        "browser.download.folderList": 2,
        "browser.download.dir": str(dl_dir),
        "browser.download.useDownloadDir": True,
        "browser.download.manager.showWhenStarting": False,
        "browser.download.alwaysOpenPanel": False,
        "browser.download.always_ask_before_handling_new_types": False,
        "browser.helperApps.neverAsk.saveToDisk": mime,
        "browser.helperApps.alwaysAsk.force": False,
        "pdfjs.disabled": True,
        # Web định dạng số theo ngôn ngữ trình duyệt: Firefox tiếng Việt -> "9500,00".
        # Dùng giống Firefox người dùng tải tay (en-US ưu tiên) -> "9500.00", file giống hệt tải tay.
        "intl.accept_languages": SETTINGS.get("browser_language", "en-US, vi-VN, vi, en"),
    }
    for k, v in prefs.items():
        opts.set_preference(k, v)
    driver = webdriver.Firefox(options=opts)
    driver.set_page_load_timeout(300)
    driver.maximize_window()
    driver.dl_dir = dl_dir  # thư mục tải tạm riêng của trình duyệt này
    return driver


# ----------------------------------------------------------------------------- tìm control
JS_CONTROL_AFTER_LABEL = """
    var want = arguments[0], sel = arguments[1], skip = arguments[2] || 0;
    var norm = function (s) { return (s || '').normalize('NFC').toLowerCase().replace(/\\s+/g, ' ').trim(); };
    var vis = function (e) { return !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length); };
    var usable = function (c) {
        if (vis(c)) return true;
        if (c.tagName !== 'SELECT') return false;
        var n = c.nextElementSibling;   // select bị plugin (select2/chosen/multiselect) che
        return !!(n && vis(n));
    };
    var labels = [];
    document.querySelectorAll('label, span, td, th, div, b, strong, p, font, legend').forEach(function (e) {
        if (!vis(e)) return;
        var own = '';
        e.childNodes.forEach(function (n) { if (n.nodeType === 3) own += ' ' + n.textContent; });
        var t = norm(own).replace(/[:*]+$/, '').trim();
        if (t && t.indexOf(want) >= 0 && t.length <= want.length + 20) labels.push(e);
    });
    var ctrls = Array.prototype.slice.call(document.querySelectorAll(sel)).filter(usable);
    for (var i = 0; i < labels.length; i++) {
        var l = labels[i];
        if (l.tagName === 'LABEL' && l.htmlFor) {
            var f = document.getElementById(l.htmlFor);
            if (f && f.matches(sel) && usable(f) && skip === 0) return f;
        }
        var found = ctrls.filter(function (c) {
            return l.compareDocumentPosition(c) & Node.DOCUMENT_POSITION_FOLLOWING;
        });
        if (found.length > skip) return found[skip];
    }
    return null;
"""

JS_SET_SELECT = """
    var s = arguments[0], idx = arguments[1];
    if (s.multiple) for (var i = 0; i < s.options.length; i++) s.options[i].selected = false;
    s.options[idx].selected = true;
    if (!s.multiple) s.selectedIndex = idx;
    if (window.jQuery) {
        var $s = jQuery(s);
        try { if ($s.data('multiselect')) $s.multiselect('refresh'); } catch (e) {}
        try { if ($s.data('selectpicker')) $s.selectpicker('refresh'); } catch (e) {}
        $s.trigger('chosen:updated');
        $s.trigger('change');
    } else {
        s.dispatchEvent(new Event('change', {bubbles: true}));
    }
"""

JS_DATE_INPUTS = """
    var vis = function (e) { return !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length); };
    var after = arguments[0];
    var re = /^\\d{1,2}[\\/\\-.]\\d{1,2}[\\/\\-.]\\d{4}$|^\\d{4}-\\d{2}-\\d{2}$/;
    var res = [];
    document.querySelectorAll("input").forEach(function (e) {
        var type = (e.getAttribute('type') || 'text').toLowerCase();
        if (['text', 'date', 'search', 'tel'].indexOf(type) < 0 || !vis(e)) return;
        if (after && e !== after && !(after.compareDocumentPosition(e) & Node.DOCUMENT_POSITION_FOLLOWING)) return;
        var ident = (e.id + ' ' + e.name + ' ' + e.className + ' ' + (e.placeholder || '')).toLowerCase();
        if (type === 'date' || re.test(e.value.trim()) ||
            /ngay|date|picker|tungay|denngay|from|to_?date/.test(ident)) res.push(e);
    });
    return res;
"""

JS_FIND_BUTTON = """
    var want = arguments[0];
    var norm = function (s) { return (s || '').normalize('NFC').toLowerCase().replace(/\\s+/g, ' ').trim(); };
    var vis = function (e) { return !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length); };
    var els = document.querySelectorAll("input[type=submit], input[type=button], input[type=image], button, a");
    var loose = null;
    for (var i = 0; i < els.length; i++) {
        var e = els[i];
        if (!vis(e)) continue;
        var t = norm(e.value || e.innerText || e.title || e.alt);
        if (t === want) return e;
        if (!loose && t.indexOf(want) >= 0) loose = e;
    }
    return loose;
"""


def find_control(driver, label, css="select", skip=0):
    el = driver.execute_script(JS_CONTROL_AFTER_LABEL, norm(label), css, skip)
    if el is None:
        raise RuntimeError(f"Không tìm thấy ô '{label}' trên trang")
    return el


def pick_option(options, wanted):
    w = norm(wanted)
    texts = [norm(o) for o in options]
    for i, t in enumerate(texts):
        if t == w:
            return i
    for i, t in enumerate(texts):
        if t and w in t:
            return i
    for i, t in enumerate(texts):
        if t and t in w and len(t) >= 0.6 * len(w):
            return i
    ratios = [difflib.SequenceMatcher(None, w, t).ratio() for t in texts]
    best = max(range(len(texts)), key=lambda i: ratios[i], default=None)
    if best is not None and ratios[best] >= 0.8:
        return best
    return None


def pick_kho_option(options, wanted):
    """`wanted` dạng 'MÃ - Tên' (vd 'KHOTB - Kho PIE'): khớp theo value = mã trước, rồi theo tên."""
    code, name = (x.strip() for x in wanted.split(" - ", 1))
    for i, (text, value) in enumerate(options):
        if norm(value) == norm(code) or re.match(rf"^{re.escape(norm(code))}\s*[-–:]", norm(text)):
            return i
    return pick_option([t for t, _ in options], name)


def choose(driver, label, wanted):
    sel = find_control(driver, label, "select")
    opts = driver.execute_script("return Array.from(arguments[0].options).map(o => [o.text, o.value]);", sel)
    options = [t for t, _ in opts]
    idx = pick_kho_option(opts, wanted) if " - " in wanted else None
    if idx is None:
        idx = pick_option(options, wanted)
    if idx is None:
        raise RuntimeError(f"Ô '{label}' không có lựa chọn '{wanted}'. Các lựa chọn: {options}")
    mark_page(driver)
    driver.execute_script(JS_SET_SELECT, sel, idx)
    wait_after_action(driver)
    log.info("    %s: %s", label, options[idx].strip())
    return options[idx].strip()


def format_date_for(driver, inp, d):
    typ, value = driver.execute_script(
        "return [(arguments[0].getAttribute('type')||'text').toLowerCase(), arguments[0].value.trim()];", inp)
    if typ == "date" or re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        return d.isoformat()
    if re.match(r"^\d{1,2}-\d{1,2}-\d{4}$", value):
        return d.strftime(SETTINGS["date_format"]).replace("/", "-")
    return d.strftime(SETTINGS["date_format"])


def set_input(driver, inp, value):
    mark_page(driver)
    # Lỗi JS của trang (vd ValidateNgay('txtNgayNhap') trỏ tới ô không tồn tại) thì bỏ qua,
    # vì giá trị của ô vẫn được gửi lên server khi bấm nút.
    driver.execute_script("""
        var e = arguments[0];
        e.value = arguments[1];
        ['input', 'change', 'blur'].forEach(function (ev) {
            try { e.dispatchEvent(new Event(ev, {bubbles: true})); } catch (x) {}
        });
    """, inp, value)
    wait_after_action(driver)


def set_dates(driver, d_from, d_to, label=None):
    """Điền Từ ngày / Đến ngày (2 ô ngày đầu tiên, hoặc 2 ô ngay sau `label`)."""
    def date_inputs():  # tìm lại mỗi lần vì trang có thể postback sau khi điền
        after = None
        if label:
            try:
                after = find_control(driver, label, "input[type=text], input[type=date], input:not([type])")
            except RuntimeError:
                after = None
        return driver.execute_script(JS_DATE_INPUTS, after)

    inputs = date_inputs()
    if not inputs:
        raise RuntimeError("Không tìm thấy ô ngày trên trang")
    if len(inputs) == 1:
        value = format_date_for(driver, inputs[0], d_to)
        set_input(driver, inputs[0], value)
        log.info("    Ngày: %s", value)
        return
    v_from = format_date_for(driver, inputs[0], d_from)
    v_to = format_date_for(driver, inputs[1], d_to)
    set_input(driver, inputs[0], v_from)
    set_input(driver, date_inputs()[1], v_to)
    log.info("    Ngày: %s -> %s", v_from, v_to)


# ----------------------------------------------------------------------------- tải file
def list_downloads(driver):
    return {p for p in driver.dl_dir.iterdir() if p.is_file()}


def page_says_no_data(driver):
    try:
        text = norm(driver.execute_script("return document.body ? document.body.innerText : '';"))
    except WebDriverException:
        return False
    return any(k in text for k in ("không có dữ liệu", "khong co du lieu", "không tìm thấy dữ liệu", "no data"))


def inline_csv(driver):
    """Nếu server trả CSV hiển thị thẳng trong tab (không tải xuống) thì lấy nội dung đó."""
    try:
        ctype = driver.execute_script("return document.contentType || '';")
        if ctype in ("text/csv", "text/plain", "application/csv"):
            return driver.execute_script("return document.body ? document.body.innerText : '';")
    except WebDriverException:
        pass
    return None


JS_BUSY = """
    var vis = function (e) { return e && getComputedStyle(e).display !== 'none' && !!(e.offsetWidth || e.offsetHeight); };
    return vis(document.getElementById('imgloadinggif')) || vis(document.getElementById('hidiv'))
        || vis(document.querySelector('.spinner-container'));
"""

SPINNER_GONE_GRACE_SEC = 15


def page_busy(driver):
    """Ảnh loading của trang còn hiện = server vẫn đang xử lý file."""
    try:
        return bool(driver.execute_script(JS_BUSY))
    except WebDriverException:
        return False


def page_reloaded(driver):
    """Marker đặt trước khi bấm nút đã mất = server trả lại trang HTML (không phải file)."""
    try:
        return not driver.execute_script("return window.__apMarker === true;")
    except WebDriverException:
        return False


def wait_for_download(driver, before, had_no_data_text):
    """
    Chờ file về. Server xử lý có thể rất lâu nên KHÔNG giới hạn thời gian bắt đầu, chỉ dừng khi:
      - có file tải về xong                                   -> trả về file
      - ảnh loading đã tắt / trang tải lại mà không có file   -> không có dữ liệu
      - quá download_timeout_sec                              -> lỗi
    """
    t0 = time.time()
    end = t0 + int(SETTINGS["download_timeout_sec"])
    last_size, stable, started = -1, 0, False
    seen_busy, last_busy, last_report, reloaded_at = False, t0, t0, None
    while time.time() < end:
        msg = dismiss_alert(driver)
        if msg:
            raise NoDataError(f"Trang báo: {msg.strip()}")
        files = list_downloads(driver) - before
        partial = [p for p in files if p.suffix == ".part"]
        done = [p for p in files if p.suffix != ".part"]
        started = started or bool(files)
        if done and not partial:
            f = max(done, key=lambda p: p.stat().st_mtime)
            size = f.stat().st_size
            if size == last_size:
                stable += 1
                if stable >= 2:
                    return f
            else:
                stable = 0
            last_size = size
        elif not started:
            for h in driver.window_handles:
                driver.switch_to.window(h)
                text = inline_csv(driver)
                if text is not None:
                    f = driver.dl_dir / "inline.csv"
                    f.write_text(text, encoding="utf-8-sig")
                    log.info("    (CSV hiển thị trong trình duyệt -> đã lưu lại nội dung)")
                    return f
            driver.switch_to.window(driver.window_handles[0])
            now = time.time()
            busy = page_busy(driver)
            if busy:
                seen_busy, last_busy = True, now
            elif seen_busy and now - last_busy > SPINNER_GONE_GRACE_SEC:
                raise NoDataError("Server xử lý xong nhưng không trả file (không có dữ liệu)")
            if not busy and page_reloaded(driver):
                reloaded_at = reloaded_at or now
                try:
                    idle = driver.execute_script(JS_IDLE)
                except WebDriverException:
                    idle = False
                if idle and not had_no_data_text and page_says_no_data(driver):
                    raise NoDataError("Trang báo không có dữ liệu")
                if now - reloaded_at > SPINNER_GONE_GRACE_SEC:
                    raise NoDataError("Server trả lại trang, không có file (không có dữ liệu)")
            if now - last_report >= 60:
                log.info("    ... server vẫn đang xử lý (%d giây)", now - t0)
                last_report = now
        time.sleep(2)
    dump_debug(driver, "download_timeout")
    raise TimeoutException(f"Hết {SETTINGS['download_timeout_sec']}s mà chưa tải xong file")


def csv_is_empty(path):
    """Rỗng = 0 byte hoặc chỉ có dòng tiêu đề (các dòng còn lại toàn dấu phân cách/khoảng trắng)."""
    raw = path.read_bytes()
    if not raw.strip():
        return True
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff") or b"\x00" in raw[:200]:
        text = raw.decode("utf-16", errors="ignore")
    else:
        text = raw.decode("utf-8-sig", errors="ignore")
    text = text.replace("\ufeff", "").replace("\x00", "")
    rows = [ln for ln in text.splitlines() if re.sub(r"[,;\t\"'\s]", "", ln)]
    return len(rows) <= 1


def click_and_download(driver, click, file_stem, delete_if_empty=False):
    """Gọi `click()` (bấm nút xuất), chờ file về rồi lưu thành OUTPUT_DIR/<file_stem>.<đuôi>."""
    for p in list_downloads(driver):
        p.unlink(missing_ok=True)
    before = list_downloads(driver)
    main_window = driver.current_window_handle
    windows_before = set(driver.window_handles)
    had_no_data_text = page_says_no_data(driver)
    mark_page(driver)
    click()
    log.info("    Đã bấm xuất file, đang chờ tải...")

    try:
        f = wait_for_download(driver, before, had_no_data_text)
    finally:
        for h in set(driver.window_handles) - windows_before:
            driver.switch_to.window(h)
            driver.close()
        driver.switch_to.window(main_window)

    if delete_if_empty and csv_is_empty(f):
        f.unlink()
        raise NoDataError("File tải về không có dữ liệu -> đã xóa")

    out_dir = output_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{safe_filename(file_stem)}{f.suffix or '.csv'}"
    if target.exists():
        target.unlink()
    shutil.move(str(f), str(target))
    log.info("    => %s (%.1f KB)", target.name, target.stat().st_size / 1024)
    return target


def export_csv(driver, file_stem, delete_if_empty=False):
    """Bấm nút 'Xuất CSV' (tìm theo chữ trên nút) và lưu file."""
    btn = driver.execute_script(JS_FIND_BUTTON, norm(SETTINGS["export_button_text"]))
    if not btn:
        raise RuntimeError(f"Không tìm thấy nút '{SETTINGS['export_button_text']}'")

    def click():
        try:
            btn.click()
        except WebDriverException:
            driver.execute_script("arguments[0].click();", btn)

    return click_and_download(driver, click, file_stem, delete_if_empty)

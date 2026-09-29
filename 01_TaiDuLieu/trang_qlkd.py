"""
Web http://qlkd.anphuoc.com.vn : "Báo cáo theo dõi hàng đang vận chuyển trên đường"
cho từng kho -> QLKD_<MÃ KHO>.xls (mặc định từ ngày 1 của tháng cách đây `months_back` tháng -> hôm nay).
Chạy tuần tự trong 1 trình duyệt riêng, song song với các báo cáo web report.
"""
from selenium.common.exceptions import TimeoutException, UnexpectedAlertPresentException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select, WebDriverWait

from common import (
    ACCOUNTS, SETTINGS, TMP_DOWNLOAD_DIR, NoDataError, click_and_download, create_driver,
    dismiss_alert, dump_debug, log, months_back_range, pick_kho_option, wait_idle,
)

ACC = ACCOUNTS["qlkd"]
BASE_URL = ACC["url"].rstrip("/")
URL_BAOCAO_THEODOI = f"{BASE_URL}/BaoCao/BaoCaoTheoDoi.aspx"

# ID các control trên trang BaoCaoTheoDoi.aspx
ID_LOAI_BAO_CAO = "cboLoaiBaoCao"
ID_KHO = "cboKho"
ID_NGAY_DAU = "txtNgayDau"
ID_NGAY_CUOI = "txtNgayCuoi"
ID_BTN_EXCEL = "dnn_ctr841_BaoCaoTheoDoi_btnInExcel"


def kho_code(kho):
    return kho.split(" - ")[0].strip()


def login(driver):
    log.info("Đăng nhập %s", BASE_URL)
    driver.get(BASE_URL + "/")
    wait_idle(driver)
    user = driver.find_elements(By.CSS_SELECTOR, "input[id$='txtUserName']")
    if not user:
        log.info("Không thấy form đăng nhập QLKD -> có thể đã đăng nhập sẵn.")
        return
    user[0].clear()
    user[0].send_keys(ACC["username"])
    pwd = driver.find_element(By.CSS_SELECTOR, "input[type='password']")
    pwd.clear()
    pwd.send_keys(ACC["password"])
    btn = driver.find_elements(By.CSS_SELECTOR, "input[id$='cmdDangNhap']")
    if btn:
        btn[0].click()
    else:
        pwd.send_keys(Keys.ENTER)
    try:
        WebDriverWait(driver, 60).until(
            lambda d: not d.find_elements(By.CSS_SELECTOR, "input[id$='txtUserName']"))
    except UnexpectedAlertPresentException as e:
        raise RuntimeError(f"Đăng nhập QLKD thất bại: {(e.alert_text or '').strip()}")
    except TimeoutException:
        dump_debug(driver, "qlkd_login_failed")
        raise RuntimeError("Đăng nhập QLKD thất bại (kiểm tra config/accounts.json).")
    wait_idle(driver)
    log.info("Đăng nhập QLKD thành công.")


def open_report_page(driver):
    driver.get(URL_BAOCAO_THEODOI)
    wait_idle(driver)
    WebDriverWait(driver, 60).until(lambda d: d.find_elements(By.ID, ID_LOAI_BAO_CAO))


def select_by_id(driver, element_id, what, value=None, wanted=None):
    sel = Select(driver.find_element(By.ID, element_id))
    if value:
        sel.select_by_value(value)
    else:
        opts = [(o.text, o.get_attribute("value")) for o in sel.options]
        idx = pick_kho_option(opts, wanted)
        if idx is None:
            raise RuntimeError(f"Không có {what} '{wanted}'. Các lựa chọn: {[t for t, _ in opts]}")
        sel.select_by_index(idx)
    log.info("    %s: %s", what, sel.first_selected_option.text.strip())
    wait_idle(driver)


def set_dates(driver, d_from, d_to):
    fmt = SETTINGS["date_format"]
    for element_id, d in ((ID_NGAY_DAU, d_from), (ID_NGAY_CUOI, d_to)):
        driver.execute_script("""
            var e = document.getElementById(arguments[0]);
            e.value = arguments[1];
            e.dispatchEvent(new Event('change', {bubbles: true}));
        """, element_id, d.strftime(fmt))
    wait_idle(driver)
    log.info("    Ngày: %s -> %s", d_from.strftime(fmt), d_to.strftime(fmt))


def download_one(driver, kho, d_from, d_to):
    cfg = SETTINGS["qlkd"]
    open_report_page(driver)
    select_by_id(driver, ID_LOAI_BAO_CAO, "Loại báo cáo", value=cfg.get("report_type_value"))
    select_by_id(driver, ID_KHO, "Kho", wanted=kho)
    set_dates(driver, d_from, d_to)

    btn = driver.find_element(By.ID, ID_BTN_EXCEL)
    try:
        WebDriverWait(driver, 10).until(lambda d: btn.is_displayed())
    except TimeoutException:
        pass

    def click():
        if btn.is_displayed():
            btn.click()
        else:  # nút đang bị ẩn -> gọi thẳng postback của nút
            driver.execute_script("__doPostBack(arguments[0], '');", btn.get_attribute("name"))

    return click_and_download(driver, click, f"{cfg['file_prefix']}{kho_code(kho)}")


def run_qlkd(results, lock, date_range=None):
    """Tải QLKD_<kho> cho mọi kho trong settings (tuần tự). Ghi kết quả vào `results`.
    `date_range`: (từ, đến) chọn tay; mặc định 1/tháng cách đây `months_back` tháng -> hôm nay."""
    cfg = SETTINGS["qlkd"]
    warehouses = cfg["warehouses"]
    d_from, d_to = date_range or months_back_range(cfg["months_back"])
    log.info("=== QLKD hàng đi đường | %d kho | %s -> %s ===", len(warehouses), d_from, d_to)

    def put(kho, status, path=None):
        with lock:
            results[f"{cfg['file_prefix']}{kho_code(kho)}"] = ("QLKD", status, path)

    driver = None
    try:
        driver = create_driver(TMP_DOWNLOAD_DIR / "qlkd")
        login(driver)
        for i, kho in enumerate(warehouses):
            log.info("--- QLKD | %s ---", kho)
            for attempt in (1, 2):
                try:
                    put(kho, "OK", download_one(driver, kho, d_from, d_to))
                    break
                except NoDataError as e:
                    log.info("    [%s] Bỏ qua: %s", kho, e)
                    put(kho, "TRỐNG")
                    break
                except Exception as e:  # noqa: BLE001
                    log.error("    [%s] Lỗi (lần %d): %s", kho, attempt, str(e).splitlines()[0])
                    dismiss_alert(driver)
                    if attempt == 2:
                        dump_debug(driver, f"qlkd_error_{kho_code(kho)}")
                        put(kho, "LỖI")
            if i == 0 and results.get(f"{cfg['file_prefix']}{kho_code(kho)}", ("", ""))[1] == "LỖI":
                log.error("QLKD: kho đầu tiên đã lỗi -> dừng phần QLKD.")
                break
    except Exception as e:  # noqa: BLE001
        log.error("QLKD không chạy được: %s", str(e).splitlines()[0])
    finally:
        for kho in warehouses:
            key = f"{cfg['file_prefix']}{kho_code(kho)}"
            with lock:
                results.setdefault(key, ("QLKD", "CHƯA CHẠY", None))
        if driver is not None:
            driver.quit()

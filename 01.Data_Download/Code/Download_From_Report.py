"""
Web http://report.anphuoc.ap:8083 : đăng nhập + các báo cáo

  ban_hang    BC_CTBH_Size.aspx   -> Baocao_BanHang_<từ>_<đến>.csv  (mặc định 1/tháng -> hôm qua)
  ban_hd      BC_NXK_CH_SL.aspx   -> Baocao_BanHD_<từ>_<đến>.csv    (mặc định 1/tháng -> hôm qua)
  ton_kho     TimKiemHH.aspx      -> TonKho_<kho>_<nhóm>.csv        (mặc định hôm qua, theo ma trận, bỏ file rỗng)
  luan_chuyen BC_LuanChuyen.aspx  -> RP_<mã kho>.csv                (kho + thời gian giống QLKD)
Khoảng ngày có thể chọn tay trên giao diện (Run_Download_Background.py truyền vào các hàm jobs_*).
"""
from selenium.common.exceptions import TimeoutException, UnexpectedAlertPresentException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from Common_Download_Utils import (
    ACCOUNTS, SETTINGS, Job, choose, dump_debug, export_csv, log, month_range,
    months_back_range, set_dates, wait_idle, yesterday,
)

ACC = ACCOUNTS["report"]
BASE_URL = ACC["url"].rstrip("/")


def login(driver):
    log.info("Đăng nhập %s", BASE_URL)
    driver.get(f"{BASE_URL}/login.aspx")
    wait_idle(driver)
    driver.find_element(By.ID, "loginUsername").clear()
    driver.find_element(By.ID, "loginUsername").send_keys(ACC["username"])
    driver.find_element(By.ID, "loginPassword").clear()
    driver.find_element(By.ID, "loginPassword").send_keys(ACC["password"])
    driver.find_element(By.ID, "loginBtn").click()
    try:
        WebDriverWait(driver, 60).until(lambda d: not d.find_elements(By.ID, "loginPassword"))
    except UnexpectedAlertPresentException as e:
        raise RuntimeError(f"Đăng nhập web report thất bại: {(e.alert_text or '').strip()}")
    except TimeoutException:
        dump_debug(driver, "report_login_failed")
        raise RuntimeError("Đăng nhập web report thất bại (kiểm tra Config/Accounts.json).")
    wait_idle(driver)
    log.info("Đăng nhập web report thành công.")


def open_page(driver, path):
    driver.get(BASE_URL + path)
    wait_idle(driver)
    if driver.find_elements(By.ID, "loginPassword"):  # hết phiên -> đăng nhập lại
        login(driver)
        driver.get(BASE_URL + path)
        wait_idle(driver)


def _month_stem(cfg, date_range=None):
    """Khoảng ngày chọn tay (từ giao diện) hoặc mặc định: 1/tháng -> hôm qua."""
    d_from, d_to = date_range or month_range()
    fd = SETTINGS["file_date_format"]
    return d_from, d_to, cfg["file_name"].format(tu=d_from.strftime(fd), den=d_to.strftime(fd))


def jobs_ban_hang(date_range=None):
    cfg = SETTINGS["ban_hang"]
    d_from, d_to, stem = _month_stem(cfg, date_range)

    def run(driver):
        open_page(driver, cfg["url"])
        set_dates(driver, d_from, d_to)
        return export_csv(driver, stem)

    return [Job("Bán hàng", stem, run)]


def jobs_ban_hd(date_range=None):
    cfg = SETTINGS["ban_hd"]
    d_from, d_to, stem = _month_stem(cfg, date_range)

    def run(driver):
        open_page(driver, cfg["url"])
        for label, value in cfg["selects"]:
            choose(driver, label, value)
        set_dates(driver, d_from, d_to)
        return export_csv(driver, stem)

    return [Job("Bán HĐ", stem, run)]


def jobs_ton_kho(date=None):
    """Mỗi ô được tích trong ma trận kho x nhóm (và có trong "available") = 1 lượt tải.
    `date`: ngày tồn kho chọn tay (mặc định hôm qua)."""
    cfg = SETTINGS["ton_kho"]
    d_to = date or yesterday()
    d_from = d_to.replace(day=1) if cfg.get("tu_ngay_mode") == "month_start" else d_to
    available = cfg.get("available", {})
    jobs = []
    for kho in cfg["kho"]:
        for nhom in cfg["nhom"]:
            if nhom not in cfg["matrix"].get(kho, []) or nhom not in available.get(kho, cfg["nhom"]):
                continue
            stem = cfg["file_name"].format(kho=kho, nhom=nhom)

            def run(driver, kho=kho, nhom=nhom, stem=stem):
                open_page(driver, cfg["url"])
                choose(driver, cfg["label_kho"], kho)
                choose(driver, cfg["label_nhom"], nhom)
                set_dates(driver, d_from, d_to, label=cfg.get("label_ngay"))
                return export_csv(driver, stem, delete_if_empty=True)

            jobs.append(Job("Tồn kho", stem, run, cacheable=True))
    return jobs


def jobs_luan_chuyen(date_range=None):
    """BC_LuanChuyen cho các kho của QLKD, cùng khoảng thời gian với QLKD."""
    q = SETTINGS["qlkd"]
    cfg = q["luan_chuyen"]
    d_from, d_to = date_range or months_back_range(q["months_back"])
    jobs = []
    for kho in q["warehouses"]:
        stem = cfg["file_name"].format(kho=kho.split(" - ")[0].strip())

        def run(driver, kho=kho, stem=stem):
            open_page(driver, cfg["url"])
            # Chọn Cửa hàng trước: trang postback rồi mới hiện ô "Loại báo cáo"
            choose(driver, cfg["label_kho"], kho)
            for label, value in cfg["selects"]:
                choose(driver, label, value)
            set_dates(driver, d_from, d_to)
            return export_csv(driver, stem)

        jobs.append(Job("QLKD-RP", stem, run))
    return jobs

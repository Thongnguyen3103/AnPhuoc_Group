"""
Chạy các mục báo cáo đã chọn (giao diện Open_Download_GUI.py gọi file này, hoặc chạy tay / đặt lịch):

    python Run_Download_Background.py                                  # chạy các mục đang tích trong Settings.json
    python Run_Download_Background.py --jobs qlkd ban_hang             # chỉ chạy các mục này
    python Run_Download_Background.py --jobs ton_kho --reload-empty    # tải lại cả các ô tồn kho đã biết rỗng
    python Run_Download_Background.py --jobs ban_hang --range-ban-hang 01/08/2026 31/08/2026   # tự chọn khoảng ngày
    python Run_Download_Background.py --jobs ton_kho --date-ton-kho 20/09/2026                  # tồn kho ngày khác
    python Run_Download_Background.py --jobs qlkd --range-qlkd 01/04/2026 28/09/2026            # QLKD ngày khác
    python Run_Download_Background.py --jobs luan_chuyen --range-luan-chuyen 01/04/2026 28/09/2026  # RP ngày khác
    python Run_Download_Background.py --jobs nx_kho --range-nx-kho 01/08/2026 31/08/2026        # NSX/XCH/TraKho tháng khác
    python Run_Download_Background.py --jobs qlkd_ntc --range-qlkd-ntc 01/08/2026 31/08/2026    # NTC tháng khác

Mục:  qlkd     = QLKD hàng đi đường (QLKD_<kho>)      luan_chuyen = Luân chuyển BC_LuanChuyen (RP_<kho>)
      ban_hang = Baocao_BanHang      ban_hd = Baocao_BanHD      ton_kho = TonKho_<kho>_<nhóm>
      qlkd_ntc = QLKD nhập kho trung chuyển, chi tiết có mã hàng (NTC_<kho>_<tg>)
      nx_kho   = BC_NX_KHO: NSX_<kho>_<tg> (nhập SX) + XCH_<kho>_<tg> (xuất CH) + TraKho_<kho>_<tg> (nhập từ CH)
"""
import argparse
import datetime as dt
import queue
import sys
import threading
import time

from selenium.common.exceptions import TimeoutException

from Common_Download_Utils import (
    EMPTY_CACHE_FILE, SETTINGS, TMP_DOWNLOAD_DIR, NoDataError, create_driver, dismiss_alert,
    dump_debug, load_json, log, output_dir, save_json, setup_logging,
)
import Download_From_QLKD as site_qlkd
import Download_From_Report as site_report

ALL_JOBS = ("qlkd", "luan_chuyen", "qlkd_ntc", "ban_hang", "ban_hd", "nx_kho", "ton_kho")


# ----------------------------------------------------------------------------- 1 lượt tải
def run_with_retry(driver, job, attempts=2):
    for attempt in range(1, attempts + 1):
        try:
            return "OK", job.run(driver)
        except NoDataError as e:
            log.info("    [%s] Bỏ qua: %s", job.stem, e)
            return "TRỐNG", None
        except TimeoutException as e:  # đã chờ rất lâu -> không thử lại
            log.error("    [%s] Lỗi: %s", job.stem, str(e).splitlines()[0] if str(e) else "hết thời gian chờ")
            return "LỖI", None
        except Exception as e:  # noqa: BLE001
            log.error("    [%s] Lỗi (lần %d): %s", job.stem, attempt, str(e).splitlines()[0])
            dismiss_alert(driver)
            if attempt == attempts:
                dump_debug(driver, f"error_{job.stem}")
    return "LỖI", None


# ----------------------------------------------------------------------------- lượt tồn kho rỗng
def skip_known_empty(jobs, cache):
    """Bỏ các ô tồn kho đã rỗng lần trước, trừ khi đã quá `empty_recheck_days` ngày."""
    days = int(SETTINGS.get("empty_recheck_days", 7))
    today = dt.date.today()
    keep, skipped = [], []
    for j in jobs:
        checked = cache.get(j.stem)
        if j.cacheable and checked and (today - dt.date.fromisoformat(checked)).days < days:
            skipped.append(j)
        else:
            keep.append(j)
    return keep, skipped


# ----------------------------------------------------------------------------- tab web report
def make_queue(jobs):
    q = queue.Queue()
    for j in jobs:
        q.put(j)
    return q


def next_job(queues):
    for q in queues:
        try:
            return q.get_nowait(), q
        except queue.Empty:
            continue
    return None, None


def run_report_jobs(jobs, results, lock):
    """
    Các tab web report cùng lấy việc:
      - `tabs_sales` tab ưu tiên Bán hàng / Bán HĐ / RP, xong thì phụ tồn kho
      - các tab còn lại ưu tiên tồn kho, hết tồn kho thì phụ phần còn lại
    """
    if not jobs:
        return
    q_sales = make_queue([j for j in jobs if not j.cacheable])
    q_ton = make_queue([j for j in jobs if j.cacheable])
    n_total = max(1, min(int(SETTINGS.get("tabs_report", 5)), len(jobs)))
    n_sales = min(int(SETTINGS.get("tabs_sales", 1)), q_sales.qsize(), n_total)
    plan = [[q_sales, q_ton]] * n_sales + [[q_ton, q_sales]] * (n_total - n_sales)
    stop = threading.Event()
    log.info("=== Web report | %d lượt | %d tab (%d ưu tiên bán hàng/RP) ===", len(jobs), n_total, n_sales)

    def worker(idx):
        driver = None
        try:
            driver = create_driver(TMP_DOWNLOAD_DIR / f"w{idx}")
            site_report.login(driver)
            while not stop.is_set():
                job, q = next_job(plan[idx - 1])
                if job is None:
                    return
                log.info("--- %s --- (còn %d lượt chờ)", job.stem, q.qsize())
                status, path = run_with_retry(driver, job)
                with lock:
                    results[job.stem] = (job.group, status, path)
                    done = [s for g, s, _ in results.values() if g != "QLKD"]
                    if len(done) >= 3 and all(s == "LỖI" for s in done):
                        log.error("3 lượt web report đầu tiên đều lỗi -> dừng web report.")
                        stop.set()
        except Exception as e:  # noqa: BLE001
            log.error("Tab W%d không chạy được: %s", idx, str(e).splitlines()[0])
        finally:
            if driver is not None:
                driver.quit()

    threads = [threading.Thread(target=worker, args=(i,), name=f"W{i}") for i in range(1, n_total + 1)]
    for t in threads:
        t.start()
        time.sleep(3)  # mở lần lượt cho đỡ nặng máy
    for t in threads:
        t.join()
    for j in jobs:
        results.setdefault(j.stem, (j.group, "CHƯA CHẠY", None))


# ----------------------------------------------------------------------------- main
def parse_date(text):
    try:
        return dt.datetime.strptime(text, "%d/%m/%Y").date()
    except ValueError:
        raise argparse.ArgumentTypeError(f"Ngày không hợp lệ: {text} (cần dd/mm/yyyy)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", nargs="+", choices=ALL_JOBS, help="Các mục cần chạy (mặc định theo Settings.json)")
    ap.add_argument("--reload-empty", action="store_true", help="Tải lại cả các ô tồn kho đã biết rỗng")
    ap.add_argument("--range-qlkd", nargs=2, metavar=("TU", "DEN"), type=parse_date,
                    help="Khoảng ngày QLKD + RP, dd/mm/yyyy (mặc định 1/tháng cách đây months_back tháng -> hôm nay)")
    ap.add_argument("--range-luan-chuyen", nargs=2, metavar=("TU", "DEN"), type=parse_date,
                    help="Khoảng ngày Luân chuyển RP, dd/mm/yyyy (mặc định giống QLKD)")
    ap.add_argument("--date-ton-kho", metavar="NGAY", type=parse_date,
                    help="Ngày tồn kho, dd/mm/yyyy (mặc định hôm qua)")
    ap.add_argument("--range-ban-hang", nargs=2, metavar=("TU", "DEN"), type=parse_date,
                    help="Khoảng ngày Bán hàng, dd/mm/yyyy (mặc định 1/tháng -> hôm qua)")
    ap.add_argument("--range-ban-hd", nargs=2, metavar=("TU", "DEN"), type=parse_date,
                    help="Khoảng ngày Bán HĐ, dd/mm/yyyy (mặc định 1/tháng -> hôm qua)")
    ap.add_argument("--range-nx-kho", nargs=2, metavar=("TU", "DEN"), type=parse_date,
                    help="Khoảng ngày NSX/XCH/TraKho, dd/mm/yyyy (mặc định trọn tháng trước)")
    ap.add_argument("--range-qlkd-ntc", nargs=2, metavar=("TU", "DEN"), type=parse_date,
                    help="Khoảng ngày QLKD nhập trung chuyển, dd/mm/yyyy (mặc định trọn tháng trước)")
    args = ap.parse_args()
    setup_logging()
    threading.current_thread().name = "Main"

    sel_cfg = dict(SETTINGS.get("selected", {}))
    sel_cfg.setdefault("luan_chuyen", sel_cfg.get("qlkd", False))  # Settings cũ: RP đi kèm qlkd
    selected = args.jobs or [k for k in ALL_JOBS if sel_cfg.get(k)]
    reload_empty = args.reload_empty or SETTINGS.get("reload_empty", False)
    if not selected:
        log.error("Chưa chọn mục nào để chạy.")
        sys.exit(2)

    report_jobs = []
    if "ban_hang" in selected:
        report_jobs += site_report.jobs_ban_hang(args.range_ban_hang)
    if "ban_hd" in selected:
        report_jobs += site_report.jobs_ban_hd(args.range_ban_hd)
    if "nx_kho" in selected:
        report_jobs += site_report.jobs_nx_kho(args.range_nx_kho)
    if "luan_chuyen" in selected:
        report_jobs += site_report.jobs_luan_chuyen(args.range_luan_chuyen)
    skipped = []
    if "ton_kho" in selected:
        ton = site_report.jobs_ton_kho(args.date_ton_kho)
        cache = load_json(EMPTY_CACHE_FILE, {})
        if not reload_empty:
            ton, skipped = skip_known_empty(ton, cache)
        report_jobs += ton

    log.info("===== BẮT ĐẦU | Mục: %s | %d lượt web report (bỏ qua %d ô tồn kho đã biết rỗng) | Lưu vào %s =====",
             ", ".join(selected), len(report_jobs), len(skipped), output_dir())

    t0 = time.time()
    results, lock = {}, threading.Lock()
    qlkd_thread = None
    if "qlkd" in selected or "qlkd_ntc" in selected:
        def run_qlkd_site():  # cùng 1 luồng: QLKD hàng đi đường xong rồi mới tới nhập trung chuyển
            if "qlkd" in selected:
                site_qlkd.run_qlkd(results, lock, args.range_qlkd)
            if "qlkd_ntc" in selected:
                site_qlkd.run_nhap_tc(results, lock, args.range_qlkd_ntc)

        qlkd_thread = threading.Thread(target=run_qlkd_site, name="QLKD")
        qlkd_thread.start()
        time.sleep(3)
    run_report_jobs(report_jobs, results, lock)
    if qlkd_thread:
        qlkd_thread.join()

    # ghi nhớ ô tồn kho rỗng / có dữ liệu
    cache = load_json(EMPTY_CACHE_FILE, {})
    today = dt.date.today().isoformat()
    for j in report_jobs:
        status = results[j.stem][1]
        if j.cacheable and status == "TRỐNG":
            cache[j.stem] = today
        elif j.cacheable and status == "OK":
            cache.pop(j.stem, None)
    save_json(EMPTY_CACHE_FILE, cache)

    log.info("===== KẾT QUẢ (%.0f phút) =====", (time.time() - t0) / 60)
    for stem, (group, status, path) in sorted(results.items(), key=lambda kv: kv[1][0]):
        log.info("  %-9s %-9s %s", group, status, path.name if path else stem)
    for j in skipped:
        log.info("  %-9s %-9s %s", j.group, "BỎ QUA", j.stem)
    n_err = sum(1 for _, s, _ in results.values() if s not in ("OK", "TRỐNG"))
    log.info("===== XONG: %d OK, %d trống, %d lỗi =====",
             sum(1 for _, s, _ in results.values() if s == "OK"),
             sum(1 for _, s, _ in results.values() if s == "TRỐNG"), n_err)
    sys.exit(1 if n_err else 0)


if __name__ == "__main__":
    main()

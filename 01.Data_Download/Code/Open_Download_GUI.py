"""
Giao diện chọn mục và chạy tool tải báo cáo An Phước.

  Tab "Chạy"       : tích các mục cần tải, bấm Chạy / Dừng, xem log trực tiếp
  Tab "Tồn kho"    : ma trận Kho x Nhóm hàng, tích ô nào thì tải ô đó
  Tab "Tài khoản"  : đổi ID / mật khẩu 2 web (lưu vào Config/Accounts.json)

Giao diện gọi Run_Download_Background.py trong 1 tiến trình riêng nên vẫn dùng được trong lúc tải.
"""
import datetime as dt
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from Common_Download_Utils import (
    ACCOUNTS_FILE, EMPTY_CACHE_FILE, LOG_DIR, ROOT, SETTINGS_FILE, load_json, month_range,
    months_back_range, prev_month_range, save_json, yesterday,
)

RUNNER = Path(__file__).resolve().parent / "Run_Download_Background.py"
FMT = "%d/%m/%Y"

JOB_LABELS = {
    "qlkd": "QLKD: Hàng đi đường (QLKD_<kho>) + Luân chuyển (RP_<kho>)",
    "ban_hang": "Bán hàng - BC_CTBH_Size (Baocao_BanHang_...)",
    "ban_hd": "Bán hợp đồng - BC_NXK_CH_SL (Baocao_BanHD_...)",
    "nx_kho": "Nhập xuất kho - BC_NX_KHO (NSX_ / XCH_ / TraKho_<kho>_...)",
    "ton_kho": "Tồn kho - TimKiemHH (TonKho_<kho>_<nhóm>)",
}


try:  # lịch chọn ngày; không có thư viện thì dùng ô gõ tay dd/mm/yyyy
    from tkcalendar import DateEntry
except ImportError:
    DateEntry = None


def make_date_input(parent):
    if DateEntry:
        return DateEntry(parent, width=11, date_pattern="dd/mm/yyyy", firstweekday="monday")
    return ttk.Entry(parent, width=12)


def set_date_input(w, d):
    if DateEntry and isinstance(w, DateEntry):
        w.set_date(d)
    else:
        w.delete(0, "end")
        w.insert(0, f"{d:{FMT}}")


def get_date_input(w):
    try:
        return dt.datetime.strptime(w.get().strip(), FMT).date()
    except ValueError:
        return None


def python_exe():
    """Luôn chạy runner bằng python.exe (kể cả khi giao diện mở bằng pythonw.exe)."""
    exe = Path(sys.executable)
    cand = exe.with_name("python.exe")
    return str(cand if cand.exists() else exe)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Tool tải báo cáo An Phước")
        self.geometry("1100x720")
        self.minsize(900, 600)

        self.settings = load_json(SETTINGS_FILE)
        self.accounts = load_json(ACCOUNTS_FILE)
        self.empty_cache = load_json(EMPTY_CACHE_FILE, {})
        self.proc = None
        self.lines = queue.Queue()

        style = ttk.Style(self)
        style.configure("Run.TButton", font=("Segoe UI", 11, "bold"), padding=8)
        style.configure("Head.TLabel", font=("Segoe UI", 10, "bold"))

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)
        self.tab_run = ttk.Frame(nb, padding=10)
        self.tab_matrix = ttk.Frame(nb, padding=10)
        self.tab_acc = ttk.Frame(nb, padding=10)
        nb.add(self.tab_run, text="  ▶ Chạy  ")
        nb.add(self.tab_matrix, text="  Tồn kho (ma trận)  ")
        nb.add(self.tab_acc, text="  Tài khoản  ")

        self.build_run_tab()
        self.build_matrix_tab()
        self.build_account_tab()
        self.refresh_job_labels()

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(150, self.poll_output)

    # ------------------------------------------------------------------ tab Chạy
    def build_run_tab(self):
        f = self.tab_run
        box = ttk.LabelFrame(f, text="Chọn mục cần tải", padding=10)
        box.pack(fill="x")
        self.job_vars, self.job_checks, self.date_inputs, self.notes = {}, {}, {}, {}
        sel = self.settings.get("selected", {})
        for key in ("qlkd", "ban_hang", "ban_hd", "nx_kho", "ton_kho"):
            row = ttk.Frame(box)
            row.pack(anchor="w", fill="x", pady=2)
            v = tk.BooleanVar(value=sel.get(key, True))
            cb = ttk.Checkbutton(row, variable=v, command=self.refresh_job_labels)
            cb.pack(side="left")
            self.job_vars[key], self.job_checks[key] = v, cb
            cb.configure(width=58)  # các hàng ô ngày thẳng cột
            self.build_date_range(row, key)
        self.reset_dates()

        opt = ttk.LabelFrame(f, text="Tuỳ chọn", padding=10)
        opt.pack(fill="x", pady=(8, 0))
        self.reload_empty = tk.BooleanVar(value=self.settings.get("reload_empty", False))
        ttk.Checkbutton(opt, text="Tồn kho: tải lại cả các ô đã biết là rỗng",
                        variable=self.reload_empty).grid(row=0, column=0, sticky="w")
        self.headless = tk.BooleanVar(value=self.settings.get("headless", False))
        ttk.Checkbutton(opt, text="Chạy ẩn Firefox (không hiện cửa sổ)",
                        variable=self.headless).grid(row=0, column=1, sticky="w", padx=(30, 0))
        ttk.Label(opt, text="Số tab web report chạy song song:").grid(row=0, column=2, sticky="e", padx=(30, 4))
        self.tabs = tk.IntVar(value=int(self.settings.get("tabs_report", 5)))
        ttk.Spinbox(opt, from_=1, to=8, width=4, textvariable=self.tabs).grid(row=0, column=3, sticky="w")

        bar = ttk.Frame(f)
        bar.pack(fill="x", pady=8)
        self.btn_run = ttk.Button(bar, text="▶  CHẠY", style="Run.TButton", command=self.start)
        self.btn_run.pack(side="left")
        self.btn_stop = ttk.Button(bar, text="■  Dừng", command=self.stop, state="disabled")
        self.btn_stop.pack(side="left", padx=8)
        ttk.Button(bar, text="Mở thư mục tải về", command=self.open_output).pack(side="left", padx=(20, 0))
        ttk.Button(bar, text="Mở thư mục log", command=lambda: self.open_path(LOG_DIR)).pack(side="left", padx=8)
        self.status = ttk.Label(bar, text="Sẵn sàng.", style="Head.TLabel")
        self.status.pack(side="right")

        self.log = ScrolledText(f, height=20, font=("Consolas", 9), wrap="none", state="disabled")
        self.log.pack(fill="both", expand=True)
        self.log.tag_configure("err", foreground="#c0392b")
        self.log.tag_configure("ok", foreground="#1e8449")
        self.log.tag_configure("head", foreground="#1f4e79", font=("Consolas", 9, "bold"))

    def build_date_range(self, row, key):
        """Ô ngày của từng mục (sửa được, nút "Mặc định" để quay về ngày tự tính)."""
        single = key == "ton_kho"
        ttk.Label(row, text="Ngày tồn" if single else "Từ ngày", width=9, anchor="e").pack(side="left")
        inputs = [make_date_input(row)]
        inputs[0].pack(side="left", padx=4)
        if not single:
            ttk.Label(row, text="Đến ngày").pack(side="left")
            inputs.append(make_date_input(row))
            inputs[1].pack(side="left", padx=4)
        ttk.Button(row, text="Mặc định", width=9,
                   command=lambda k=key: self.reset_dates(k)).pack(side="left", padx=6)
        self.notes[key] = ttk.Label(row, foreground="#666")
        self.notes[key].pack(side="left")
        self.date_inputs[key] = inputs

    def default_dates(self, key):
        if key == "qlkd":  # 1/tháng cách đây months_back tháng -> hôm nay (QLKD + RP)
            return months_back_range(self.settings["qlkd"]["months_back"])
        if key == "ton_kho":  # hôm qua
            return (yesterday(),)
        if key == "nx_kho":  # trọn tháng trước
            return prev_month_range()
        return month_range()  # bán hàng, bán HĐ: 1/tháng -> hôm qua

    def reset_dates(self, key=None):
        for k, inputs in self.date_inputs.items():
            if key in (None, k):
                for w, d in zip(inputs, self.default_dates(k)):
                    set_date_input(w, d)

    def refresh_job_labels(self):
        n_cells = self.count_selected_cells() if hasattr(self, "cells") else 0
        notes = {
            "qlkd": f"({len(self.settings['qlkd']['warehouses'])} kho, bấm 1 lần tải cả 2 báo cáo)",
            "ban_hang": "",
            "ban_hd": "(Báo cáo xuất kho + Xuất bán hợp đồng)",
            "nx_kho": f"({sum(len(r['kho']) for r in self.settings['nx_kho']['reports'])} file)",
            "ton_kho": f"({n_cells} ô đang tích trong ma trận)",
        }
        for key, cb in self.job_checks.items():
            cb.configure(text=JOB_LABELS[key])
            self.notes[key].configure(text=notes[key])

    DATE_FLAGS = {"qlkd": "--range-qlkd", "ban_hang": "--range-ban-hang",
                  "ban_hd": "--range-ban-hd", "nx_kho": "--range-nx-kho", "ton_kho": "--date-ton-kho"}
    JOB_NAMES = {"qlkd": "QLKD", "ban_hang": "Bán hàng", "ban_hd": "Bán hợp đồng",
                 "nx_kho": "Nhập xuất kho", "ton_kho": "Tồn kho"}

    def date_range_args(self, jobs):
        """['--range-qlkd', 'tu', 'den', '--date-ton-kho', 'ngay', ...] theo ô ngày; báo lỗi nếu ngày sai."""
        args = []
        for key in jobs:
            dates = [get_date_input(w) for w in self.date_inputs[key]]
            if None in dates:
                raise ValueError(f"{self.JOB_NAMES[key]}: ngày không hợp lệ (cần dd/mm/yyyy).")
            if len(dates) == 2 and dates[0] > dates[1]:
                raise ValueError(f"{self.JOB_NAMES[key]}: Từ ngày phải trước hoặc bằng Đến ngày.")
            args += [self.DATE_FLAGS[key], *(f"{d:{FMT}}" for d in dates)]
        return args

    # ------------------------------------------------------------------ tab ma trận tồn kho
    def build_matrix_tab(self):
        f = self.tab_matrix
        tk_cfg = self.settings["ton_kho"]
        self.kho_list, self.nhom_list = tk_cfg["kho"], tk_cfg["nhom"]

        ttk.Label(f, text="Tích ô (Kho x Nhóm hàng) cần tải tồn kho. Bấm tên kho / tên nhóm để "
                          "tích hoặc bỏ cả hàng / cả cột.", style="Head.TLabel").pack(anchor="w")
        ttk.Label(f, text="Ô \"–\" = kho không có nhóm hàng này (sửa danh sách ở mục \"available\" "
                          "trong Config/Settings.json).", foreground="#666").pack(anchor="w")
        ttk.Label(f, text="Ô ghi \"rỗng\" = lần kiểm tra gần nhất không có dữ liệu, sẽ tự bỏ qua "
                          "(trừ khi tích \"tải lại cả các ô đã biết là rỗng\" ở tab Chạy).",
                  foreground="#666").pack(anchor="w", pady=(0, 8))

        grid = ttk.Frame(f)
        grid.pack(anchor="w")
        self.cells = {}
        for c, nhom in enumerate(self.nhom_list, start=1):
            tk.Button(grid, text=nhom, width=14, height=2, wraplength=110, relief="groove",
                      command=lambda n=nhom: self.toggle_line(nhom=n)).grid(row=0, column=c, padx=2, pady=2)
        for r, kho in enumerate(self.kho_list, start=1):
            ttk.Button(grid, text=kho, width=26,
                       command=lambda k=kho: self.toggle_line(kho=k)).grid(row=r, column=0, sticky="w", padx=2, pady=2)
            chosen = set(tk_cfg["matrix"].get(kho, []))
            available = set(tk_cfg.get("available", {}).get(kho, self.nhom_list))
            for c, nhom in enumerate(self.nhom_list, start=1):
                if nhom not in available:  # kho không có nhóm này -> không hiện ô
                    ttk.Label(grid, text="–", foreground="#bbb").grid(row=r, column=c)
                    continue
                v = tk.BooleanVar(value=nhom in chosen)
                cell = ttk.Frame(grid)
                cell.grid(row=r, column=c)
                ttk.Checkbutton(cell, variable=v, command=self.on_matrix_change).pack(side="left")
                if tk_cfg["file_name"].format(kho=kho, nhom=nhom) in self.empty_cache:
                    ttk.Label(cell, text="rỗng", foreground="#999").pack(side="left")
                self.cells[(kho, nhom)] = v

        bar = ttk.Frame(f)
        bar.pack(anchor="w", pady=10)
        ttk.Button(bar, text="Chọn tất cả", command=lambda: self.set_all(True)).pack(side="left")
        ttk.Button(bar, text="Bỏ chọn tất cả", command=lambda: self.set_all(False)).pack(side="left", padx=6)
        ttk.Button(bar, text="Lưu ma trận", command=self.save_settings_clicked).pack(side="left", padx=(20, 0))
        self.matrix_count = ttk.Label(bar, style="Head.TLabel")
        self.matrix_count.pack(side="left", padx=20)
        self.on_matrix_change()

    def count_selected_cells(self):
        return sum(v.get() for v in self.cells.values())

    def on_matrix_change(self):
        self.matrix_count.configure(text=f"Đang tích {self.count_selected_cells()} / {len(self.cells)} ô")
        if hasattr(self, "job_checks"):
            self.refresh_job_labels()

    def toggle_line(self, kho=None, nhom=None):
        keys = [k for k in self.cells if (kho and k[0] == kho) or (nhom and k[1] == nhom)]
        target = not all(self.cells[k].get() for k in keys)
        for k in keys:
            self.cells[k].set(target)
        self.on_matrix_change()

    def set_all(self, value):
        for v in self.cells.values():
            v.set(value)
        self.on_matrix_change()

    # ------------------------------------------------------------------ tab tài khoản
    def build_account_tab(self):
        f = self.tab_acc
        self.acc_vars = {}
        titles = {"qlkd": "QLKD  (qlkd.anphuoc.com.vn)", "report": "Web report  (report.anphuoc.ap:8083)"}
        self.pw_entries = []
        for i, key in enumerate(("qlkd", "report")):
            box = ttk.LabelFrame(f, text=titles[key], padding=10)
            box.grid(row=i, column=0, sticky="we", pady=6)
            acc = self.accounts[key]
            vs = {k: tk.StringVar(value=acc.get(k, "")) for k in ("url", "username", "password")}
            self.acc_vars[key] = vs
            for r, (k, label) in enumerate((("url", "Địa chỉ web"), ("username", "Tên đăng nhập"),
                                            ("password", "Mật khẩu"))):
                ttk.Label(box, text=label, width=16).grid(row=r, column=0, sticky="w", pady=3)
                e = ttk.Entry(box, textvariable=vs[k], width=50, show="•" if k == "password" else "")
                e.grid(row=r, column=1, sticky="w", pady=3)
                if k == "password":
                    self.pw_entries.append(e)
        self.show_pw = tk.BooleanVar(value=False)
        ttk.Checkbutton(f, text="Hiện mật khẩu", variable=self.show_pw,
                        command=lambda: [e.configure(show="" if self.show_pw.get() else "•")
                                         for e in self.pw_entries]).grid(row=2, column=0, sticky="w")
        ttk.Button(f, text="Lưu tài khoản", command=self.save_accounts).grid(row=3, column=0, sticky="w", pady=10)
        ttk.Label(f, text=f"Lưu tại: {ACCOUNTS_FILE}", foreground="#666").grid(row=4, column=0, sticky="w")

    def save_accounts(self):
        for key, vs in self.acc_vars.items():
            self.accounts[key] = {k: v.get().strip() for k, v in vs.items()}
        save_json(ACCOUNTS_FILE, self.accounts)
        messagebox.showinfo("Tài khoản", "Đã lưu tài khoản. Lần chạy sau sẽ dùng thông tin mới.")

    # ------------------------------------------------------------------ lưu cấu hình
    def collect_settings(self):
        s = self.settings
        s["selected"] = {k: v.get() for k, v in self.job_vars.items()}
        s["reload_empty"] = self.reload_empty.get()
        s["headless"] = self.headless.get()
        try:
            s["tabs_report"] = max(1, min(8, int(self.tabs.get())))
        except (tk.TclError, ValueError):
            pass
        s["ton_kho"]["matrix"] = {kho: [n for n in self.nhom_list
                                        if (kho, n) in self.cells and self.cells[(kho, n)].get()]
                                  for kho in self.kho_list}
        save_json(SETTINGS_FILE, s)

    def save_settings_clicked(self):
        self.collect_settings()
        messagebox.showinfo("Tồn kho", "Đã lưu ma trận tồn kho.")

    # ------------------------------------------------------------------ chạy / dừng
    def start(self):
        if self.proc:
            return
        jobs = [k for k, v in self.job_vars.items() if v.get()]
        if not jobs:
            messagebox.showwarning("Chưa chọn", "Hãy tích ít nhất 1 mục cần tải.")
            return
        if "ton_kho" in jobs and self.count_selected_cells() == 0:
            messagebox.showwarning("Tồn kho", "Ma trận tồn kho chưa tích ô nào.")
            return
        try:
            range_args = self.date_range_args(jobs)
        except ValueError as e:
            messagebox.showwarning("Ngày", str(e))
            return
        self.collect_settings()

        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        cmd = [python_exe(), "-u", str(RUNNER), "--jobs", *jobs, *range_args]
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
        self.proc = subprocess.Popen(
            cmd, cwd=str(ROOT), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        threading.Thread(target=self.read_output, args=(self.proc,), daemon=True).start()
        self.started_at = dt.datetime.now()
        self.btn_run.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.status.configure(text=f"Đang chạy: {', '.join(jobs)}", foreground="#1f4e79")

    def read_output(self, proc):
        for raw in proc.stdout:
            self.lines.put(raw.decode("utf-8", errors="replace").rstrip())
        proc.wait()
        self.lines.put(None)

    def poll_output(self):
        try:
            while True:
                line = self.lines.get_nowait()
                if line is None:
                    self.on_finished()
                    continue
                tag = ("err" if "| ERROR" in line or "LỖI" in line else
                       "ok" if "=> " in line or " OK " in line else
                       "head" if "=====" in line else None)
                self.log.configure(state="normal")
                self.log.insert("end", line + "\n", tag)
                self.log.see("end")
                self.log.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(150, self.poll_output)

    def on_finished(self):
        code = self.proc.returncode if self.proc else None
        self.proc = None
        self.btn_run.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        mins = (dt.datetime.now() - self.started_at).total_seconds() / 60
        if code == 0:
            self.status.configure(text=f"Xong ({mins:.0f} phút).", foreground="#1e8449")
        else:
            self.status.configure(text=f"Kết thúc, có lỗi / bị dừng ({mins:.0f} phút) - xem log.",
                                  foreground="#c0392b")
        # cập nhật chữ "rỗng" trong ma trận theo lần chạy vừa xong
        self.empty_cache = load_json(EMPTY_CACHE_FILE, {})
        for w in self.tab_matrix.winfo_children():
            w.destroy()
        self.build_matrix_tab()

    def stop(self):
        if not self.proc:
            return
        if not messagebox.askyesno("Dừng", "Dừng tải và đóng các cửa sổ Firefox đang chạy?"):
            return
        self.kill_proc()
        self.status.configure(text="Đang dừng...", foreground="#c0392b")

    def kill_proc(self):
        if self.proc and self.proc.poll() is None:
            # /T: đóng luôn geckodriver + Firefox do tiến trình này mở
            subprocess.run(["taskkill", "/PID", str(self.proc.pid), "/T", "/F"],
                           capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def on_close(self):
        if self.proc and self.proc.poll() is None:
            if not messagebox.askyesno("Thoát", "Tool đang chạy. Dừng tải và thoát?"):
                return
            self.kill_proc()
        self.destroy()

    # ------------------------------------------------------------------ tiện ích
    def open_output(self):
        self.open_path(Path(self.settings.get("output_dir") or (Path.home() / "Downloads")))

    @staticmethod
    def open_path(path):
        Path(path).mkdir(parents=True, exist_ok=True)
        os.startfile(str(path))


if __name__ == "__main__":
    App().mainloop()

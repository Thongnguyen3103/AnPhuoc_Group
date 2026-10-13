# -*- coding: utf-8 -*-
"""TransferApp — Giao diện Báo cáo Điều chuyển Hàng hoá (1 cửa sổ).
Chọn file/tham số, bấm "Chạy Báo Cáo", xem tiến trình trong khung log, xong bấm nút mở file kết quả."""
import json
import os
import queue
import subprocess
import sys
import threading
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, scrolledtext

from Config import Paths_Transfer as paths
from Config.Config_Gui_Theme import (BG, CARD, CARD_BORDER, TEXT, LABEL, ACCENT, ACCENT_HOVER, GREEN, GREEN_HOVER, RED, RED_HOVER, ENTRY_BG, BTN_SECONDARY, BTN_SECONDARY_HOVER, FONT, FONT_BOLD, FONT_TITLE, FONT_BIG_TITLE)
from Core.Load_Data_Parquet import TransferDataLoader
from Core.Run_Transfer_Report import TransferReportRunner, CancelledError


class TransferApp:
    """Cửa sổ chọn file/tham số, chạy TransferReportRunner ở luồng nền, hiện log + mở file kết quả."""
    def __init__(self, root):
        self.root = root
        self.root.title("Báo cáo Điều chuyển Hàng hoá")
        self.root.geometry("920x860")
        self.root.minsize(920, 800)
        self.root.configure(bg=BG)

        self._store_list = []       # [(Store_name, Region, Loai_CH)]
        self._region_vars = {}
        self._store_vars = {}
        self._khong_rut = self._load_khong_rut()   # set Store_name: CH mới / không tham gia rút
        self._log_queue = queue.Queue()
        self._worker = None
        self._cancel_event = None
        self._result = None

        self._init_styles()
        self._build_ui()
        self.root.after(150, self._poll_queue)
        self._load_stores_async()

    def _init_styles(self):
        self.style = ttk.Style()
        if "clam" in self.style.theme_names():
            self.style.theme_use("clam")
        
        # Configure custom TTK scrollbar to match dark theme
        self.style.configure("TScrollbar",
                             gripcount=0,
                             background="#1e293b",
                             troughcolor="#090d16",
                             bordercolor="#223047",
                             lightcolor="#1e293b",
                             darkcolor="#1e293b",
                             arrowcolor="#94a3b8")
        self.style.map("TScrollbar",
                       background=[("active", "#334155")])

        # Configure custom TTK progressbar
        self.style.configure("Horizontal.TProgressbar",
                             troughcolor="#090d16",
                             background="#10b981",
                             lightcolor="#10b981",
                             darkcolor="#10b981",
                             bordercolor="#223047")

        # Configure custom TTK Combobox to match dark theme
        self.style.configure("TCombobox",
                             fieldbackground=ENTRY_BG,
                             background=CARD,
                             foreground=TEXT,
                             bordercolor=CARD_BORDER,
                             arrowcolor=TEXT)
        self.style.map("TCombobox",
                       fieldbackground=[("readonly", ENTRY_BG)],
                       foreground=[("readonly", TEXT)])

    def _bind_hover(self, widget, normal_bg, hover_bg):
        def on_enter(e):
            if widget.cget("state") != "disabled":
                widget.config(bg=hover_bg)
        def on_leave(e):
            if widget.cget("state") != "disabled":
                widget.config(bg=normal_bg)
        widget.bind("<Enter>", on_enter)
        widget.bind("<Leave>", on_leave)

    def _create_rounded_card(self, parent, bg_color=BG, fill_color=CARD, border_color=CARD_BORDER):
        canvas = tk.Canvas(parent, bg=bg_color, highlightthickness=0)
        
        def draw_bg(event=None):
            canvas.delete("bg")
            w = canvas.winfo_width()
            h = canvas.winfo_height()
            r = 10 # corner radius
            
            # Fill
            canvas.create_arc(0, 0, 2*r, 2*r, start=90, extent=90, fill=fill_color, outline="", tags="bg")
            canvas.create_arc(w - 2*r, 0, w, 2*r, start=0, extent=90, fill=fill_color, outline="", tags="bg")
            canvas.create_arc(0, h - 2*r, 2*r, h, start=180, extent=90, fill=fill_color, outline="", tags="bg")
            canvas.create_arc(w - 2*r, h - 2*r, w, h, start=270, extent=90, fill=fill_color, outline="", tags="bg")
            canvas.create_rectangle(r, 0, w - r, h, fill=fill_color, outline="", tags="bg")
            canvas.create_rectangle(0, r, w, h - r, fill=fill_color, outline="", tags="bg")
            
            # Draw border
            canvas.create_arc(0, 0, 2*r, 2*r, start=90, extent=90, outline=border_color, style="arc", tags="bg")
            canvas.create_arc(w - 2*r - 1, 0, w - 1, 2*r, start=0, extent=90, outline=border_color, style="arc", tags="bg")
            canvas.create_arc(0, h - 2*r - 1, 2*r, h - 1, start=180, extent=90, outline=border_color, style="arc", tags="bg")
            canvas.create_arc(w - 2*r - 1, h - 2*r - 1, w - 1, h - 1, start=270, extent=90, outline=border_color, style="arc", tags="bg")
            canvas.create_line(r, 0, w - r, 0, fill=border_color, tags="bg")
            canvas.create_line(r, h - 1, w - r, h - 1, fill=border_color, tags="bg")
            canvas.create_line(0, r, 0, h - r, fill=border_color, tags="bg")
            canvas.create_line(w - 1, r, w - 1, h - r, fill=border_color, tags="bg")
            
            canvas.tag_lower("bg")
            
        canvas.bind("<Configure>", draw_bg)
        return canvas

    def _create_rounded_entry_border(self, parent, bg_color=CARD, fill_color=ENTRY_BG, border_color=CARD_BORDER):
        canvas = tk.Canvas(parent, bg=bg_color, highlightthickness=0, height=28)
        canvas.focus_color = border_color
        
        def draw_bg(event=None):
            canvas.delete("bg")
            w = canvas.winfo_width()
            h = canvas.winfo_height()
            r = 5 # corner radius for entry
            curr_border = getattr(canvas, "focus_color", border_color)
            
            # Fill
            canvas.create_arc(0, 0, 2*r, 2*r, start=90, extent=90, fill=fill_color, outline="", tags="bg")
            canvas.create_arc(w - 2*r, 0, w, 2*r, start=0, extent=90, fill=fill_color, outline="", tags="bg")
            canvas.create_arc(0, h - 2*r, 2*r, h, start=180, extent=90, fill=fill_color, outline="", tags="bg")
            canvas.create_arc(w - 2*r, h - 2*r, w, h, start=270, extent=90, fill=fill_color, outline="", tags="bg")
            canvas.create_rectangle(r, 0, w - r, h, fill=fill_color, outline="", tags="bg")
            canvas.create_rectangle(0, r, w, h - r, fill=fill_color, outline="", tags="bg")
            
            # Border
            canvas.create_arc(0, 0, 2*r, 2*r, start=90, extent=90, outline=curr_border, style="arc", tags="bg")
            canvas.create_arc(w - 2*r - 1, 0, w - 1, 2*r, start=0, extent=90, outline=curr_border, style="arc", tags="bg")
            canvas.create_arc(0, h - 2*r - 1, 2*r, h - 1, start=180, outline=curr_border, style="arc", tags="bg")
            canvas.create_arc(w - 2*r - 1, h - 2*r - 1, w - 1, h - 1, start=270, extent=90, outline=curr_border, style="arc", tags="bg")
            canvas.create_line(r, 0, w - r, 0, fill=curr_border, tags="bg")
            canvas.create_line(r, h - 1, w - r, h - 1, fill=curr_border, tags="bg")
            canvas.create_line(0, r, 0, h - r, fill=curr_border, tags="bg")
            canvas.create_line(w - 1, r, w - 1, h - r, fill=curr_border, tags="bg")
            
            canvas.tag_lower("bg")
            
        canvas.bind("<Configure>", draw_bg)
        return canvas

    # ---- Xây khung giao diện ----
    def _card(self, parent, title):
        canvas = self._create_rounded_card(parent, BG, CARD, CARD_BORDER)
        tk.Label(canvas, text=title, font=FONT_TITLE, bg=CARD, fg="#60a5fa").pack(anchor="w", padx=12, pady=(10, 4))
        return canvas

    def _entry_row(self, parent, var, browse_cmd, browse_text="Chọn..."):
        row = tk.Frame(parent, bg=CARD)
        row.pack(fill="x", padx=12, pady=(0, 6))
        
        # Rounded border canvas instead of square Frame
        entry_border = self._create_rounded_entry_border(row, bg_color=CARD, fill_color=ENTRY_BG, border_color=CARD_BORDER)
        entry_border.pack(side="left", fill="x", expand=True, padx=(0, 6))
        
        entry = tk.Entry(entry_border, textvariable=var, bg=ENTRY_BG, fg=TEXT, insertbackground=TEXT,
                          relief="flat", font=FONT, bd=0)
        entry.pack(fill="x", expand=True, ipady=3, padx=8, pady=3)
        
        def on_focus_in(e):
            entry_border.focus_color = ACCENT
            entry_border.event_generate("<Configure>")
        def on_focus_out(e):
            entry_border.focus_color = CARD_BORDER
            entry_border.event_generate("<Configure>")
            
        entry.bind("<FocusIn>", on_focus_in)
        entry.bind("<FocusOut>", on_focus_out)
        
        btn = tk.Button(row, text=browse_text, command=browse_cmd, bg=ACCENT, fg="white",
                        activebackground=ACCENT_HOVER, activeforeground="white",
                        font=FONT_BOLD, relief="flat", cursor="hand2", padx=14, pady=2)
        btn.pack(side="left")
        self._bind_hover(btn, ACCENT, ACCENT_HOVER)
        return entry

    def _build_ui(self):
        outer = tk.Frame(self.root, bg=BG)
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(outer, bg=BG, highlightthickness=0)
        vsb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview, style="TScrollbar")
        sf = tk.Frame(canvas, bg=BG)
        
        sf_id = canvas.create_window((0, 0), window=sf, anchor="nw")
        sf.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(sf_id, width=e.width))
        
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # Premium Title Banner
        header_frame = tk.Frame(sf, bg=BG)
        header_frame.pack(fill="x", padx=14, pady=(20, 10))
        indicator = tk.Canvas(header_frame, width=5, height=24, bg=ACCENT, highlightthickness=0)
        indicator.pack(side="left", padx=(4, 10))
        title_lbl = tk.Label(header_frame, text="BÁO CÁO ĐIỀU CHUYỂN HÀNG HOÁ", font=FONT_BIG_TITLE, bg=BG, fg=TEXT)
        title_lbl.pack(side="left")
        subtitle_lbl = tk.Label(header_frame, text="  v2.0 Premium Edition", font=("Segoe UI", 9, "italic"), bg=BG, fg=LABEL)
        subtitle_lbl.pack(side="left", anchor="s", pady=(0, 2))

        # Context-aware mouse wheel scrolling
        def _on_mousewheel(event):
            if hasattr(self, "_list_canvas") and str(self._list_canvas) in str(event.widget):
                self._list_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            else:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        self.root.bind_all("<MouseWheel>", _on_mousewheel)

        # 1) + 2) CSV & Kho dữ liệu Parquet — 2 cột song song (thiết kế tinh gọn)
        paths_row = tk.Frame(sf, bg=BG)
        paths_row.pack(fill="x", padx=14, pady=4)
        paths_row.grid_columnconfigure(0, weight=1, uniform="path")
        paths_row.grid_columnconfigure(1, weight=1, uniform="path")

        c1 = self._create_rounded_card(paths_row, BG, CARD, CARD_BORDER)
        c1.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        tk.Label(c1, text="📂  File CSV kế hoạch điều chuyển", font=FONT_TITLE, bg=CARD, fg="#60a5fa").pack(anchor="w", padx=12, pady=(8, 2))
        tk.Label(c1, text="Cột bắt buộc: Combined PK", font=("Segoe UI", 8), bg=CARD, fg=LABEL).pack(anchor="w", padx=12, pady=(0, 4))
        self.csv_var = tk.StringVar()
        self._entry_row(c1, self.csv_var, self._browse_csv)

        c2 = self._create_rounded_card(paths_row, BG, CARD, CARD_BORDER)
        c2.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        tk.Label(c2, text="🗄️  Kho dữ liệu (Parquet)", font=FONT_TITLE, bg=CARD, fg="#60a5fa").pack(anchor="w", padx=12, pady=(8, 2))
        tk.Label(c2, text=" ", font=("Segoe UI", 8), bg=CARD, fg=LABEL).pack(anchor="w", padx=12, pady=(0, 4))
        self.db_var = tk.StringVar(value=paths.DATA_ROOT_DEFAULT)
        self._entry_row(c2, self.db_var, self._browse_db)
        
        reload_btn = tk.Button(c2, text="🔄  Tải lại danh sách cửa hàng", command=self._load_stores_async,
                               bg=BTN_SECONDARY, fg=TEXT, activebackground=BTN_SECONDARY_HOVER, activeforeground=TEXT,
                               font=("Segoe UI", 8, "bold"), relief="flat", cursor="hand2", padx=12, pady=2)
        reload_btn.pack(anchor="w", padx=12, pady=(0, 6))
        self._bind_hover(reload_btn, BTN_SECONDARY, BTN_SECONDARY_HOVER)

        # 3) Thư mục xuất — cùng hàng 2 cột với Lần điều chuyển (thiết kế tinh gọn)
        row2 = tk.Frame(sf, bg=BG)
        row2.pack(fill="x", padx=14, pady=4)
        row2.grid_columnconfigure(0, weight=1, uniform="row2")
        row2.grid_columnconfigure(1, weight=1, uniform="row2")

        c3 = self._create_rounded_card(row2, BG, CARD, CARD_BORDER)
        c3.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        tk.Label(c3, text="💾  Thư mục lưu file kết quả", font=FONT_TITLE, bg=CARD, fg="#60a5fa").pack(anchor="w", padx=12, pady=(8, 2))
        self.out_var = tk.StringVar(value=paths.output_dir_default())
        self._entry_row(c3, self.out_var, self._browse_out)
        tk.Label(c3, text="(Để trống: lưu cùng thư mục với file CSV)", font=("Segoe UI", 8), bg=CARD, fg=LABEL).pack(anchor="w", padx=12, pady=(0, 6))

        c4 = self._create_rounded_card(row2, BG, CARD, CARD_BORDER)
        c4.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        tk.Label(c4, text="🔁  Lần điều chuyển", font=FONT_TITLE, bg=CARD, fg="#60a5fa").pack(anchor="w", padx=12, pady=(8, 2))
        tk.Label(c4, text="(Bỏ qua nếu CSV đã có cột 'Dot Chuyen')", font=("Segoe UI", 8), bg=CARD, fg=LABEL).pack(anchor="w", padx=12, pady=(0, 4))
        
        self.round_combo = ttk.Combobox(c4, values=[
            "Tự động — suy theo mốc KHPP",
            "Lần 1 — chuẩn bị và phân bổ",
            "Lần 2 — thu hẹp mạng lưới bán",
            "Lần 3 — gom điểm theo xu hướng"
        ], font=FONT, state="readonly", style="TCombobox")
        self.round_combo.set("Tự động — suy theo mốc KHPP")
        self.round_combo.pack(fill="x", padx=12, pady=(0, 10))

        # 5) Phạm vi cửa hàng (chiếm toàn bộ bề ngang để hiển thị rộng rãi, không bị nén ngang)
        c5 = self._create_rounded_card(sf, BG, CARD, CARD_BORDER)
        c5.pack(fill="x", padx=14, pady=6)
        tk.Label(c5, text="🏪  Phạm vi cửa hàng điều chuyển", font=FONT_TITLE, bg=CARD, fg="#60a5fa").pack(anchor="w", padx=12, pady=(10, 4))
        
        self.include_hanoi_var = tk.BooleanVar(value=True)
        cb_hanoi = tk.Checkbutton(c5, text="Bao gồm cửa hàng khu vực Hà Nội", variable=self.include_hanoi_var,
                                  command=self._refresh_store_checklist, bg=CARD, fg=TEXT, selectcolor=ENTRY_BG,
                                  activebackground=CARD, activeforeground=TEXT, font=FONT, cursor="hand2")
        cb_hanoi.pack(anchor="w", padx=12, pady=(0, 6))
        
        tk.Label(c5, text="Bỏ chọn (tick) cửa hàng muốn LOẠI khỏi đợt này — mỗi cột là 1 Vùng:",
                 font=FONT, bg=CARD, fg=TEXT).pack(anchor="w", padx=12, pady=(10, 6))

        list_frame = tk.Frame(c5, bg=CARD)
        list_frame.pack(fill="both", expand=True, padx=12, pady=(4, 6))
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        self._list_canvas = tk.Canvas(list_frame, bg=ENTRY_BG, height=240, highlightthickness=0)
        vsb2 = ttk.Scrollbar(list_frame, orient="vertical", command=self._list_canvas.yview, style="TScrollbar")
        self._store_inner = tk.Frame(self._list_canvas, bg=ENTRY_BG)
        self._store_inner.bind("<Configure>", lambda e: self._list_canvas.configure(scrollregion=self._list_canvas.bbox("all")))
        self._list_canvas.create_window((0, 0), window=self._store_inner, anchor="nw")
        self._list_canvas.configure(yscrollcommand=vsb2.set)
        self._list_canvas.grid(row=0, column=0, sticky="nsew")
        vsb2.grid(row=0, column=1, sticky="ns")

        self.store_status_label = tk.Label(c5, text="⏳ Đang tải danh sách cửa hàng...", font=("Segoe UI", 8), bg=CARD, fg=LABEL)
        self.store_status_label.pack(anchor="w", padx=12, pady=(2, 4))

        khong_rut_row = tk.Frame(c5, bg=CARD)
        khong_rut_row.pack(fill="x", padx=12, pady=(0, 8))
        self.khong_rut_btn = tk.Button(khong_rut_row, text=self._khong_rut_btn_text(), font=("Segoe UI", 8, "bold"),
                                       command=self._open_khong_rut_dialog, bg=BTN_SECONDARY, fg=TEXT,
                                       activebackground=BTN_SECONDARY_HOVER, activeforeground=TEXT,
                                       relief="flat", cursor="hand2", padx=8, pady=3)
        self.khong_rut_btn.pack(side="left")
        self._bind_hover(self.khong_rut_btn, BTN_SECONDARY, BTN_SECONDARY_HOVER)
        tk.Label(khong_rut_row, text="CH mới / CH không tham gia rút: vẫn được NHẬN, không bị XUẤT",
                 font=("Segoe UI", 8), bg=CARD, fg=LABEL).pack(side="left", padx=8)

        # 6) Hàng dưới cùng: chia làm 2 cột cho Toạ độ địa lý (trái) và Chạy báo cáo (phải) (tối giản diện tích)
        bottom_row = tk.Frame(sf, bg=BG)
        bottom_row.pack(fill="x", padx=14, pady=4)
        bottom_row.grid_columnconfigure(0, weight=1, uniform="bottom")
        bottom_row.grid_columnconfigure(1, weight=1, uniform="bottom")

        c6 = self._create_rounded_card(bottom_row, BG, CARD, CARD_BORDER)
        c6.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        tk.Label(c6, text="🗺️  Toạ độ địa lý", font=FONT_TITLE, bg=CARD, fg="#60a5fa").pack(anchor="w", padx=12, pady=(8, 2))
        self.do_geocode_var = tk.BooleanVar(value=True)
        cb_geo = tk.Checkbutton(c6, text="Tự động geocode cửa hàng chưa có toạ độ\n(nếu chưa chạy Generate_Store_Coordinates.py)",
                                variable=self.do_geocode_var, bg=CARD, fg=TEXT, selectcolor=ENTRY_BG,
                                activebackground=CARD, activeforeground=TEXT, font=FONT, justify="left",
                                anchor="w", cursor="hand2")
        cb_geo.pack(anchor="w", padx=12, pady=(0, 10))

        run_card = self._create_rounded_card(bottom_row, BG, CARD, CARD_BORDER)
        run_card.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        tk.Label(run_card, text="▶  Chạy báo cáo", font=FONT_TITLE, bg=CARD, fg="#60a5fa").pack(anchor="w", padx=12, pady=(8, 2))
        
        # Frame chứa 2 nút nằm ngang bên dưới
        btn_frame = tk.Frame(run_card, bg=CARD)
        btn_frame.pack(fill="x", padx=12, pady=(0, 4))
        
        self.run_btn = tk.Button(btn_frame, text="▶  Chạy Báo Cáo", command=self._on_run, bg=GREEN, fg="white",
                                  activebackground=GREEN_HOVER, activeforeground="white",
                                  disabledforeground="#64748b",
                                  font=("Segoe UI", 11, "bold"), relief="flat", cursor="hand2", pady=5)
        self.run_btn.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self._bind_hover(self.run_btn, GREEN, GREEN_HOVER)
        
        self.cancel_btn = tk.Button(btn_frame, text="⏹  Huỷ", command=self._on_cancel, bg=RED, fg="white",
                                     activebackground=RED_HOVER, activeforeground="white",
                                     disabledforeground="#64748b",
                                     font=("Segoe UI", 11, "bold"), relief="flat", cursor="hand2", pady=5,
                                     state="disabled")
        self.cancel_btn.pack(side="left", fill="x", expand=True, padx=(4, 0))
        self._bind_hover(self.cancel_btn, RED, RED_HOVER)
        
        self.progress = ttk.Progressbar(run_card, mode="indeterminate", style="Horizontal.TProgressbar")
        self.progress.pack(fill="x", padx=12, pady=(0, 14))

        # Khung log tiến trình
        log_card = self._create_rounded_card(sf, BG, CARD, CARD_BORDER)
        log_card.pack(fill="both", padx=14, pady=(0, 10))
        tk.Label(log_card, text="📋  Tiến trình chạy", font=FONT_TITLE, bg=CARD, fg="#60a5fa").pack(anchor="w", padx=12, pady=(10, 4))
        self.log_box = scrolledtext.ScrolledText(log_card, height=14, bg=ENTRY_BG, fg=TEXT, insertbackground=TEXT,
                                                   relief="flat", font=("Consolas", 9), state="disabled", wrap="word")
        self.log_box.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        # Khung kết quả (ẩn ban đầu)
        self.result_frame = self._create_rounded_card(sf, BG, "#062f21", GREEN)
        self.result_label = tk.Label(self.result_frame, text="", font=FONT_BOLD, bg="#062f21", fg="#a7f3d0",
                                      justify="left", wraplength=680)
        self.result_label.pack(anchor="w", padx=12, pady=(12, 6))
        btn_row = tk.Frame(self.result_frame, bg="#062f21")
        btn_row.pack(anchor="w", padx=12, pady=(0, 12))
        
        btn_open = tk.Button(btn_row, text="📂  Mở file kết quả", command=self._open_result_file, bg=GREEN, fg="white",
                             activebackground=GREEN_HOVER, activeforeground="white",
                             font=FONT_BOLD, relief="flat", cursor="hand2", padx=14, pady=6)
        btn_open.pack(side="left", padx=(0, 8))
        self._bind_hover(btn_open, GREEN, GREEN_HOVER)
        
        btn_dir = tk.Button(btn_row, text="📁  Mở thư mục chứa file", command=self._open_result_folder, bg="#1e293b", fg=TEXT,
                            activebackground="#334155", activeforeground=TEXT,
                            font=FONT_BOLD, relief="flat", cursor="hand2", padx=14, pady=6)
        btn_dir.pack(side="left")
        self._bind_hover(btn_dir, "#1e293b", "#334155")

    # ---- Chọn file/thư mục ----
    def _browse_csv(self):
        path = filedialog.askopenfilename(title="Chọn file CSV kế hoạch điều chuyển",
                                           filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if path:
            self.csv_var.set(path)
            if not self.out_var.get():
                self.out_var.set(os.path.dirname(path))

    def _browse_db(self):
        path = filedialog.askdirectory(title="Chọn thư mục kho dữ liệu (00.Data_AnPhuoc_Group — chứa 02.Master, 03.Data_Parquest)")
        if path:
            self.db_var.set(path)

    def _browse_out(self):
        path = filedialog.askdirectory(title="Chọn thư mục lưu file kết quả")
        if path:
            self.out_var.set(path)

    # ---- Nạp danh sách cửa hàng (chạy nền, không đứng giao diện) ----
    def _load_stores_async(self):
        self.store_status_label.config(text="⏳ Đang tải danh sách cửa hàng...")

        def _load():
            try:
                loader = TransferDataLoader(self.db_var.get())
                try:
                    df = loader.load_scope_stores()
                finally:
                    loader.close()
                self._store_list = df[["Store_name", "Region", "Loai_CH"]].values.tolist()
                self.root.after(0, self._refresh_store_checklist)
            except Exception as e:
                msg = str(e)
                self.root.after(0, lambda: self.store_status_label.config(text=f"⚠ Lỗi tải DS cửa hàng: {msg}"))
        threading.Thread(target=_load, daemon=True).start()

    def _refresh_store_checklist(self):
        for w in self._store_inner.winfo_children():
            w.destroy()
        self._store_vars = {}
        include_hanoi = self.include_hanoi_var.get()

        by_region = {}
        for name, region, loai in self._store_list:
            if not include_hanoi and region == "Hà Nội":
                continue
            by_region.setdefault(region, []).append((name, loai))

        count = 0
        first = True
        for region in sorted(by_region.keys()):
            if not first:
                # Vertical divider line
                div = tk.Frame(self._store_inner, bg=CARD_BORDER, width=1)
                div.pack(side="left", fill="y", padx=0)
            first = False
            
            # Region container holding header + toggle_row + columns_frame
            region_container = tk.Frame(self._store_inner, bg=ENTRY_BG)
            region_container.pack(side="left", fill="y", anchor="n", padx=2)

            header_bg = "#17253d"
            header = tk.Frame(region_container, bg=header_bg)
            header.pack(fill="x", ipady=2)
            tk.Label(header, text=f" {region} ", font=("Segoe UI", 9, "bold"),
                     bg=header_bg, fg=TEXT).pack(side="left", padx=(6, 2), pady=4)
            tk.Label(header, text=f"({len(by_region[region])})", font=("Segoe UI", 8, "bold"),
                     bg=header_bg, fg=ACCENT).pack(side="left", pady=4)

            toggle_row = tk.Frame(region_container, bg=ENTRY_BG)
            toggle_row.pack(fill="x", pady=(4, 6))
            
            btn_all = tk.Button(toggle_row, text="Chọn tất cả", font=("Segoe UI", 7, "bold"),
                                command=lambda r=region: self._toggle_region(r, True),
                                bg=BTN_SECONDARY, fg=TEXT, activebackground=BTN_SECONDARY_HOVER, activeforeground=TEXT,
                                relief="flat", cursor="hand2", padx=6, pady=2)
            btn_all.pack(side="left", padx=(6, 2))
            self._bind_hover(btn_all, BTN_SECONDARY, BTN_SECONDARY_HOVER)
            
            btn_none = tk.Button(toggle_row, text="Bỏ chọn", font=("Segoe UI", 7, "bold"),
                                 command=lambda r=region: self._toggle_region(r, False),
                                 bg=BTN_SECONDARY, fg=TEXT, activebackground=BTN_SECONDARY_HOVER, activeforeground=TEXT,
                                 relief="flat", cursor="hand2", padx=6, pady=2)
            btn_none.pack(side="left", padx=2)
            self._bind_hover(btn_none, BTN_SECONDARY, BTN_SECONDARY_HOVER)

            # Sub-frame for columns to arrange checkbuttons
            columns_frame = tk.Frame(region_container, bg=ENTRY_BG)
            columns_frame.pack(fill="both", expand=True)

            stores = sorted(by_region[region])
            # Split into 2 columns ONLY for TP HCM (or regions containing HCM/Hồ Chí Minh)
            should_split = "HCM" in region.upper() or "HỒ CHÍ MINH" in region.upper()
            
            if should_split:
                col1 = tk.Frame(columns_frame, bg=ENTRY_BG)
                col1.pack(side="left", fill="y", anchor="n", padx=(0, 4))
                col2 = tk.Frame(columns_frame, bg=ENTRY_BG)
                col2.pack(side="left", fill="y", anchor="n", padx=(4, 0))
                
                mid = (len(stores) + 1) // 2
                stores_col1 = stores[:mid]
                stores_col2 = stores[mid:]
            else:
                col1 = tk.Frame(columns_frame, bg=ENTRY_BG)
                col1.pack(side="left", fill="y", anchor="n")
                stores_col1 = stores
                stores_col2 = []

            for name, loai in stores_col1:
                var = tk.BooleanVar(value=True)
                cb = tk.Checkbutton(col1, text=f"{name}  [{loai}]", variable=var, bg=ENTRY_BG, fg=TEXT,
                                    selectcolor=CARD, activebackground=ENTRY_BG, activeforeground=TEXT,
                                    font=("Segoe UI", 8), anchor="w", cursor="hand2")
                cb.pack(anchor="w", padx=6, pady=1)
                self._store_vars[name] = (var, region)
                count += 1

            for name, loai in stores_col2:
                var = tk.BooleanVar(value=True)
                cb = tk.Checkbutton(col2, text=f"{name}  [{loai}]", variable=var, bg=ENTRY_BG, fg=TEXT,
                                    selectcolor=CARD, activebackground=ENTRY_BG, activeforeground=TEXT,
                                    font=("Segoe UI", 8), anchor="w", cursor="hand2")
                cb.pack(anchor="w", padx=6, pady=1)
                self._store_vars[name] = (var, region)
                count += 1

        self._store_inner.update_idletasks()
        self._list_canvas.configure(scrollregion=self._list_canvas.bbox("all"))
        self._list_canvas.xview_moveto(0)
        self._list_canvas.yview_moveto(0)
        self.store_status_label.config(text=f"✅ {count} cửa hàng trong phạm vi, chia theo {len(by_region)} Vùng (bỏ tick = loại khỏi đợt)")

    # ---- CH không rút (CH mới / không tham gia rút) ----
    @staticmethod
    def _load_khong_rut():
        try:
            with open(paths.KHONG_RUT_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except (OSError, ValueError):
            return set()

    def _save_khong_rut(self):
        os.makedirs(os.path.dirname(paths.KHONG_RUT_FILE), exist_ok=True)
        with open(paths.KHONG_RUT_FILE, "w", encoding="utf-8") as f:
            json.dump(sorted(self._khong_rut), f, ensure_ascii=False, indent=2)

    def _khong_rut_btn_text(self):
        return f"🛡  CH không rút ({len(self._khong_rut)})"

    def _open_khong_rut_dialog(self):
        if not self._store_list:
            messagebox.showinfo("CH không rút", "Danh sách cửa hàng chưa tải xong — vui lòng đợi.")
            return
        win = tk.Toplevel(self.root)
        win.title("Chọn CH không rút (CH mới / không tham gia rút)")
        win.geometry("520x620")
        win.configure(bg=CARD)
        win.transient(self.root)
        win.grab_set()

        tk.Label(win, text="Tick các CH chỉ được NHẬN, không bị rút hàng trong đợt này:",
                 font=FONT, bg=CARD, fg=TEXT).pack(anchor="w", padx=12, pady=(10, 4))
        search_var = tk.StringVar()
        tk.Entry(win, textvariable=search_var, font=FONT, bg=ENTRY_BG, fg=TEXT, insertbackground=TEXT,
                 relief="flat").pack(fill="x", padx=12, pady=(0, 6), ipady=3)

        frame = tk.Frame(win, bg=ENTRY_BG)
        frame.pack(fill="both", expand=True, padx=12, pady=4)
        canvas = tk.Canvas(frame, bg=ENTRY_BG, highlightthickness=0)
        vsb = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview, style="TScrollbar")
        inner = tk.Frame(canvas, bg=ENTRY_BG)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        vars_ = {name: tk.BooleanVar(value=name in self._khong_rut) for name, _r, _l in self._store_list}
        rows = []
        for name, region, loai in sorted(self._store_list, key=lambda t: (t[1], t[0])):
            cb = tk.Checkbutton(inner, text=f"{name}  [{loai}]  —  {region}", variable=vars_[name], bg=ENTRY_BG,
                                fg=TEXT, selectcolor=CARD, activebackground=ENTRY_BG, activeforeground=TEXT,
                                font=("Segoe UI", 8), anchor="w", cursor="hand2")
            rows.append((name, region, cb))

        def _render(*_):
            kw = search_var.get().strip().lower()
            for _n, _r, cb in rows:
                cb.pack_forget()
            for n, r, cb in rows:
                if not kw or kw in n.lower() or kw in str(r).lower():
                    cb.pack(anchor="w", padx=6, pady=1)
        search_var.trace_add("write", _render)
        _render()

        def _ok():
            self._khong_rut = {n for n, v in vars_.items() if v.get()}
            self._save_khong_rut()
            self.khong_rut_btn.config(text=self._khong_rut_btn_text())
            win.destroy()

        btns = tk.Frame(win, bg=CARD)
        btns.pack(fill="x", padx=12, pady=10)
        tk.Button(btns, text="Lưu", command=_ok, bg=GREEN, fg="white", activebackground=GREEN_HOVER,
                  relief="flat", cursor="hand2", font=FONT_BOLD, padx=16).pack(side="right")
        tk.Button(btns, text="Bỏ chọn tất cả", command=lambda: [v.set(False) for v in vars_.values()],
                  bg=BTN_SECONDARY, fg=TEXT, relief="flat", cursor="hand2", font=FONT, padx=10).pack(side="left")

    def _toggle_region(self, region, value):
        for _name, (var, r) in self._store_vars.items():
            if r == region:
                var.set(value)

    # ---- Log ----
    def _log(self, msg):
        self._log_queue.put(msg)

    def _poll_queue(self):
        try:
            while True:
                item = self._log_queue.get_nowait()
                if isinstance(item, tuple) and item and item[0] == "__DONE__":
                    self._on_worker_done(item[1], item[2])
                else:
                    self.log_box.configure(state="normal")
                    self.log_box.insert("end", str(item) + "\n")
                    self.log_box.see("end")
                    self.log_box.configure(state="disabled")
        except queue.Empty:
            pass
        self.root.after(150, self._poll_queue)

    # ---- Chạy ----
    def _on_run(self):
        if self._worker is not None and self._worker.is_alive():
            return
        csv_path = self.csv_var.get().strip()
        if not csv_path or not os.path.exists(csv_path):
            messagebox.showerror("Lỗi", "Vui lòng chọn file CSV hợp lệ.")
            return
        data_root = self.db_var.get().strip()
        if not data_root or not os.path.isdir(os.path.join(data_root, "03.Data_Parquest")):
            messagebox.showerror("Lỗi", "Thư mục kho dữ liệu không đúng (phải chứa 02.Master và 03.Data_Parquest) — vui lòng chọn lại.")
            return
        if not self._store_vars:
            messagebox.showerror("Lỗi", "Danh sách cửa hàng chưa tải xong — vui lòng đợi rồi thử lại "
                                         "(hoặc bấm '🔄 Tải lại danh sách cửa hàng').")
            return
        out_dir = self.out_var.get().strip() or paths.output_dir_default()
        excluded_stores = [name for name, (var, _r) in self._store_vars.items() if not var.get()]

        round_display_map = {
            "Tự động — suy theo mốc KHPP": "AUTO",
            "Lần 1 — chuẩn bị và phân bổ": "Lan1",
            "Lần 2 — thu hẹp mạng lưới bán": "Lan2",
            "Lần 3 — gom điểm theo xu hướng": "Lan3"
        }
        selected_display = self.round_combo.get()
        round_choice = round_display_map.get(selected_display, "AUTO")

        params = dict(
            csv_path=csv_path, data_root=data_root, out_dir=out_dir,
            round_choice=round_choice, selected_regions=self._active_regions(),
            excluded_stores=excluded_stores, do_geocode=self.do_geocode_var.get(),
            no_export_stores=sorted(self._khong_rut),
        )

        self.result_frame.pack_forget()
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")
        self.run_btn.config(state="disabled", text="⏳  Đang chạy...", bg="#1e293b")
        self.cancel_btn.config(state="normal", text="⏹  Huỷ", bg=RED)
        self.progress.start(12)

        self._cancel_event = threading.Event()

        def _worker():
            try:
                result = TransferReportRunner(params, self._log, self._cancel_event).run()
                self._log_queue.put(("__DONE__", "ok", result))
            except CancelledError as e:
                self._log_queue.put(("__DONE__", "cancelled", str(e)))
            except Exception:
                err = traceback.format_exc()
                self._log_queue.put(("__DONE__", "error", err))

        self._worker = threading.Thread(target=_worker, daemon=True)
        self._worker.start()

    def _on_cancel(self):
        if self._cancel_event is not None:
            self._cancel_event.set()
            self.cancel_btn.config(state="disabled", text="⏳  Đang huỷ...", bg="#1e293b")
            self._log("⏹ Đã yêu cầu huỷ — chờ bước hiện tại xử lý xong...")

    def _active_regions(self):
        regions = sorted(set(r for _n, (_v, r) in self._store_vars.items()))
        return regions

    def _on_worker_done(self, status, payload):
        self.progress.stop()
        self.run_btn.config(state="normal", text="▶  Chạy Báo Cáo", bg=GREEN)
        self.cancel_btn.config(state="disabled", text="⏹  Huỷ", bg="#1e293b")
        if status == "ok":
            self._result = payload
            self.result_label.config(
                text=f"✅  Đã tạo báo cáo thành công!\n{payload['out_path']}\n"
                     f"Số mã xử lý: {payload['n_sku']}   |   Số dòng lệnh chi tiết: {payload['n_lenh']}")
            self.result_frame.pack(fill="x", padx=14, pady=(0, 14))
        elif status == "cancelled":
            self._log("⏹ Đã huỷ theo yêu cầu — chưa tạo file kết quả.")
        else:
            self._log(f"❌ LỖI:\n{payload}")
            messagebox.showerror("Lỗi khi chạy báo cáo", payload[-1500:])

    def _open_result_file(self):
        if self._result:
            self._open_path(self._result["out_path"])

    def _open_result_folder(self):
        if self._result:
            self._open_path(os.path.dirname(self._result["out_path"]))

    @staticmethod
    def _open_path(path):
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)  # noqa: S606 — mở file/thư mục theo yêu cầu người dùng
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không mở được:\n{path}\n\n{e}")

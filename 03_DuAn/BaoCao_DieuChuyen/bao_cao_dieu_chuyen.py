# -*- coding: utf-8 -*-
"""
BÁO CÁO ĐIỀU CHUYỂN HÀNG HÓA — chạy: python main.py
Yêu cầu: pip install duckdb pandas openpyxl numpy

Giao diện: 1 cửa sổ duy nhất — chọn file/tham số ngay trên đó, bấm "Chạy Báo Cáo",
xem tiến trình chạy trực tiếp trong khung log, xong thì bấm nút để mở file kết quả.

Xem README.md để biết chi tiết quy trình, các điểm đã đơn giản hoá, và cách chạy
generate_geo.py trước để có toạ độ cửa hàng chính xác hơn.
"""
import os
import sys
import json
import queue
import traceback
import threading
import datetime as dt
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, scrolledtext

import pandas as pd

import dc_config as cfg
import dc_data as data
import dc_pipeline as pipeline
import dc_allocate as allocate
import dc_output as outp
import dc_writer as writer
import dc_geo as geo_mod
import dc_compute as comp
import dc_display as disp

DUCKDB_PATH_DEFAULT = r"D:\AnPhuocGroup\AnPhuoc_Data\00.Data_AnPhuoc_Group\04.Data_Db\01.Data_DuckDB\Database_AP.duckdb"
HERE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(HERE, "hieu_suat_ky_history.json")
GEO_CSV = os.path.join(HERE, "ViTri_DiaLy_CuaHang.csv")


class CancelledError(Exception):
    """Người dùng bấm Huỷ giữa chừng."""
    pass


def _check_cancel(cancel_event):
    if cancel_event is not None and cancel_event.is_set():
        raise CancelledError("Đã huỷ theo yêu cầu người dùng.")


# ── Bảng màu giao diện (Modern Dark Mode) ──
BG = "#090d16"           # Darker background for depth
CARD = "#131a26"         # Card background
CARD_BORDER = "#223047"  # Slate border
TEXT = "#f1f5f9"         # Muted white text
LABEL = "#94a3b8"        # Gray text
ACCENT = "#3b82f6"       # Blue-500
ACCENT_HOVER = "#2563eb" # Blue-600
GREEN = "#10b981"        # Emerald-500
GREEN_HOVER = "#059669"  # Emerald-600
RED = "#f43f5e"          # Rose-500
RED_HOVER = "#e11d48"    # Rose-600
ENTRY_BG = "#0a0f1d"     # Inner dark entry fields
BTN_SECONDARY = "#1e293b"# Slate-800
BTN_SECONDARY_HOVER = "#334155" # Slate-700

FONT = ("Segoe UI", 9)
FONT_BOLD = ("Segoe UI", 9, "bold")
FONT_TITLE = ("Segoe UI", 10, "bold")
FONT_BIG_TITLE = ("Segoe UI", 13, "bold")



# ---------------------------------------------------------------- State (Lần 3 — Xu hướng)
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def update_state_with_hieu_suat_ky(state, df_store):
    for _, r in df_store.iterrows():
        key = f"{r['Combined_PK']}|{r['Store_name']}|{r['Lan_dieu_chuyen']}"
        state[key] = {"hieu_suat_ky": r["Hieu_suat_ky"], "khi_luu": f"{cfg.CURRENT_YEAR}-{cfg.CURRENT_MONTH:02d}"}
    return state


# ---------------------------------------------------------------- Lõi xử lý (không đụng UI)
def run_pipeline(params, log, cancel_event=None):
    """params: dict do App thu thập từ giao diện. log(msg): callback ghi tiến trình.
    cancel_event: threading.Event — nếu được set() giữa chừng, hàm dừng lại ở điểm
    kiểm tra gần nhất và ném CancelledError (không huỷ được giữa 1 câu truy vấn SQL
    hay 1 vòng lặp đang chạy, nhưng dừng ngay giữa các bước lớn).
    Trả về dict {out_path, n_sku, n_lenh} khi thành công; ném Exception khi lỗi."""
    csv_path = params["csv_path"]
    db_path = params["db_path"]
    out_dir = params["out_dir"]
    round_choice = params["round_choice"]          # 'AUTO' | 'Lan1' | 'Lan2' | 'Lan3'
    selected_regions = params["selected_regions"]
    excluded_stores = params["excluded_stores"]
    do_geocode = params["do_geocode"]

    df_input = pd.read_csv(csv_path, encoding="utf-8-sig")
    pk_col = next((c for c in df_input.columns if c.strip().lower().replace("_", " ") == "combined pk"), None)
    if pk_col is None:
        raise ValueError("Không tìm thấy cột 'Combined PK' trong file CSV.")
    combined_pks = df_input[pk_col].dropna().astype(str).str.strip().unique().tolist()
    log(f"Đã đọc {len(combined_pks)} mã (Combined PK) cần xử lý.")
    _check_cancel(cancel_event)

    dot_col = next((c for c in df_input.columns if c.strip().lower().replace("_", " ") == "dot chuyen"), None)
    forced_round_map = {}
    if dot_col is not None:
        for _, row in df_input.iterrows():
            pk_val = str(row[pk_col]).strip()
            code = comp.parse_round_label(row[dot_col])
            if pk_val and code:
                forced_round_map[pk_val] = code
        n_parsed = len(forced_round_map)
        log(f"Đã đọc cột 'Dot Chuyen' từ CSV: {n_parsed}/{len(combined_pks)} mã xác định được Lần.")
        if n_parsed < len(combined_pks):
            log(f"  → {len(combined_pks) - n_parsed} mã không xác định được Lần từ CSV, sẽ tự suy theo mốc KHPP.")
    elif round_choice != "AUTO":
        forced_round_map = {pk: round_choice for pk in combined_pks}
        log(f"Lần điều chuyển áp dụng cho toàn bộ file: {round_choice}")
    else:
        log("Lần điều chuyển: Tự động suy theo mốc KHPP của từng mã.")

    log("Đang kết nối Database...")
    con = data.connect(db_path)
    _check_cancel(cancel_event)

    all_stores_df = data.load_scope_stores(con)
    scope_stores_df = data.load_scope_stores(con, selected_regions=selected_regions, excluded_stores=excluded_stores)
    log(f"Phạm vi luân chuyển: {len(scope_stores_df)} cửa hàng.")
    _check_cancel(cancel_event)

    geo_df = data.load_geo_csv(GEO_CSV)
    if geo_df is not None:
        log(f"Đã nạp toạ độ từ ViTri_DiaLy_CuaHang.csv ({len(geo_df)} CH).")
        all_stores_df = all_stores_df.merge(geo_df, on="Store_name", how="left")
    elif do_geocode:
        log("Chưa có ViTri_DiaLy_CuaHang.csv — tự geocode xấp xỉ (khuyến nghị chạy generate_geo.py để chính xác hơn).")
        coords = geo_mod.build_store_coords(all_stores_df)
        all_stores_df["Lat"] = all_stores_df["Store_name"].map(lambda s: coords.get(s, (None, None, None))[0])
        all_stores_df["Lon"] = all_stores_df["Store_name"].map(lambda s: coords.get(s, (None, None, None))[1])
    else:
        all_stores_df["Lat"] = None
        all_stores_df["Lon"] = None
        log("Bỏ qua geocode — cột khoảng cách sẽ để trống.")
    scope_stores_df = scope_stores_df.merge(all_stores_df[["Store_name", "Lat", "Lon"]], on="Store_name", how="left")
    _check_cancel(cancel_event)

    store_meta = scope_stores_df.set_index("Store_name")[["Region", "Warehouse", "Loai_CH", "Lat", "Lon"]].to_dict("index")

    log("Đang tính chỉ số Mục 5 (mã / cửa hàng / size)...")
    hieu_suat_state = load_state()
    df_sku, df_store, df_size, df_store_size, so_ch_pham_vi = pipeline.build_all(
        con, combined_pks, scope_stores_df, forced_round_map, hieu_suat_state)
    if df_sku.empty:
        raise ValueError("Không tìm thấy mã nào khớp trong Database.")
    ma_op_map = df_sku.set_index("Combined_PK").apply(lambda r: (r["Ma_Hang"], r["Operation"]), axis=1).to_dict()
    _check_cancel(cancel_event)

    inv_by_size = data.load_inventory_size(con, combined_pks, scope_stores_df["Store_name"].tolist())

    size_weight_by_sku, size_seq_by_sku = {}, {}
    for pk, g in df_size.groupby("Combined_PK"):
        size_weight_by_sku[pk] = dict(zip(g["Size"], g["Ty_trong"]))
    item_name_map = data.load_sku_master(con, combined_pks).set_index("Combined_PK")["System_item_name"].to_dict()
    size_order_map = data.load_size_order(con, list(set(item_name_map.values())))
    for pk in df_sku["Combined_PK"]:
        sizes = list(size_weight_by_sku.get(pk, {}).keys())
        size_seq_by_sku[pk] = comp.build_size_sequence(sizes, item_name_map.get(pk), size_order_map)
    _check_cancel(cancel_event)

    log("Đang lập lệnh điều chuyển...")
    detail_df = allocate.build_transfer_orders(
        df_sku, df_store, inv_by_size, size_weight_by_sku, size_seq_by_sku,
        so_ch_pham_vi, item_name_map, store_meta)
    detail_df = allocate.apply_batch_minimum(detail_df)
    log(f"Đã sinh {len(detail_df)} dòng lệnh chi tiết.")
    _check_cancel(cancel_event)

    log("Đang tổng hợp các sheet đầu ra...")
    sheet3_int = outp.build_sheet3(df_store_size, detail_df)
    sheet4_int = outp.build_sheet4_with_stock(detail_df, inv_by_size, store_meta)
    sheet5_int = outp.build_sheet5(sheet4_int)
    sheet6_int = outp.build_sheet6(df_store, sheet4_int, scope_stores_df)

    sheet1_disp = disp.to_display_sheet1(df_sku)
    sheet2_disp = disp.to_display_sheet2(df_store, ma_op_map)
    sheet3_disp = disp.to_display_sheet3(sheet3_int, ma_op_map)
    sheet4_disp = disp.to_display_sheet4(sheet4_int, ma_op_map) if not sheet4_int.empty else sheet4_int
    sheet5_disp = disp.to_display_sheet5(sheet5_int, ma_op_map) if not sheet5_int.empty else sheet5_int
    sheet6_disp = disp.to_display_sheet6(sheet6_int)
    if sheet4_disp.empty:
        sheet4_disp = pd.DataFrame(columns=["Combined PK", "Ma Hang", "Operation", "Size", "CH Xuất",
                                             "Region Xuất", "CH Nhận", "Region Nhận", "Loại Lệnh",
                                             "Khoảng Cách (km)", "SL Chuyển", "Giá Bán", "Giá Trị Chuyển",
                                             "Tồn Xuất Trước DC", "Tồn Xuất Sau DC", "Tồn Nhận Trước DC", "Tồn Nhận Sau DC"])
        sheet5_disp = pd.DataFrame(columns=["STT", "CH Xuất", "Combined PK", "Ma Hang", "Size", "SL Chuyển",
                                             "Giá Trị Chuyển", "CH Nhận", "Region Xuất", "Region Nhận",
                                             "Loại Lệnh", "Khoảng Cách (km)"])
    _check_cancel(cancel_event)

    dashboard_kwargs = disp.build_dashboard_kwargs(os.path.basename(csv_path), df_sku, sheet4_disp,
                                                     all_stores_df, selected_regions, df_store_size)

    os.makedirs(out_dir, exist_ok=True)
    out_name = f"BaoCao_DieuChuyen_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    out_path = os.path.join(out_dir, out_name)
    log(f"Đang ghi file Excel: {out_name} ...")
    _check_cancel(cancel_event)
    writer.write_workbook(out_path, dashboard_kwargs, sheet1_disp, sheet2_disp, sheet3_disp,
                           sheet4_disp, sheet5_disp, sheet6_disp)

    state = update_state_with_hieu_suat_ky(hieu_suat_state, df_store)
    save_state(state)

    log("Hoàn tất.")
    return dict(out_path=out_path, n_sku=len(df_sku), n_lenh=len(sheet4_disp))


# ---------------------------------------------------------------- Giao diện
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Báo cáo Điều chuyển Hàng hoá")
        self.root.geometry("920x860")
        self.root.minsize(920, 800)
        self.root.configure(bg=BG)

        self._store_list = []       # [(Store_name, Region, Loai_CH)]
        self._region_vars = {}
        self._store_vars = {}
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

        # 1) + 2) CSV & Database — 2 cột song song (thiết kế tinh gọn)
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
        tk.Label(c2, text="🗄️  Database (DuckDB)", font=FONT_TITLE, bg=CARD, fg="#60a5fa").pack(anchor="w", padx=12, pady=(8, 2))
        tk.Label(c2, text=" ", font=("Segoe UI", 8), bg=CARD, fg=LABEL).pack(anchor="w", padx=12, pady=(0, 4))
        self.db_var = tk.StringVar(value=DUCKDB_PATH_DEFAULT)
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
        self.out_var = tk.StringVar()
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
        self.store_status_label.pack(anchor="w", padx=12, pady=(2, 8))

        # 6) Hàng dưới cùng: chia làm 2 cột cho Toạ độ địa lý (trái) và Chạy báo cáo (phải) (tối giản diện tích)
        bottom_row = tk.Frame(sf, bg=BG)
        bottom_row.pack(fill="x", padx=14, pady=4)
        bottom_row.grid_columnconfigure(0, weight=1, uniform="bottom")
        bottom_row.grid_columnconfigure(1, weight=1, uniform="bottom")

        c6 = self._create_rounded_card(bottom_row, BG, CARD, CARD_BORDER)
        c6.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        tk.Label(c6, text="🗺️  Toạ độ địa lý", font=FONT_TITLE, bg=CARD, fg="#60a5fa").pack(anchor="w", padx=12, pady=(8, 2))
        self.do_geocode_var = tk.BooleanVar(value=True)
        cb_geo = tk.Checkbutton(c6, text="Tự động geocode cửa hàng chưa có toạ độ\n(nếu chưa chạy generate_geo.py)",
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
        path = filedialog.askopenfilename(title="Chọn Database_AP.duckdb",
                                           filetypes=[("DuckDB", "*.duckdb"), ("All files", "*.*")])
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
                con = data.connect(self.db_var.get())
                df = data.load_scope_stores(con)
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
        db_path = self.db_var.get().strip()
        if not db_path or not os.path.exists(db_path):
            messagebox.showerror("Lỗi", "Không tìm thấy file Database (.duckdb) — vui lòng chọn lại.")
            return
        if not self._store_vars:
            messagebox.showerror("Lỗi", "Danh sách cửa hàng chưa tải xong — vui lòng đợi rồi thử lại "
                                         "(hoặc bấm '🔄 Tải lại danh sách cửa hàng').")
            return
        out_dir = self.out_var.get().strip() or os.path.dirname(csv_path)
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
            csv_path=csv_path, db_path=db_path, out_dir=out_dir,
            round_choice=round_choice, selected_regions=self._active_regions(),
            excluded_stores=excluded_stores, do_geocode=self.do_geocode_var.get(),
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
                result = run_pipeline(params, self._log, self._cancel_event)
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


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
    finally:
        # Ép tiến trình thoát ngay khi cửa sổ đóng — tránh treo phiên PowerShell/CMD.
        os._exit(0)

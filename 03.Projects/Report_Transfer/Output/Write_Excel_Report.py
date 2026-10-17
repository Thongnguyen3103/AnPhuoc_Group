# -*- coding: utf-8 -*-
"""ExcelReportWriter — Ghi workbook Excel 7 sheet (style dashboard: navy header, freeze panes...)."""
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter


class ExcelReportWriter:
    """Ghi workbook Excel 7 sheet (style dashboard: navy header, freeze panes...)."""

    # ── Bảng màu (giống DC_BaoCao_AP.py) ──
    COL_HEADER_BG = "1e3a5f"
    COL_HEADER_FG = "FFFFFF"
    COL_SECTION = "0f172a"
    COL_ROW_ALT = "f0f4f8"
    COL_ROW_NORM = "FFFFFF"
    FONT_NAME = "Segoe UI"

    STATUS_COLORS = {"rất chậm": "fecaca", "chậm": "fef3c7", "tốt": "d1fae5", "hết": "dbeafe"}
    HS_COLORS = {"A": "d1fae5", "B": "dbeafe", "C": "fef3c7", "D": "fecaca"}
    TAB_COLORS = ["1e3a5f", "0f5132", "155e75", "7c3aed", "9a3412", "166534"]

    @staticmethod
    def _header_style(ws, row, cols, bg=COL_HEADER_BG, fg=COL_HEADER_FG, bold=True):
        fill = PatternFill("solid", fgColor=bg)
        font = Font(bold=bold, color=fg, name=ExcelReportWriter.FONT_NAME, size=9)
        align = Alignment(horizontal="center", vertical="center", wrap_text=True)
        border = Border(bottom=Side(style="medium", color="2563eb"), top=Side(style="thin", color="1e3a5f"))
        for col in range(1, cols + 1):
            cell = ws.cell(row=row, column=col)
            cell.fill = fill
            cell.font = font
            cell.alignment = align
            cell.border = border

    @staticmethod
    def _write_df_sheet(ws, df, start_row=2, col_widths=None, freeze_row=2):
        for col_idx, col_name in enumerate(df.columns, 1):
            ws.cell(row=start_row, column=col_idx, value=col_name)
        ExcelReportWriter._header_style(ws, start_row, len(df.columns))
        ws.row_dimensions[start_row].height = 30

        for r_idx, row_data in enumerate(df.itertuples(index=False), start_row + 1):
            is_alt = (r_idx % 2 == 0)
            bg = ExcelReportWriter.COL_ROW_ALT if is_alt else ExcelReportWriter.COL_ROW_NORM
            fill = PatternFill("solid", fgColor=bg)
            for c_idx, val in enumerate(row_data, 1):
                cell = ws.cell(row=r_idx, column=c_idx, value=(None if pd.isna(val) else val))
                cell.fill = fill
                cell.font = Font(name=ExcelReportWriter.FONT_NAME, size=9)
                cell.alignment = Alignment(vertical="center", wrap_text=False)
                if isinstance(val, float):
                    cell.number_format = "#,##0.00" if abs(val) < 1000 else "#,##0"

        if col_widths:
            for col_name, width in col_widths.items():
                if col_name in df.columns:
                    col_idx = df.columns.get_loc(col_name) + 1
                    ws.column_dimensions[get_column_letter(col_idx)].width = width
        else:
            for col_idx, col_name in enumerate(df.columns, 1):
                max_len = max(len(str(col_name)), df[col_name].astype(str).str.len().max() if len(df) else 0)
                ws.column_dimensions[get_column_letter(col_idx)].width = min(max(max_len + 2, 8), 40)

        if freeze_row:
            ws.freeze_panes = ws.cell(row=freeze_row + 1, column=1)
        if len(df) > 0:
            last_col = get_column_letter(len(df.columns))
            ws.auto_filter.ref = f"A{start_row}:{last_col}{start_row + len(df)}"

    @staticmethod
    def _title(ws, text):
        ws.cell(row=1, column=1, value=text).font = Font(bold=True, name=ExcelReportWriter.FONT_NAME, size=12, color=ExcelReportWriter.COL_HEADER_BG)

    # ---------------------------------------------------------------- Sheet 0 — Dashboard
    @staticmethod
    def write_dashboard(ws, run_info, status_table, abcd_table, region_matrix, size_window_table, geocode_note):
        ws.sheet_view.showGridLines = True
        for col, w in zip("ABCDEF", [25, 30, 25, 30, 35, 30]):
            ws.column_dimensions[col].width = w

        def write_title(row, text, bg="1e3a5f", cols=6):
            cell = ws.cell(row=row, column=1, value=text)
            cell.fill = PatternFill("solid", fgColor=bg)
            cell.font = Font(bold=True, color="FFFFFF", name=ExcelReportWriter.FONT_NAME, size=11)
            ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=cols)
            ws.row_dimensions[row].height = 25

        def write_kv(row, key, val, col_k=1, col_v=2):
            ws.cell(row=row, column=col_k, value=key).font = Font(name=ExcelReportWriter.FONT_NAME, size=9, bold=True, color="1e3a5f")
            ws.cell(row=row, column=col_v, value=val).font = Font(name=ExcelReportWriter.FONT_NAME, size=9)

        r = 1
        write_title(r, run_info["title"], cols=6)
        r += 1
        left_pairs = run_info["left"]
        right_pairs = run_info["right"]
        for i, (k, v) in enumerate(left_pairs):
            write_kv(r + i, k, v)
        for i, (k, v) in enumerate(right_pairs):
            write_kv(r + i, k, v, col_k=4, col_v=5)
        r += max(len(left_pairs), len(right_pairs)) + 1

        banner = run_info.get("banner")
        if banner:
            write_title(r, banner, bg="b45309", cols=6)
            r += 2

        # Cột mốc (2/3/4) tương ứng Lần 1/2/3 đang tô sáng theo đợt đang chạy
        LAN_COL = {"Lan1": 2, "Lan2": 3, "Lan3": 4}
        highlight_col = LAN_COL.get(status_table.get("current_lan"))
        HIGHLIGHT_HEADER_BG = "d97706"
        HIGHLIGHT_CELL_BG = "fef08a"

        # 1. Trạng thái mã
        write_title(r, "📊  1. TIÊU CHÍ ĐÁNH GIÁ TRẠNG THÁI MÃ HÀNG (Dựa trên vòng đời & tỷ lệ bán lũy kế)", bg=ExcelReportWriter.COL_SECTION, cols=6)
        r += 1
        for c_idx, h in enumerate(status_table["headers"], 1):
            cell = ws.cell(row=r, column=c_idx, value=h)
            cell.fill = PatternFill("solid", fgColor=HIGHLIGHT_HEADER_BG if c_idx == highlight_col else "475569")
            cell.font = Font(bold=True, color="FFFFFF", name=ExcelReportWriter.FONT_NAME, size=9)
        for row_data in status_table["rows"]:
            r += 1
            is_last = row_data == status_table["rows"][-1]
            for c_idx, val in enumerate(row_data, 1):
                cell = ws.cell(row=r, column=c_idx, value=val)
                cell.font = Font(name=ExcelReportWriter.FONT_NAME, size=9)
                if c_idx == 1 or is_last:
                    cell.font = Font(bold=True, name=ExcelReportWriter.FONT_NAME, size=9)
                    cell.fill = PatternFill("solid", fgColor="f8fafc")
                if c_idx == highlight_col:
                    cell.font = Font(bold=True, name=ExcelReportWriter.FONT_NAME, size=9)
                    cell.fill = PatternFill("solid", fgColor=HIGHLIGHT_CELL_BG)
        r += 2

        # 2. ABCD
        write_title(r, "🏪  2. PHÂN LOẠI HIỆU SUẤT CỬA HÀNG (ABCD)", bg=ExcelReportWriter.COL_SECTION, cols=6)
        r += 1
        for c_idx, h in enumerate(abcd_table["headers"], 1):
            cell = ws.cell(row=r, column=c_idx, value=h)
            cell.fill = PatternFill("solid", fgColor="475569")
            cell.font = Font(bold=True, color="FFFFFF", name=ExcelReportWriter.FONT_NAME, size=9)
        for row_data in abcd_table["rows"]:
            r += 1
            for c_idx, val in enumerate(row_data, 1):
                cell = ws.cell(row=r, column=c_idx, value=val)
                cell.font = Font(name=ExcelReportWriter.FONT_NAME, size=9)
                if c_idx == 1:
                    cell.font = Font(bold=True, name=ExcelReportWriter.FONT_NAME, size=10)
                    cell.alignment = Alignment(horizontal="center")
                    cell.fill = PatternFill("solid", fgColor=ExcelReportWriter.HS_COLORS.get(val, "FFFFFF"))
        r += 2

        # 3. Ma trận khoảng cách vùng
        write_title(r, "🗺️  3. MA TRẬN KHOẢNG CÁCH ĐỊA LÝ THỰC TẾ GIỮA CÁC VÙNG (Đơn vị: km)", bg="1e3a5f", cols=6)
        r += 1
        ws.cell(row=r, column=1, value="Vùng Xuất / Nhập").font = Font(bold=True, name=ExcelReportWriter.FONT_NAME, size=9)
        regions = region_matrix["regions"]
        for c_idx, reg in enumerate(regions, 2):
            cell = ws.cell(row=r, column=c_idx, value=reg)
            cell.fill = PatternFill("solid", fgColor="475569")
            cell.font = Font(bold=True, color="FFFFFF", name=ExcelReportWriter.FONT_NAME, size=9)
            cell.alignment = Alignment(horizontal="center")
        for reg_a in regions:
            r += 1
            cell_label = ws.cell(row=r, column=1, value=reg_a)
            cell_label.font = Font(bold=True, name=ExcelReportWriter.FONT_NAME, size=9)
            cell_label.fill = PatternFill("solid", fgColor="f8fafc")
            for c_idx, reg_b in enumerate(regions, 2):
                dist = region_matrix["dist"].get((reg_a, reg_b))
                cell_val = ws.cell(row=r, column=c_idx, value=(round(dist, 1) if dist is not None else None))
                cell_val.font = Font(name=ExcelReportWriter.FONT_NAME, size=9)
                cell_val.alignment = Alignment(horizontal="right")
                cell_val.number_format = "#,##0.0"
                if dist is not None and dist > 0:
                    if dist < 150:
                        cell_val.fill = PatternFill("solid", fgColor="d1fae5")
                    elif dist > 800:
                        cell_val.fill = PatternFill("solid", fgColor="fee2e2")
        r += 2

        # 4. Cửa sổ size mẫu
        write_title(r, f"🗺️  4. BẢNG CỬA SỔ SIZE TIÊU CHUẨN — {size_window_table['category']}", bg="1e3a5f", cols=6)
        r += 1
        for c_idx, h in enumerate(size_window_table["headers"], 1):
            ws.cell(row=r, column=c_idx, value=h).font = Font(bold=True, name=ExcelReportWriter.FONT_NAME, size=9)
        for row_vals in size_window_table["rows"]:
            r += 1
            ws.cell(row=r, column=1, value=row_vals[0]).font = Font(bold=True, name=ExcelReportWriter.FONT_NAME, size=9)
            for c_idx, val in enumerate(row_vals[1:], 2):
                ws.cell(row=r, column=c_idx, value=val).font = Font(name=ExcelReportWriter.FONT_NAME, size=9)
        r += 2

        write_title(r, geocode_note, bg="052e16", cols=6)

    # ---------------------------------------------------------------- Sheet 1-6
    @staticmethod
    def write_sheet1(wb, sheet1_df):
        ws = wb.create_sheet("1.Tổng hợp SKU")
        ws.sheet_view.showGridLines = False
        ExcelReportWriter._title(ws, "THÔNG TIN TỔNG HỢP CÁC SKU CẦN ĐIỀU CHUYỂN")
        if sheet1_df.empty:
            return ws
        ws.merge_cells(f"A1:{get_column_letter(len(sheet1_df.columns))}1")
        ExcelReportWriter._write_df_sheet(ws, sheet1_df, start_row=2)
        status_col = sheet1_df.columns.get_loc("Trạng thái mã") + 1
        for r_idx in range(3, 3 + len(sheet1_df)):
            cell = ws.cell(row=r_idx, column=status_col)
            val = str(cell.value or "").lower()
            for key, color in ExcelReportWriter.STATUS_COLORS.items():
                if key in val:
                    cell.fill = PatternFill("solid", fgColor=color)
                    break
        return ws

    @staticmethod
    def write_sheet2(wb, sheet2_df):
        ws = wb.create_sheet("2.Thông tin cửa hàng × SKU")
        ws.sheet_view.showGridLines = False
        ExcelReportWriter._title(ws, "THÔNG TIN CỬA HÀNG THEO SKU")
        if sheet2_df.empty:
            return ws
        ExcelReportWriter._write_df_sheet(ws, sheet2_df, start_row=2)
        hs_col = sheet2_df.columns.get_loc("Nhóm Hiệu Suất") + 1
        for r_idx in range(3, 3 + len(sheet2_df)):
            cell = ws.cell(row=r_idx, column=hs_col)
            cell.fill = PatternFill("solid", fgColor=ExcelReportWriter.HS_COLORS.get(str(cell.value or ""), "FFFFFF"))
            cell.font = Font(bold=True, name=ExcelReportWriter.FONT_NAME, size=9)
        return ws

    @staticmethod
    def write_sheet3(wb, sheet3_df):
        ws = wb.create_sheet("3.Chi tiết Bán-Tồn Size")
        ws.sheet_view.showGridLines = False
        ExcelReportWriter._title(ws, "CHI TIẾT BÁN-TỒN THEO SIZE TỪNG SKU × CỬA HÀNG")
        if sheet3_df.empty:
            return ws
        ExcelReportWriter._write_df_sheet(ws, sheet3_df, start_row=2)
        gap_col = sheet3_df.columns.get_loc("Size Gãy") + 1
        xuat_col = sheet3_df.columns.get_loc("Đề Xuất Xuất") + 1
        nhan_col = sheet3_df.columns.get_loc("Đề Xuất Nhận") + 1
        for r_idx in range(3, 3 + len(sheet3_df)):
            if ws.cell(row=r_idx, column=gap_col).value:
                ws.cell(row=r_idx, column=gap_col).fill = PatternFill("solid", fgColor="fef3c7")
            if (ws.cell(row=r_idx, column=xuat_col).value or 0) > 0:
                ws.cell(row=r_idx, column=xuat_col).fill = PatternFill("solid", fgColor="fee2e2")
                ws.cell(row=r_idx, column=xuat_col).font = Font(bold=True, color="991b1b", name=ExcelReportWriter.FONT_NAME, size=9)
            if (ws.cell(row=r_idx, column=nhan_col).value or 0) > 0:
                ws.cell(row=r_idx, column=nhan_col).fill = PatternFill("solid", fgColor="d1fae5")
                ws.cell(row=r_idx, column=nhan_col).font = Font(bold=True, color="065f46", name=ExcelReportWriter.FONT_NAME, size=9)
        return ws

    @staticmethod
    def write_sheet4(wb, sheet4_df):
        ws = wb.create_sheet("4.Lệnh điều chuyển chi tiết")
        ws.sheet_view.showGridLines = False
        ExcelReportWriter._title(ws, "LỆNH ĐIỀU CHUYỂN CHI TIẾT (CÓ KIỂM TRA RÀNG BUỘC VÒNG LẶP)")
        if sheet4_df.empty:
            return ws
        ExcelReportWriter._write_df_sheet(ws, sheet4_df, start_row=2)
        loai_col = sheet4_df.columns.get_loc("Loại Lệnh") + 1
        for r_idx in range(3, 3 + len(sheet4_df)):
            val = str(ws.cell(row=r_idx, column=loai_col).value or "")
            if "Liên" in val:
                ws.cell(row=r_idx, column=loai_col).fill = PatternFill("solid", fgColor="fef3c7")
        ExcelReportWriter._mark_below_batch_minimum(ws, sheet4_df)
        return ws

    @staticmethod
    def _mark_below_batch_minimum(ws, df):
        """Tô đỏ nhạt ô 'Đạt Lô Tối Thiểu' = ✗ (cặp CH xuất→nhận chưa đạt lô tối thiểu Mục 14.1)."""
        if "Đạt Lô Tối Thiểu" not in df.columns:
            return
        lo_col = df.columns.get_loc("Đạt Lô Tối Thiểu") + 1
        for r_idx in range(3, 3 + len(df)):
            if ws.cell(row=r_idx, column=lo_col).value == "✗":
                ws.cell(row=r_idx, column=lo_col).fill = PatternFill("solid", fgColor="fee2e2")

    @staticmethod
    def write_sheet5(wb, sheet5_df):
        ws = wb.create_sheet("5.Tổng hợp lệnh")
        ws.sheet_view.showGridLines = False
        ExcelReportWriter._title(ws, "TỔNG HỢP CÁC LỆNH ĐIỀU CHUYỂN")
        if not sheet5_df.empty:
            ExcelReportWriter._write_df_sheet(ws, sheet5_df, start_row=2)
            ExcelReportWriter._mark_below_batch_minimum(ws, sheet5_df)
        return ws

    @staticmethod
    def write_sheet6(wb, sheet6_df):
        ws = wb.create_sheet("6.Tổng hợp theo cửa hàng")
        ws.sheet_view.showGridLines = False
        ExcelReportWriter._title(ws, "TỔNG HỢP XUẤT-NHẬN-TỒN THEO CỬA HÀNG")
        if not sheet6_df.empty:
            ExcelReportWriter._write_df_sheet(ws, sheet6_df, start_row=2)
        return ws

    @staticmethod
    def write_sheet7(wb, sheet7_df):
        ws = wb.create_sheet("7.DX chia từ Kho")
        ws.sheet_view.showGridLines = False
        ExcelReportWriter._title(ws, "ĐỀ XUẤT CHIA TỪ KHO ĐI CỬA HÀNG (PHẦN NHU CẦU CHƯA ĐỦ SAU ĐIỀU CHUYỂN GIỮA CÁC CH)")
        if not sheet7_df.empty:
            ExcelReportWriter._write_df_sheet(ws, sheet7_df, start_row=2)
        return ws

    @staticmethod
    def write_sheet8(wb, sheet8_df):
        ws = wb.create_sheet("8.Tồn-Chuyển-Nhận CH×Nhóm")
        ws.sheet_view.showGridLines = False
        ExcelReportWriter._title(ws, "TỒN BAN ĐẦU – CHUYỂN – NHẬN – TỒN CUỐI THEO CỬA HÀNG × NHÓM HÀNG × MÃ (CHỈ MÃ ĐANG LUÂN CHUYỂN)")
        if sheet8_df.empty:
            return ws
        is_total = sheet8_df["La_total"].tolist() if "La_total" in sheet8_df.columns else []
        df = sheet8_df.drop(columns=["La_total"], errors="ignore")
        ExcelReportWriter._write_df_sheet(ws, df, start_row=2)
        ws.auto_filter.ref = None   # dòng Total xen giữa — tắt filter để không lọc lệch total
        fills = {True: PatternFill("solid", fgColor="dbeafe"),     # Total mã điều chuyển
                 "full": PatternFill("solid", fgColor="fef3c7"),   # tồn toàn CH (nguyên giá)
                 "grand": PatternFill("solid", fgColor="93c5fd")}  # TỔNG CỘNG
        for i, tot in enumerate(is_total):
            if tot is False or tot not in fills:
                continue
            r_idx = 3 + i
            fill = fills[tot]
            for c_idx in range(1, len(df.columns) + 1):
                cell = ws.cell(row=r_idx, column=c_idx)
                cell.fill = fill
                cell.font = Font(name=ExcelReportWriter.FONT_NAME, size=9, bold=True)
        return ws

    @staticmethod
    def write_workbook(path, dashboard_kwargs, sheet1, sheet2, sheet3, sheet4, sheet5, sheet6, sheet7=None,
                       sheet8=None):
        wb = Workbook()
        wb.remove(wb.active)

        ws0 = wb.create_sheet("0.Dashboard & Tham số")
        ExcelReportWriter.write_dashboard(ws0, **dashboard_kwargs)

        ws1 = ExcelReportWriter.write_sheet1(wb, sheet1)
        ws2 = ExcelReportWriter.write_sheet2(wb, sheet2)
        ws3 = ExcelReportWriter.write_sheet3(wb, sheet3)
        ws4 = ExcelReportWriter.write_sheet4(wb, sheet4)
        ws5 = ExcelReportWriter.write_sheet5(wb, sheet5)
        ws6 = ExcelReportWriter.write_sheet6(wb, sheet6)
        all_ws = [ws0, ws1, ws2, ws3, ws4, ws5, ws6]
        if sheet7 is not None:
            all_ws.append(ExcelReportWriter.write_sheet7(wb, sheet7))
        if sheet8 is not None:
            all_ws.append(ExcelReportWriter.write_sheet8(wb, sheet8))

        for i, ws in enumerate(all_ws):
            try:
                ws.sheet_properties.tabColor = ExcelReportWriter.TAB_COLORS[i % len(ExcelReportWriter.TAB_COLORS)]
            except Exception:
                pass

        wb.save(path)

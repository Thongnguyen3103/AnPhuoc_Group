# -*- coding: utf-8 -*-
"""TransferReportRunner — Chạy trọn 1 đợt báo cáo điều chuyển (không đụng giao diện).

    runner = TransferReportRunner(params, log=print)
    result = runner.run()      # -> {out_path, n_sku, n_lenh}

params: csv_path, data_root, out_dir, round_choice ('AUTO'|'Lan1'|'Lan2'|'Lan3'),
        selected_regions, excluded_stores, do_geocode
"""
import datetime as dt
import os

import pandas as pd

from Config import Paths_Transfer as paths
from Core.Allocate_Transfers import TransferAllocator
from Core.Build_Pipeline_Tables import PipelineTableBuilder
from Core.Compute_Metrics import MetricRules
from Core.Load_Data_Parquet import TransferDataLoader
from Core.Store_Performance_State import PerformanceStateStore
from Geo.Compute_Geo_Distance import GeoLocator
from Output.Format_Display import DisplayFormatter
from Output.Summarize_Output import OutputSummarizer
from Output.Write_Excel_Report import ExcelReportWriter

EMPTY_SHEET4_COLUMNS = ["Combined PK", "Ma Hang", "Operation", "Size", "CH Xuất",
                        "Region Xuất", "CH Nhận", "Region Nhận", "Loại Lệnh",
                        "Khoảng Cách (km)", "SL Chuyển", "Giá Bán", "Giá Trị Chuyển",
                        "Tồn Xuất Trước DC", "Tồn Xuất Sau DC", "Tồn Nhận Trước DC", "Tồn Nhận Sau DC",
                        "Đạt Lô Tối Thiểu"]
EMPTY_SHEET5_COLUMNS = ["STT", "CH Xuất", "Combined PK", "Ma Hang", "Size", "SL Chuyển",
                        "Giá Trị Chuyển", "CH Nhận", "Region Xuất", "Region Nhận",
                        "Loại Lệnh", "Khoảng Cách (km)", "Đạt Lô Tối Thiểu"]


class CancelledError(Exception):
    """Người dùng bấm Huỷ giữa chừng."""


class TransferReportRunner:
    """Điều phối các bước: đọc CSV → nạp CH + toạ độ → tính chỉ số → phân bổ → tổng hợp → ghi Excel.

    cancel_event: threading.Event — nếu được set() giữa chừng, dừng ở điểm kiểm tra gần
    nhất (giữa các bước lớn) và ném CancelledError."""

    def __init__(self, params, log=print, cancel_event=None, state_store=None, geo_csv=None):
        self.params = params
        self.log = log
        self.cancel_event = cancel_event
        self.state_store = state_store or PerformanceStateStore(paths.STATE_FILE)
        self.geo_csv = geo_csv or paths.GEO_CSV

    # ---------------------------------------------------------------- tiện ích
    def _check_cancel(self):
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise CancelledError("Đã huỷ theo yêu cầu người dùng.")

    # ---------------------------------------------------------------- các bước
    def _read_input(self):
        """Đọc CSV kế hoạch → danh sách Combined PK + Lần ép theo cột 'Dot Chuyen' / lựa chọn trên GUI."""
        round_choice = self.params["round_choice"]
        df_input = pd.read_csv(self.params["csv_path"], encoding="utf-8-sig")
        pk_col = next((c for c in df_input.columns if c.strip().lower().replace("_", " ") == "combined pk"), None)
        if pk_col is None:
            raise ValueError("Không tìm thấy cột 'Combined PK' trong file CSV.")
        combined_pks = df_input[pk_col].dropna().astype(str).str.strip().unique().tolist()
        self.log(f"Đã đọc {len(combined_pks)} mã (Combined PK) cần xử lý.")
        self._check_cancel()

        dot_col = next((c for c in df_input.columns if c.strip().lower().replace("_", " ") == "dot chuyen"), None)
        forced_round_map = {}
        if dot_col is not None:
            for _, row in df_input.iterrows():
                pk_val = str(row[pk_col]).strip()
                code = MetricRules.parse_round_label(row[dot_col])
                if pk_val and code:
                    forced_round_map[pk_val] = code
            n_parsed = len(forced_round_map)
            self.log(f"Đã đọc cột 'Dot Chuyen' từ CSV: {n_parsed}/{len(combined_pks)} mã xác định được Lần.")
            if n_parsed < len(combined_pks):
                self.log(f"  → {len(combined_pks) - n_parsed} mã không xác định được Lần từ CSV, sẽ tự suy theo mốc KHPP.")
        elif round_choice != "AUTO":
            forced_round_map = {pk: round_choice for pk in combined_pks}
            self.log(f"Lần điều chuyển áp dụng cho toàn bộ file: {round_choice}")
        else:
            self.log("Lần điều chuyển: Tự động suy theo mốc KHPP của từng mã.")
        return combined_pks, forced_round_map

    def _load_stores(self, loader):
        """CH toàn hệ thống + CH trong phạm vi đợt này, gắn toạ độ (file CSV / geocode xấp xỉ)."""
        all_stores_df = loader.load_scope_stores()
        scope_stores_df = loader.load_scope_stores(selected_regions=self.params["selected_regions"],
                                                   excluded_stores=self.params["excluded_stores"])
        self.log(f"Phạm vi luân chuyển: {len(scope_stores_df)} cửa hàng.")
        self._check_cancel()

        geo_df = TransferDataLoader.load_geo_csv(self.geo_csv)
        if geo_df is not None:
            self.log(f"Đã nạp toạ độ từ ViTri_DiaLy_CuaHang.csv ({len(geo_df)} CH).")
            all_stores_df = all_stores_df.merge(geo_df, on="Store_name", how="left")
        elif self.params["do_geocode"]:
            self.log("Chưa có ViTri_DiaLy_CuaHang.csv — tự geocode xấp xỉ "
                     "(khuyến nghị chạy Generate_Store_Coordinates.py để chính xác hơn).")
            coords = GeoLocator.build_store_coords(all_stores_df)
            all_stores_df["Lat"] = all_stores_df["Store_name"].map(lambda s: coords.get(s, (None, None, None))[0])
            all_stores_df["Lon"] = all_stores_df["Store_name"].map(lambda s: coords.get(s, (None, None, None))[1])
        else:
            all_stores_df["Lat"] = None
            all_stores_df["Lon"] = None
            self.log("Bỏ qua geocode — cột khoảng cách sẽ để trống.")
        scope_stores_df = scope_stores_df.merge(all_stores_df[["Store_name", "Lat", "Lon"]], on="Store_name", how="left")
        self._check_cancel()
        return all_stores_df, scope_stores_df

    def _build_size_maps(self, loader, combined_pks, df_sku, df_size):
        size_weight_by_sku, size_seq_by_sku = {}, {}
        for pk, g in df_size.groupby("Combined_PK"):
            size_weight_by_sku[pk] = dict(zip(g["Size"], g["Ty_trong"]))
        item_name_map = loader.load_sku_master(combined_pks).set_index("Combined_PK")["System_item_name"].to_dict()
        size_order_map = loader.load_size_order(list(set(item_name_map.values())))
        for pk in df_sku["Combined_PK"]:
            sizes = list(size_weight_by_sku.get(pk, {}).keys())
            size_seq_by_sku[pk] = MetricRules.build_size_sequence(sizes, item_name_map.get(pk), size_order_map)
        return size_weight_by_sku, size_seq_by_sku, item_name_map

    def _attach_group_caps(self, df_sku, df_store, group_sales):
        """Mục 8 — gắn khóa nhóm + bán TB tháng của CH ở nhóm + hạn mức nhận nhóm/đợt vào df_store."""
        from Config import Config_Parameters as cfg
        if df_store.empty:
            return df_store
        n_thang = len(cfg.EVAL_MONTHS) or 1
        gs = group_sales.copy()
        gs["Nhom_han_muc"] = [MetricRules.group_cap_key(g, dict(Color_group=c, Form=f, Style=s))
                              for g, c, f, s in zip(gs["Group_Report"], gs["Color_group"], gs["Form"], gs["Style"])]
        ban_tb = (gs.groupby(["Store_name", "Nhom_han_muc"])["Qty_Ban"].sum() / n_thang).to_dict()
        sku_key = {r["Combined_PK"]: MetricRules.group_cap_key(
                       r.get("Group_Report"), dict(Color_group=r.get("Group_color"), Form=r.get("Form"), Style=r.get("Style")))
                   for _, r in df_sku.iterrows()}
        df_store = df_store.copy()
        df_store["Nhom_han_muc"] = df_store["Combined_PK"].map(sku_key)
        df_store["Ban_TB_nhom"] = [round(ban_tb.get((s, k), 0), 1) for s, k in zip(df_store["Store_name"], df_store["Nhom_han_muc"])]
        df_store["Han_muc_nhom"] = [round(b * cfg.HAN_MUC_NHOM_THANG_BAN) if b > 0 else None
                                    for b in df_store["Ban_TB_nhom"]]
        df_store["Nhom_han_muc_label"] = df_store["Nhom_han_muc"].map(MetricRules.group_cap_label)
        self.log(f"Hạn mức nhận theo nhóm hàng: {df_store['Nhom_han_muc'].nunique()} nhóm, "
                 f"tối đa {cfg.HAN_MUC_NHOM_THANG_BAN} tháng bán / CH / đợt.")
        return df_store

    @staticmethod
    def _build_display_sheets(df_sku, df_store, df_store_size, detail_df, inv_by_size, store_meta, scope_stores_df):
        ma_op_map = df_sku.set_index("Combined_PK").apply(lambda r: (r["Ma_Hang"], r["Operation"]), axis=1).to_dict()
        sheet3_int = OutputSummarizer.build_sheet3(df_store_size, detail_df)
        sheet4_int = OutputSummarizer.build_sheet4_with_stock(detail_df, inv_by_size, store_meta)
        sheet5_int = OutputSummarizer.build_sheet5(sheet4_int)
        sheet6_int = OutputSummarizer.build_sheet6(df_store, sheet4_int, scope_stores_df)

        sheets = dict(
            sheet1=DisplayFormatter.to_display_sheet1(df_sku),
            sheet2=DisplayFormatter.to_display_sheet2(df_store, ma_op_map),
            sheet3=DisplayFormatter.to_display_sheet3(sheet3_int, ma_op_map),
            sheet4=DisplayFormatter.to_display_sheet4(sheet4_int, ma_op_map) if not sheet4_int.empty else sheet4_int,
            sheet5=DisplayFormatter.to_display_sheet5(sheet5_int, ma_op_map) if not sheet5_int.empty else sheet5_int,
            sheet6=DisplayFormatter.to_display_sheet6(sheet6_int),
        )
        if sheets["sheet4"].empty:
            sheets["sheet4"] = pd.DataFrame(columns=EMPTY_SHEET4_COLUMNS)
            sheets["sheet5"] = pd.DataFrame(columns=EMPTY_SHEET5_COLUMNS)
        return sheets

    # ---------------------------------------------------------------- chạy trọn
    def run(self):
        combined_pks, forced_round_map = self._read_input()

        self.log("Đang nạp dữ liệu Parquet...")
        loader = TransferDataLoader(self.params.get("data_root"))
        try:
            self._check_cancel()
            all_stores_df, scope_stores_df = self._load_stores(loader)
            store_meta = scope_stores_df.set_index("Store_name")[["Region", "Warehouse", "Loai_CH", "Lat", "Lon"]].to_dict("index")

            self.log("Đang tính chỉ số Mục 5 (mã / cửa hàng / size)...")
            hieu_suat_state = self.state_store.load()
            df_sku, df_store, df_size, df_store_size, so_ch_pham_vi = PipelineTableBuilder(loader).build_all(
                combined_pks, scope_stores_df, forced_round_map, hieu_suat_state)
            if df_sku.empty:
                raise ValueError("Không tìm thấy mã nào khớp trong dữ liệu (F_DataTracking).")
            self._check_cancel()

            inv_by_size = loader.load_inventory_size(combined_pks, scope_stores_df["Store_name"].tolist())
            from Config import Config_Parameters as cfg
            group_sales = loader.load_store_group_sales(scope_stores_df["Store_name"].tolist(), cfg.EVAL_MONTHS)
            group_inv = loader.load_store_group_inventory(scope_stores_df["Store_name"].tolist())
            inv_kho = loader.load_inventory_size(
                combined_pks, list(cfg.KHO_CHIA_CHUNG) + list(cfg.KHO_CHIA_THEO_VUNG.keys()))
            size_weight_by_sku, size_seq_by_sku, item_name_map = self._build_size_maps(loader, combined_pks, df_sku, df_size)
            self._check_cancel()
        finally:
            loader.close()

        # CH chọn tay "Không rút" trên GUI (CH mới / không tham gia rút) — vẫn được nhận.
        khong_rut = set(self.params.get("no_export_stores") or [])
        if not df_store.empty:
            df_store["Khong_rut"] = df_store["Store_name"].map(lambda s: "✓" if s in khong_rut else None)
        if khong_rut:
            self.log(f"CH không rút (chỉ nhận): {len(khong_rut)} cửa hàng.")

        df_store = self._attach_group_caps(df_sku, df_store, group_sales)

        self.log("Đang lập lệnh điều chuyển...")
        unmet_rows = []
        detail_df = TransferAllocator.build_transfer_orders(
            df_sku, df_store, inv_by_size, size_weight_by_sku, size_seq_by_sku,
            so_ch_pham_vi, item_name_map, store_meta, unmet_out=unmet_rows,
            store_size_sales=(df_store_size.groupby(["Combined_PK", "Store_name", "Size"])["Ban_3T"].sum().to_dict()
                              if not df_store_size.empty else {}))
        detail_df = TransferAllocator.apply_batch_minimum(detail_df)
        self.log(f"Đã sinh {len(detail_df)} dòng lệnh chi tiết.")
        sk = TransferAllocator.last_skipped_cap
        if sk:
            self.log(f"  Hạn mức nhóm: {len(sk)} (CH, nhóm) đã đủ hạn mức → nhường {sum(sk.values())} lượt điểm bán cho CH kế tiếp.")
        warns = TransferAllocator.validate_orders(detail_df, df_store, inv_by_size)
        for w in warns:
            self.log(f"  ⚠ Kiểm tra lệnh: {w}")
        if not warns:
            self.log("  ✓ Kiểm tra lệnh: đạt mọi ràng buộc.")
        if not detail_df.empty:
            n_cap = detail_df[["CH_xuat", "CH_nhan"]].drop_duplicates().shape[0]
            self.log(f"  Số chuyến (cặp CH xuất→nhận): {n_cap}")

        hold_after = inv_by_size.groupby(["Combined_PK", "Store_name"])["Qty_TonKho"].sum()
        if not detail_df.empty:
            hold_after = (hold_after
                          .sub(detail_df.groupby(["Combined_PK", "CH_xuat"])["So_luong"].sum().rename_axis(hold_after.index.names), fill_value=0)
                          .add(detail_df.groupby(["Combined_PK", "CH_nhan"])["So_luong"].sum().rename_axis(hold_after.index.names), fill_value=0))
        kho_df = TransferAllocator.build_warehouse_orders(pd.DataFrame(unmet_rows), inv_kho, store_meta,
                                                          hold_after=hold_after.to_dict())
        self.log(f"Đề xuất chia từ Kho: {int(kho_df['SL_chia'].sum()) if not kho_df.empty else 0} cái "
                 f"/ nhu cầu còn thiếu {int(sum(u['SL_thieu'] for u in unmet_rows))} cái.")
        self._check_cancel()

        self.log("Đang tổng hợp các sheet đầu ra...")
        sheets = self._build_display_sheets(df_sku, df_store, df_store_size, detail_df,
                                            inv_by_size, store_meta, scope_stores_df)
        self._check_cancel()
        dashboard_kwargs = DisplayFormatter.build_dashboard_kwargs(
            os.path.basename(self.params["csv_path"]), df_sku, sheets["sheet4"],
            all_stores_df, self.params["selected_regions"], df_store_size)

        out_dir = self.params["out_dir"]
        os.makedirs(out_dir, exist_ok=True)
        out_name = f"BaoCao_DieuChuyen_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        out_path = os.path.join(out_dir, out_name)
        self.log(f"Đang ghi file Excel: {out_name} ...")
        self._check_cancel()
        ExcelReportWriter.write_workbook(out_path, dashboard_kwargs, sheets["sheet1"], sheets["sheet2"],
                                         sheets["sheet3"], sheets["sheet4"], sheets["sheet5"], sheets["sheet6"],
                                         sheet7=DisplayFormatter.to_display_sheet7(kho_df, df_sku),
                                         sheet8=DisplayFormatter.to_display_sheet8(
                                             OutputSummarizer.build_sheet8(df_store, detail_df, kho_df, df_sku, group_inv)))

        state = PerformanceStateStore.update_with_hieu_suat_ky(hieu_suat_state, df_store)
        self.state_store.save(state)

        self.log("Hoàn tất.")
        return dict(out_path=out_path, n_sku=len(df_sku), n_lenh=len(sheets["sheet4"]))

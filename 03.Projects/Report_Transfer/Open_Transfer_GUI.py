# -*- coding: utf-8 -*-
"""
BÁO CÁO ĐIỀU CHUYỂN HÀNG HÓA — mở giao diện:  python Open_Transfer_GUI.py
Yêu cầu: pip install duckdb pandas openpyxl numpy

Cấu trúc (OOP):
  Config/  Config_Parameters (tham số Phụ lục C), Config_Gui_Theme, Paths_Transfer
  Core/    TransferDataLoader, MetricRules, PipelineTableBuilder, TransferAllocator,
           PerformanceStateStore, TransferReportRunner
  Geo/     GeoLocator, Geo_Reference_Data
  Output/  OutputSummarizer, DisplayFormatter, ExcelReportWriter
  Gui/     TransferApp
Xem README.md để biết chi tiết quy trình.
"""
import os
import sys
import traceback
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # Report_Transfer -> import Config/Core/...

from Gui.Transfer_App import TransferApp  # noqa: E402


def main():
    root = tk.Tk()
    TransferApp(root)
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
    finally:
        # Ép tiến trình thoát ngay khi cửa sổ đóng — tránh treo phiên PowerShell/CMD.
        os._exit(0)

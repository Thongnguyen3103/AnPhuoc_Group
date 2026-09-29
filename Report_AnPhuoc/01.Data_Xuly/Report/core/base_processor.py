# -*- coding: utf-8 -*-
"""Base class cho các nguồn dữ liệu giao dịch theo tháng (CSV/Excel nhiều file
-> gộp -> group theo tháng -> xuất Parquet phân mảnh theo năm/tháng).

Thêm 1 nguồn dữ liệu mới chỉ cần kế thừa MonthlySourceProcessor và cài đặt 3
phương thức: load_lookups(), read_files(), transform() — phần đọc thư mục,
kiểm tra file rỗng và xuất Parquet đã có sẵn ở run(), không phải viết lại."""
from __future__ import annotations

import glob
import os
from abc import ABC, abstractmethod

import pandas as pd

from .parquet_io import export_parquet_partitioned


class MonthlySourceProcessor(ABC):
    #: Thư mục chứa file nguồn (CSV/Excel)
    source_dir: str = ""
    #: Pattern glob file nguồn (mặc định *.csv, có thể override vd "**/*.xlsx")
    file_glob: str = "*.csv"
    #: Tên thư mục con dưới PARQUET_ROOT để xuất kết quả
    output_dir_name: str = ""
    #: Tiền tố tên file Parquet xuất ra (vd "System_sales" -> System_sales_07.parquet)
    file_prefix: str = ""
    #: Nhãn hiển thị trong log; mặc định lấy tên class
    label: str = ""

    def _files(self) -> list[str]:
        pattern = os.path.join(self.source_dir, self.file_glob)
        recursive = "**" in self.file_glob
        return glob.glob(pattern, recursive=recursive)

    @abstractmethod
    def load_lookups(self):
        """Đọc các bảng lookup cần thiết (Parquet Master: A_Region, D_Category, E_T-Shirt...)."""

    @abstractmethod
    def read_files(self, files: list[str]) -> pd.DataFrame:
        """Đọc + gộp toàn bộ file nguồn thành 1 DataFrame thô."""

    @abstractmethod
    def transform(self, df_raw: pd.DataFrame, lookups) -> pd.DataFrame:
        """Làm sạch, merge lookup, group theo tháng -> DataFrame kết quả cuối
        (đã có đủ cột Year/Month để export_parquet_partitioned phân mảnh)."""

    def run(self, lookups=None) -> pd.DataFrame | None:
        """lookups: truyền sẵn nếu muốn tái sử dụng lookups đã load (vd chạy chung
        System_sales + Contract_sales chỉ cần đọc Parquet Master 1 lần)."""
        label = self.label or self.__class__.__name__
        files = self._files()
        if not files:
            print(f"[{label}] Không tìm thấy file nguồn trong {self.source_dir}.")
            return None

        if lookups is None:
            lookups = self.load_lookups()
        df_raw = self.read_files(files)
        df_grouped = self.transform(df_raw, lookups)
        export_parquet_partitioned(df_grouped, self.output_dir_name, self.file_prefix)
        return df_grouped

# -*- coding: utf-8 -*-
import pandas as pd


def parse_date(series: pd.Series, fmt: str) -> pd.Series:
    """Parse cột ngày với format tường minh, bỏ qua phần giờ nếu có.
    fmt ví dụ: '%m/%d/%Y' hoặc '%d/%m/%Y'."""
    raw = series.astype(str).str.strip()
    date_str = raw.str.extract(r'(\d{1,2}/\d{1,2}/\d{4})', expand=False)
    result = pd.to_datetime(date_str, format=fmt, errors='coerce')
    failed = result.isna() & raw.ne('nan') & raw.ne('')
    n_failed = failed.sum()
    if n_failed:
        print(f"  [WARN] {n_failed} dòng không parse được ngày.")
    return result

# -*- coding: utf-8 -*-
"""Tien ich doc du lieu + chuan hoa khoa doi chieu (dung chung pipeline + performance)."""
from __future__ import annotations

import glob
import os

import pandas as pd


def key_norm(s: pd.Series) -> pd.Series:
    """Chuan hoa MaHang / Operation / Size: bo khoang trang + IN HOA."""
    return s.astype("string").str.strip().str.upper()


def store_norm(s: pd.Series, alias: dict) -> pd.Series:
    """Chuan hoa ten cua hang de doi chieu: bo khoang trang + in thuong + alias."""
    out = s.astype("string").str.strip()
    if alias:
        out = out.replace(alias)
    return out.str.lower()


def ym_of(year: pd.Series, month: pd.Series) -> pd.Series:
    return year.astype("int64") * 12 + month.astype("int64")


def read_many(folder: str) -> pd.DataFrame:
    """Doc toan bo file .parquet nam duoi 1 thu muc (moi nam / moi thang 1 file)."""
    files = sorted(glob.glob(os.path.join(folder, "**", "*.parquet"), recursive=True))
    if not files:
        raise FileNotFoundError(f"Khong tim thay .parquet trong {folder}")
    frames = []
    for fp in files:
        df = pd.read_parquet(fp)
        df["__src_file"] = os.path.basename(fp)
        frames.append(df)
    print(f"   - {folder}: {len(files)} file, {sum(len(f) for f in frames):,} dong")
    return pd.concat(frames, ignore_index=True)


def mode_or_first(s: pd.Series):
    s = s.dropna()
    if s.empty:
        return None
    m = s.mode()
    return m.iloc[0] if len(m) else s.iloc[0]


def join_unique(s: pd.Series) -> str:
    vals = sorted({str(x).strip() for x in s.dropna() if str(x).strip() not in ("", "None", "nan")})
    return " | ".join(vals)

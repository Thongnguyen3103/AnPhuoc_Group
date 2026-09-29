# -*- coding: utf-8 -*-
"""Tồn kho (Inventory + InventorySize), gộp thêm HDD_QLKD_Tong_hop. Đầu ra là 2
bảng snapshot (có Size / không Size) — khác nhóm MonthlySourceProcessor nên
không kế thừa base class đó, nhưng vẫn cung cấp cùng interface run()."""
import csv
import os
import re
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # 02_XuLyDuLieu
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # 01.Python_Projects (dung_chung)
from dung_chung import duong_dan
from dung_chung.quy_doi_size import actual_size

INVENTORY_DIR = Path(duong_dan.nguon_ton_kho)
MASTER_DIR = Path(duong_dan.master)
PARQUET_DIR = Path(duong_dan.ton_kho_parquet)
KEEP_ZERO_QTY = os.environ.get("INVENTORY_KEEP_ZERO", "0") == "1"

# --- Compiled regex constants (module level để tránh compile lại mỗi lần gọi) ---
_RE_NON_NUMERIC = re.compile(r"[^\d\-,\.]")
_RE_COMMA_THOUSANDS = re.compile(r"^-?\d{1,3}(,\d{3})+$")
_RE_DOT_THOUSANDS = re.compile(r"^-?\d{1,3}(\.\d{3})+$")
_RE_BAD_CHARS = re.compile(r"[\x00-\x08\x0B-\x0C\x0E-\x1F]")

ID_COLUMNS = ["TenCH", "Mahang", "gia", "sale", "Nam", "LanSX"]

SIZE_COLUMNS = [
    "size_25", "size_26", "size_27", "size_28", "size_29", "size_30",
    "size_31", "size_32", "size_33", "size_34", "size_35", "size_36",
    "size_37", "size_38", "size_39", "size_40", "size_41", "size_42",
    "size_43", "size_44", "size_45", "size_46", "size_47", "size_48",
    "size_49", "size_50", "size_51", "size_52", "size_S", "size_M",
    "size_L", "size_XL", "size_XXL", "size_3XL", "size_TS", "size_DAT1",
    "size_DAT2", "size_DAT3", "size_01", "size_02", "size_03", "size_04",
    "size_05", "size_06", "size_07", "size_08", "size_KHAC", "size_XS",
    "size_7A", "size_7B", "size_7C", "size_8A", "size_8B", "size_8C",
    "size_9A", "size_9B", "size_A7", "size_B7", "size_C7", "size_A8",
    "size_B8", "size_C8", "size_A9", "size_B9", "size_FS",
]

FINAL_COLUMNS = [
    "Warehouse", "Region", "Store_name", "Brand", "System_item_name",
    "Report_item_name", "Mahang", "Operation", "Size", "Qty_TonKho",
    "Status", "Product_type", "Gender", "Product_group", "Group_Report",
]

GROUP_COLUMNS = [c for c in FINAL_COLUMNS if c != "Qty_TonKho"]
NO_SIZE_FINAL_COLUMNS = [c for c in FINAL_COLUMNS if c != "Size"]
NO_SIZE_GROUP_COLUMNS = [c for c in GROUP_COLUMNS if c != "Size"]


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [" ".join(str(c).replace("\ufeff", "").strip().split()) for c in df.columns]
    return df


def normalize_column_name(value: object) -> str:
    return " ".join(str(value).replace("\ufeff", "").replace("\xa0", " ").strip().split())


def _detect_encoding_and_delimiter(raw: bytes) -> tuple[list[str], str]:
    """Detect encoding (BOM-first) và sniff delimiter từ raw bytes."""
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        enc_candidates = ["utf-16", "utf-16-le", "utf-16-be"]
    elif raw[:3] == b"\xef\xbb\xbf":
        enc_candidates = ["utf-8-sig", "utf-8"]
    elif raw.count(b"\x00") > len(raw) // 8:
        enc_candidates = ["utf-16-le", "utf-16-be", "utf-16", "utf-8-sig", "utf-8", "cp1258", "cp1252", "latin1"]
    else:
        enc_candidates = ["utf-8-sig", "utf-8", "cp1258", "cp1252", "latin1"]

    delimiter = ","
    for enc in enc_candidates:
        try:
            sample = raw.decode(enc, errors="replace")
            if sample.strip():
                delimiter = csv.Sniffer().sniff(sample[:8_192], delimiters=[",", ";", "\t", "|"]).delimiter
                break
        except Exception:
            continue

    return enc_candidates, delimiter


def _read_csv_tolerant(path: Path, encoding: str, delimiter: str, usecols_set: set | None) -> pd.DataFrame:
    """
    Đọc CSV bằng Python csv module — không skip dòng có cột thừa.

    Chiến lược khi dòng có n+k cột thừa:
    - Thử cắt k cột từ cuối (xử lý dấu phẩy ở cuối dòng / cột trống cuối).
    - Nếu k==1 và cột đầu tiên không phải số → ghép cột 0+1 thành 1
      (xử lý dấu phẩy trong tên cửa hàng/sản phẩm ở đầu dòng).
    """
    rows = []
    header = None
    n = 0

    with open(path, "r", encoding=encoding, newline="", errors="replace") as f:
        reader = csv.reader(f, delimiter=delimiter)
        for raw_row in reader:
            if not raw_row or all(c.strip() == "" for c in raw_row):
                continue

            if header is None:
                header = [normalize_column_name(c) for c in raw_row]
                n = len(header)
                continue

            extra = len(raw_row) - n
            if extra > 0:
                raw_row = raw_row[:n]
            elif extra < 0:
                raw_row = raw_row + [""] * (-extra)

            rows.append(raw_row)

    if header is None:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=header)
    if usecols_set:
        keep = [c for c in df.columns if c in usecols_set]
        df = df[keep]
    return df


def robust_read_csv(path: Path, usecols: list[str] | None = None) -> pd.DataFrame:
    """Đọc file CSV: auto-detect encoding + giữ lại dòng có dấu phẩy không được quote."""
    usecols_set = set(usecols) if usecols else None

    with open(path, "rb") as fb:
        raw = fb.read(16_384)

    enc_candidates, delimiter = _detect_encoding_and_delimiter(raw)

    last_error = None
    for encoding in enc_candidates:
        try:
            df = _read_csv_tolerant(path, encoding, delimiter, usecols_set)
            if df.empty and usecols_set:
                continue
            return normalize_columns(df)
        except Exception as exc:
            last_error = exc

    for encoding in ["utf-8-sig", "utf-8", "utf-16", "utf-16-le", "cp1258", "cp1252", "latin1"]:
        if encoding in enc_candidates:
            continue
        try:
            df = _read_csv_tolerant(path, encoding, delimiter, usecols_set)
            if df.empty and usecols_set:
                continue
            return normalize_columns(df)
        except Exception as exc:
            last_error = exc

    raise RuntimeError(f"Khong doc duoc file CSV {path}: {last_error}")


def read_data_file(path: Path, usecols: list[str] | None = None) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return robust_read_csv(path, usecols=usecols)
    if suffix in {".xlsx", ".xlsm", ".xls"}:
        usecols_set = set(usecols) if usecols else None
        try:
            df = pd.read_excel(
                path, dtype=str, engine="calamine",
                usecols=(lambda c: normalize_column_name(c) in usecols_set) if usecols_set else None,
            )
        except Exception:
            df = pd.read_excel(
                path, dtype=str,
                usecols=(lambda c: normalize_column_name(c) in usecols_set) if usecols_set else None,
            )
        return normalize_columns(df)
    raise ValueError(f"Khong ho tro dinh dang file: {path}")


def read_lookup_sheet(table_name: str) -> pd.DataFrame:
    try:
        df = pd.read_parquet(MASTER_DIR / f"{table_name}.parquet")
        return normalize_columns(df).fillna("")
    except Exception as exc:
        print(f"Canh bao: khong doc duoc table {table_name}: {exc}")
        return pd.DataFrame()


def load_lookups() -> dict[str, pd.DataFrame]:
    """Đọc các bảng lookup (Parquet) từ MASTER_DIR."""
    table_map = {"d_category": "D_Category", "a_region": "A_Region", "e_tshirt": "E_T-Shirt"}
    return {key: read_lookup_sheet(table) for key, table in table_map.items()}


def to_number(series: pd.Series) -> pd.Series:
    arr = (
        series.fillna("").astype(str).str.strip()
        .str.replace(_RE_NON_NUMERIC, "", regex=True)
        .to_numpy()
    )

    has_comma = np.array(["," in s for s in arr], dtype=bool)
    has_dot = np.array(["." in s for s in arr], dtype=bool)
    both = has_comma & has_dot

    rfind_comma = np.array([s.rfind(",") for s in arr])
    rfind_dot = np.array([s.rfind(".") for s in arr])
    comma_decimal = both & (rfind_comma > rfind_dot)
    dot_decimal = both & ~comma_decimal

    comma_thousands = has_comma & ~has_dot & np.array([bool(_RE_COMMA_THOUSANDS.match(s)) for s in arr])
    dot_thousands = has_dot & ~has_comma & np.array([bool(_RE_DOT_THOUSANDS.match(s)) for s in arr])
    comma_decimal_only = has_comma & ~has_dot & ~comma_thousands

    def _transform(s, mask_cd, mask_dd, mask_ct, mask_dt, mask_cdo):
        if mask_cd:
            return s.replace(".", "").replace(",", ".")
        if mask_dd:
            return s.replace(",", "")
        if mask_ct:
            return s.replace(",", "")
        if mask_dt:
            return s.replace(".", "")
        if mask_cdo:
            return s.replace(",", ".")
        return s

    result = np.array([
        _transform(s, cd, dd, ct, dt, cdo)
        for s, cd, dd, ct, dt, cdo
        in zip(arr, comma_decimal, dot_decimal, comma_thousands, dot_thousands, comma_decimal_only)
    ])
    return pd.to_numeric(pd.Series(result, index=series.index), errors="coerce").fillna(0)


def cast_inventory_number_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in [*SIZE_COLUMNS, "cong", "sale", "Nam", "LanSX", "gia", "tong"]:
        if col in df.columns:
            df[col] = to_number(df[col])
    return df


def list_inventory_files() -> list[Path]:
    if not INVENTORY_DIR.exists():
        raise FileNotFoundError(f"Khong tim thay folder inventory: {INVENTORY_DIR}")

    files = sorted(
        p for p in INVENTORY_DIR.iterdir()
        if p.is_file() and not p.name.startswith("~$") and p.suffix.lower() in {".csv", ".xlsx", ".xlsm", ".xls"}
    )
    if not files:
        raise FileNotFoundError(f"Khong co file CSV/Excel trong: {INVENTORY_DIR}")
    return files


def prepare_inventory_fast(df: pd.DataFrame) -> pd.DataFrame:
    for col in ["TenCH", "Mahang", "sale", "Nam", "LanSX"]:
        if col not in df.columns:
            df[col] = ""

    existing_size_cols = [c for c in SIZE_COLUMNS if c in df.columns]
    if not existing_size_cols:
        raise RuntimeError("Khong tim thay cot size_* de unpivot.")

    id_cols = ["TenCH", "Mahang", "sale", "Nam", "LanSX"]
    work = df[id_cols + existing_size_cols].copy()
    work["Operation"] = (
        to_number(work["Nam"]).astype("int64").astype(str).str[-2:]
        + "/"
        + to_number(work["LanSX"]).astype("int64").astype(str).str.zfill(3)
    )

    melted = work.melt(
        id_vars=["TenCH", "Mahang", "sale", "Operation"],
        value_vars=existing_size_cols,
        var_name="Size",
        value_name="Qty_TonKho",
    )
    melted["Qty_TonKho"] = to_number(melted["Qty_TonKho"])
    if not KEEP_ZERO_QTY:
        melted = melted[melted["Qty_TonKho"] != 0]
    melted["Size"] = melted["Size"].astype(str).str.replace("size_", "", regex=False)
    melted = melted.rename(columns={"TenCH": "Store_name"})
    return (
        melted
        .groupby(["Store_name", "Mahang", "Operation", "Size", "sale"], dropna=False, as_index=False)
        .agg(Qty_TonKho=("Qty_TonKho", "sum"))
    )


def prepare_inventory_no_size_fast(df: pd.DataFrame) -> pd.DataFrame:
    for col in ["TenCH", "Mahang", "sale", "Nam", "LanSX", "cong"]:
        if col not in df.columns:
            df[col] = ""

    existing_size_cols = [c for c in SIZE_COLUMNS if c in df.columns]
    work = df[["TenCH", "Mahang", "sale", "Nam", "LanSX", "cong", *existing_size_cols]].copy()
    work["Operation"] = (
        to_number(work["Nam"]).astype("int64").astype(str).str[-2:]
        + "/"
        + to_number(work["LanSX"]).astype("int64").astype(str).str.zfill(3)
    )
    if existing_size_cols:
        work["Qty_TonKho"] = sum(to_number(work[col]) for col in existing_size_cols)
    else:
        work["Qty_TonKho"] = to_number(work["cong"])
    work = work.rename(columns={"TenCH": "Store_name"})
    return (
        work
        .groupby(["Store_name", "Mahang", "Operation", "sale"], dropna=False, as_index=False)
        .agg(Qty_TonKho=("Qty_TonKho", "sum"))
    )


def enrich_grouped_inventory(df: pd.DataFrame, lookups: dict[str, pd.DataFrame]) -> pd.DataFrame:
    df = df.copy()
    df["Short_name"] = df["Mahang"].fillna("").astype(str).apply(lambda x: x[:-4] if len(x) >= 4 else "")

    d_category = lookups["d_category"]
    a_region = lookups["a_region"]
    e_tshirt = lookups["e_tshirt"]

    category_cols = [
        "Short_name", "Brand", "System_item_name", "Report_item_name",
        "Product_type", "Gender", "Product_group", "Group_Report",
    ]
    if all(c in d_category.columns for c in category_cols):
        df = df.merge(d_category[category_cols].drop_duplicates("Short_name"), on="Short_name", how="left")

    if "Size" in df.columns:
        if "Report_item_name" not in df.columns:
            df["Report_item_name"] = ""
        df["Size"] = [actual_size(sz, name) for sz, name in zip(df["Size"], df["Report_item_name"])]

    if all(c in a_region.columns for c in ["Store_name", "Region", "Warehouse"]):
        df = df.merge(
            a_region[["Store_name", "Region", "Warehouse"]].drop_duplicates("Store_name"),
            on="Store_name", how="left",
        )

    product_type = df.get("Product_type", pd.Series("", index=df.index)).fillna("").astype(str).str.lower()
    sale = to_number(df.get("sale", pd.Series(0, index=df.index)))
    df["Status"] = np.select(
        [product_type.str.contains("thanh lý|thanh ly", regex=True, na=False), sale.isin([30, 50])],
        ["Thanh lý", "Sale"],
        default="Nguyên giá",
    )

    if all(c in e_tshirt.columns for c in ["item_code", "T-shirt_name"]):
        df = df.merge(
            e_tshirt[["item_code", "T-shirt_name"]].drop_duplicates("item_code"),
            left_on="Mahang", right_on="item_code", how="left",
        )
        tshirt = df["T-shirt_name"].fillna("").astype(str).str.strip()
        df["Report_item_name"] = np.where(tshirt != "", tshirt, df.get("Report_item_name", ""))
        df = df.drop(columns=["item_code", "T-shirt_name"], errors="ignore")

    df = df.drop(columns=["sale", "Short_name"], errors="ignore")
    for col in FINAL_COLUMNS:
        if col not in df.columns:
            df[col] = np.nan
    return df[FINAL_COLUMNS]


def group_inventory(df: pd.DataFrame, with_size: bool = True) -> pd.DataFrame:
    df = df.copy()
    final_columns = FINAL_COLUMNS if with_size else NO_SIZE_FINAL_COLUMNS
    group_columns = GROUP_COLUMNS if with_size else NO_SIZE_GROUP_COLUMNS
    for col in final_columns:
        if col not in df.columns:
            df[col] = np.nan
    df["Qty_TonKho"] = to_number(df["Qty_TonKho"])
    return (
        df[final_columns]
        .groupby(group_columns, dropna=False, as_index=False)
        .agg(Qty_TonKho=("Qty_TonKho", "sum"))
    )[final_columns]


def clean_text(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    text_cols = [
        col for col in df.columns
        if pd.api.types.is_object_dtype(df[col]) or pd.api.types.is_string_dtype(df[col])
    ]
    if not text_cols:
        return df
    for col in text_cols:
        s = df[col].astype(str)
        s = s.str.replace(_RE_BAD_CHARS, "", regex=True)
        df[col] = s.replace({"nan": "", "None": ""})
    return df


class InventoryProcessor:
    """Đọc toàn bộ file tồn kho (size_* unpivot) + HDD_QLKD_Tong_hop, gom nhóm,
    xuất 2 bảng Parquet: InventorySize.parquet (có Size) và Inventory.parquet
    (không Size) vào 03.Data_Parquest/03.Inventory."""

    needed_cols = ["TenCH", "Mahang", "sale", "Nam", "LanSX", "cong", *SIZE_COLUMNS]

    def _process_folder(self, lookups: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
        files = list_inventory_files()
        grouped_size_parts = []
        grouped_no_size_parts = []

        for index, path in enumerate(files, 1):
            try:
                print(f"Xu ly inventory {index}/{len(files)}: {path.name}")
                raw = read_data_file(path, usecols=self.needed_cols)
                raw = cast_inventory_number_columns(raw)
                grouped_size_parts.append(prepare_inventory_fast(raw))
                grouped_no_size_parts.append(prepare_inventory_no_size_fast(raw))
            except Exception as exc:
                print(f"Canh bao: bo qua {path.name}: {exc}")

            if len(grouped_size_parts) >= 5:
                grouped_size_parts = [pd.concat(grouped_size_parts, ignore_index=True, sort=False)
                    .groupby(["Store_name", "Mahang", "Operation", "Size", "sale"], dropna=False, as_index=False)
                    .agg(Qty_TonKho=("Qty_TonKho", "sum"))]
            if len(grouped_no_size_parts) >= 5:
                grouped_no_size_parts = [pd.concat(grouped_no_size_parts, ignore_index=True, sort=False)
                    .groupby(["Store_name", "Mahang", "Operation", "sale"], dropna=False, as_index=False)
                    .agg(Qty_TonKho=("Qty_TonKho", "sum"))]

        if not grouped_size_parts:
            raise RuntimeError("Khong xu ly duoc file inventory nao.")

        grouped_size = (
            pd.concat(grouped_size_parts, ignore_index=True, sort=False)
            .groupby(["Store_name", "Mahang", "Operation", "Size", "sale"], dropna=False, as_index=False)
            .agg(Qty_TonKho=("Qty_TonKho", "sum"))
        )
        grouped_no_size = (
            pd.concat(grouped_no_size_parts, ignore_index=True, sort=False)
            .groupby(["Store_name", "Mahang", "Operation", "sale"], dropna=False, as_index=False)
            .agg(Qty_TonKho=("Qty_TonKho", "sum"))
        )
        return (
            enrich_grouped_inventory(grouped_size, lookups),
            enrich_grouped_inventory(grouped_no_size, lookups)[NO_SIZE_FINAL_COLUMNS],
        )

    def _load_hdd_inventory(self) -> pd.DataFrame:
        try:
            df = pd.read_parquet(MASTER_DIR / "HDD_QLKD_Tong_hop.parquet")
        except Exception as exc:
            print(f"Canh bao: khong doc duoc HDD_QLKD_Tong_hop: {exc}")
            return pd.DataFrame(columns=FINAL_COLUMNS)

        df = normalize_columns(df)
        for col in FINAL_COLUMNS:
            if col not in df.columns:
                df[col] = np.nan
        return df[FINAL_COLUMNS]

    def run(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        print("Bat dau xu ly Inventory")
        lookups = load_lookups()
        inventory_with_size, inventory_no_size = self._process_folder(lookups)
        print(f"Inventory co Size sau transform: {len(inventory_with_size):,} dong")
        print(f"Inventory khong Size sau transform: {len(inventory_no_size):,} dong")

        hdd_inventory = self._load_hdd_inventory()
        qty_source = float(inventory_with_size["Qty_TonKho"].sum())
        qty_hdd = float(hdd_inventory["Qty_TonKho"].sum()) if len(hdd_inventory) > 0 else 0.0
        if len(hdd_inventory) > 0:
            print(f"HDD append: {len(hdd_inventory):,} dong")

        grouped_with_size = group_inventory(pd.concat(
            [inventory_with_size.reset_index(drop=True), hdd_inventory.reset_index(drop=True)],
            ignore_index=True, sort=False,
        ))
        grouped_no_size = group_inventory(
            pd.concat(
                [inventory_no_size.reset_index(drop=True), hdd_inventory.drop(columns=["Size"], errors="ignore").reset_index(drop=True)],
                ignore_index=True, sort=False,
            ),
            with_size=False,
        )
        grouped_with_size = clean_text(grouped_with_size)
        grouped_no_size = clean_text(grouped_no_size)

        PARQUET_DIR.mkdir(parents=True, exist_ok=True)
        con = duckdb.connect()
        con.register("_size", grouped_with_size)
        con.execute(f"COPY (SELECT * FROM _size) TO '{PARQUET_DIR / 'InventorySize.parquet'}' (FORMAT PARQUET)")
        con.unregister("_size")
        con.register("_nosize", grouped_no_size)
        con.execute(f"COPY (SELECT * FROM _nosize) TO '{PARQUET_DIR / 'Inventory.parquet'}' (FORMAT PARQUET)")
        con.unregister("_nosize")
        con.close()

        qty_final = float(grouped_with_size["Qty_TonKho"].sum())
        diff = (qty_source + qty_hdd) - qty_final
        flag = "  ⚠️ LỆCH" if abs(diff) > 0.01 else "  ✓ khớp"
        print(f"📊 Đối chiếu SL — Tồn kho nguồn: {qty_source:,.0f} | HDD gộp: {qty_hdd:,.0f} | "
              f"Tổng cuối: {qty_final:,.0f} | Chênh lệch: {diff:,.0f}{flag}")

        print(f"Inventory — {len(grouped_with_size):,} dòng (có Size) | "
              f"{len(grouped_no_size):,} dòng (không Size) | Tổng Qty_TonKho: {qty_final:,.0f} "
              f"-> {PARQUET_DIR}")
        return grouped_with_size, grouped_no_size


def main():
    InventoryProcessor().run()


if __name__ == "__main__":
    main()

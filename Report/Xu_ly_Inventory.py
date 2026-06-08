# -*- coding: utf-8 -*-
import csv
import io
import os
import re
from pathlib import Path

import numpy as np
import pandas as pd


INVENTORY_DIR = Path(r"\\hovmfs01\PKD\PhanPhoi\Thong.Nguyen\Analysis_data\4.Inventory_data")
DB_PATH = Path(r"\\hovmfs01\PKD\PhanPhoi\Thong.Nguyen\Analysis_data\1.Processed_data\1.Data_Tracking.xlsx")
HDD_PATH = Path(r"\\hovmfs01\PKD\PhanPhoi\Thong.Nguyen\Analysis_data\1.Processed_data\5.In_transit_stock_HDD.xlsx")
OUTPUT_DIR = Path(r"D:\DataBase\3.Inventory")
OUTPUT_WITH_SIZE_FILE = OUTPUT_DIR / "InventorySize.csv"
OUTPUT_NO_SIZE_FILE = OUTPUT_DIR / "Inventory.csv"
KEEP_ZERO_QTY = os.environ.get("INVENTORY_KEEP_ZERO", "0") == "1"

# --- Compiled regex constants (module level để tránh compile lại mỗi lần gọi) ---
_RE_NON_NUMERIC    = re.compile(r"[^\d\-,\.]")
_RE_COMMA_THOUSANDS = re.compile(r"^-?\d{1,3}(,\d{3})+$")
_RE_DOT_THOUSANDS   = re.compile(r"^-?\d{1,3}(\.\d{3})+$")
_RE_BAD_CHARS       = re.compile(r"[\x00-\x08\x0B-\x0C\x0E-\x1F]")

DROP_COLUMNS = [
    "Source.Name", "\ufeffSTT", "STT", "TenVietTat", "Tenhang", "tac_nghiep",
    "NgayNhapKho", "mau_so", "DonViId", "clieu", "Hoavan", "Kieudang",
    "gchu", "", "cong", "tong",
]

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
    "Color_group", "Form", "Style", "Attribute", "Dist_plan", "Production_month",
    "Production_year",
]

GROUP_COLUMNS = [c for c in FINAL_COLUMNS if c != "Qty_TonKho"]
NO_SIZE_FINAL_COLUMNS = [c for c in FINAL_COLUMNS if c != "Size"]
NO_SIZE_GROUP_COLUMNS = [c for c in GROUP_COLUMNS if c != "Size"]


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [" ".join(str(c).replace("\ufeff", "").strip().split()) for c in df.columns]
    return df


def _detect_encoding_and_delimiter(raw: bytes) -> tuple[list[str], str]:
    """Detect encoding (BOM-first) và sniff delimiter từ raw bytes."""
    # Detect UTF-16 bằng BOM trước (chính xác nhất)
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        enc_candidates = ["utf-16", "utf-16-le", "utf-16-be"]
    elif raw[:3] == b"\xef\xbb\xbf":
        enc_candidates = ["utf-8-sig", "utf-8"]
    elif raw.count(b"\x00") > len(raw) // 8:
        # Nhiều null bytes → có thể UTF-16 không có BOM
        enc_candidates = ["utf-16-le", "utf-16-be", "utf-16", "utf-8-sig", "utf-8", "cp1258", "cp1252", "latin1"]
    else:
        enc_candidates = ["utf-8-sig", "utf-8", "cp1258", "cp1252", "latin1"]

    # Sniff delimiter từ sample text
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


def _read_csv_tolerant(path: Path, encoding: str, delimiter: str,
                        usecols_set: set | None) -> pd.DataFrame:
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
            # Bỏ qua dòng trống hoàn toàn
            if not raw_row or all(c.strip() == "" for c in raw_row):
                continue

            if header is None:
                header = [normalize_column_name(c) for c in raw_row]
                n = len(header)
                continue

            extra = len(raw_row) - n

            if extra > 0:
                # Thử ghép các cột text ở đầu trước (nếu extra == 1)
                if extra == 1:
                    # Ghép cột 0 và 1 → giảm bớt 1 cột
                    merged = raw_row[0] + delimiter + raw_row[1]
                    candidate = [merged] + raw_row[2:]
                    # Chọn candidate nếu cột cuối cùng trông hợp lệ hơn
                    # (kiểm tra cột cong và size cuối có phải số không)
                    last_needed = raw_row[:n]   # truncation từ cuối
                    raw_row = last_needed       # mặc định: cắt từ cuối
                else:
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
        raw = fb.read(16_384)   # 16KB đủ để detect BOM + sniff delimiter

    enc_candidates, delimiter = _detect_encoding_and_delimiter(raw)

    last_error = None
    for encoding in enc_candidates:
        try:
            df = _read_csv_tolerant(path, encoding, delimiter, usecols_set)
            # Validate: phải có ít nhất 1 cột hợp lệ
            if df.empty and usecols_set:
                continue
            return normalize_columns(df)
        except Exception as exc:
            last_error = exc

    # Fallback toàn bộ encoding nếu detection ban đầu sai
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




def normalize_column_name(value: object) -> str:
    return " ".join(str(value).replace("\ufeff", "").replace("\xa0", " ").strip().split())


def normalize_text(series: pd.Series) -> pd.Series:
    return (
        series.fillna("")
        .astype(str)
        .str.replace("\ufeff", "", regex=False)
        .str.replace("\xa0", " ", regex=False)
        .str.replace(r"\.0$", "", regex=True)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
        .str.upper()
    )


def read_data_file(path: Path, usecols: list[str] | None = None) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return robust_read_csv(path, usecols=usecols)
    if suffix in {".xlsx", ".xlsm", ".xls"}:
        usecols_set = set(usecols) if usecols else None
        try:
            df = pd.read_excel(
                path,
                dtype=str,
                engine="calamine",
                usecols=(lambda c: normalize_column_name(c) in usecols_set) if usecols_set else None,
            )
        except Exception:
            df = pd.read_excel(
                path,
                dtype=str,
                usecols=(lambda c: normalize_column_name(c) in usecols_set) if usecols_set else None,
            )
        return normalize_columns(df)
    raise ValueError(f"Khong ho tro dinh dang file: {path}")


def read_lookup_sheet(sheet_name: str) -> pd.DataFrame:
    try:
        try:
            df = pd.read_excel(DB_PATH, sheet_name=sheet_name, engine="calamine", dtype=str)
        except Exception:
            df = pd.read_excel(DB_PATH, sheet_name=sheet_name, dtype=str)
        return normalize_columns(df).fillna("")
    except Exception as exc:
        print(f"Canh bao: khong doc duoc sheet {sheet_name}: {exc}")
        return pd.DataFrame()


def load_lookups() -> dict[str, pd.DataFrame]:
    """Đọc tất cả 4 sheet từ DB_PATH trong 1 lần mở file."""
    sheet_map = {
        "d_category": "D_Category",
        "a_region": "A_Region",
        "e_tshirt": "E_T-Shirt",
        "f_tracking": "F_DataTracking",
    }
    try:
        try:
            all_sheets = pd.read_excel(
                DB_PATH,
                sheet_name=list(sheet_map.values()),
                engine="calamine",
                dtype=str,
            )
        except Exception:
            all_sheets = pd.read_excel(
                DB_PATH,
                sheet_name=list(sheet_map.values()),
                dtype=str,
            )
        return {
            key: normalize_columns(all_sheets[sheet]).fillna("")
            for key, sheet in sheet_map.items()
        }
    except Exception as exc:
        print(f"Canh bao: khong doc duoc DB {DB_PATH}: {exc}")
        # Fallback: đọc từng sheet
        return {key: read_lookup_sheet(sheet) for key, sheet in sheet_map.items()}


def to_number(series: pd.Series) -> pd.Series:
    arr = (
        series.fillna("").astype(str).str.strip()
        .str.replace(_RE_NON_NUMERIC, "", regex=True)
        .to_numpy()
    )

    has_comma = np.array(["," in s for s in arr], dtype=bool)
    has_dot   = np.array(["." in s for s in arr], dtype=bool)
    both = has_comma & has_dot

    # Tìm dấu phẩy hoặc chấm cuối cùng để xác định decimal
    rfind_comma = np.array([s.rfind(",") for s in arr])
    rfind_dot   = np.array([s.rfind(".") for s in arr])
    comma_decimal = both & (rfind_comma > rfind_dot)
    dot_decimal   = both & ~comma_decimal

    # Dấu phẩy / chấm ngăn cách hàng nghìn (dạng 1,234 hoặc 1.234)
    comma_thousands = has_comma & ~has_dot & np.array([bool(_RE_COMMA_THOUSANDS.match(s)) for s in arr])
    dot_thousands   = has_dot   & ~has_comma & np.array([bool(_RE_DOT_THOUSANDS.match(s))   for s in arr])
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


def merge_f_tracking(df: pd.DataFrame, f_tracking: pd.DataFrame) -> pd.DataFrame:
    tracking_cols = [
        "item_code", "Operation", "Color_group", "Dist_plan", "Form",
        "Production_month", "Production_year", "Style","Attribute",
    ]
    if not all(c in f_tracking.columns for c in tracking_cols):
        return df

    result = df.copy()
    lookup = f_tracking[tracking_cols].copy()
    lookup["_ft_item_key"] = normalize_text(lookup["item_code"])
    lookup["_ft_operation_key"] = normalize_text(lookup["Operation"])
    result["_ft_item_key"] = normalize_text(result["Mahang"])
    result["_ft_operation_key"] = normalize_text(result["Operation"])

    lookup_value_cols = [
        "Color_group", "Dist_plan", "Form", "Production_month",
        "Production_year", "Style","Attribute",
    ]
    lookup = lookup[
        ["_ft_item_key", "_ft_operation_key", *lookup_value_cols]
    ].drop_duplicates(["_ft_item_key", "_ft_operation_key"])

    result = result.merge(
        lookup,
        on=["_ft_item_key", "_ft_operation_key"],
        how="left",
    )
    return result.drop(columns=["_ft_item_key", "_ft_operation_key"], errors="ignore")


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


def prepare_inventory(df: pd.DataFrame) -> pd.DataFrame:
    df = df.drop(columns=[c for c in DROP_COLUMNS if c in df.columns], errors="ignore")
    df = cast_inventory_number_columns(df)

    for col in ["gia", "sale", "Nam", "LanSX", *SIZE_COLUMNS]:
        if col in df.columns:
            df[col] = to_number(df[col]).astype("int64")

    for col in ID_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    existing_size_cols = [c for c in SIZE_COLUMNS if c in df.columns]
    if not existing_size_cols:
        raise RuntimeError("Khong tim thay cot size_* de unpivot.")

    df = df.melt(
        id_vars=ID_COLUMNS,
        value_vars=existing_size_cols,
        var_name="Size",
        value_name="Qty_TonKho",
    )
    df["Size"] = df["Size"].astype(str).str.replace("size_", "", regex=False)
    df["Qty_TonKho"] = to_number(df["Qty_TonKho"])

    mahang = df["Mahang"].fillna("").astype(str)
    df["Short_name"] = mahang.apply(lambda x: x[:-4] if len(x) >= 4 else "")
    df["Color_code"] = mahang.apply(lambda x: x[-4:] if len(x) >= 4 else "")
    df["Operation"] = (
        to_number(df["Nam"]).astype("int64").astype(str).str[-2:]
        + "/"
        + to_number(df["LanSX"]).astype("int64").astype(str).str.zfill(3)
    )
    return df


def enrich_inventory(df: pd.DataFrame, lookups: dict[str, pd.DataFrame]) -> pd.DataFrame:
    d_category = lookups["d_category"]
    a_region = lookups["a_region"]
    e_tshirt = lookups["e_tshirt"]
    f_tracking = lookups["f_tracking"]

    category_cols = [
        "Short_name", "Brand", "System_item_name", "Report_item_name",
        "Product_type", "Gender", "Product_group", "Group_Report",
    ]
    if all(c in d_category.columns for c in category_cols):
        df = df.merge(d_category[category_cols].drop_duplicates("Short_name"), on="Short_name", how="left")

    region_cols = ["Store_name", "Region", "Warehouse"]
    if all(c in a_region.columns for c in region_cols):
        df = df.merge(
            a_region[region_cols].drop_duplicates("Store_name"),
            left_on="TenCH",
            right_on="Store_name",
            how="left",
        )
        df = df.drop(columns=["Store_name"], errors="ignore")

    product_type = df.get("Product_type", pd.Series("", index=df.index)).fillna("").astype(str).str.lower()
    sale = to_number(df.get("sale", pd.Series(0, index=df.index)))
    df["Status"] = np.select(
        [product_type.str.contains("thanh lý|thanh ly", regex=True, na=False), sale.isin([30, 50])],
        ["Thanh lý", "Sale"],
        default="Nguyên Giá",
    )

    if all(c in e_tshirt.columns for c in ["item_code", "T-shirt_name"]):
        df = df.merge(
            e_tshirt[["item_code", "T-shirt_name"]].drop_duplicates("item_code"),
            left_on="Mahang",
            right_on="item_code",
            how="left",
        )
        tshirt = df["T-shirt_name"].fillna("").astype(str).str.strip()
        df["Report_item_name"] = np.where(tshirt != "", tshirt, df.get("Report_item_name", ""))
        df = df.drop(columns=["item_code", "T-shirt_name"], errors="ignore")

    df = merge_f_tracking(df, f_tracking)

    df = df.drop(columns=["gia", "sale", "Nam", "LanSX", "Short_name", "Color_code"], errors="ignore")
    df = df.rename(columns={"TenCH": "Store_name"})
    for col in FINAL_COLUMNS:
        if col not in df.columns:
            df[col] = np.nan
    return df[FINAL_COLUMNS]


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


def reconcile_size_vs_cong(df: pd.DataFrame, source_name: str) -> dict[str, object]:
    existing_size_cols = [c for c in SIZE_COLUMNS if c in df.columns]
    has_cong = "cong" in df.columns

    if not existing_size_cols:
        return {
            "Source.Name": source_name,
            "Rows": len(df),
            "Size_Columns": 0,
            "Qty_From_Size": 0,
            "Qty_From_Cong": float(to_number(df["cong"]).sum()) if has_cong else 0,
            "Diff_Size_Minus_Cong": 0,
            "Rows_Diff": 0,
            "Has_Cong": has_cong,
        }

    size_sum = sum(to_number(df[col]) for col in existing_size_cols)

    # Nếu không có cột 'cong', không thể so sánh → không báo lệch
    if not has_cong:
        return {
            "Source.Name": source_name,
            "Rows": len(df),
            "Size_Columns": len(existing_size_cols),
            "Qty_From_Size": float(size_sum.sum()),
            "Qty_From_Cong": 0,
            "Diff_Size_Minus_Cong": 0,
            "Rows_Diff": 0,
            "Has_Cong": False,
        }

    cong = to_number(df["cong"])
    diff = size_sum - cong
    # Dùng tolerance 0.5 để loại floating-point noise
    significant_diff = diff.abs() > 0.5
    return {
        "Source.Name": source_name,
        "Rows": len(df),
        "Size_Columns": len(existing_size_cols),
        "Qty_From_Size": float(size_sum.sum()),
        "Qty_From_Cong": float(cong.sum()),
        "Diff_Size_Minus_Cong": float(diff[significant_diff].sum()),
        "Rows_Diff": int(significant_diff.sum()),
        "Has_Cong": True,
    }


def enrich_grouped_inventory(df: pd.DataFrame, lookups: dict[str, pd.DataFrame]) -> pd.DataFrame:
    df = df.copy()
    df["Short_name"] = df["Mahang"].fillna("").astype(str).apply(lambda x: x[:-4] if len(x) >= 4 else "")

    d_category = lookups["d_category"]
    a_region = lookups["a_region"]
    e_tshirt = lookups["e_tshirt"]
    f_tracking = lookups["f_tracking"]

    category_cols = [
        "Short_name", "Brand", "System_item_name", "Report_item_name",
        "Product_type", "Gender", "Product_group", "Group_Report",
    ]
    if all(c in d_category.columns for c in category_cols):
        df = df.merge(d_category[category_cols].drop_duplicates("Short_name"), on="Short_name", how="left")

    if all(c in a_region.columns for c in ["Store_name", "Region", "Warehouse"]):
        df = df.merge(
            a_region[["Store_name", "Region", "Warehouse"]].drop_duplicates("Store_name"),
            on="Store_name",
            how="left",
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
            left_on="Mahang",
            right_on="item_code",
            how="left",
        )
        tshirt = df["T-shirt_name"].fillna("").astype(str).str.strip()
        df["Report_item_name"] = np.where(tshirt != "", tshirt, df.get("Report_item_name", ""))
        df = df.drop(columns=["item_code", "T-shirt_name"], errors="ignore")

    df = merge_f_tracking(df, f_tracking)

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


def process_inventory_folder(lookups: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
    files = list_inventory_files()
    grouped_size_parts = []
    grouped_no_size_parts = []
    needed_cols = ["TenCH", "Mahang", "sale", "Nam", "LanSX", "cong", *SIZE_COLUMNS]

    for index, path in enumerate(files, 1):
        try:
            print(f"Xu ly inventory {index}/{len(files)}: {path.name}")
            raw = read_data_file(path, usecols=needed_cols)
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


def load_hdd_inventory() -> pd.DataFrame:
    if not HDD_PATH.exists():
        print(f"Canh bao: khong tim thay file HDD append: {HDD_PATH}")
        return pd.DataFrame(columns=FINAL_COLUMNS)

    try:
        try:
            df = pd.read_excel(HDD_PATH, sheet_name="HDD_QLKD_Tong_hop", engine="calamine", dtype=str)
        except Exception:
            df = pd.read_excel(HDD_PATH, sheet_name="HDD_QLKD_Tong_hop", dtype=str)
    except Exception as exc:
        print(f"Canh bao: khong doc duoc HDD_QLKD_Tong_hop: {exc}")
        return pd.DataFrame(columns=FINAL_COLUMNS)

    df = normalize_columns(df)
    for col in FINAL_COLUMNS:
        if col not in df.columns:
            df[col] = np.nan
    return df[FINAL_COLUMNS]


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


def write_csv(df: pd.DataFrame, path: Path) -> Path:
    try:
        df.to_csv(path, index=False, encoding="utf-8-sig")
        return path
    except PermissionError:
        raise PermissionError(f"File dang bi khoa, hay dong file roi chay lai: {path}")


def main() -> None:
    print("Bat dau xu ly Inventory")
    print("Doc lookup tu Data_Tracking")
    lookups = load_lookups()
    inventory_with_size, inventory_no_size = process_inventory_folder(lookups)
    print(f"Inventory co Size sau transform: {len(inventory_with_size):,} dong")
    print(f"Inventory khong Size sau transform: {len(inventory_no_size):,} dong")

    hdd_inventory = load_hdd_inventory()
    if len(hdd_inventory) > 0:
        print(f"HDD append: {len(hdd_inventory):,} dong")

    grouped_with_size = group_inventory(pd.concat([inventory_with_size.reset_index(drop=True), hdd_inventory.reset_index(drop=True)], ignore_index=True, sort=False))
    grouped_no_size = group_inventory(
        pd.concat([inventory_no_size.reset_index(drop=True), hdd_inventory.drop(columns=["Size"], errors="ignore").reset_index(drop=True)], ignore_index=True, sort=False),
        with_size=False,
    )
    grouped_with_size = clean_text(grouped_with_size)
    grouped_no_size = clean_text(grouped_no_size)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with_size_file = write_csv(grouped_with_size, OUTPUT_WITH_SIZE_FILE)
    no_size_file = write_csv(grouped_no_size, OUTPUT_NO_SIZE_FILE)

    print("Hoan thanh")
    print(f"File co Size: {with_size_file}")
    print(f"So dong co Size: {len(grouped_with_size):,}")
    print(f"Tong Qty_TonKho co Size: {grouped_with_size['Qty_TonKho'].sum():,.0f}")
    print(f"File khong Size: {no_size_file}")
    print(f"So dong khong Size: {len(grouped_no_size):,}")
    print(f"Tong Qty_TonKho khong Size: {grouped_no_size['Qty_TonKho'].sum():,.0f}")


if __name__ == "__main__":
    main()

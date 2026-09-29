"""Core data access for the Reallocation Pro Flask app."""
import hashlib
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd


sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # 01.Python_Projects (dung_chung)
from dung_chung import duong_dan  # noqa: E402

APP_DIR = Path(__file__).resolve().parent
PROJECT_DIR = APP_DIR.parent
DATA_DIR = PROJECT_DIR / "du_lieu"          # user, trang thai duyet, log, DB upload tay
KET_QUA_DIR = Path(duong_dan.thu_muc_ket_qua("KiemSoat_TonKho"))   # 04_KetQua/KiemSoat_TonKho
DB_FILE = KET_QUA_DIR / "Reallocation_Database.xlsx"
LOCK_FILE = KET_QUA_DIR / "Reallocation_Database.xlsx.lock"

USERS_FILE = DATA_DIR / "transfer_review_users.csv"
REVIEW_FILE = DATA_DIR / "transfer_order_review_state.csv"
AUDIT_FILE = DATA_DIR / "transfer_review_audit_log.csv"

STATUS_LABELS = {"pending": "Pending", "approved": "Approved", "rejected": "Rejected"}
ROLE_LABELS = {"viewer": "Viewer", "reviewer": "Reviewer", "admin": "Admin"}

INVENTORY_SHEET = "Chi_Tiet_Cua_Hang"
TRANSFER_SHEET = "Lenh_Dieu_Chuyen"


def clean(v):
    return " ".join(str(v).replace("\ufeff", "").replace("\xa0", " ").strip().split())


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_db_source():
    local = DATA_DIR / DB_FILE.name
    return local if local.exists() else DB_FILE


def is_db_rebuilding():
    """Return True if xay_dung_database.py is currently writing the xlsx file."""
    return LOCK_FILE.exists()


def set_db_lock(active: bool):
    """Create or remove the lock sentinel file."""
    try:
        if active:
            LOCK_FILE.write_text(datetime.now().isoformat(), encoding="utf-8")
        else:
            if LOCK_FILE.exists():
                LOCK_FILE.unlink()
    except Exception:
        pass  # Non-fatal: lock is best-effort


def generate_password_hash(pw):
    return str(pw)


def check_password_hash(stored, pw):
    return str(stored) == str(pw)


def load_users():
    if USERS_FILE.exists():
        df = pd.read_csv(USERS_FILE, dtype=object, keep_default_na=False).fillna("")
        if "approval_status" not in df.columns:
            df["approval_status"] = "approved"
        if not df.empty:
            return df
    df = pd.DataFrame([{
        "username": "Thong.Nguyen",
        "display_name": "Thong.Nguyen",
        "password": "123456",
        "role": "admin",
        "is_active": "1",
        "approval_status": "approved",
    }])
    save_users(df)
    return df


def save_users(df):
    df.to_csv(USERS_FILE, index=False, encoding="utf-8-sig")


_inv_cache = {"mtime": 0, "df": None, "path": None}
_tr_cache = {"mtime": 0, "df": None, "path": None}


def _read_excel(path, sheet_name, **kwargs):
    try:
        return pd.read_excel(path, sheet_name=sheet_name, engine="calamine", **kwargs)
    except Exception:
        return pd.read_excel(path, sheet_name=sheet_name, **kwargs)


def _ensure_cols(df, cols, default=""):
    for c in cols:
        if c not in df.columns:
            df[c] = default
    return df


def _num(df, cols):
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)


def _str(df, cols):
    for c in cols:
        if c in df.columns:
            df[c] = df[c].fillna("").astype(str).str.strip()


def load_inventory(source=None):
    """Load the web detail grid from Reallocation_Database.xlsx.

    Lock-aware: if xay_dung_database.py is currently writing the file, we
    return the stale cached copy (if available) instead of reading a
    partially-written file.  If no cache exists yet we retry up to 3 times
    with a 1-second pause before raising.
    """
    global _inv_cache
    path = Path(source or get_db_source())

    # --- Lock-aware fast path: serve stale cache while DB is being rebuilt ---
    if is_db_rebuilding() and _inv_cache["df"] is not None:
        return _inv_cache["df"]

    if not path.exists():
        if _inv_cache["df"] is not None:
            return _inv_cache["df"]  # Fallback to stale cache
        raise FileNotFoundError(f"File khong ton tai: {path}")

    mtime = path.stat().st_mtime
    if _inv_cache["df"] is not None and _inv_cache["mtime"] == mtime and _inv_cache["path"] == str(path):
        return _inv_cache["df"]

    # --- Retry loop: protect against reading a partially-written file ---
    last_exc = None
    for attempt in range(3):
        try:
            df = _read_excel(path, INVENTORY_SHEET, dtype=object)
            last_exc = None
            break
        except Exception as exc:
            last_exc = exc
            if attempt < 2:
                time.sleep(1.0)

    if last_exc is not None:
        # All retries failed — return stale cache if available, else raise
        if _inv_cache["df"] is not None:
            return _inv_cache["df"]
        raise last_exc

    df.columns = [clean(c) for c in df.columns]

    required = [
        "Brand", "Report_item_name", "Group_Report", "MaHang", "Operation",
        "Dist_plan", "Tháng_XK", "Group", "Store_RP", "Store_rank", "Region",
        "Color_group", "Form", "Style", "Size", "Ton_Size", "Ban_Size",
        "Ty_Le_Ban_Size", "Hành_Động", "SL_Đề_Xuất", "Ton_Sau_Dieu_Chuyen",
        "Cửa_Hàng_Đối_Tác", "Total_Ton_Store", "Total_Ban_Store_All",
        "Rate_All_Store", "Trang_Thai", "Ban_Recent_Store", "So_Thang_Ban",
        "Avg_Ban_Store", "Rate_Recent_Store",
    ]
    _ensure_cols(df, required)
    _ensure_cols(df, ["Total_Ton", "Total_Ban", "Type", "Status", "Gender", "Product_group", "Product_type"])

    if "Type" in df.columns:
        df["Type"] = df["Type"].replace("", pd.NA).fillna(df["Group"])
    df["Total_Ton"] = pd.to_numeric(df["Ton_Size"], errors="coerce").fillna(0)
    df["Total_Ban"] = pd.to_numeric(df["Ban_Size"], errors="coerce").fillna(0)

    _num(df, [
        "Ton_Size", "Ban_Size", "Ty_Le_Ban_Size", "SL_Đề_Xuất",
        "Ton_Sau_Dieu_Chuyen", "Total_Ton_Store", "Total_Ban_Store_All",
        "Rate_All_Store", "Ban_Recent_Store", "So_Thang_Ban",
        "Avg_Ban_Store", "Rate_Recent_Store", "Total_Ton", "Total_Ban",
    ])
    _str(df, [
        "Brand", "Report_item_name", "Group_Report", "MaHang", "Operation",
        "Dist_plan", "Tháng_XK", "Group", "Type", "Store_RP", "Store_rank",
        "Region", "Color_group", "Form", "Style", "Size", "Hành_Động",
        "Cửa_Hàng_Đối_Tác", "Trang_Thai", "Status", "Gender", "Product_group",
        "Product_type",
    ])

    _inv_cache.update({"df": df, "mtime": mtime, "path": str(path)})
    return df


def _agg_records(df, keys, sort_by="ton", limit=None, extra_aggs=None):
    aggs = {
        "count": ("MaHang", "nunique"),
        "ton": ("Ton_Size", "sum"),
        "ban": ("Ban_Size", "sum"),
        "chuyen": ("SL_Đề_Xuất", "sum"),
        "ton_sau": ("Ton_Sau_Dieu_Chuyen", "sum"),
    }
    if extra_aggs:
        aggs.update(extra_aggs)
    out = df.groupby(keys, dropna=False).agg(**aggs).reset_index()
    if sort_by in out.columns:
        out = out.sort_values(sort_by, ascending=False)
    if limit:
        out = out.head(limit)
    return out.to_dict("records")


def build_summary(df):
    """Build dashboard/report summaries expected by web_duyet_dieu_chuyen.py."""
    if df.empty:
        empty = []
        return {
            "cards": [
                {"icon": "🏷️", "label": "Total SKUs", "value": 0},
                {"icon": "📦", "label": "Total Stock", "value": 0},
                {"icon": "💰", "label": "Total Sales", "value": 0},
                {"icon": "🏪", "label": "Stores", "value": 0},
                {"icon": "🗺️", "label": "Regions", "value": 0},
                {"icon": "🔀", "label": "Transfer Orders", "value": 0},
                {"icon": "📤", "label": "Transfer Qty", "value": 0},
            ],
            "type_rows": empty, "region_rows": empty, "tt_rows": empty,
            "store_rows": empty, "sku_rows": empty, "prod_rows": empty,
            "pg_rows": empty, "gender_rows": empty, "color_rows": empty,
            "form_rows": empty, "style_rows": empty,
        }

    total_ton = df["Ton_Size"].sum()
    total_ban = df["Ban_Size"].sum()
    transfer_rows = df[df["SL_Đề_Xuất"] > 0]

    type_rows = _agg_records(df, ["Type"], sort_by="Type")
    region_rows = _agg_records(df, ["Region"], extra_aggs={"stores": ("Store_RP", "nunique")})
    tt_rows = _agg_records(df, ["Trang_Thai"], sort_by="count")
    store_rows = _agg_records(
        df, ["Region", "Store_RP"],
        extra_aggs={"Store_rank": ("Store_rank", "first")},
        limit=100,
    )
    sku_rows = _agg_records(
        df, ["MaHang", "Operation", "Group", "Report_item_name"],
        limit=200,
    )
    prod_rows = sku_rows[:20]
    pg_rows = _agg_records(df, ["Report_item_name"], limit=20)
    gender_rows = _agg_records(df, ["Gender"]) if "Gender" in df.columns else []
    color_rows = _agg_records(df, ["Color_group"], limit=10)
    form_rows = _agg_records(df, ["Form"], limit=10)
    style_rows = _agg_records(df, ["Style"], limit=10)

    return {
        "cards": [
            {"icon": "🏷️", "label": "Total SKUs", "value": df["MaHang"].nunique()},
            {"icon": "📦", "label": "Total Stock", "value": total_ton},
            {"icon": "💰", "label": "Total Sales", "value": total_ban},
            {"icon": "🏪", "label": "Stores", "value": df["Store_RP"].nunique()},
            {"icon": "🗺️", "label": "Regions", "value": df["Region"].nunique()},
            {"icon": "🔀", "label": "Transfer Orders", "value": len(transfer_rows)},
            {"icon": "📤", "label": "Transfer Qty", "value": transfer_rows["SL_Đề_Xuất"].sum()},
        ],
        "type_rows": type_rows,
        "region_rows": region_rows,
        "tt_rows": tt_rows,
        "store_rows": store_rows,
        "sku_rows": sku_rows,
        "prod_rows": prod_rows,
        "pg_rows": pg_rows,
        "gender_rows": gender_rows,
        "color_rows": color_rows,
        "form_rows": form_rows,
        "style_rows": style_rows,
    }


TRANSFER_RENAME = {
    "MaHang": "Ma hang",
    "Từ_Cửa_Hàng": "CH Nguon",
    "Từ_Vùng": "Khu vuc Nguon",
    "Đến_Cửa_Hàng": "CH Nhan",
    "Đến_Vùng": "Khu vuc Nhan",
    "Số_Lượng": "So luong chuyen",
    "Cung_KV": "Loai dieu chuyen",
}
TRANSFER_COLS = [
    "Group", "Ma hang", "Operation", "Size", "CH Nguon", "Khu vuc Nguon",
    "Trang_Thai_Nguon", "So luong chuyen", "CH Nhan", "Khu vuc Nhan",
    "Trang_Thai_Nhan", "Loai dieu chuyen",
]


def load_transfer_orders(source=None):
    """Lock-aware loader — mirrors the retry logic in load_inventory()."""
    global _tr_cache
    path = Path(source or get_db_source())

    # Serve stale cache while DB is being rebuilt
    if is_db_rebuilding() and _tr_cache["df"] is not None:
        return _tr_cache["df"]

    if not path.exists():
        if _tr_cache["df"] is not None:
            return _tr_cache["df"]
        raise FileNotFoundError(f"File khong ton tai: {path}")

    mtime = path.stat().st_mtime
    if _tr_cache["df"] is not None and _tr_cache["mtime"] == mtime and _tr_cache["path"] == str(path):
        return _tr_cache["df"]

    # Retry loop
    last_exc = None
    for attempt in range(3):
        try:
            df = _read_excel(path, TRANSFER_SHEET, dtype=object)
            last_exc = None
            break
        except Exception as exc:
            last_exc = exc
            if attempt < 2:
                time.sleep(1.0)

    if last_exc is not None:
        if _tr_cache["df"] is not None:
            return _tr_cache["df"]
        raise last_exc

    df.columns = [clean(c) for c in df.columns]
    df = df.rename(columns=TRANSFER_RENAME)
    _ensure_cols(df, TRANSFER_COLS)

    df = df[TRANSFER_COLS].copy()
    _num(df, ["So luong chuyen"])
    for c in TRANSFER_COLS:
        if c != "So luong chuyen":
            df[c] = df[c].map(clean)

    df["Source row"] = range(2, len(df) + 2)
    df["order_id"] = df.apply(lambda r: hashlib.sha1("|".join([
        clean(r[c]).upper() if c != "So luong chuyen" else f"{float(r[c]):.6f}"
        for c in TRANSFER_COLS
    ] + [str(r["Source row"])]).encode("utf-8")).hexdigest()[:16], axis=1)

    _tr_cache.update({"df": df, "mtime": mtime, "path": str(path)})
    return df


def load_review_state():
    if not REVIEW_FILE.exists():
        return pd.DataFrame(columns=["order_id", "review_status", "reviewed_by", "reviewed_at", "review_note"])
    return pd.read_csv(REVIEW_FILE, dtype=object, keep_default_na=False).fillna("")


def save_review_state(df):
    df.to_csv(REVIEW_FILE, index=False, encoding="utf-8-sig")


def merge_transfer_with_review(source=None):
    orders = load_transfer_orders(source)
    reviews = load_review_state()
    merged = orders.merge(reviews, on="order_id", how="left")
    merged["review_status"] = merged["review_status"].replace("", pd.NA).fillna("pending")
    for c in ["reviewed_by", "reviewed_at", "review_note"]:
        merged[c] = merged[c].fillna("")

    try:
        inv = load_inventory(source)
        inv_map = inv[["MaHang", "Report_item_name"]].drop_duplicates().set_index("MaHang")["Report_item_name"].to_dict()
        merged["Report_item_name"] = merged["Ma hang"].map(inv_map).fillna("Unknown")
    except Exception:
        merged["Report_item_name"] = "Unknown"
    return merged


def update_review(order_ids, status, actor_name, note=""):
    reviews = load_review_state().set_index("order_id", drop=False)
    ts = now_str()
    audit_rows = []
    for oid in order_ids:
        oid = clean(oid)
        if not oid:
            continue
        old = "pending"
        if oid in reviews.index:
            old = clean(reviews.loc[oid, "review_status"]) or "pending"
        reviews.loc[oid] = {
            "order_id": oid,
            "review_status": status,
            "reviewed_by": actor_name,
            "reviewed_at": ts if status != "pending" else "",
            "review_note": clean(note),
        }
        audit_rows.append({"order_id": oid, "old": old, "new": status, "by": actor_name, "at": ts, "note": clean(note)})

    save_review_state(reviews.reset_index(drop=True))
    if audit_rows:
        audit = pd.DataFrame(audit_rows)
        if AUDIT_FILE.exists():
            audit = pd.concat([pd.read_csv(AUDIT_FILE, dtype=object, keep_default_na=False), audit], ignore_index=True)
        audit.to_csv(AUDIT_FILE, index=False, encoding="utf-8-sig")
    return len(audit_rows)


def recent_audit_rows(limit=50):
    if not AUDIT_FILE.exists():
        return []
    df = pd.read_csv(AUDIT_FILE, dtype=object, keep_default_na=False).fillna("")
    if df.empty:
        return []
    if "at" in df.columns:
        df = df.sort_values("at", ascending=False)
    return df.head(limit).to_dict("records")

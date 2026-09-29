import os
import sys
import io
import pandas as pd
import datetime
import calendar
import duckdb

# Force stdout/stderr to use UTF-8 to prevent charmap/unicode encode errors on Windows terminal
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='ignore')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='ignore')

# Define database and output paths
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # 01.Python_Projects (dung_chung)
from dung_chung import duong_dan  # noqa: E402

DATABASE_PATH = duong_dan.duckdb_report_ap            # tao boi 02_XuLyDuLieu/doanh_thu.py
OUTPUT_DIR = duong_dan.thu_muc_ket_qua("BaoCao_QLKD_Tuan")   # 04_KetQua/BaoCao_QLKD_Tuan

# The columns of Database (Aggregated weekly/monthly metrics per Store-Brand)
COLUMNS_DB = [
    # Metadata
    "Mã_CH", "Tên_Cửa_Hàng", "Thương_Hiệu", "Cụm_Cửa_Hàng",
    
    # Targets
    "Target_Month", "Target_Week",
    
    # Revenue (Doanh thu tổng)
    "Revenue_WTD", "Revenue_MTD", "Revenue_LW", "Revenue_LM", "Revenue_LY_WTD", "Revenue_LY_MTD",
    
    # Revenue Retail (Doanh thu bán lẻ)
    "Revenue_Retail_WTD", "Revenue_Retail_MTD", "Revenue_Retail_LW", "Revenue_Retail_LM", "Revenue_Retail_LY_WTD", "Revenue_Retail_LY_MTD",
    
    # Revenue Contract (Doanh thu hợp đồng)
    "Revenue_Contract_WTD", "Revenue_Contract_MTD", "Revenue_Contract_LW", "Revenue_Contract_LM", "Revenue_Contract_LY_WTD", "Revenue_Contract_LY_MTD",
    
    # Bills Total (BILL chung)
    "Bills_Total_WTD", "Bills_Total_MTD", "Bills_Total_LW", "Bills_Total_LM", "Bills_Total_LY_WTD", "Bills_Total_LY_MTD",
    
    # Bills Store (Bill riêng)
    "Bills_Store_WTD", "Bills_Store_MTD", "Bills_Store_LW", "Bills_Store_LM", "Bills_Store_LY_WTD", "Bills_Store_LY_MTD",
    
    # Sold Qty (SL bán)
    "Sold_Qty_WTD", "Sold_Qty_MTD", "Sold_Qty_LW", "Sold_Qty_LM", "Sold_Qty_LY_WTD", "Sold_Qty_LY_MTD",
    
    # Exchange Qty (SL đổi)
    "Exchange_Qty_WTD", "Exchange_Qty_MTD", "Exchange_Qty_LW", "Exchange_Qty_LM", "Exchange_Qty_LY_WTD", "Exchange_Qty_LY_MTD"
]

HEADER_TRANSLATIONS = {
    # Metadata
    "Mã_CH": "Mã_CH",
    "Tên_Cửa_Hàng": "Tên_CH",
    "Thương_Hiệu": "Thương_Hiệu",
    "Cụm_Cửa_Hàng": "Cụm_CH",
    
    # Targets
    "Target_Month": "Target_Tháng",
    "Target_Week": "Target_Tuần",
    
    # Revenue (Doanh thu tổng)
    "Revenue_WTD": "DT_Tuần_Report",
    "Revenue_MTD": "DT_Lũy_Kế_Tháng",
    "Revenue_LW": "DT_Tuần_Trước",
    "Revenue_LM": "DT_Tháng_Trước",
    "Revenue_LY_WTD": "DT_Cùng_Kỳ_Tuần",
    "Revenue_LY_MTD": "DT_Cùng_Kỳ_Tháng",
    
    # Revenue Retail (Doanh thu bán lẻ)
    "Revenue_Retail_WTD": "DT_Sales_Tuần_Report",
    "Revenue_Retail_MTD": "DT_Sales_Lũy_Kế_Tháng",
    "Revenue_Retail_LW": "DT_Sales_Tuần_Trước",
    "Revenue_Retail_LM": "DT_Sales_Tháng_Trước",
    "Revenue_Retail_LY_WTD": "DT_Sales_Cùng_Kỳ_Tuần",
    "Revenue_Retail_LY_MTD": "DT_Sales_Cùng_Kỳ_Tháng",
    
    # Revenue Contract (Doanh thu hợp đồng)
    "Revenue_Contract_WTD": "DT_HD_Tuần_Report",
    "Revenue_Contract_MTD": "DT_HD_Lũy_Kế_Tháng",
    "Revenue_Contract_LW": "DT_HD_Tuần_Trước",
    "Revenue_Contract_LM": "DT_HD_Tháng_Trước",
    "Revenue_Contract_LY_WTD": "DT_HD_Cùng_Kỳ_Tuần",
    "Revenue_Contract_LY_MTD": "DT_HD_Cùng_Kỳ_Tháng",
    
    # Bills Total (BILL chung)
    "Bills_Total_WTD": "Tong_Bill_Tuần_Report",
    "Bills_Total_MTD": "Tong_Bill_Lũy_Kế_Tháng",
    "Bills_Total_LW": "Tong_Bill_Tuần_Trước",
    "Bills_Total_LM": "Tong_Bill_Tháng_Trước",
    "Bills_Total_LY_WTD": "Tong_Bill_Cùng_Kỳ_Tuần",
    "Bills_Total_LY_MTD": "Tong_Bill_Cùng_Kỳ_Tháng",
    
    # Bills Store (Bill riêng)
    "Bills_Store_WTD": "Bill_Tuần_Report",
    "Bills_Store_MTD": "Bill_Lũy_Kế_Tháng",
    "Bills_Store_LW": "Bill_Tuần_Trước",
    "Bills_Store_LM": "Bill_Tháng_Trước",
    "Bills_Store_LY_WTD": "Bill_Cùng_Kỳ_Tuần",
    "Bills_Store_LY_MTD": "Bill_Cùng_Kỳ_Tháng",
    
    # Sold Qty (SL bán)
    "Sold_Qty_WTD": "SLB_Tuần_Report",
    "Sold_Qty_MTD": "SLB_Lũy_Kế_Tháng",
    "Sold_Qty_LW": "SLB_Tuần_Trước",
    "Sold_Qty_LM": "SLB_Tháng_Trước",
    "Sold_Qty_LY_WTD": "SLB_Cùng_Kỳ_Tuần",
    "Sold_Qty_LY_MTD": "SLB_Cùng_Kỳ_Tháng",
    
    # Exchange Qty (SL đổi)
    "Exchange_Qty_WTD": "SLD_Tuần_Report",
    "Exchange_Qty_MTD": "SLD_Lũy_Kế_Tháng",
    "Exchange_Qty_LW": "SLD_Tuần_Trước",
    "Exchange_Qty_LM": "SLD_Tháng_Trước",
    "Exchange_Qty_LY_WTD": "SLD_Cùng_Kỳ_Tuần",
    "Exchange_Qty_LY_MTD": "SLD_Cùng_Kỳ_Tháng"
}

def get_all_stores(df_rev, df_bill, df_tgt):
    """Builds a unified list of store-brands for the entire company directly from CSV databases."""
    raw_map = {} # sc -> sname
    region_map = {} # sc -> region
    
    # 1. Scan Target.csv
    if not df_tgt.empty:
        for _, row in df_tgt.dropna(subset=["Store_code"]).iterrows():
            sc = str(row["Store_code"]).strip()
            sname = str(row["Store_RP"]).strip() if pd.notnull(row["Store_RP"]) else sc
            region = str(row["Region"]).strip() if pd.notnull(row["Region"]) else "Khác"
            raw_map[sc] = sname
            region_map[sc] = region
            
    # 2. Scan Revenue.csv
    if not df_rev.empty:
        for _, row in df_rev.dropna(subset=["Store_code"]).iterrows():
            sc = str(row["Store_code"]).strip()
            sname = str(row["Store_RP"]).strip() if pd.notnull(row["Store_RP"]) else sc
            region = str(row["Region"]).strip() if pd.notnull(row["Region"]) else "Khác"
            if sc not in raw_map:
                raw_map[sc] = sname
            if sc not in region_map:
                region_map[sc] = region
                
    # 3. Scan Bill_sales.csv
    if not df_bill.empty:
        for _, row in df_bill.dropna(subset=["Store_code"]).iterrows():
            sc = str(row["Store_code"]).strip()
            sname = str(row["Store_RP"]).strip() if pd.notnull(row["Store_RP"]) else sc
            region = str(row["Region"]).strip() if pd.notnull(row["Region"]) else "Khác"
            if sc not in raw_map:
                raw_map[sc] = sname
            if sc not in region_map:
                region_map[sc] = region
                
    stores_list = []
    seen_keys = set() # (Brand, Store_code)
    
    # Check Target.csv for stores with AP or FLD target
    if not df_tgt.empty:
        for _, row in df_tgt.dropna(subset=["Store_code"]).iterrows():
            sc = str(row["Store_code"]).strip()
            sname = raw_map.get(sc, sc)
            region = region_map.get(sc, "Khác")
            
            # Check AP
            has_ap = pd.notnull(row.get("Chỉ tiêu AP")) and row.get("Chỉ tiêu AP") > 0
            if has_ap and ("AP", sc) not in seen_keys:
                stores_list.append({
                    "Ma_CH": f"AP_{sc}",
                    "Tên_Cửa_Hàng": sname,
                    "Thương_Hiệu": "AP",
                    "Cụm_Cửa_Hàng": region,
                    "Raw_Code": sc
                })
                seen_keys.add(("AP", sc))
                
            # Check FLD
            has_fld = pd.notnull(row.get("Chỉ tiêu FLD")) and row.get("Chỉ tiêu FLD") > 0
            if has_fld and ("AM", sc) not in seen_keys:
                stores_list.append({
                    "Ma_CH": f"AM_{sc}",
                    "Tên_Cửa_Hàng": sname,
                    "Thương_Hiệu": "AM",
                    "Cụm_Cửa_Hàng": region,
                    "Raw_Code": sc
                })
                seen_keys.add(("AM", sc))
                
    # Check Revenue.csv and Bill_sales.csv for any other stores or transactions
    if not df_rev.empty:
        for _, row in df_rev.dropna(subset=["Store_code"]).iterrows():
            sc = str(row["Store_code"]).strip()
            if sc == "Unknown" or sc == "nan" or not sc:
                continue
            sname = raw_map.get(sc, sc)
            region = region_map.get(sc, "Khác")
            
            # Check AP revenue columns
            has_ap_rev = (pd.notnull(row.get("DT AP")) and row.get("DT AP") > 0) or \
                          (pd.notnull(row.get("DT AP NAM")) and row.get("DT AP NAM") > 0) or \
                          (pd.notnull(row.get("DT PIE")) and row.get("DT PIE") > 0) or \
                          (pd.notnull(row.get("DT AP LADIES")) and row.get("DT AP LADIES") > 0)
            if has_ap_rev and ("AP", sc) not in seen_keys:
                stores_list.append({
                    "Ma_CH": f"AP_{sc}",
                    "Tên_Cửa_Hàng": sname,
                    "Thương_Hiệu": "AP",
                    "Cụm_Cửa_Hàng": region,
                    "Raw_Code": sc
                })
                seen_keys.add(("AP", sc))
                
            # Check FLD revenue
            has_fld_rev = pd.notnull(row.get("DT FLD")) and row.get("DT FLD") > 0
            if has_fld_rev and ("AM", sc) not in seen_keys:
                stores_list.append({
                    "Ma_CH": f"AM_{sc}",
                    "Tên_Cửa_Hàng": sname,
                    "Thương_Hiệu": "AM",
                    "Cụm_Cửa_Hàng": region,
                    "Raw_Code": sc
                })
                seen_keys.add(("AM", sc))
                
    # Fallback scan for all unique codes in df_rev and df_bill
    all_raw_stores = set(df_rev["Store_code"].dropna().unique()).union(set(df_bill["Store_code"].dropna().unique()))
    for sc in all_raw_stores:
        sc = str(sc).strip()
        if sc == "Unknown" or sc == "nan" or not sc:
            continue
        sname = raw_map.get(sc, sc)
        region = region_map.get(sc, "Khác")
        
        if ("AP", sc) not in seen_keys:
            stores_list.append({
                "Ma_CH": f"AP_{sc}",
                "Tên_Cửa_Hàng": sname,
                "Thương_Hiệu": "AP",
                "Cụm_Cửa_Hàng": region,
                "Raw_Code": sc
            })
            seen_keys.add(("AP", sc))
            
        if ("AM", sc) not in seen_keys:
            stores_list.append({
                "Ma_CH": f"AM_{sc}",
                "Tên_Cửa_Hàng": sname,
                "Thương_Hiệu": "AM",
                "Cụm_Cửa_Hàng": region,
                "Raw_Code": sc
            })
            seen_keys.add(("AM", sc))
            
    return stores_list

def prompt_dates():
    """Prompts user for Start Date and End Date or uses command line args."""
    if len(sys.argv) == 3:
        start_str, end_str = sys.argv[1], sys.argv[2]
        try:
            start_date = datetime.datetime.strptime(start_str, "%Y-%m-%d").date()
            end_date = datetime.datetime.strptime(end_str, "%Y-%m-%d").date()
            return start_date, end_date
        except ValueError:
            print("Lỗi: Định dạng ngày đối số dòng lệnh không hợp lệ! Vui lòng dùng YYYY-MM-DD.")
            sys.exit(1)
            
    print("=== CHƯƠNG TRÌNH XUẤT DATABASE BÁO CÁO TUẦN ===")
    while True:
        start_str = input("Nhập ngày bắt đầu tuần báo cáo (YYYY-MM-DD, ví dụ 2026-06-14): ").strip()
        try:
            start_date = datetime.datetime.strptime(start_str, "%Y-%m-%d").date()
            break
        except ValueError:
            print("Ngày không hợp lệ! Vui lòng nhập lại.")
            
    while True:
        end_str = input("Nhập ngày kết thúc tuần báo cáo (YYYY-MM-DD, ví dụ 2026-06-20): ").strip()
        try:
            end_date = datetime.datetime.strptime(end_str, "%Y-%m-%d").date()
            if end_date < start_date:
                print("Ngày kết thúc phải lớn hơn hoặc bằng ngày bắt đầu!")
                continue
            break
        except ValueError:
            print("Ngày không hợp lệ! Vui lòng nhập lại.")
            
    return start_date, end_date

def calculate_date_periods(start_date, end_date):
    """Calculates all target date periods based on start and end dates."""
    n_days = (end_date - start_date).days + 1
    
    # CW: Current Week
    cw_dates = [start_date + datetime.timedelta(days=x) for x in range(n_days)]
    
    # LW: Last Week
    lw_start = start_date - datetime.timedelta(days=n_days)
    lw_dates = [lw_start + datetime.timedelta(days=x) for x in range(n_days)]
    
    # LY_W: Same Week Last Year
    try:
        ly_start = start_date.replace(year=start_date.year - 1)
        ly_end = end_date.replace(year=end_date.year - 1)
    except ValueError:
        ly_start = (start_date - datetime.timedelta(days=1)).replace(year=start_date.year - 1)
        ly_end = (end_date - datetime.timedelta(days=1)).replace(year=end_date.year - 1)
    ly_w_dates = [ly_start + datetime.timedelta(days=x) for x in range(n_days)]
    
    # MTD_CW: Month-to-Date Current
    mtd_start = datetime.date(end_date.year, end_date.month, 1)
    mtd_cw_dates = [mtd_start + datetime.timedelta(days=x) for x in range((end_date - mtd_start).days + 1)]
    
    # MTD_LY: Month-to-Date Last Year
    mtd_ly_year = end_date.year - 1
    mtd_ly_month = end_date.month
    mtd_ly_start = datetime.date(mtd_ly_year, mtd_ly_month, 1)
    try:
        mtd_ly_end = end_date.replace(year=mtd_ly_year)
    except ValueError:
        mtd_ly_end = datetime.date(mtd_ly_year, 2, 28)
    mtd_ly_dates = [mtd_ly_start + datetime.timedelta(days=x) for x in range((mtd_ly_end - mtd_ly_start).days + 1)]
    
    # LM: Last Month (Full Month)
    first_of_this_month = datetime.date(end_date.year, end_date.month, 1)
    last_of_prev_month = first_of_this_month - datetime.timedelta(days=1)
    first_of_prev_month = datetime.date(last_of_prev_month.year, last_of_prev_month.month, 1)
    lm_dates = [first_of_prev_month + datetime.timedelta(days=x) for x in range((last_of_prev_month - first_of_prev_month).days + 1)]
    
    # LY_Month: Same Month Last Year (Full Month)
    first_of_ly_month = datetime.date(end_date.year - 1, end_date.month, 1)
    days_in_ly_month = calendar.monthrange(end_date.year - 1, end_date.month)[1]
    last_of_ly_month = datetime.date(end_date.year - 1, end_date.month, days_in_ly_month)
    ly_month_dates = [first_of_ly_month + datetime.timedelta(days=x) for x in range((last_of_ly_month - first_of_ly_month).days + 1)]
    
    # Target Month full days (Current Month)
    days_in_current_month = calendar.monthrange(end_date.year, end_date.month)[1]
    current_month_dates = [mtd_start + datetime.timedelta(days=x) for x in range(days_in_current_month)]
    
    return {
        "cw": cw_dates,
        "lw": lw_dates,
        "ly_w": ly_w_dates,
        "mtd_cw": mtd_cw_dates,
        "mtd_ly": mtd_ly_dates,
        "lm": lm_dates,
        "ly_month": ly_month_dates,
        "current_month": current_month_dates
    }

def process_daily_database(dates_list, all_stores, df_rev, df_bill, df_tgt):
    """Consolidates metrics for every date and store combination (All History Daily) using fast dictionary lookups."""
    # 1. Convert DataFrames to dicts for fast lookups
    df_rev_dict = {}
    for _, r in df_rev.iterrows():
        day_val = str(r["Ngày"]).strip()
        sc_val = str(r["Store_code"]).strip()
        df_rev_dict[(day_val, sc_val)] = r
        
    df_bill_dict = {}
    for _, r in df_bill.iterrows():
        day_val = str(r["Ngày"]).strip()
        sc_val = str(r["Store_code"]).strip()
        df_bill_dict[(day_val, sc_val)] = r
        
    df_tgt_dict = {}
    for _, r in df_tgt.iterrows():
        if pd.notnull(r["Năm"]) and pd.notnull(r["Tháng"]):
            yr_val = int(r["Năm"])
            mo_val = int(r["Tháng"])
            sc_val = str(r["Store_code"]).strip()
            df_tgt_dict[(yr_val, mo_val, sc_val)] = r
        
    rows = []
    
    for day in dates_list:
        day_str = day.strftime("%Y-%m-%d")
        year_val = day.year
        month_val = day.month
        
        for store in all_stores:
            ma_ch = store["Ma_CH"]
            brand = store["Thương_Hiệu"]
            ten_ch = store["Tên_Cửa_Hàng"]
            cum_ch = store["Cụm_Cửa_Hàng"]
            csv_store_code = store["Raw_Code"]
            
            # 1. Fetch Revenue
            dt_retail = 0
            dt_contract = 0
            
            rev_row = df_rev_dict.get((day_str, csv_store_code))
            if rev_row is not None:
                if brand == "AP":
                    dt_ap = rev_row["DT AP"] if pd.notnull(rev_row["DT AP"]) else 0
                    dt_ap_ladies = rev_row["DT AP LADIES"] if pd.notnull(rev_row["DT AP LADIES"]) else 0
                    dt_retail = dt_ap + dt_ap_ladies
                    dt_contract = rev_row["Số tiền HĐ"] if pd.notnull(rev_row["Số tiền HĐ"]) else 0
                else:
                    dt_retail = rev_row["DT FLD"] if pd.notnull(rev_row["DT FLD"]) else 0
                    dt_contract = 0
            
            dt_total = dt_retail + dt_contract
            
            # 2. Fetch Bills & Quantities
            bills_brand = 0  # Total actual bills of the store (for WTD)
            bills_store = 0  # Brand-specific bills (for all periods)
            sold_qty = 0
            exchange_qty = 0
            
            bill_row = df_bill_dict.get((day_str, csv_store_code))
            if bill_row is not None:
                # Both brands get the total actual bills of the store
                bills_brand = bill_row["Tổng số bill (số chứng từ)"] if pd.notnull(bill_row["Tổng số bill (số chứng từ)"]) else 0
                
                if brand == "AP":
                    # Brand-specific bills for AP
                    bills_store = bill_row["Số bill AP/Pie"] if pd.notnull(bill_row["Số bill AP/Pie"]) else 0
                    sold_qty = bill_row["SL bán AP + PIE"] if pd.notnull(bill_row["SL bán AP + PIE"]) else 0
                    exchange_qty = bill_row["Số lượng đổi"] if pd.notnull(bill_row["Số lượng đổi"]) else 0
                else:
                    # Brand-specific bills for AM (FLD)
                    bills_store = bill_row["Số bill FLD"] if pd.notnull(bill_row["Số bill FLD"]) else 0
                    sold_qty = bill_row["SL bán FLD (Anamai + Bonjour)"] if pd.notnull(bill_row["SL bán FLD (Anamai + Bonjour)"]) else 0
                    exchange_qty = 0
            
            # 3. Fetch Targets
            target_daily = 0
            tgt_row = df_tgt_dict.get((year_val, month_val, csv_store_code))
            if tgt_row is not None:
                num_days = tgt_row["Số ngày"] if pd.notnull(tgt_row["Số ngày"]) and tgt_row["Số ngày"] > 0 else 30
                if brand == "AP":
                    ch_ap = tgt_row["Chỉ tiêu AP"] if pd.notnull(tgt_row["Chỉ tiêu AP"]) else 0
                    target_daily = ch_ap / num_days
                else:
                    ch_fld = tgt_row["Chỉ tiêu FLD"] if pd.notnull(tgt_row["Chỉ tiêu FLD"]) else 0
                    target_daily = ch_fld / num_days
            
            rows.append({
                "Ngày": day,
                "Mã_CH_BaoCao": ma_ch,
                "Tên_Cửa_Hàng": ten_ch,
                "Thương_Hiệu": brand,
                "Cụm_Cửa_Hàng": cum_ch,
                "DT_Retail": dt_retail,
                "DT_Contract": dt_contract,
                "DT_Total": dt_total,
                "Target_Daily": target_daily,
                "Bills_Total": bills_brand,
                "Bills_Store": bills_store,
                "Sold_Qty": sold_qty,
                "Exchange_Qty": exchange_qty
            })
            
    return pd.DataFrame(rows)

def main():
    start_date, end_date = prompt_dates()
    print(f"\nKhoảng ngày chọn: {start_date} -> {end_date}")
    
    # 1. Load DuckDB tables
    print("Đang đọc các bảng từ database DuckDB...")
    try:
        conn = duckdb.connect(DATABASE_PATH)
        df_rev = conn.execute("SELECT * FROM revenue").df()
        df_bill = conn.execute("SELECT * FROM bill_sales").df()
        df_tgt = conn.execute("SELECT * FROM target").df()
        conn.close()
    except Exception as e:
        print(f"Lỗi đọc database DuckDB: {e}")
        sys.exit(1)
        
    # 2. Build complete store list directly from DuckDB data
    print("Đang tổng hợp danh sách tất cả cửa hàng trong hệ thống trực tiếp từ database...")
    all_stores = get_all_stores(df_rev, df_bill, df_tgt)
    print(f"Tổng số cửa hàng/thương hiệu toàn công ty: {len(all_stores)}")
    
    # 3. Calculate target dates for filtering
    print("Đang tính toán các mốc ngày...")
    periods = calculate_date_periods(start_date, end_date)
    
    # 4. Build full daily history database in memory (to calculate aggregated metrics)
    print("Đang xây dựng cơ sở dữ liệu lịch sử tổng hợp trong bộ nhớ...")
    rev_dates = pd.to_datetime(df_rev["Ngày"]).dt.date.unique()
    all_hist_dates = sorted(list(rev_dates))
    
    # Process full daily history
    df_daily_hist = process_daily_database(all_hist_dates, all_stores, df_rev, df_bill, df_tgt)
    
    # 5. Aggregate data per store-brand for the selected periods
    print("Đang tổng hợp các chỉ số tuần/tháng/cùng kỳ cho từng cửa hàng...")
    
    # Convert df_daily_hist "Ngày" back to date object if not already
    df_daily_hist["Ngày"] = pd.to_datetime(df_daily_hist["Ngày"]).dt.date
    
    # We will compute the aggregated metrics for each store-brand
    agg_rows = []
    
    # Period date list helpers
    cw = periods["cw"]
    lw = periods["lw"]
    ly_w = periods["ly_w"]
    mtd = periods["mtd_cw"]
    mtd_ly = periods["mtd_ly"]
    lm = periods["lm"]
    ly_month = periods["ly_month"]
    curr_month = periods["current_month"]
    
    for store in all_stores:
        ma_ch = store["Ma_CH"]
        ten_ch = store["Tên_Cửa_Hàng"]
        brand = store["Thương_Hiệu"]
        cum_ch = store["Cụm_Cửa_Hàng"]
        
        df_store = df_daily_hist[df_daily_hist["Mã_CH_BaoCao"] == ma_ch]
        
        # Helper to sum column over date range
        def get_sum(col, dates):
            return df_store[df_store["Ngày"].isin(dates)][col].sum()
            
        row_agg = {
            "Mã_CH": ma_ch,
            "Tên_Cửa_Hàng": ten_ch,
            "Thương_Hiệu": brand,
            "Cụm_Cửa_Hàng": cum_ch,
            
            "Target_Month": get_sum("Target_Daily", curr_month),
            "Revenue_MTD": get_sum("DT_Total", mtd),
            "Target_Week": get_sum("Target_Daily", cw),
            "Revenue_WTD": get_sum("DT_Total", cw),
            "Revenue_LY_MTD": get_sum("DT_Total", mtd_ly),
            "Revenue_LW": get_sum("DT_Total", lw),
            "Sold_Qty_WTD": get_sum("Sold_Qty", cw),
            "Bills_Total_WTD": get_sum("Bills_Total", cw),
            "Bills_Total_MTD": get_sum("Bills_Total", mtd),
            "Bills_Total_LW": get_sum("Bills_Total", lw),
            "Bills_Total_LM": get_sum("Bills_Total", lm),
            "Bills_Total_LY_WTD": get_sum("Bills_Total", ly_w),
            "Bills_Total_LY_MTD": get_sum("Bills_Total", mtd_ly),
            "Revenue_Retail_WTD": get_sum("DT_Retail", cw),
            "Revenue_Contract_MTD": get_sum("DT_Contract", mtd),
            "Revenue_Contract_LY_MTD": get_sum("DT_Contract", mtd_ly),
            "Bills_Store_MTD": get_sum("Bills_Store", mtd),
            "Bills_Store_WTD": get_sum("Bills_Store", cw),
            "Revenue_Retail_MTD": get_sum("DT_Retail", mtd),
            "Revenue_Contract_WTD": get_sum("DT_Contract", cw),
            "Revenue_Contract_LW": get_sum("DT_Contract", lw),
            "Revenue_Contract_LY_WTD": get_sum("DT_Contract", ly_w),
            "Revenue_Contract_LM": get_sum("DT_Contract", lm),
            "Revenue_Retail_LW": get_sum("DT_Retail", lw),
            "Revenue_Retail_LY_WTD": get_sum("DT_Retail", ly_w),
            "Revenue_Retail_LM": get_sum("DT_Retail", lm),
            "Bills_Store_LW": get_sum("Bills_Store", lw),
            "Bills_Store_LY_WTD": get_sum("Bills_Store", ly_w),
            "Bills_Store_LM": get_sum("Bills_Store", lm),
            "Sold_Qty_MTD": get_sum("Sold_Qty", mtd),
            "Sold_Qty_LW": get_sum("Sold_Qty", lw),
            "Sold_Qty_LY_WTD": get_sum("Sold_Qty", ly_w),
            "Sold_Qty_LM": get_sum("Sold_Qty", lm),
            "Exchange_Qty_WTD": get_sum("Exchange_Qty", cw),
            "Exchange_Qty_MTD": get_sum("Exchange_Qty", mtd),
            "Exchange_Qty_LW": get_sum("Exchange_Qty", lw),
            "Exchange_Qty_LY_WTD": get_sum("Exchange_Qty", ly_w),
            "Exchange_Qty_LM": get_sum("Exchange_Qty", lm),
            "Revenue_LM": get_sum("DT_Total", lm),
            "Revenue_LY_WTD": get_sum("DT_Total", ly_w),
            "Revenue_Retail_LY_MTD": get_sum("DT_Retail", mtd_ly),
            "Bills_Store_LY_MTD": get_sum("Bills_Store", mtd_ly),
            "Sold_Qty_LY_MTD": get_sum("Sold_Qty", mtd_ly),
            "Exchange_Qty_LY_MTD": get_sum("Exchange_Qty", mtd_ly)
        }
        agg_rows.append(row_agg)
        
    df_agg_db = pd.DataFrame(agg_rows)[COLUMNS_DB]
    
    # Save the aggregated database to CSV file
    df_agg_db_translated = df_agg_db.rename(columns=HEADER_TRANSLATIONS)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filename = f"Report_QLKD_{start_date.strftime('%d%m%y')}-{end_date.strftime('%d%m%y')}.csv"
    agg_db_csv_path = os.path.join(OUTPUT_DIR, filename)
    try:
        df_agg_db_translated.to_csv(agg_db_csv_path, index=False, encoding="utf-8-sig")
        print(f"Đã lưu database tổng hợp ra file CSV: {agg_db_csv_path}")
    except PermissionError:
        print(f"CẢNH BÁO: Không thể ghi đè file CSV {agg_db_csv_path} vì file đang được mở trong Excel hoặc chương trình khác. Vui lòng đóng file và chạy lại nếu cần cập nhật file này.")
    
    print("\n=== HOÀN THÀNH XUẤT DATABASE CSV THÀNH CÔNG! ===")

if __name__ == "__main__":
    main()

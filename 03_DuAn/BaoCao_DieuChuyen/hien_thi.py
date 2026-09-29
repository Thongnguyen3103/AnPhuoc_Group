# -*- coding: utf-8 -*-
"""dc_display.py — Dựng nội dung Dashboard + đổi tên cột hiển thị (không phụ thuộc tkinter,
tách riêng để dễ test/tái sử dụng)."""
import datetime as dt
import dc_config as cfg
import dc_geo as geo_mod
import dc_compute as comp

# ---------------------------------------------------------------- Dựng nội dung Dashboard (Sheet 0)
def build_dashboard_kwargs(csv_filename, df_sku, sheet4_disp, all_stores_geo, scope_regions, df_store_size=None):
    n_sku = len(df_sku)
    n_lenh = len(sheet4_disp)
    tong_sl = int(sheet4_disp["SL Chuyển"].sum()) if n_lenh else 0
    tong_gt = int(sheet4_disp["Giá Trị Chuyển"].sum()) if n_lenh else 0
    ky_str = f"T{cfg.EVAL_MONTHS[0][1]:02d}/{cfg.EVAL_MONTHS[0][0]} → T{cfg.EVAL_MONTHS[-1][1]:02d}/{cfg.EVAL_MONTHS[-1][0]}"

    round_label = df_sku["Dot_chuyen"].mode().iloc[0] if n_sku else "Lần 1"
    current_lan = comp.parse_round_label(round_label) or "Lan1"
    round_moc_text = {"Lan1": "mốc 6 tháng", "Lan2": "mốc 9 tháng", "Lan3": "mốc 12 tháng"}[current_lan]
    run_info = dict(
        title=f"📦  BÁO CÁO ĐIỀU CHUYỂN HÀNG HÓA — ĐỢT {round_label}",
        current_lan=current_lan,
        left=[
            ("Ngày tạo báo cáo", dt.datetime.now().strftime("%d/%m/%Y %H:%M")),
            ("File CSV đầu vào", csv_filename),
            ("Kỳ đánh giá (3T)", ky_str),
        ],
        right=[
            ("Số SKU điều chuyển", n_sku),
            ("Tổng lệnh điều chuyển", n_lenh),
            ("Tổng SL chuyển thực tế", tong_sl),
            ("Tổng giá trị chuyển (VNĐ)", f"{tong_gt:,}"),
        ],
        banner=f"🔵  ĐANG CHẠY: {round_label} — áp dụng ngưỡng trạng thái theo {round_moc_text} (bảng Mục 1 bên dưới, cột tô vàng)",
    )

    # Bảng ngưỡng Mục 5.1 — đúng chiều tài liệu: hàng = trạng thái, cột = mốc tháng
    # trên kệ; ngưỡng ÁP THEO LẦN: Lần 1 → cột mốc 6 tháng, Lần 2 → mốc 9 tháng,
    # Lần 3 → mốc 12 tháng ("mã bán càng lâu phải đạt tỷ lệ càng cao").
    status_table = dict(
        headers=["Trạng thái mã", "Lần 1 (mốc 6 tháng)", "Lần 2 (mốc 9 tháng)",
                 "Lần 3 (mốc 12 tháng)", "Quy tắc điều chuyển"],
        current_lan=current_lan,
        rows=[
            ["Sắp hết hàng", "Trên 85%", "Trên 88%", "Trên 90%", "Chỉ gom về Top CH bán chạy"],
            ["Bán tốt", "65% – 85%", "70% – 88%", "75% – 90%", "Áp trần suất chia, không chia rộng"],
            ["Bán trung bình – chậm", "25% – dưới 65%", "30% – dưới 70%", "35% – dưới 75%", "Luân chuyển theo ma trận hiệu suất"],
            ["Bán rất chậm", "Dưới 25%", "Dưới 30%", "Dưới 35%", "Dừng luân chuyển, đề xuất CTKM/xả"],
        ],
    )

    abcd_table = dict(
        headers=["Nhóm hiệu suất", "Chỉ số hiệu suất (HS)", "Đặc điểm sức bán tại CH", "Đề xuất hành động"],
        rows=[
            ["A", "HS >= 1.20", "Sức bán vượt trội so với mức chuẩn toàn hệ thống",
             "Ưu tiên nhận hàng để nạp lại định mức / Nới cửa sổ size"],
            ["B", "0.80 <= HS < 1.20", "Sức bán đạt chuẩn ổn định",
             "Giữ hàng / Nhận bổ sung nhẹ khi gãy size chính"],
            ["C", "0.40 <= HS < 0.80", "Bán chậm hơn trung bình hệ thống",
             "Duy trì tồn kho tối thiểu, xuất bớt phần dư thừa"],
            ["D", "HS < 0.40 (hoặc 0 bán)", "Bán cực kỳ chậm hoặc không phát sinh bán trong kỳ 3T",
             "Xuất toàn bộ tồn kho hiện tại để đưa về cửa hàng bán tốt"],
        ],
    )

    regions_order = sorted([r for r in cfg.VALID_STORE_REGIONS if r in all_stores_geo["Region"].unique()])
    dist = geo_mod.build_region_distance_matrix(all_stores_geo, regions_order)
    region_matrix = dict(regions=regions_order, dist=dist)

    # Bảng cửa sổ size tiêu chuẩn (Phụ lục B): cửa sổ gốc tính từ dữ liệu bán thật
    # toàn hệ thống của danh mục phổ biến nhất trong đợt, sau đó DỊCH THEO ĐỘ LỆCH
    # VÙNG quy định tại Phụ lục B: Miền Trung thiên size NHỎ (−1 bậc), Miền Tây thiên
    # size LỚN (+2/+2/+3/+4 theo loại CH), TP.HCM/Đông Nam Bộ chuẩn, vùng khác theo TP.HCM.
    if not df_sku.empty and df_store_size is not None and not df_store_size.empty:
        cat_pk = df_sku.loc[df_sku["Ten_san_pham"] == df_sku["Ten_san_pham"].mode().iloc[0], "Combined_PK"]
        cat_name = df_sku["Ten_san_pham"].mode().iloc[0]
        cat_size_data = df_store_size[df_store_size["Combined_PK"].isin(cat_pk)]
        all_sizes = sorted(cat_size_data["Size"].dropna().unique().tolist())
        size_seq = comp.build_size_sequence(all_sizes, None, {})
        overall_weight = cat_size_data.groupby("Size")["Ban_3T"].sum()
        if overall_weight.sum() == 0:
            overall_weight = cat_size_data.groupby("Size")["Ton_hien_tai"].sum()
        weight_map = overall_weight.to_dict()
        bo_chinh = comp.bo_size_chinh(sorted(overall_weight.items(), key=lambda kv: -kv[1])) if overall_weight.sum() else size_seq
        n_bo_chinh = len(bo_chinh) or len(size_seq) or 4

        def _shift_window(window, offset):
            """Dịch cửa sổ theo số bậc size trên trục size_seq, kẹp trong dải của danh mục."""
            if not window or not offset:
                return window
            n = len(window)
            try:
                start = size_seq.index(window[0])
            except ValueError:
                return window
            new_start = max(0, min(start + offset, len(size_seq) - n))
            return size_seq[new_start:new_start + n]

        size_window_headers = ["Vùng", "Loại I (6 size)", "Loại II (5 size)", "Loại III (4 size)", "Loại IV (4 size)"]
        size_window_rows = []
        for region in regions_order:
            offsets = cfg.PHU_LUC_B_OFFSET.get(region, {})
            row = [region]
            for loai in ["I", "II", "III", "IV"]:
                n = comp.suat_chia_lookup(n_bo_chinh, loai)
                base_window = comp.best_window(size_seq, weight_map, n)
                window = _shift_window(base_window, offsets.get(loai, 0))
                row.append(", ".join(window) if window else "—")
            size_window_rows.append(row)
        size_window_table = dict(
            category=f"{cat_name} (cửa sổ gốc theo dữ liệu bán thực tế + độ lệch vùng Phụ lục B: Miền Trung −1, Miền Tây +2/+3/+4)",
            headers=size_window_headers, rows=size_window_rows)
    else:
        size_window_table = dict(category="—", headers=["Vùng", "Loại I", "Loại II", "Loại III", "Loại IV"], rows=[])

    n_geo = all_stores_geo["Lat"].notna().sum()
    geocode_note = f"📍  TỌA ĐỘ BẢN ĐỒ: Đã geocode {n_geo}/{len(all_stores_geo)} cửa hàng thực tế thành công"

    return dict(run_info=run_info, status_table=status_table, abcd_table=abcd_table,
                region_matrix=region_matrix, size_window_table=size_window_table, geocode_note=geocode_note)


# ---------------------------------------------------------------- Đổi tên cột hiển thị
def to_display_sheet1(df_sku):
    d = df_sku.rename(columns={
        "Combined_PK": "Combined PK", "Ma_Hang": "Ma Hang", "Operation": "Operation",
        "Ten_san_pham": "Ten San Pham", "Thuong_hieu": "Thuong Hieu", "Gia_ban": "Gia Ban",
        "Nhom_KHPP": "Nhom Hang", "So_thang_PP_moc": "So Thang PP", "Dot_chuyen": "Dot Chuyen",
        "Dist_plan": "Dist_plan", "Group_color": "Color_group", "Form": "Form", "Style": "Style",
        "Composition": "Composition", "Tong_ban": "Total Bán (lũy kế theo mốc Lần)",
        "Ton_HTCH": "Tồn HTCH",
        "Ton_Cac_Kho": "Tồn Các Kho", "Tong_ton": "Total Tồn", "Tong_nhap": "Total Nhập (Bán+Tồn)",
        "Ty_le_ban_pct": "Tỷ lệ Bán (%) [30% kỳ + 70% lũy kế]", "So_CH_co_hang": "Số CH Có Hàng",
        "So_CH_da_ban": "Số CH Đã Bán",
        "Ban_3T": "Bán Kỳ Đánh Giá (6T Lần1 / 3T Lần2-3)", "So_thang_ky": "Số Tháng Kỳ",
        "So_thang_ban": "Số Tháng Bán",
        "TB_ban_thang": "TB Bán/Tháng (HT)", "Toc_do_ban_chuan": "Tốc độ bán chuẩn (/CH)",
        "Trang_thai": "Trạng thái mã",
    })
    cols = ["Combined PK", "Ma Hang", "Operation", "Ten San Pham", "Thuong Hieu", "Gia Ban", "Nhom Hang",
            "So Thang PP", "Dot Chuyen", "Dist_plan", "Color_group", "Form", "Style", "Composition",
            "Total Bán (lũy kế theo mốc Lần)", "Bán Kỳ Đánh Giá (6T Lần1 / 3T Lần2-3)", "Số Tháng Kỳ",
            "Tồn HTCH", "Tồn Các Kho", "Total Tồn", "Total Nhập (Bán+Tồn)",
            "Tỷ lệ Bán (%) [30% kỳ + 70% lũy kế]", "Số CH Có Hàng", "Số CH Đã Bán", "Số Tháng Bán",
            "TB Bán/Tháng (HT)", "Tốc độ bán chuẩn (/CH)", "Trạng thái mã"]
    return d[cols]


def to_display_sheet2(df_store, ma_op_map):
    d = df_store.copy()
    d["Ma Hang"] = d["Combined_PK"].map(lambda p: ma_op_map.get(p, (None, None))[0])
    d["Operation"] = d["Combined_PK"].map(lambda p: ma_op_map.get(p, (None, None))[1])
    d = d.rename(columns={
        "Combined_PK": "Combined PK", "Store_name": "Store_name", "Region": "Region", "Loai_CH": "Loai_CH",
        "Dia_chi": "Dia_Chi", "Nhan_luyke": "SL Nhận (Bán+Tồn)", "Ban_ky_3T": "SL Bán Kỳ Đánh Giá",
        "So_thang_ky": "Số Tháng Kỳ",
        "Ban_luyke": "SL Bán Lũy Kế", "Ton": "SL Tồn", "Ty_le_ban_tai_CH": "Tỷ lệ Bán tại CH (%)",
        "Toc_do_ban": "Tốc độ Bán CH (cái/T)", "So_thang_ton": "Tháng Tồn", "Chi_so_hieu_suat": "Hiệu suất CH",
        "Hieu_suat_ky": "Hiệu Suất Kỳ", "Xu_huong": "Xu Hướng (L3/L2)", "Xu_huong_nhan": "Nhãn Xu Hướng",
        "Hanh_dong_L3": "Hành Động Lần 3",
        "Nhom": "Nhóm Hiệu Suất", "Co_BanHet": "Cờ BÁN HẾT", "Dinh_muc_ton": "Định Mức Tồn",
        "Han_muc_nhan": "Hạn Mức Nhận", "Hanh_dong_matran": "Đề Xuất", "Gia_ban": "Giá Bán",
    })
    cols = ["Combined PK", "Ma Hang", "Operation", "Store_name", "Region", "Loai_CH", "Dia_Chi",
            "SL Nhận (Bán+Tồn)", "SL Bán Kỳ Đánh Giá", "Số Tháng Kỳ", "SL Bán Lũy Kế", "SL Tồn",
            "Tỷ lệ Bán tại CH (%)",
            "Tốc độ Bán CH (cái/T)", "Tháng Tồn", "Hiệu suất CH", "Hiệu Suất Kỳ",
            "Xu Hướng (L3/L2)", "Nhãn Xu Hướng", "Hành Động Lần 3", "Nhóm Hiệu Suất", "Cờ BÁN HẾT",
            "Định Mức Tồn", "Hạn Mức Nhận", "Đề Xuất", "Giá Bán"]
    return d[cols]


def to_display_sheet3(sheet3_df, ma_op_map):
    d = sheet3_df.copy()
    d["Ma Hang"] = d["Combined_PK"].map(lambda p: ma_op_map.get(p, (None, None))[0])
    d["Operation"] = d["Combined_PK"].map(lambda p: ma_op_map.get(p, (None, None))[1])
    d = d.rename(columns={
        "Combined_PK": "Combined PK", "Ton_hien_tai": "Tồn Hiện Tại", "Ban_3T": "Bán Kỳ Đánh Giá",
        "Toc_do_ban_size": "Tốc độ Bán Size", "Thang_ton_size": "Tháng Tồn Size",
        "Trong_cua_so": "Trong Cửa Sổ", "Size_gay": "Size Gãy",
        "De_xuat_xuat": "Đề Xuất Xuất", "De_xuat_nhan": "Đề Xuất Nhận",
    })
    cols = ["Combined PK", "Ma Hang", "Operation", "Store_name", "Region", "Size", "Tồn Hiện Tại",
            "Bán Kỳ Đánh Giá", "Tốc độ Bán Size", "Tháng Tồn Size", "Trong Cửa Sổ", "Size Gãy",
            "Đề Xuất Xuất", "Đề Xuất Nhận"]
    return d[cols]


def to_display_sheet4(sheet4_df, ma_op_map):
    d = sheet4_df.copy()
    d["Ma Hang"] = d["Combined_PK"].map(lambda p: ma_op_map.get(p, (None, None))[0])
    d["Operation"] = d["Combined_PK"].map(lambda p: ma_op_map.get(p, (None, None))[1])
    d = d.rename(columns={
        "Combined_PK": "Combined PK", "CH_xuat": "CH Xuất", "Region_xuat": "Region Xuất",
        "CH_nhan": "CH Nhận", "Region_nhan": "Region Nhận", "Loai_lenh": "Loại Lệnh",
        "Khoang_cach_km": "Khoảng Cách (km)", "SL_chuyen": "SL Chuyển", "Gia_ban": "Giá Bán",
        "Gia_tri_chuyen": "Giá Trị Chuyển", "Ton_xuat_truoc": "Tồn Xuất Trước DC",
        "Ton_xuat_sau": "Tồn Xuất Sau DC", "Ton_nhan_truoc": "Tồn Nhận Trước DC",
        "Ton_nhan_sau": "Tồn Nhận Sau DC",
    })
    cols = ["Combined PK", "Ma Hang", "Operation", "Size", "CH Xuất", "Region Xuất", "CH Nhận",
            "Region Nhận", "Loại Lệnh", "Khoảng Cách (km)", "SL Chuyển", "Giá Bán", "Giá Trị Chuyển",
            "Tồn Xuất Trước DC", "Tồn Xuất Sau DC", "Tồn Nhận Trước DC", "Tồn Nhận Sau DC"]
    return d[cols]


def to_display_sheet5(sheet5_df, ma_op_map):
    d = sheet5_df.copy()
    d["Ma Hang"] = d["Combined_PK"].map(lambda p: ma_op_map.get(p, (None, None))[0])
    d = d.rename(columns={
        "CH_xuat": "CH Xuất", "Combined_PK": "Combined PK", "SL_chuyen": "SL Chuyển",
        "Gia_tri_chuyen": "Giá Trị Chuyển", "CH_nhan": "CH Nhận", "Region_xuat": "Region Xuất",
        "Region_nhan": "Region Nhận", "Loai_lenh": "Loại Lệnh", "Khoang_cach_km": "Khoảng Cách (km)",
    })
    cols = ["STT", "CH Xuất", "Combined PK", "Ma Hang", "Size", "SL Chuyển", "Giá Trị Chuyển",
            "CH Nhận", "Region Xuất", "Region Nhận", "Loại Lệnh", "Khoảng Cách (km)"]
    return d[cols]


def to_display_sheet6(sheet6_df):
    return sheet6_df.rename(columns={
        "Loai_CH": "Loại CH", "Ton_dau_ky": "Tổng Tồn Đầu Kỳ", "Tong_xuat": "Tổng SL Xuất",
        "Tong_nhan": "Tổng SL Nhận", "Ton_cuoi_du_kien": "Tồn Cuối Dự Kiến",
    })



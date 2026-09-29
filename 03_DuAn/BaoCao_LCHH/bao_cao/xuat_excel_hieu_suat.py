"""
BÁO CÁO HIỆU SUẤT BÁN SAU LUÂN CHUYỂN (LCHH) — v1.0 PROFESSIONAL
─────────────────────────────────────────────────────────────────────────────
Nguồn dữ liệu: KQ_LCHH_HieuSuat.parquet
Phân tích: Mức độ tiêu thụ hàng hóa tại cửa hàng nhận sau khi nhận lệnh luân chuyển.

Các chỉ số chính:
  - Tồn trước / Tồn sau điều chuyển
  - Qty Bán 30d / 60d / 90d / Lũy kế
  - Tỷ lệ bán 90d (Qty_Ban_90d / Ton_sau_dieu_chuyen)
  - Tỷ lệ bán Lũy kế
  - Tồn hiện tại
  - Đánh giá bán: Bán tốt / Chưa bán / Không nhận

Sheet layout:
  1. DASHBOARD_HIEU_SUAT   — KPI tổng quan + bảng theo đợt
  2. THEO_HANG_HOA         — Nhóm hàng × Thương hiệu × Tên hàng
  3. THEO_CUA_HANG         — Hiệu suất từng cửa hàng nhận
  4. DANH_GIA_BAN          — Chi tiết Bán tốt / Chưa bán / Không nhận
  5. DU_LIEU_CHI_TIET      — Raw data + autofilter
"""
import os, sys, datetime
import pandas as pd
import numpy as np
import xlsxwriter

if sys.stdout.encoding != 'utf-8':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except: pass

BASE_DIR          = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR       = os.path.dirname(BASE_DIR)
sys.path.insert(0, os.path.dirname(os.path.dirname(PROJECT_DIR)))  # 01.Python_Projects (dung_chung)
from dung_chung import duong_dan  # noqa: E402
OUTPUT_DIR = duong_dan.thu_muc_ket_qua("BaoCao_LCHH")   # 04_KetQua/BaoCao_LCHH
PARQUET_HIEUSUAT  = os.path.join(OUTPUT_DIR, "KQ_LCHH_HieuSuat.parquet")
REPORTS_DIR       = os.path.join(OUTPUT_DIR, "bao_cao_excel")

# ══════════════════════════════════════════════════════════════════
#  COLOR TOKENS
# ══════════════════════════════════════════════════════════════════
P = {
    'navy':   '#1B2A4A',  'blue':   '#2C7BE5',  'steel':  '#3D5A80',  'lblue':  '#EBF2FF',
    'green':  '#00B050',  'lgreen': '#E2F5EA',  'dgreen': '#1A6B35',
    'amber':  '#F4A100',  'lamber': '#FFF6E0',  'damber': '#7A5000',
    'red':    '#E63946',  'lred':   '#FDE8EA',  'dred':   '#8B0000',
    'teal':   '#0F9B8E',  'lteal':  '#E0F7F5',  'dteal':  '#065F55',
    'purple': '#6F42C1',  'lpurp':  '#F0EBFF',  'dpurp':  '#3D1A8B',
    'white':  '#FFFFFF',  'g100':   '#F2F4F8',  'g200':   '#E3E7EF',
    'g400':   '#9AA5B4',  'g900':   '#1A202C',
}

TAB_COLORS = {
    'DASHBOARD_HIEU_SUAT': '#2C7BE5',
    'THEO_HANG_HOA':        '#0F9B8E',
    'THEO_CUA_HANG':        '#3D5A80',
    'DANH_GIA_BAN':         '#6F42C1',
    'DU_LIEU_CHI_TIET':     '#6C757D',
}

# ══════════════════════════════════════════════════════════════════
#  DATA LOADER
# ══════════════════════════════════════════════════════════════════
def load_hieusuat(path):
    df = pd.read_parquet(path)
    df['NgayChungTu_YeuCau'] = pd.to_datetime(df['NgayChungTu_YeuCau'], errors='coerce')
    df['NgayYeuCau_Str'] = df['NgayChungTu_YeuCau'].dt.strftime('%Y-%m-%d').fillna('—')

    for c in ['Store_from','Region_from','Store_to','Region_to','MaHang','Report_item_name',
              'Operation','Size','Brand','Product_type','Gender','Product_group','Group_Report',
              'Danh_gia_ban']:
        if c in df.columns: df[c] = df[c].fillna('')

    num_cols = ['Qty_Lenh','Ton_truoc_dieu_chuyen','Ton_sau_dieu_chuyen',
                'Qty_Ban_30d','Qty_Ban_60d','Qty_Ban_90d','Qty_Ban_LuyKe',
                'So_thang_ban_co_DL','Ton_hien_tai','Ty_le_ban_90d','Ty_le_ban_LuyKe']
    for c in num_cols:
        if c in df.columns: df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)

    return df

# ══════════════════════════════════════════════════════════════════
#  FORMAT FACTORY
# ══════════════════════════════════════════════════════════════════
def make_formats(wb):
    def f(**kw):
        base = {'font_name':'Aptos','font_size':10,'valign':'vcenter'}
        base.update(kw); return wb.add_format(base)

    fmt = {}
    fmt['title'] = f(bold=True, font_size=20, font_color=P['white'],
                     bg_color=P['navy'], align='left')
    fmt['meta']  = f(italic=True, font_size=9, font_color=P['g400'],
                     bg_color=P['navy'], align='left')
    fmt['sec']   = f(bold=True, font_size=10, font_color=P['navy'], bg_color=P['g100'],
                     align='left', left=3, left_color=P['blue'],
                     bottom=1, bottom_color=P['g200'])
    fmt['sec2']  = f(bold=True, font_size=10, font_color=P['dteal'], bg_color=P['g100'],
                     align='left', left=3, left_color=P['teal'],
                     bottom=1, bottom_color=P['g200'])
    fmt['sec3']  = f(bold=True, font_size=10, font_color=P['dpurp'], bg_color=P['g100'],
                     align='left', left=3, left_color=P['purple'],
                     bottom=1, bottom_color=P['g200'])

    fmt['th']   = f(bold=True, font_size=9, font_color=P['white'], bg_color=P['navy'],
                    align='center', text_wrap=True, border=1, border_color=P['steel'])
    fmt['th_b'] = f(bold=True, font_size=9, font_color=P['white'], bg_color=P['blue'],
                    align='center', text_wrap=True, border=1, border_color=P['blue'])
    fmt['th_t'] = f(bold=True, font_size=9, font_color=P['white'], bg_color=P['teal'],
                    align='center', text_wrap=True, border=1, border_color=P['teal'])
    fmt['th_p'] = f(bold=True, font_size=9, font_color=P['white'], bg_color=P['purple'],
                    align='center', text_wrap=True, border=1, border_color=P['purple'])

    # Data rows (white / stripe)
    for pfx, bg in [('d', P['white']), ('s', P['lblue'])]:
        fmt[pfx+'l'] = f(align='left',   border=1, border_color=P['g200'], bg_color=bg)
        fmt[pfx+'c'] = f(align='center', border=1, border_color=P['g200'], bg_color=bg)
        fmt[pfx+'i'] = f(align='right',  border=1, border_color=P['g200'], bg_color=bg, num_format='#,##0')
        fmt[pfx+'p'] = f(align='right',  border=1, border_color=P['g200'], bg_color=bg, num_format='0.0%')
        fmt[pfx+'d'] = f(align='right',  border=1, border_color=P['g200'], bg_color=bg, num_format='#,##0.0')
        fmt[pfx+'p2']= f(align='right',  border=1, border_color=P['g200'], bg_color=bg, num_format='0.00%')

    # Total row — dark navy
    fmt['TL'] = f(bold=True, align='left',   bg_color=P['navy'], font_color=P['white'],
                  border=1, border_color=P['steel'])
    fmt['TC'] = f(bold=True, align='center', bg_color=P['navy'], font_color=P['white'],
                  border=1, border_color=P['steel'])
    fmt['TI'] = f(bold=True, align='right',  bg_color=P['navy'], font_color=P['white'],
                  border=1, border_color=P['steel'], num_format='#,##0')
    fmt['TP'] = f(bold=True, align='right',  bg_color=P['navy'], font_color=P['white'],
                  border=1, border_color=P['steel'], num_format='0.0%')
    fmt['TD'] = f(bold=True, align='right',  bg_color=P['navy'], font_color=P['white'],
                  border=1, border_color=P['steel'], num_format='#,##0.0')
    fmt['TP2']= f(bold=True, align='right',  bg_color=P['navy'], font_color=P['white'],
                  border=1, border_color=P['steel'], num_format='0.00%')

    # Status badges
    fmt['ok']  = f(bold=True, align='center', font_color=P['dgreen'], bg_color=P['lgreen'],
                   border=1, border_color=P['green'])
    fmt['war'] = f(bold=True, align='center', font_color=P['damber'], bg_color=P['lamber'],
                   border=1, border_color=P['amber'])
    fmt['err'] = f(bold=True, align='center', font_color=P['dred'],   bg_color=P['lred'],
                   border=1, border_color=P['red'])
    fmt['inf'] = f(bold=True, align='center', font_color=P['dpurp'],  bg_color=P['lpurp'],
                   border=1, border_color=P['purple'])

    # KPI cards
    for tag, bg, fc, bc in [
        ('n', P['lblue'],  P['navy'],   P['blue']),
        ('g', P['lgreen'], P['dgreen'], P['green']),
        ('r', P['lred'],   P['dred'],   P['red']),
        ('a', P['lamber'], P['damber'], P['amber']),
        ('p', P['lpurp'],  P['dpurp'],  P['purple']),
    ]:
        fmt[f'kL{tag}'] = f(bold=True, font_size=8,  font_color=fc, bg_color=bg, align='center',
                             top=2, left=2, right=2, top_color=bc, left_color=bc, right_color=bc)
        fmt[f'kV{tag}'] = f(bold=True, font_size=22, font_color=fc, bg_color=bg, align='center',
                             left=2, right=2, left_color=bc, right_color=bc)
        fmt[f'kS{tag}'] = f(font_size=8, font_color=fc, bg_color=bg, align='center',
                             bottom=2, left=2, right=2, bottom_color=bc, left_color=bc, right_color=bc)
    return fmt

def kpi(ws, fmt, row, c1, c2, tag, label, value, sub):
    ws.merge_range(row,   c1, row,   c2, label, fmt[f'kL{tag}'])
    ws.merge_range(row+1, c1, row+1, c2, value, fmt[f'kV{tag}'])
    ws.merge_range(row+2, c1, row+2, c2, sub,   fmt[f'kS{tag}'])

def databar(ws, r0, r1, col, color, pct=True):
    if pct:
        ws.conditional_format(r0,col,r1,col,{
            'type':'data_bar','bar_color':color,'bar_only':False,
            'min_type':'num','min_value':0,'max_type':'num','max_value':1})
    else:
        ws.conditional_format(r0,col,r1,col,{
            'type':'data_bar','bar_color':color,'bar_only':False,
            'min_type':'min','max_type':'max'})

def section(ws, fmt, row, c1, c2, text, style='sec'):
    ws.set_row(row, 20)
    ws.merge_range(row, c1, row, c2, f'  {text}', fmt[style])

def hdr(ws, fmt, row, cols, style='th', height=32):
    ws.set_row(row, height)
    for ci, h in enumerate(cols): ws.write(row, ci, h, fmt[style])

def setup_sheet(ws, tab_color, cw, title, meta, fmt, month_val, year_val):
    ws.set_tab_color(tab_color)
    ws.hide_gridlines(2)
    ws.set_margins(left=0.5, right=0.5, top=0.7, bottom=0.7)
    ws.set_header(f'&L&"Aptos,Bold"&10{title}&R&"Aptos"&8Tháng {month_val:02d}/{year_val}  |  Trang &P / &N')
    ws.set_footer('&L&"Aptos"&8Nguồn: KQ_LCHH_HieuSuat.parquet  —  Data Analytics Team&R&"Aptos"&8Bảo mật nội bộ')
    for ci, w in enumerate(cw): ws.set_column(ci, ci, w)
    ws.set_row(0, 8); ws.set_row(1, 42); ws.set_row(2, 16); ws.set_row(3, 8)
    ws.merge_range(1, 0, 1, len(cw)-1, f'  {title}', fmt['title'])
    ws.merge_range(2, 0, 2, len(cw)-1, f'  {meta}',  fmt['meta'])
    ws.merge_range(3, 0, 3, len(cw)-1, '',            fmt['meta'])
    return 4

def badge_danh_gia(val):
    if val == 'Bán tốt':   return ('✔ Bán tốt',   'ok')
    if val == 'Chưa bán':  return ('▷ Chưa bán',  'war')
    if val == 'Không nhận':return ('— Không nhận', 'inf')
    return ('—', 'war')


# ══════════════════════════════════════════════════════════════════
#  SHEET 1 — DASHBOARD HIỆU SUẤT
# ══════════════════════════════════════════════════════════════════
def sheet_dashboard(wb, df, fmt, month_val, year_val, quarter_val, now_str):
    ws = wb.add_worksheet('DASHBOARD_HIEU_SUAT')
    # col: A(2) B(16) C(14) D(14) E(14) F(14) G(14) H(14) I(14) J(14) K(14) L(14) M(2)
    cw = [2,16,14,14,14,14,14,14,14,14,14,14,2]
    row = setup_sheet(ws, TAB_COLORS['DASHBOARD_HIEU_SUAT'], cw,
        f'HIỆU SUẤT BÁN SAU LUÂN CHUYỂN — THÁNG {month_val:02d}/{year_val}  ({quarter_val})',
        f'Cập nhật: {now_str}   ·   Đo lường mức độ tiêu thụ hàng hóa sau khi nhận lệnh điều chuyển   ·   Data Analytics Team',
        fmt, month_val, year_val)

    # ── Tính KPI tổng ──
    N          = len(df)
    Ql         = int(df['Qty_Lenh'].sum())
    ton_truoc  = int(df['Ton_truoc_dieu_chuyen'].sum())
    ton_sau    = int(df['Ton_sau_dieu_chuyen'].sum())
    ban_30d    = int(df['Qty_Ban_30d'].sum())
    ban_90d    = int(df['Qty_Ban_90d'].sum())
    ban_lk     = int(df['Qty_Ban_LuyKe'].sum())
    ton_ht     = int(df['Ton_hien_tai'].sum())
    n_bantot   = int((df['Danh_gia_ban']=='Bán tốt').sum())
    n_chuaban  = int((df['Danh_gia_ban']=='Chưa bán').sum())
    n_khongnhan= int((df['Danh_gia_ban']=='Không nhận').sum())
    # Tỷ lệ bán = ban_lk / ton_sau (trừ Không nhận)
    co_dl = df[df['Danh_gia_ban']!='Không nhận']
    ty_le_ban  = co_dl['Qty_Ban_LuyKe'].sum() / co_dl['Ton_sau_dieu_chuyen'].sum() if co_dl['Ton_sau_dieu_chuyen'].sum() else 0
    ty_le_ok   = n_bantot / (N - n_khongnhan) if (N - n_khongnhan) > 0 else 0

    # ── KPI CARDS ──
    ws.set_row(row, 20); ws.set_row(row+1, 36); ws.set_row(row+2, 16)
    kpi(ws,fmt, row, 1, 2, 'n', 'TỔNG MÃ HÀNG ĐIỀU CHUYỂN', f'{N:,}',
        f'Tổng qty lệnh: {Ql:,} sp')
    kpi(ws,fmt, row, 3, 4, 'a', 'TỒN SAU ĐIỀU CHUYỂN',    f'{ton_sau:,} sp',
        f'Trước DC: {ton_truoc:,} · Tồn hiện tại: {ton_ht:,}')
    kpi(ws,fmt, row, 5, 6, 'g', 'ĐÃ BÁN (LŨY KẾ)',         f'{ban_lk:,} sp',
        f'Tỷ lệ tiêu thụ: {ty_le_ban:.1%}')
    kpi(ws,fmt, row, 7, 8, 'g', 'BÁN TỐT',                 f'{n_bantot:,} mã',
        f'Tỷ lệ đạt: {ty_le_ok:.1%} (trong mã có DL)')
    kpi(ws,fmt, row, 9,10, 'r', 'CHƯA BÁN ĐƯỢC',           f'{n_chuaban:,} mã',
        f'Không nhận: {n_khongnhan:,} mã (không có DL bán)')
    row += 4

    # ── SECTION 1: TỔNG QUAN THEO ĐỢT ──
    ws.set_row(row,8); row+=1
    section(ws, fmt, row, 1, 11,
        '1 ·  TỔNG QUAN HIỆU SUẤT THEO ĐỢT  (Ngày Chứng Từ Yêu Cầu)')
    row+=1
    h1=['','Đợt Báo Cáo\n(Ngày YC)','Số Mã\nHàng','Qty\nLệnh',
        'Tồn Trước\nDC','Tồn Sau\nDC','Bán\n30 ngày','Bán\n90 ngày',
        'Bán Lũy\nKế','Tỷ Lệ Tiêu\nThụ LK ↑','Tồn Hiện\nTại','Bán\nTốt','Chưa\nBán','Không\nNhận','']
    hdr(ws, fmt, row, h1, height=32); row+=1

    dot = df.groupby('NgayYeuCau_Str', as_index=False).agg(
        SL=('Qty_Lenh','count'), QL=('Qty_Lenh','sum'),
        TT=('Ton_truoc_dieu_chuyen','sum'), TS=('Ton_sau_dieu_chuyen','sum'),
        B30=('Qty_Ban_30d','sum'), B90=('Qty_Ban_90d','sum'), BLK=('Qty_Ban_LuyKe','sum'),
        THT=('Ton_hien_tai','sum'),
        BTot=('Danh_gia_ban', lambda s:(s=='Bán tốt').sum()),
        CBan=('Danh_gia_ban', lambda s:(s=='Chưa bán').sum()),
        KNhan=('Danh_gia_ban', lambda s:(s=='Không nhận').sum()),
    ).sort_values('NgayYeuCau_Str')
    # Tỷ lệ: BLK / TS  (tính trên mã có DL — trừ Không nhận)
    for idx, r in dot.iterrows():
        ts_eff = df[(df['NgayYeuCau_Str']==r['NgayYeuCau_Str']) & (df['Danh_gia_ban']!='Không nhận')]['Ton_sau_dieu_chuyen'].sum()
        blk_eff = df[(df['NgayYeuCau_Str']==r['NgayYeuCau_Str']) & (df['Danh_gia_ban']!='Không nhận')]['Qty_Ban_LuyKe'].sum()
        dot.at[idx,'TyLe'] = blk_eff/ts_eff if ts_eff else 0

    DR=row
    for ri, r in dot.reset_index(drop=True).iterrows():
        odd=ri%2==1; z='s' if odd else 'd'; ws.set_row(DR+ri,20)
        ws.write(DR+ri, 0,'',     fmt[z+'l']); ws.write(DR+ri,14,'',fmt[z+'l'])
        ws.write(DR+ri, 1, r['NgayYeuCau_Str'], fmt[z+'c'])
        ws.write(DR+ri, 2, r['SL'],  fmt[z+'i'])
        ws.write(DR+ri, 3, r['QL'],  fmt[z+'i'])
        ws.write(DR+ri, 4, r['TT'],  fmt[z+'i'])
        ws.write(DR+ri, 5, r['TS'],  fmt[z+'i'])
        ws.write(DR+ri, 6, r['B30'], fmt[z+'i'])
        ws.write(DR+ri, 7, r['B90'], fmt[z+'i'])
        ws.write(DR+ri, 8, r['BLK'], fmt[z+'i'])
        ws.write(DR+ri, 9, r['TyLe'],fmt[z+'p'])
        ws.write(DR+ri,10, r['THT'], fmt[z+'i'])
        ws.write(DR+ri,11, r['BTot'],fmt[z+'i'])
        ws.write(DR+ri,12, r['CBan'],fmt[z+'i'])
        ws.write(DR+ri,13, r['KNhan'],fmt[z+'i'])

    databar(ws, DR, DR+len(dot)-1, 9, P['green'], pct=True)
    databar(ws, DR, DR+len(dot)-1, 12, P['red'],  pct=False)

    TR=DR+len(dot); ws.set_row(TR,22)
    ts_eff_all = df[df['Danh_gia_ban']!='Không nhận']['Ton_sau_dieu_chuyen'].sum()
    blk_eff_all = df[df['Danh_gia_ban']!='Không nhận']['Qty_Ban_LuyKe'].sum()
    tt_tyle = blk_eff_all/ts_eff_all if ts_eff_all else 0
    for c,v,fk in [
        (0,'','TL'),(1,'TỔNG CỘNG','TL'),(2,int(dot['SL'].sum()),'TI'),(3,int(dot['QL'].sum()),'TI'),
        (4,int(dot['TT'].sum()),'TI'),(5,int(dot['TS'].sum()),'TI'),
        (6,int(dot['B30'].sum()),'TI'),(7,int(dot['B90'].sum()),'TI'),(8,int(dot['BLK'].sum()),'TI'),
        (9,tt_tyle,'TP'),(10,int(dot['THT'].sum()),'TI'),
        (11,int(dot['BTot'].sum()),'TI'),(12,int(dot['CBan'].sum()),'TI'),(13,int(dot['KNhan'].sum()),'TI'),
        (14,'','TL')
    ]:
        ws.write(TR, c, v, fmt[fk])
    row = TR+2

    # ── SECTION 2: CƠ CẤU ĐÁNH GIÁ BÁN ──
    ws.set_row(row,8); row+=1
    section(ws, fmt, row, 1, 11, '2 ·  CƠ CẤU ĐÁNH GIÁ TIÊU THỤ', 'sec2')
    row+=1

    h2=['','Đánh Giá Bán','Số Mã','Tỷ Lệ\nTrên Tổng','Qty Lệnh','Tồn Sau DC',
        'Đã Bán LK','Tỷ Lệ Tiêu\nThụ LK','Tồn Hiện Tại','Nhận Xét','']
    hdr(ws, fmt, row, h2, 'th_t', height=32); row+=1

    dg = df.groupby('Danh_gia_ban', as_index=False).agg(
        SL=('Qty_Lenh','count'), QL=('Qty_Lenh','sum'),
        TS=('Ton_sau_dieu_chuyen','sum'), BLK=('Qty_Ban_LuyKe','sum'),
        THT=('Ton_hien_tai','sum'),
        TyLe90d_mean=('Ty_le_ban_90d','mean'),
    ).sort_values('SL', ascending=False)
    dg['PctSL'] = dg['SL']/N
    dg['TyLeBan'] = dg['BLK']/dg['TS'].replace(0,np.nan)

    NHANXET = {
        'Bán tốt':    ('✔ Điều chuyển hiệu quả', 'ok'),
        'Chưa bán':   ('▷ Cần theo dõi tiêu thụ','war'),
        'Không nhận': ('— Không có dữ liệu bán', 'inf'),
    }
    DR2=row
    for ri, r in dg.reset_index(drop=True).iterrows():
        odd=ri%2==1; z='s' if odd else 'd'; ws.set_row(DR2+ri,20)
        lbl, fk = NHANXET.get(r['Danh_gia_ban'], ('—','war'))
        ws.write(DR2+ri, 0,'',fmt[z+'l']); ws.write(DR2+ri,10,'',fmt[z+'l'])
        ws.write(DR2+ri, 1, r['Danh_gia_ban'],  fmt[z+'l'])
        ws.write(DR2+ri, 2, r['SL'],             fmt[z+'i'])
        ws.write(DR2+ri, 3, r['PctSL'],          fmt[z+'p'])
        ws.write(DR2+ri, 4, r['QL'],             fmt[z+'i'])
        ws.write(DR2+ri, 5, r['TS'],             fmt[z+'i'])
        ws.write(DR2+ri, 6, r['BLK'],            fmt[z+'i'])
        tl = r['TyLeBan'] if pd.notna(r['TyLeBan']) else 0
        ws.write(DR2+ri, 7, tl,                  fmt[z+'p'])
        ws.write(DR2+ri, 8, r['THT'],            fmt[z+'i'])
        ws.write(DR2+ri, 9, lbl,                 fmt[fk])

    databar(ws, DR2, DR2+len(dg)-1, 3, P['blue'],  pct=True)
    databar(ws, DR2, DR2+len(dg)-1, 7, P['green'], pct=True)

    ws.conditional_format(DR2, 1, DR2+len(dg)-1, 1, {
        'type':'text','criteria':'containing','value':'Bán tốt',
        'format': wb.add_format({'bg_color':P['lgreen'],'font_color':P['dgreen'],'bold':True})})
    ws.conditional_format(DR2, 1, DR2+len(dg)-1, 1, {
        'type':'text','criteria':'containing','value':'Không nhận',
        'format': wb.add_format({'bg_color':P['lpurp'],'font_color':P['dpurp'],'bold':True})})

    ws.freeze_panes(4, 0)


# ══════════════════════════════════════════════════════════════════
#  SHEET 2 — THEO HÀNG HÓA
# ══════════════════════════════════════════════════════════════════
def sheet_hang_hoa(wb, df, fmt, month_val, year_val, quarter_val, now_str):
    ws = wb.add_worksheet('THEO_HANG_HOA')
    cw = [2,20,18,12,12,12,12,12,12,12,12,12,12,2]
    row = setup_sheet(ws, TAB_COLORS['THEO_HANG_HOA'], cw,
        f'HIỆU SUẤT BÁN THEO HÀNG HÓA — Tháng {month_val:02d}/{year_val}',
        'Nhóm hàng · Thương hiệu · Top tên hàng · Tiêu thụ sau điều chuyển',
        fmt, month_val, year_val)

    # ── 1. Nhóm Hàng × Brand ──
    ws.set_row(row,8); row+=1
    section(ws, fmt, row, 1, 12, '1 ·  HIỆU SUẤT THEO NHÓM HÀNG & THƯƠNG HIỆU')
    row+=1
    h1=['','Nhóm Hàng','Thương Hiệu','Số Mã',
        'Tồn Sau DC','Bán 30d','Bán 60d','Bán 90d','Bán Lũy Kế',
        'Tỷ Lệ Tiêu\nThụ LK ↑','Tồn Hiện Tại',
        'Bán Tốt','Chưa Bán','Không Nhận','']
    hdr(ws, fmt, row, h1, height=32); row+=1

    g1 = df.groupby(['Group_Report','Brand'], as_index=False).agg(
        SL=('Qty_Lenh','count'),
        TS=('Ton_sau_dieu_chuyen','sum'), B30=('Qty_Ban_30d','sum'),
        B60=('Qty_Ban_60d','sum'), B90=('Qty_Ban_90d','sum'), BLK=('Qty_Ban_LuyKe','sum'),
        THT=('Ton_hien_tai','sum'),
        BTot=('Danh_gia_ban', lambda s:(s=='Bán tốt').sum()),
        CBan=('Danh_gia_ban', lambda s:(s=='Chưa bán').sum()),
        KNhan=('Danh_gia_ban', lambda s:(s=='Không nhận').sum()),
    ).sort_values(['Group_Report','SL'], ascending=[True,False])
    # Tỷ lệ tiêu thụ = BLK / TS (chỉ tính mã Không nhận = không có DL)
    g1['TyLe'] = g1['BLK']/g1['TS'].replace(0,np.nan)

    DR=row
    for ri, r in g1.reset_index(drop=True).iterrows():
        odd=ri%2==1; z='s' if odd else 'd'; ws.set_row(DR+ri,20)
        ws.write(DR+ri, 0,'',fmt[z+'l']); ws.write(DR+ri,13,'',fmt[z+'l'])
        ws.write(DR+ri, 1, r['Group_Report'],fmt[z+'l'])
        ws.write(DR+ri, 2, r['Brand'],       fmt[z+'l'])
        ws.write(DR+ri, 3, r['SL'],          fmt[z+'i'])
        ws.write(DR+ri, 4, r['TS'],          fmt[z+'i'])
        ws.write(DR+ri, 5, r['B30'],         fmt[z+'i'])
        ws.write(DR+ri, 6, r['B60'],         fmt[z+'i'])
        ws.write(DR+ri, 7, r['B90'],         fmt[z+'i'])
        ws.write(DR+ri, 8, r['BLK'],         fmt[z+'i'])
        ws.write(DR+ri, 9, r['TyLe'] if pd.notna(r['TyLe']) else 0, fmt[z+'p'])
        ws.write(DR+ri,10, r['THT'],         fmt[z+'i'])
        ws.write(DR+ri,11, r['BTot'],        fmt[z+'i'])
        ws.write(DR+ri,12, r['CBan'],        fmt[z+'i'])
        ws.write(DR+ri,13, r['KNhan'],       fmt[z+'i'])

    databar(ws, DR, DR+len(g1)-1, 9, P['green'], pct=True)
    databar(ws, DR, DR+len(g1)-1, 8, P['teal'],  pct=False)
    databar(ws, DR, DR+len(g1)-1, 12, P['red'],  pct=False)

    # Conditional: CBan > 50% của SL → highlight đỏ
    ws.conditional_format(DR, 12, DR+len(g1)-1, 12, {
        'type':'cell','criteria':'>','value':50,
        'format': wb.add_format({'bg_color':P['lred'],'font_color':P['dred'],'bold':True})
    })

    TR=DR+len(g1); ws.set_row(TR,22)
    ts_all=g1['TS'].sum()
    blk_all=g1['BLK'].sum()
    for c,v,fk in [
        (0,'','TL'),(1,'TỔNG CỘNG','TL'),(2,'','TL'),(3,int(g1['SL'].sum()),'TI'),
        (4,int(g1['TS'].sum()),'TI'),(5,int(g1['B30'].sum()),'TI'),(6,int(g1['B60'].sum()),'TI'),
        (7,int(g1['B90'].sum()),'TI'),(8,int(g1['BLK'].sum()),'TI'),
        (9,blk_all/ts_all if ts_all else 0,'TP'),(10,int(g1['THT'].sum()),'TI'),
        (11,int(g1['BTot'].sum()),'TI'),(12,int(g1['CBan'].sum()),'TI'),
        (13,int(g1['KNhan'].sum()),'TI')
    ]:
        ws.write(TR, c, v, fmt[fk])
    row=TR+2

    # ── 2. Top 30 Tên Hàng ──
    ws.set_row(row,8); row+=1
    section(ws, fmt, row, 1, 12,
        '2 ·  TOP 30 TÊN HÀNG THEO KHỐI LƯỢNG ĐIỀU CHUYỂN VÀ MỨC ĐỘ TIÊU THỤ', 'sec2')
    row+=1
    h2=['','#','Tên Hàng','Mã Hàng','Nhóm','Thương Hiệu',
        'Số Mã','Tồn Sau DC','Bán 30d','Bán 90d','Bán Lũy Kế',
        'Tỷ Lệ TT LK ↑','Tồn Hiện Tại','Bán Tốt','']
    hdr(ws, fmt, row, h2, 'th_t', height=32); row+=1

    top = df.groupby(['Report_item_name','MaHang','Group_Report','Brand'], as_index=False).agg(
        SL=('Qty_Lenh','count'), TS=('Ton_sau_dieu_chuyen','sum'),
        B30=('Qty_Ban_30d','sum'), B90=('Qty_Ban_90d','sum'), BLK=('Qty_Ban_LuyKe','sum'),
        THT=('Ton_hien_tai','sum'),
        BTot=('Danh_gia_ban', lambda s:(s=='Bán tốt').sum()),
    ).sort_values('TS', ascending=False).head(30)
    top['TyLe'] = top['BLK']/top['TS'].replace(0,np.nan)

    DR2=row
    for ri, r in top.reset_index(drop=True).iterrows():
        odd=ri%2==1; z='s' if odd else 'd'; ws.set_row(DR2+ri,20)
        ws.write(DR2+ri, 0,'',fmt[z+'l']); ws.write(DR2+ri,14,'',fmt[z+'l'])
        ws.write(DR2+ri, 1, f'#{ri+1}',           fmt[z+'c'])
        ws.write(DR2+ri, 2, r['Report_item_name'], fmt[z+'l'])
        ws.write(DR2+ri, 3, r['MaHang'],           fmt[z+'c'])
        ws.write(DR2+ri, 4, r['Group_Report'],     fmt[z+'l'])
        ws.write(DR2+ri, 5, r['Brand'],            fmt[z+'l'])
        ws.write(DR2+ri, 6, r['SL'],               fmt[z+'i'])
        ws.write(DR2+ri, 7, r['TS'],               fmt[z+'i'])
        ws.write(DR2+ri, 8, r['B30'],              fmt[z+'i'])
        ws.write(DR2+ri, 9, r['B90'],              fmt[z+'i'])
        ws.write(DR2+ri,10, r['BLK'],              fmt[z+'i'])
        ws.write(DR2+ri,11, r['TyLe'] if pd.notna(r['TyLe']) else 0, fmt[z+'p'])
        ws.write(DR2+ri,12, r['THT'],              fmt[z+'i'])
        ws.write(DR2+ri,13, r['BTot'],             fmt[z+'i'])

    databar(ws, DR2, DR2+len(top)-1, 11, P['green'], pct=True)
    databar(ws, DR2, DR2+len(top)-1, 7,  P['teal'],  pct=False)
    # 3-color scale tỷ lệ TT
    ws.conditional_format(DR2, 11, DR2+len(top)-1, 11, {
        'type':'3_color_scale',
        'min_color':P['lred'],'mid_color':P['lamber'],'max_color':P['lgreen'],
        'min_type':'num','min_value':0,'max_type':'num','max_value':1})

    ws.freeze_panes(4, 0)


# ══════════════════════════════════════════════════════════════════
#  SHEET 3 — THEO CỬA HÀNG
# ══════════════════════════════════════════════════════════════════
def sheet_cua_hang(wb, df, fmt, month_val, year_val, quarter_val, now_str):
    ws = wb.add_worksheet('THEO_CUA_HANG')
    cw = [2,26,16,10,12,12,12,12,12,12,10,10,10,2]
    row = setup_sheet(ws, TAB_COLORS['THEO_CUA_HANG'], cw,
        f'HIỆU SUẤT BÁN THEO CỬA HÀNG NHẬN — Tháng {month_val:02d}/{year_val}',
        'Hiệu suất tiêu thụ của từng cửa hàng nhận sau điều chuyển · Sắp xếp theo Tồn Sau DC giảm dần',
        fmt, month_val, year_val)

    ws.set_row(row,8); row+=1
    section(ws, fmt, row, 1, 12,
        '1 ·  HIỆU SUẤT TIÊU THỤ TỪng CỬA HÀNG NHẬN  —  Sắp xếp: Tồn Sau DC ↓')
    row+=1
    h=['','Cửa Hàng Nhận','Vùng','Số Mã','Tồn Sau\nDC','Bán\n30d','Bán\n60d',
       'Bán\n90d','Bán Lũy\nKế','Tỷ Lệ Tiêu\nThụ LK ↑','Tồn Hiện\nTại','Bán\nTốt','Chưa\nBán','']
    hdr(ws, fmt, row, h, height=32); row+=1

    ct = df.groupby(['Store_to','Region_to'], as_index=False).agg(
        SL=('Qty_Lenh','count'),
        TS=('Ton_sau_dieu_chuyen','sum'), B30=('Qty_Ban_30d','sum'),
        B60=('Qty_Ban_60d','sum'), B90=('Qty_Ban_90d','sum'), BLK=('Qty_Ban_LuyKe','sum'),
        THT=('Ton_hien_tai','sum'),
        BTot=('Danh_gia_ban', lambda s:(s=='Bán tốt').sum()),
        CBan=('Danh_gia_ban', lambda s:(s=='Chưa bán').sum()),
    ).sort_values('TS', ascending=False)
    ct['TyLe'] = ct['BLK']/ct['TS'].replace(0,np.nan)

    DR=row
    for ri, r in ct.reset_index(drop=True).iterrows():
        odd=ri%2==1; z='s' if odd else 'd'; ws.set_row(DR+ri,20)
        ws.write(DR+ri, 0,'',fmt[z+'l']); ws.write(DR+ri,13,'',fmt[z+'l'])
        ws.write(DR+ri, 1, r['Store_to'],  fmt[z+'l'])
        ws.write(DR+ri, 2, r['Region_to'], fmt[z+'c'])
        ws.write(DR+ri, 3, r['SL'],        fmt[z+'i'])
        ws.write(DR+ri, 4, r['TS'],        fmt[z+'i'])
        ws.write(DR+ri, 5, r['B30'],       fmt[z+'i'])
        ws.write(DR+ri, 6, r['B60'],       fmt[z+'i'])
        ws.write(DR+ri, 7, r['B90'],       fmt[z+'i'])
        ws.write(DR+ri, 8, r['BLK'],       fmt[z+'i'])
        ws.write(DR+ri, 9, r['TyLe'] if pd.notna(r['TyLe']) else 0, fmt[z+'p'])
        ws.write(DR+ri,10, r['THT'],       fmt[z+'i'])
        ws.write(DR+ri,11, r['BTot'],      fmt[z+'i'])
        ws.write(DR+ri,12, r['CBan'],      fmt[z+'i'])

    databar(ws, DR, DR+len(ct)-1, 9, P['green'], pct=True)
    databar(ws, DR, DR+len(ct)-1, 4, P['teal'],  pct=False)
    # Highlight: Bán tốt >= 5
    ws.conditional_format(DR, 11, DR+len(ct)-1, 11, {
        'type':'cell','criteria':'>=','value':5,
        'format': wb.add_format({'bg_color':P['lgreen'],'font_color':P['dgreen'],'bold':True,'border':1})
    })
    # Highlight: Chưa bán >= 40
    ws.conditional_format(DR, 12, DR+len(ct)-1, 12, {
        'type':'cell','criteria':'>=','value':40,
        'format': wb.add_format({'bg_color':P['lred'],'font_color':P['dred'],'bold':True,'border':1})
    })
    # 3-color scale tỷ lệ tiêu thụ
    ws.conditional_format(DR, 9, DR+len(ct)-1, 9, {
        'type':'3_color_scale',
        'min_color':P['lred'],'mid_color':P['lamber'],'max_color':P['lgreen'],
        'min_type':'num','min_value':0,'max_type':'num','max_value':1})

    TR=DR+len(ct); ws.set_row(TR,22)
    ts_all=ct['TS'].sum(); blk_all=ct['BLK'].sum()
    for c,v,fk in [
        (0,'','TL'),(1,'TỔNG CỘNG','TL'),(2,f'{len(ct)} cửa hàng','TL'),(3,int(ct['SL'].sum()),'TI'),
        (4,int(ct['TS'].sum()),'TI'),(5,int(ct['B30'].sum()),'TI'),(6,int(ct['B60'].sum()),'TI'),
        (7,int(ct['B90'].sum()),'TI'),(8,int(ct['BLK'].sum()),'TI'),
        (9,blk_all/ts_all if ts_all else 0,'TP'),(10,int(ct['THT'].sum()),'TI'),
        (11,int(ct['BTot'].sum()),'TI'),(12,int(ct['CBan'].sum()),'TI'),(13,'','TL')
    ]:
        ws.write(TR, c, v, fmt[fk])

    ws.freeze_panes(4, 0)


# ══════════════════════════════════════════════════════════════════
#  SHEET 4 — ĐÁNH GIÁ BÁN CHI TIẾT
# ══════════════════════════════════════════════════════════════════
def sheet_danh_gia(wb, df, fmt, month_val, year_val, quarter_val, now_str):
    ws = wb.add_worksheet('DANH_GIA_BAN')
    cw = [2,12,24,24,14,20,8,8,8,8,8,8,14,2]
    row = setup_sheet(ws, TAB_COLORS['DANH_GIA_BAN'], cw,
        f'CHI TIẾT ĐÁNH GIÁ TIÊU THỤ — Tháng {month_val:02d}/{year_val}',
        'Danh sách chi tiết từng mã hàng tại từng cửa hàng nhận · Đánh giá: Bán tốt / Chưa bán / Không nhận',
        fmt, month_val, year_val)

    GROUPS = [
        ('Bán tốt',    '1 ·  DANH SÁCH BÁN TỐT',   'sec'),
        ('Chưa bán',   '2 ·  DANH SÁCH CHƯA BÁN',   'sec2'),
        ('Không nhận', '3 ·  KHÔNG CÓ DỮ LIỆU BÁN (KHÔNG NHẬN)',  'sec3'),
    ]
    h=['','Ngày YC','Cửa Hàng Chuyển','Cửa Hàng Nhận','Mã Hàng','Tên Hàng','Size',
        'Tồn Sau\nDC','Bán 30d','Bán 60d','Bán 90d','Bán LK','Tỷ Lệ TT','']
    h_styles = {'Bán tốt':'th','Chưa bán':'th_t','Không nhận':'th_p'}

    for dg_val, sec_title, sec_style in GROUPS:
        sub = df[df['Danh_gia_ban']==dg_val].sort_values(
            ['NgayYeuCau_Str','Store_to','Group_Report']
        )
        ws.set_row(row,8); row+=1
        section(ws, fmt, row, 1, 12, f'{sec_title}  ({len(sub):,} mã)', sec_style)
        row+=1
        hdr(ws, fmt, row, h, h_styles.get(dg_val,'th'), height=32); row+=1

        DR=row
        for ri, r in sub.reset_index(drop=True).iterrows():
            odd=ri%2==1; z='s' if odd else 'd'; ws.set_row(DR+ri,20)
            ts = r['Ton_sau_dieu_chuyen']
            blk = r['Qty_Ban_LuyKe']
            tl = blk/ts if ts else 0
            ws.write(DR+ri, 0,'',fmt[z+'l']); ws.write(DR+ri,13,'',fmt[z+'l'])
            ws.write(DR+ri, 1, r['NgayYeuCau_Str'],   fmt[z+'c'])
            ws.write(DR+ri, 2, r['Store_from'],       fmt[z+'l'])
            ws.write(DR+ri, 3, r['Store_to'],         fmt[z+'l'])
            ws.write(DR+ri, 4, r['MaHang'],           fmt[z+'c'])
            ws.write(DR+ri, 5, r['Report_item_name'], fmt[z+'l'])
            ws.write(DR+ri, 6, r['Size'],             fmt[z+'c'])
            ws.write(DR+ri, 7, ts,                    fmt[z+'i'])
            ws.write(DR+ri, 8, r['Qty_Ban_30d'],      fmt[z+'i'])
            ws.write(DR+ri, 9, r['Qty_Ban_60d'],      fmt[z+'i'])
            ws.write(DR+ri,10, r['Qty_Ban_90d'],      fmt[z+'i'])
            ws.write(DR+ri,11, blk,                   fmt[z+'i'])
            if dg_val != 'Không nhận':
                ws.write(DR+ri,12, tl, fmt[z+'p'])
            else:
                ws.write(DR+ri,12, '—', fmt[z+'c'])

        if dg_val != 'Không nhận' and len(sub) > 0:
            databar(ws, DR, DR+len(sub)-1, 12, P['green'], pct=True)
            ws.conditional_format(DR, 12, DR+len(sub)-1, 12, {
                'type':'3_color_scale',
                'min_color':P['lred'],'mid_color':P['lamber'],'max_color':P['lgreen'],
                'min_type':'num','min_value':0,'max_type':'num','max_value':1})
        row = DR+len(sub)+2

    ws.freeze_panes(4, 0)


# ══════════════════════════════════════════════════════════════════
#  SHEET 5 — DỮ LIỆU CHI TIẾT
# ══════════════════════════════════════════════════════════════════
def sheet_detail(wb, df, fmt, month_val, year_val, quarter_val, now_str):
    ws = wb.add_worksheet('DU_LIEU_CHI_TIET')
    ws.set_tab_color(TAB_COLORS['DU_LIEU_CHI_TIET'])
    ws.hide_gridlines(2)
    ws.set_row(0, 28)

    COLS = ['NgayChungTu_YeuCau','Operation','Store_from','Region_from','Store_to','Region_to',
            'MaHang','Report_item_name','Size','Brand','Group_Report','Gender',
            'Qty_Lenh','Ton_truoc_dieu_chuyen','Ton_sau_dieu_chuyen',
            'Qty_Ban_30d','Qty_Ban_60d','Qty_Ban_90d','Qty_Ban_LuyKe',
            'So_thang_ban_co_DL','Ton_hien_tai',
            'Ty_le_ban_90d','Ty_le_ban_LuyKe','Danh_gia_ban']
    COLS = [c for c in COLS if c in df.columns]

    INT_C  = {'Qty_Lenh','So_thang_ban_co_DL'}
    DEC_C  = {'Ton_truoc_dieu_chuyen','Ton_sau_dieu_chuyen','Qty_Ban_30d','Qty_Ban_60d',
               'Qty_Ban_90d','Qty_Ban_LuyKe','Ton_hien_tai','Ty_le_ban_90d','Ty_le_ban_LuyKe'}
    DATE_C = {'NgayChungTu_YeuCau'}
    PCT_C  = {'Ty_le_ban_90d','Ty_le_ban_LuyKe'}

    for ci, col in enumerate(COLS):
        ws.write(0, ci, col, fmt['th'])
        ws.set_column(ci, ci, max(10, min(28, len(col)+4)))

    DG_COL = COLS.index('Danh_gia_ban') if 'Danh_gia_ban' in COLS else None

    for ri, row in df.reset_index(drop=True).iterrows():
        r = ri+1; odd=ri%2==1; z='s' if odd else 'd'
        for ci, col in enumerate(COLS):
            val = row[col]
            if col in DATE_C:
                ws.write(r, ci, str(val)[:10] if pd.notna(val) else '—', fmt[z+'c'])
            elif col in PCT_C:
                ws.write(r, ci, float(val) if pd.notna(val) and val!=0 else 0.0, fmt[z+'p'])
            elif col in INT_C:
                ws.write(r, ci, int(val) if pd.notna(val) else 0, fmt[z+'i'])
            elif col in DEC_C:
                ws.write(r, ci, float(val) if pd.notna(val) else 0.0, fmt[z+'d'])
            else:
                ws.write(r, ci, str(val) if pd.notna(val) else '—', fmt[z+'l'])

    if DG_COL is not None:
        ws.conditional_format(1,DG_COL,len(df),DG_COL,{
            'type':'text','criteria':'containing','value':'Bán tốt',
            'format': wb.add_format({'bg_color':P['lgreen'],'font_color':P['dgreen'],'bold':True})})
        ws.conditional_format(1,DG_COL,len(df),DG_COL,{
            'type':'text','criteria':'containing','value':'Không nhận',
            'format': wb.add_format({'bg_color':P['lpurp'],'font_color':P['dpurp'],'bold':True})})

    ws.freeze_panes(1, 0)
    ws.autofilter(0, 0, len(df), len(COLS)-1)


# ══════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════
def create_report(df, output_path):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    wb = xlsxwriter.Workbook(output_path, {'nan_inf_to_errors':True,'strings_to_numbers':False})
    fmt = make_formats(wb)

    year_val    = int(df['Year'].iloc[0])  if 'Year'    in df.columns and len(df) else datetime.datetime.now().year
    month_val   = int(df['Month'].iloc[0]) if 'Month'   in df.columns and len(df) else datetime.datetime.now().month
    quarter_val = df['Quarter'].iloc[0]    if 'Quarter' in df.columns and len(df) else f"Q{(month_val-1)//3+1}.{year_val}"
    now_str     = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    args = (wb, df, fmt, month_val, year_val, quarter_val, now_str)

    for name, fn in [
        ('DASHBOARD_HIEU_SUAT', sheet_dashboard),
        ('THEO_HANG_HOA',       sheet_hang_hoa),
        ('THEO_CUA_HANG',       sheet_cua_hang),
        ('DANH_GIA_BAN',        sheet_danh_gia),
        ('DU_LIEU_CHI_TIET',    sheet_detail),
    ]:
        fn(*args)
        print(f'  ✓ [{name}]')

    wb.close()
    print(f'→ {output_path}')


def main():
    print('═'*70)
    print('  BÁO CÁO HIỆU SUẤT BÁN SAU LUÂN CHUYỂN — v1.0 PROFESSIONAL')
    print('═'*70)
    df = load_hieusuat(PARQUET_HIEUSUAT)
    print(f'  Dữ liệu: {len(df):,} dòng  |  {df["NgayYeuCau_Str"].nunique()} đợt  |  '
          f'Tháng {int(df["Month"].iloc[0]):02d}/{int(df["Year"].iloc[0])}')
    print(f'  Đánh giá: Bán tốt={int((df["Danh_gia_ban"]=="Bán tốt").sum())}  '
          f'Chưa bán={int((df["Danh_gia_ban"]=="Chưa bán").sum())}  '
          f'Không nhận={int((df["Danh_gia_ban"]=="Không nhận").sum())}')

    y, m = int(df['Year'].iloc[0]), int(df['Month'].iloc[0])
    fn_month  = f'BaoCao_HieuSuat_BanSauLC_{y}_{m:02d}.xlsx'
    fn_latest = 'BaoCao_HieuSuat_BanSauLC_Latest.xlsx'

    print('\n  Đang tạo file Excel...')
    create_report(df, os.path.join(REPORTS_DIR, fn_month))
    create_report(df, os.path.join(REPORTS_DIR, fn_latest))

    print('\n' + '═'*70)
    print('  HOÀN THÀNH!')
    print(f'  📁 {os.path.join(REPORTS_DIR, fn_month)}')
    print(f'  📁 {os.path.join(REPORTS_DIR, fn_latest)}')
    print('═'*70)


if __name__ == '__main__':
    main()

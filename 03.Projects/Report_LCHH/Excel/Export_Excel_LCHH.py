"""
BÁO CÁO PHÂN TÍCH HOẠT ĐỘNG LUÂN CHUYỂN HÀNG HÓA (LCHH) — v3.0 PROFESSIONAL
─────────────────────────────────────────────────────────────────────────────
Design: Modern BI Dashboard aesthetic — dark header, clean flat layout,
        data bars, smart conditional formatting, professional charts,
        tab colors, print settings, consistent spacing.
"""
import os, sys, datetime
import pandas as pd
import numpy as np
import xlsxwriter

if sys.stdout.encoding != 'utf-8':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except: pass

BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR     = os.path.dirname(BASE_DIR)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(PROJECT_DIR)), "00.Shared"))  # 00.Shared (Get_Paths...)
import Get_Paths  # noqa: E402
OUTPUT_DIR = Get_Paths.thu_muc_ket_qua("Report_LCHH")   # 04.Output/Report_LCHH
DEFAULT_PARQUET = os.path.join(OUTPUT_DIR, "KQ_LCHH.parquet")
REPORTS_DIR     = os.path.join(OUTPUT_DIR, "Excel_Reports")

# ══════════════════════════════════════════════════════════════════
#  COLOR TOKENS  (single source of truth)
# ══════════════════════════════════════════════════════════════════
P = {
    # Primary palette
    'navy':    '#1B2A4A',   # dark navy — title bars, main headers
    'blue':    '#2C7BE5',   # bright blue — section headers, secondary KPI
    'steel':   '#3D5A80',   # steel blue — alternating use
    'lblue':   '#EBF2FF',   # pale blue — even-row bg
    # Semantic
    'green':   '#00B050',   'lgreen':  '#E2F5EA',   'dgreen':  '#1A6B35',
    'amber':   '#F4A100',   'lamber':  '#FFF6E0',   'damber':  '#7A5000',
    'red':     '#E63946',   'lred':    '#FDE8EA',   'dred':    '#8B0000',
    'teal':    '#0F9B8E',   'lteal':   '#E0F7F5',   'dteal':   '#065F55',
    # Neutral
    'white':   '#FFFFFF',
    'bg':      '#F7F9FC',   # sheet background simulation
    'g100':    '#F2F4F8',   # lightest gray
    'g200':    '#E3E7EF',   # divider
    'g400':    '#9AA5B4',   # muted text
    'g700':    '#4A5568',   # dark text
    'g900':    '#1A202C',   # near black
}

TAB_COLORS = {
    'DASHBOARD_TONG_QUAN': '#2C7BE5',
    'PHAN_TICH_HANG_HOA':  '#0F9B8E',
    'CUA_HANG':            '#3D5A80',
    'TIEN_DO_VA_SLA':      '#F4A100',
    'CHUA_THUC_HIEN':      '#E63946',
    'DU_LIEU_CHI_TIET':    '#6C757D',
}

# ══════════════════════════════════════════════════════════════════
#  DATA LOADER
# ══════════════════════════════════════════════════════════════════
def load_data(path):
    df = pd.read_parquet(path)
    for c in ['NgayChungTu_YeuCau','Ngay_thuc_hien']:
        if c in df.columns: df[c] = pd.to_datetime(df[c], errors='coerce')
    df['NgayYeuCau_Str'] = df['NgayChungTu_YeuCau'].dt.strftime('%Y-%m-%d').fillna('—')

    for c in ['Store_from','Region_from','Store_to','Region_to','MaHang','Report_item_name',
              'Operation','Size','Brand','Product_type','Gender','Product_group','Group_Report',
              'trang_thai_thuc_hien','Danh_gia_han','ly_do','ChuyenDiTiep_toi','Status_list']:
        if c in df.columns: df[c] = df[c].fillna('')
    for c in ['Qty_Lenh','Qty_DaChuyen','Qty_DaNhapKho','Qty_DiDuong',
              'Qty_TraKho','Qty_TraKho_vuot_nhan','Qty_ChuyenDiTiep',
              'So_ngay_thuc_hien','So_ngay_tre']:
        if c in df.columns: df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)

    def bucket(r):
        tt = r['trang_thai_thuc_hien']
        if tt == 'Chưa thực hiện': return 'E. Chưa thực hiện'
        if tt == 'Đang đi đường':  return 'D. Đang đi đường'
        d = r['So_ngay_thuc_hien']
        if d <= 3:  return 'A. ≤ 3 ngày (Nhanh)'
        if d <= 7:  return 'B. 4–7 ngày (Tiêu chuẩn)'
        if d <= 15: return 'C. 8–15 ngày (Chậm)'
        return 'D. > 15 ngày (Quá hạn)'
    df['LeadBucket'] = df.apply(bucket, axis=1)
    return df

# ══════════════════════════════════════════════════════════════════
#  FORMAT FACTORY
# ══════════════════════════════════════════════════════════════════
def make_formats(wb):
    def f(**kw):
        base = {'font_name': 'Aptos', 'font_size': 10, 'valign': 'vcenter'}
        base.update(kw)
        return wb.add_format(base)

    fmt = {}

    # ── Title / Section ──
    fmt['title'] = f(bold=True, font_size=20, font_color=P['white'],
                     bg_color=P['navy'], align='left', valign='vcenter',
                     left=0, right=0, top=0, bottom=0)
    fmt['meta']  = f(italic=True, font_size=9, font_color=P['g400'],
                     bg_color=P['navy'], align='left')
    fmt['sec']   = f(bold=True, font_size=10, font_color=P['navy'],
                     bg_color=P['g100'], align='left',
                     left=3, left_color=P['blue'],
                     bottom=1, bottom_color=P['g200'])
    fmt['sec2']  = f(bold=True, font_size=10, font_color=P['dteal'],
                     bg_color=P['g100'], align='left',
                     left=3, left_color=P['teal'],
                     bottom=1, bottom_color=P['g200'])

    # ── Table header ──
    fmt['th']    = f(bold=True, font_size=9, font_color=P['white'],
                     bg_color=P['navy'], align='center',
                     text_wrap=True, border=1, border_color=P['steel'])
    fmt['th_b']  = f(bold=True, font_size=9, font_color=P['white'],
                     bg_color=P['blue'], align='center',
                     text_wrap=True, border=1, border_color=P['blue'])
    fmt['th_t']  = f(bold=True, font_size=9, font_color=P['white'],
                     bg_color=P['teal'], align='center',
                     text_wrap=True, border=1, border_color=P['teal'])

    # ── Data cells — white rows ──
    fmt['dl'] = f(align='left',   border=1, border_color=P['g200'], bg_color=P['white'])
    fmt['dc'] = f(align='center', border=1, border_color=P['g200'], bg_color=P['white'])
    fmt['di'] = f(align='right',  border=1, border_color=P['g200'], bg_color=P['white'],
                  num_format='#,##0')
    fmt['dp'] = f(align='right',  border=1, border_color=P['g200'], bg_color=P['white'],
                  num_format='0.0%')
    fmt['dd'] = f(align='right',  border=1, border_color=P['g200'], bg_color=P['white'],
                  num_format='#,##0.0')

    # ── Data cells — stripe rows ──
    fmt['sl'] = f(align='left',   border=1, border_color=P['g200'], bg_color=P['lblue'])
    fmt['sc'] = f(align='center', border=1, border_color=P['g200'], bg_color=P['lblue'])
    fmt['si'] = f(align='right',  border=1, border_color=P['g200'], bg_color=P['lblue'],
                  num_format='#,##0')
    fmt['sp'] = f(align='right',  border=1, border_color=P['g200'], bg_color=P['lblue'],
                  num_format='0.0%')
    fmt['sd'] = f(align='right',  border=1, border_color=P['g200'], bg_color=P['lblue'],
                  num_format='#,##0.0')

    # ── Total row ──
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

    # ── Status badges ──
    fmt['ok']  = f(bold=True, align='center', font_color=P['dgreen'], bg_color=P['lgreen'],
                   border=1, border_color=P['green'])
    fmt['war'] = f(bold=True, align='center', font_color=P['damber'], bg_color=P['lamber'],
                   border=1, border_color=P['amber'])
    fmt['err'] = f(bold=True, align='center', font_color=P['dred'],   bg_color=P['lred'],
                   border=1, border_color=P['red'])
    fmt['inf'] = f(bold=True, align='center', font_color=P['dteal'],  bg_color=P['lteal'],
                   border=1, border_color=P['teal'])

    # ── KPI cards ──
    for tag, bg, fc, bc in [
        ('n', P['lblue'],   P['navy'],  P['blue']),
        ('g', P['lgreen'],  P['dgreen'],P['green']),
        ('r', P['lred'],    P['dred'],  P['red']),
        ('a', P['lamber'],  P['damber'],P['amber']),
        ('t', P['lteal'],   P['dteal'], P['teal']),
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
        ws.conditional_format(r0, col, r1, col, {
            'type':'data_bar','bar_color':color,'bar_only':False,
            'min_type':'num','min_value':0,'max_type':'num','max_value':1
        })
    else:
        ws.conditional_format(r0, col, r1, col, {
            'type':'data_bar','bar_color':color,'bar_only':False,
            'min_type':'min','max_type':'max'
        })


def wr(ws, fmt, r, col, vals, types, stripe):
    """Write a data row. types: l/c/i/p/d => format key prefix"""
    p = 's' if stripe else 'd'
    for i,(v,t) in enumerate(zip(vals,types)):
        fk = p+t
        if fk not in fmt: fk = ('s' if stripe else 'd')+t  # fallback
        if fk not in fmt: fk = 'dl'
        if v is None or (isinstance(v,float) and np.isnan(v)):
            ws.write_blank(r, col+i, None, fmt.get(fk, fmt['dl']))
        else:
            ws.write(r, col+i, v, fmt.get(fk, fmt['dl']))


def section(ws, fmt, row, c1, c2, text, style='sec'):
    ws.set_row(row, 20)
    ws.merge_range(row, c1, row, c2, f'  {text}', fmt[style])


def header_row(ws, fmt, row, cols, style='th', height=32):
    ws.set_row(row, height)
    for ci, h in enumerate(cols):
        ws.write(row, ci, h, fmt[style])


# ══════════════════════════════════════════════════════════════════
#  SHEET SETUP HELPER
# ══════════════════════════════════════════════════════════════════
def setup_sheet(ws, tab_color, col_widths, title_text, meta_text, fmt, month_val, year_val):
    ws.set_tab_color(tab_color)
    ws.hide_gridlines(2)
    ws.set_margins(left=0.5, right=0.5, top=0.7, bottom=0.7)
    ws.set_header(f'&L&"Aptos,Bold"&10{title_text}&R&"Aptos"&8Tháng {month_val:02d}/{year_val}  |  Trang &P / &N')
    ws.set_footer('&L&"Aptos"&8Nguồn: KQ_LCHH.parquet  —  Data Analytics Team&R&"Aptos"&8Bảo mật nội bộ')

    for ci, w in enumerate(col_widths):
        ws.set_column(ci, ci, w)

    # Title banner rows
    ws.set_row(0, 10)   # top margin
    ws.set_row(1, 42)
    ws.set_row(2, 16)
    ws.set_row(3, 8)    # gap

    ws.merge_range(1, 0, 1, len(col_widths)-1, f'  {title_text}', fmt['title'])
    ws.merge_range(2, 0, 2, len(col_widths)-1, f'  {meta_text}',  fmt['meta'])
    ws.merge_range(3, 0, 3, len(col_widths)-1, '',               fmt['meta'])

    return 4   # next available row


# ══════════════════════════════════════════════════════════════════
#  SHEET 1 — DASHBOARD TỔNG QUAN
# ══════════════════════════════════════════════════════════════════
def sheet_dashboard(wb, df, fmt, month_val, year_val, quarter_val, now_str):
    ws = wb.add_worksheet('DASHBOARD_TONG_QUAN')
    # col widths: A(2) B(18) C(14) D(14) E(14) F(14) G(14) H(14) I(14) J(14) K(14) L(2)
    cw = [2, 18, 14, 14, 14, 14, 14, 14, 14, 14, 14, 2]
    row = setup_sheet(ws, TAB_COLORS['DASHBOARD_TONG_QUAN'], cw,
        f'DASHBOARD — BÁO CÁO LUÂN CHUYỂN HÀNG HÓA  ({quarter_val})',
        f'Cập nhật: {now_str}   ·   Kỳ: Tháng {month_val:02d}/{year_val}   ·   Data Analytics Team',
        fmt, month_val, year_val)

    # ── Tính KPI ──
    N      = len(df)
    Ql     = int(df['Qty_Lenh'].sum())
    Qn     = int(df['Qty_DaNhapKho'].sum())
    Qd     = int(df['Qty_DiDuong'].sum())
    n_ok   = int((df['Danh_gia_han']=='Đúng hạn').sum())
    n_tre  = int(df['Danh_gia_han'].isin(['Trễ hạn','Trễ hạn - chưa thực hiện']).sum())
    n_chua = int((df['trang_thai_thuc_hien']=='Chưa thực hiện').sum())
    lt_avg = df.loc[df['trang_thai_thuc_hien']=='Đã thực hiện','So_ngay_thuc_hien'].mean()
    pct_n  = Qn/Ql if Ql else 0
    pct_ok = n_ok/N if N else 0

    # ── KPI CARDS (5 cards, 2 cols each, cols 1-10) ──
    ws.set_row(row,   20); ws.set_row(row+1, 36); ws.set_row(row+2, 16)
    kpi(ws,fmt, row, 1,2,  'n', 'TỔNG SỐ LỆNH',      f'{N:,}',            f'Tổng qty yêu cầu: {Ql:,} sp')
    kpi(ws,fmt, row, 3,4,  'g', 'ĐÃ NHẬP KHO CH',     f'{Qn:,} sp',        f'Hoàn thành: {pct_n:.1%}')
    kpi(ws,fmt, row, 5,6,  'g', 'ĐÚNG HẠN (SLA)',      f'{n_ok:,} lệnh',    f'Tỷ lệ SLA: {pct_ok:.1%}')
    kpi(ws,fmt, row, 7,8,  'r', 'TRỄ HẠN & CHƯA TH',  f'{n_tre:,} lệnh',   f'Đang đi đường: {Qd:,} sp')
    kpi(ws,fmt, row, 9,10, 'a', 'LEAD TIME TB',         f'{lt_avg:.1f} ngày',f'Tính trên lệnh Đã thực hiện')
    row += 4

    # ── SECTION 1: TIẾN ĐỘ THEO ĐỢT ──
    ws.set_row(row, 8)
    row += 1
    section(ws, fmt, row, 1, 10,
        '1 ·  TIẾN ĐỘ THỰC HIỆN THEO ĐỢT BÁO CÁO  (Ngày Chứng Từ Yêu Cầu)')
    row += 1

    cols1 = ['Đợt Báo Cáo\n(Ngày YC)', 'Tổng\nLệnh', 'Qty\nLệnh',
             'Đã Nhập\nKho', 'Đang Đi\nĐường', 'Chưa\nTH',
             'Tỷ Lệ\nHoàn Thành ↑', 'Đúng\nHạn', 'Trễ\nHạn', 'Lead Time\nTB (ngày)']
    header_row(ws, fmt, row, ['']+cols1+[''], height=34)
    row += 1

    dot = df.groupby('NgayYeuCau_Str', as_index=False).agg(
        SL=('Qty_Lenh','count'), QL=('Qty_Lenh','sum'),
        QN=('Qty_DaNhapKho','sum'), QD=('Qty_DiDuong','sum'),
        CTH=('trang_thai_thuc_hien', lambda s:(s=='Chưa thực hiện').sum()),
        DH=('Danh_gia_han', lambda s:(s=='Đúng hạn').sum()),
        TH=('Danh_gia_han', lambda s:s.isin(['Trễ hạn','Trễ hạn - chưa thực hiện']).sum()),
        LT=('So_ngay_thuc_hien','mean')
    ).sort_values('NgayYeuCau_Str')
    dot['PCT'] = dot['QN']/dot['QL'].replace(0,np.nan)

    DR = row
    for ri, r in dot.reset_index(drop=True).iterrows():
        odd = ri%2==1
        ws.set_row(DR+ri, 20)
        pct = r['PCT']
        ws.write(DR+ri, 0, '',          fmt['sl' if odd else 'dl'])
        ws.write(DR+ri, 1, r['NgayYeuCau_Str'], fmt['sc' if odd else 'dc'])
        ws.write(DR+ri, 2, r['SL'],     fmt['si' if odd else 'di'])
        ws.write(DR+ri, 3, r['QL'],     fmt['si' if odd else 'di'])
        ws.write(DR+ri, 4, r['QN'],     fmt['si' if odd else 'di'])
        ws.write(DR+ri, 5, r['QD'],     fmt['si' if odd else 'di'])
        ws.write(DR+ri, 6, r['CTH'],    fmt['si' if odd else 'di'])
        ws.write(DR+ri, 7, pct,         fmt['sp' if odd else 'dp'])
        ws.write(DR+ri, 8, r['DH'],     fmt['si' if odd else 'di'])
        ws.write(DR+ri, 9, r['TH'],     fmt['si' if odd else 'di'])
        ws.write(DR+ri,10, r['LT'],     fmt['sd' if odd else 'dd'])
        ws.write(DR+ri,11, '',          fmt['sl' if odd else 'dl'])

    databar(ws, DR, DR+len(dot)-1, 7, P['green'], pct=True)
    databar(ws, DR, DR+len(dot)-1, 9, P['red'],   pct=False)

    TR = DR+len(dot)
    ws.set_row(TR, 22)
    tt_pct = dot['QN'].sum()/dot['QL'].sum()
    for c, v, fk in [
        (0,'',  'TL'),(1,'TỔNG CỘNG','TL'),(2,int(dot['SL'].sum()),'TI'),
        (3,int(dot['QL'].sum()),'TI'),(4,int(dot['QN'].sum()),'TI'),
        (5,int(dot['QD'].sum()),'TI'),(6,int(dot['CTH'].sum()),'TI'),
        (7,tt_pct,'TP'),(8,int(dot['DH'].sum()),'TI'),
        (9,int(dot['TH'].sum()),'TI'),(10,float(dot['LT'].mean()),'TD'),
        (11,'','TL')
    ]:
        ws.write(TR, c, v, fmt[fk])
    row = TR+2

    # ── SECTION 2 & 3 side by side ──
    ws.set_row(row, 8); row += 1
    section(ws, fmt, row, 1, 5, '2 ·  TRẠNG THÁI THỰC HIỆN')
    section(ws, fmt, row, 6, 10,'3 ·  ĐÁNH GIÁ THỜI HẠN (SLA)', 'sec2')
    row += 1

    # Headers side by side
    ws.set_row(row, 30)
    for ci, h in enumerate(['', 'Trạng Thái', 'Số Lệnh', 'Tỷ Lệ', 'Qty Nhập', 'Đánh Giá',
                             '', 'Phân Loại', 'Số Lệnh', 'Tỷ Lệ', 'SLA', '']):
        fk = 'th' if ci <= 5 else ('th_t' if ci <= 10 else 'th')
        ws.write(row, ci, h if h else '', fmt[fk])
    row += 1

    tt = df.groupby('trang_thai_thuc_hien', as_index=False).agg(
        SL=('Qty_Lenh','count'), QN=('Qty_DaNhapKho','sum')
    ).sort_values('SL', ascending=False)
    tt['PCT'] = tt['SL']/N

    sla = df.groupby('Danh_gia_han', as_index=False).agg(
        SL=('Qty_Lenh','count')
    ).sort_values('SL', ascending=False)
    sla['PCT'] = sla['SL']/N

    ST_MAP = {
        'Đã thực hiện':       ('✔ Hoàn thành', 'ok'),
        'Thực hiện một phần': ('◑ Một phần',   'war'),
        'Đang đi đường':      ('→ In-Transit',  'inf'),
        'Chưa thực hiện':     ('✖ Tồn đọng',   'err'),
    }
    SLA_MAP = {
        'Đúng hạn':                  ('✔ On-Time',   'ok'),
        'Đang đi đường':             ('→ In-Transit', 'inf'),
        'Trễ hạn':                   ('✖ Late',       'err'),
        'Trễ hạn - chưa thực hiện': ('✖ Overdue',    'err'),
    }

    DR2 = row
    maxr = max(len(tt), len(sla))
    for ri in range(maxr):
        ws.set_row(DR2+ri, 20)
        odd = ri%2==1
        # Left table
        if ri < len(tt):
            r = tt.iloc[ri]
            lbl, fk = ST_MAP.get(r['trang_thai_thuc_hien'], ('—','dc'))
            ws.write(DR2+ri, 0, '', fmt['sl' if odd else 'dl'])
            ws.write(DR2+ri, 1, r['trang_thai_thuc_hien'], fmt['sl' if odd else 'dl'])
            ws.write(DR2+ri, 2, r['SL'],  fmt['si' if odd else 'di'])
            ws.write(DR2+ri, 3, r['PCT'], fmt['sp' if odd else 'dp'])
            ws.write(DR2+ri, 4, r['QN'],  fmt['si' if odd else 'di'])
            ws.write(DR2+ri, 5, lbl,      fmt[fk])
        else:
            for c in range(6): ws.write_blank(DR2+ri, c, None, fmt['sl' if odd else 'dl'])
        # Right table
        if ri < len(sla):
            r2 = sla.iloc[ri]
            lbl2, fk2 = SLA_MAP.get(r2['Danh_gia_han'], ('—','dc'))
            ws.write(DR2+ri, 6,  '', fmt['sl' if odd else 'dl'])
            ws.write(DR2+ri, 7,  r2['Danh_gia_han'], fmt['sl' if odd else 'dl'])
            ws.write(DR2+ri, 8,  r2['SL'],  fmt['si' if odd else 'di'])
            ws.write(DR2+ri, 9,  r2['PCT'], fmt['sp' if odd else 'dp'])
            ws.write(DR2+ri, 10, lbl2,      fmt[fk2])
            ws.write(DR2+ri, 11, '', fmt['sl' if odd else 'dl'])
        else:
            for c in range(6,12): ws.write_blank(DR2+ri, c, None, fmt['sl' if odd else 'dl'])

    databar(ws, DR2, DR2+len(tt)-1,  3, P['blue'],  pct=True)
    databar(ws, DR2, DR2+len(sla)-1, 9, P['teal'],  pct=True)

    ws.freeze_panes(4, 0)


# ══════════════════════════════════════════════════════════════════
#  SHEET 2 — PHÂN TÍCH HÀNG HÓA
# ══════════════════════════════════════════════════════════════════
def sheet_hang_hoa(wb, df, fmt, month_val, year_val, quarter_val, now_str):
    ws = wb.add_worksheet('PHAN_TICH_HANG_HOA')
    cw = [2, 22, 18, 12, 13, 13, 13, 13, 13, 13, 13, 2]
    row = setup_sheet(ws, TAB_COLORS['PHAN_TICH_HANG_HOA'], cw,
        f'PHÂN TÍCH HÀNG HÓA — Tháng {month_val:02d}/{year_val}',
        'Thống kê theo Tên hàng · Mã hàng · Nhóm hàng · Thương hiệu · Giới tính',
        fmt, month_val, year_val)

    # ── 1. Nhóm Hàng × Thương Hiệu ──
    ws.set_row(row, 8); row+=1
    section(ws, fmt, row, 1, 10, '1 ·  HIỆU SUẤT THEO NHÓM HÀNG & THƯƠNG HIỆU')
    row += 1

    h1 = ['','Nhóm Hàng','Thương Hiệu','Giới Tính','Số Lệnh','Qty Lệnh',
          'Đã Nhập','Đi Đường','Chưa TH','Tỷ Lệ\nHoàn Thành','Lead Time TB','']
    header_row(ws, fmt, row, h1, height=32); row += 1

    g1 = df.groupby(['Group_Report','Brand','Gender'], as_index=False).agg(
        SL=('Qty_Lenh','count'), QL=('Qty_Lenh','sum'), QN=('Qty_DaNhapKho','sum'),
        QD=('Qty_DiDuong','sum'), CTH=('trang_thai_thuc_hien', lambda s:(s=='Chưa thực hiện').sum()),
        LT=('So_ngay_thuc_hien','mean')
    ).sort_values(['Group_Report','QL'], ascending=[True,False])
    g1['PCT'] = g1['QN']/g1['QL'].replace(0,np.nan)

    DR = row
    for ri, r in g1.reset_index(drop=True).iterrows():
        odd = ri%2==1; z='s' if odd else 'd'; ws.set_row(DR+ri, 20)
        ws.write(DR+ri, 0,'',fmt[z+'l']); ws.write(DR+ri,11,'',fmt[z+'l'])
        ws.write(DR+ri, 1, r['Group_Report'], fmt[z+'l'])
        ws.write(DR+ri, 2, r['Brand'],         fmt[z+'l'])
        ws.write(DR+ri, 3, r['Gender'],         fmt[z+'c'])
        ws.write(DR+ri, 4, r['SL'],             fmt[z+'i'])
        ws.write(DR+ri, 5, r['QL'],             fmt[z+'i'])
        ws.write(DR+ri, 6, r['QN'],             fmt[z+'i'])
        ws.write(DR+ri, 7, r['QD'],             fmt[z+'i'])
        ws.write(DR+ri, 8, r['CTH'],            fmt[z+'i'])
        ws.write(DR+ri, 9, r['PCT'],            fmt[z+'p'])
        ws.write(DR+ri,10, r['LT'],             fmt[z+'d'])

    databar(ws, DR, DR+len(g1)-1, 9, P['green'], pct=True)
    databar(ws, DR, DR+len(g1)-1, 8, P['red'],   pct=False)
    ws.conditional_format(DR, 8, DR+len(g1)-1, 8, {
        'type':'cell','criteria':'>','value':0,
        'format': wb.add_format({'font_color':P['dred'],'bold':True,'bg_color':P['lred']})
    })

    TR = DR+len(g1); ws.set_row(TR, 22)
    tt_p = g1['QN'].sum()/g1['QL'].sum()
    row_vals = ['','TỔNG CỘNG','','', int(g1['SL'].sum()),int(g1['QL'].sum()),
                int(g1['QN'].sum()),int(g1['QD'].sum()),int(g1['CTH'].sum()),
                tt_p, float(g1['LT'].mean()),'']
    row_fmts = ['TL','TL','TL','TL','TI','TI','TI','TI','TI','TP','TD','TL']
    for ci,(v,fk) in enumerate(zip(row_vals, row_fmts)):
        ws.write(TR, ci, v, fmt[fk])
    row = TR + 2

    # ── 2. Top 25 Tên Hàng ──
    ws.set_row(row, 8); row+=1
    section(ws, fmt, row, 1, 10, '2 ·  TOP 25 TÊN HÀNG LUÂN CHUYỂN NHIỀU NHẤT', 'sec2')
    row += 1

    h2 = ['','#','Tên Hàng (Report_item_name)','Mã Hàng','Nhóm','Thương Hiệu',
          'Số Lệnh','Qty Lệnh','Đã Nhập','Đi Đường','Tỷ Lệ Nhập','']
    header_row(ws, fmt, row, h2, 'th_t', height=28); row += 1

    top = df.groupby(['Report_item_name','MaHang','Group_Report','Brand'], as_index=False).agg(
        SL=('Qty_Lenh','count'), QL=('Qty_Lenh','sum'),
        QN=('Qty_DaNhapKho','sum'), QD=('Qty_DiDuong','sum')
    ).sort_values('QL', ascending=False).head(25)
    top['PCT'] = top['QN']/top['QL'].replace(0,np.nan)

    DR2 = row
    for ri, r in top.reset_index(drop=True).iterrows():
        odd = ri%2==1; z='s' if odd else 'd'; ws.set_row(DR2+ri, 20)
        ws.write(DR2+ri, 0, '',          fmt[z+'l'])
        ws.write(DR2+ri, 1, f'#{ri+1}', fmt[z+'c'])
        ws.write(DR2+ri, 2, r['Report_item_name'], fmt[z+'l'])
        ws.write(DR2+ri, 3, r['MaHang'],  fmt[z+'c'])
        ws.write(DR2+ri, 4, r['Group_Report'], fmt[z+'l'])
        ws.write(DR2+ri, 5, r['Brand'],   fmt[z+'l'])
        ws.write(DR2+ri, 6, r['SL'],      fmt[z+'i'])
        ws.write(DR2+ri, 7, r['QL'],      fmt[z+'i'])
        ws.write(DR2+ri, 8, r['QN'],      fmt[z+'i'])
        ws.write(DR2+ri, 9, r['QD'],      fmt[z+'i'])
        ws.write(DR2+ri,10, r['PCT'],     fmt[z+'p'])
        ws.write(DR2+ri,11, '',           fmt[z+'l'])

    databar(ws, DR2, DR2+len(top)-1, 10, P['green'], pct=True)
    databar(ws, DR2, DR2+len(top)-1, 7,  P['blue'],  pct=False)
    ws.freeze_panes(4, 0)


# ══════════════════════════════════════════════════════════════════
#  SHEET 3 — CỬA HÀNG
# ══════════════════════════════════════════════════════════════════
def sheet_cua_hang(wb, df, fmt, month_val, year_val, quarter_val, now_str):
    ws = wb.add_worksheet('CUA_HANG')
    cw = [2, 28, 16, 10, 12, 12, 12, 12, 12, 2]
    row = setup_sheet(ws, TAB_COLORS['CUA_HANG'], cw,
        f'PHÂN TÍCH CỬA HÀNG ĐIỀU CHUYỂN — Tháng {month_val:02d}/{year_val}',
        'Hiệu suất gửi (Store From) và tiếp nhận (Store To) · Toàn bộ cửa hàng · Sắp xếp Qty giảm dần',
        fmt, month_val, year_val)

    # ── 1. Cửa hàng GỬI ──
    ws.set_row(row,8); row+=1
    section(ws, fmt, row, 1, 8, '1 ·  CỬA HÀNG GỬI HÀNG (STORE FROM)')
    row += 1
    h_from = ['','Cửa Hàng Gửi','Vùng','Số Lệnh','Qty Lệnh',
               'Đã Xuất','Chưa Xuất ↓','Tỷ Lệ Xuất ↑','Lead Time TB','']
    header_row(ws, fmt, row, h_from, height=30); row += 1

    sf = df.groupby(['Store_from','Region_from'], as_index=False).agg(
        SL=('Qty_Lenh','count'), QL=('Qty_Lenh','sum'),
        QX=('Qty_DaChuyen','sum'), LT=('So_ngay_thuc_hien','mean')
    ).sort_values('QL', ascending=False)
    sf['CX']  = (sf['QL']-sf['QX']).clip(lower=0)
    sf['PCT'] = sf['QX']/sf['QL'].replace(0,np.nan)

    DR = row
    for ri, r in sf.reset_index(drop=True).iterrows():
        odd = ri%2==1; z='s' if odd else 'd'; ws.set_row(DR+ri, 20)
        ws.write(DR+ri,0,'',fmt[z+'l']); ws.write(DR+ri,9,'',fmt[z+'l'])
        ws.write(DR+ri,1, r['Store_from'],  fmt[z+'l'])
        ws.write(DR+ri,2, r['Region_from'], fmt[z+'c'])
        ws.write(DR+ri,3, r['SL'],          fmt[z+'i'])
        ws.write(DR+ri,4, r['QL'],          fmt[z+'i'])
        ws.write(DR+ri,5, r['QX'],          fmt[z+'i'])
        ws.write(DR+ri,6, r['CX'],          fmt[z+'i'])
        ws.write(DR+ri,7, r['PCT'],         fmt[z+'p'])
        ws.write(DR+ri,8, r['LT'],          fmt[z+'d'])

    databar(ws, DR, DR+len(sf)-1, 7, P['green'], pct=True)
    databar(ws, DR, DR+len(sf)-1, 4, P['blue'],  pct=False)
    ws.conditional_format(DR, 6, DR+len(sf)-1, 6, {
        'type':'cell','criteria':'>','value':0,
        'format': wb.add_format({'bg_color':P['lred'],'font_color':P['dred'],'bold':True,'border':1})
    })

    TR = DR+len(sf); ws.set_row(TR, 22)
    for c,v,fk in [(0,'','TL'),(1,'TỔNG CỘNG','TL'),(2,f'{len(sf)} cửa hàng','TL'),
                   (3,int(sf['SL'].sum()),'TI'),(4,int(sf['QL'].sum()),'TI'),
                   (5,int(sf['QX'].sum()),'TI'),(6,int(sf['CX'].sum()),'TI'),
                   (7,sf['QX'].sum()/sf['QL'].sum(),'TP'),(8,float(sf['LT'].mean()),'TD'),(9,'','TL')]:
        ws.write(TR, c, v, fmt[fk])
    row = TR+2

    # ── 2. Cửa hàng NHẬN ──
    ws.set_row(row,8); row+=1
    section(ws, fmt, row, 1, 8, '2 ·  CỬA HÀNG NHẬN HÀNG (STORE TO)', 'sec2')
    row += 1
    h_to = ['','Cửa Hàng Nhận','Vùng','Số Lệnh','Qty Lệnh',
             'Đã Nhập Kho','Chưa Nhập ↓','Tỷ Lệ Nhập ↑','Lead Time TB','']
    header_row(ws, fmt, row, h_to, 'th_t', height=30); row += 1

    st = df.groupby(['Store_to','Region_to'], as_index=False).agg(
        SL=('Qty_Lenh','count'), QL=('Qty_Lenh','sum'),
        QN=('Qty_DaNhapKho','sum'), QD=('Qty_DiDuong','sum'), LT=('So_ngay_thuc_hien','mean')
    ).sort_values('QL', ascending=False)
    st['CN']  = (st['QL']-st['QN']-st['QD']).clip(lower=0)
    st['PCT'] = st['QN']/st['QL'].replace(0,np.nan)

    DR2 = row
    for ri, r in st.reset_index(drop=True).iterrows():
        odd = ri%2==1; z='s' if odd else 'd'; ws.set_row(DR2+ri, 20)
        ws.write(DR2+ri,0,'',fmt[z+'l']); ws.write(DR2+ri,9,'',fmt[z+'l'])
        ws.write(DR2+ri,1, r['Store_to'],   fmt[z+'l'])
        ws.write(DR2+ri,2, r['Region_to'],  fmt[z+'c'])
        ws.write(DR2+ri,3, r['SL'],         fmt[z+'i'])
        ws.write(DR2+ri,4, r['QL'],         fmt[z+'i'])
        ws.write(DR2+ri,5, r['QN'],         fmt[z+'i'])
        ws.write(DR2+ri,6, r['CN'],         fmt[z+'i'])
        ws.write(DR2+ri,7, r['PCT'],        fmt[z+'p'])
        ws.write(DR2+ri,8, r['LT'],         fmt[z+'d'])

    databar(ws, DR2, DR2+len(st)-1, 7, P['teal'],  pct=True)
    databar(ws, DR2, DR2+len(st)-1, 4, P['steel'], pct=False)
    ws.conditional_format(DR2, 6, DR2+len(st)-1, 6, {
        'type':'cell','criteria':'>','value':0,
        'format': wb.add_format({'bg_color':P['lred'],'font_color':P['dred'],'bold':True,'border':1})
    })

    TR2 = DR2+len(st); ws.set_row(TR2, 22)
    for c,v,fk in [(0,'','TL'),(1,'TỔNG CỘNG','TL'),(2,f'{len(st)} cửa hàng','TL'),
                   (3,int(st['SL'].sum()),'TI'),(4,int(st['QL'].sum()),'TI'),
                   (5,int(st['QN'].sum()),'TI'),(6,int(st['CN'].sum()),'TI'),
                   (7,st['QN'].sum()/st['QL'].sum(),'TP'),(8,float(st['LT'].mean()),'TD'),(9,'','TL')]:
        ws.write(TR2, c, v, fmt[fk])

    ws.freeze_panes(4, 0)


# ══════════════════════════════════════════════════════════════════
#  SHEET 4 — TIẾN ĐỘ & SLA
# ══════════════════════════════════════════════════════════════════
def sheet_sla(wb, df, fmt, month_val, year_val, quarter_val, now_str):
    ws = wb.add_worksheet('TIEN_DO_VA_SLA')
    cw = [2, 26, 16, 14, 10, 10, 14, 10, 10, 10, 10, 26, 2]
    row = setup_sheet(ws, TAB_COLORS['TIEN_DO_VA_SLA'], cw,
        f'PHÂN TÍCH TIẾN ĐỘ & SLA — Tháng {month_val:02d}/{year_val}',
        'Lead Time Distribution  ·  Danh sách lệnh trễ hạn  ·  Sắp xếp: Số ngày trễ giảm dần',
        fmt, month_val, year_val)

    # ── 1. Lead Time Distribution ──
    ws.set_row(row,8); row+=1
    section(ws, fmt, row, 1, 6, '1 ·  PHÂN BỔ THỜI GIAN HOÀN TẤT LỆNH')
    row+=1

    h1=['','Nhóm Thời Gian','Số Lệnh','Tỷ Lệ','Qty Lệnh','Đã Nhập','Tỷ Lệ Nhập','']
    header_row(ws, fmt, row, h1, height=28); row+=1

    lead = df.groupby('LeadBucket', as_index=False).agg(
        SL=('Qty_Lenh','count'), QL=('Qty_Lenh','sum'), QN=('Qty_DaNhapKho','sum')
    ).sort_values('LeadBucket')
    lead['PL'] = lead['SL']/len(df)
    lead['PN'] = lead['QN']/lead['QL'].replace(0,np.nan)

    LEAD_FMT = {
        'A. ≤ 3 ngày (Nhanh)':       'ok',
        'B. 4–7 ngày (Tiêu chuẩn)':  'ok',
        'C. 8–15 ngày (Chậm)':       'war',
        'D. > 15 ngày (Quá hạn)':    'err',
        'D. Đang đi đường':          'inf',
        'E. Chưa thực hiện':          'err',
    }
    DR = row
    for ri, r in lead.reset_index(drop=True).iterrows():
        odd=ri%2==1; z='s' if odd else 'd'; ws.set_row(DR+ri, 20)
        ws.write(DR+ri,0,'',fmt[z+'l']); ws.write(DR+ri,7,'',fmt[z+'l'])
        ws.write(DR+ri,1, r['LeadBucket'], fmt[LEAD_FMT.get(r['LeadBucket'],'war')])
        ws.write(DR+ri,2, r['SL'],  fmt[z+'i'])
        ws.write(DR+ri,3, r['PL'],  fmt[z+'p'])
        ws.write(DR+ri,4, r['QL'],  fmt[z+'i'])
        ws.write(DR+ri,5, r['QN'],  fmt[z+'i'])
        ws.write(DR+ri,6, r['PN'],  fmt[z+'p'])

    databar(ws, DR, DR+len(lead)-1, 3, P['blue'],  pct=True)
    databar(ws, DR, DR+len(lead)-1, 6, P['green'], pct=True)


    row = DR+len(lead)+2

    # ── 2. Danh Sách Trễ Hạn ──
    ws.set_row(row,8); row+=1
    delay = df[df['Danh_gia_han'].isin(['Trễ hạn','Trễ hạn - chưa thực hiện'])].sort_values(
        'So_ngay_tre', ascending=False)
    section(ws, fmt, row, 1, 11,
        f'2 ·  DANH SÁCH {len(delay)} LỆNH TRỄ HẠN — Sắp xếp: Số ngày trễ giảm dần', 'sec2')
    row+=1

    h2=['','Ngày YC','Cửa Hàng Chuyển','Cửa Hàng Nhận','Mã Hàng','Size',
        'Qty\nLệnh','Đã\nNhập','Số Ngày\nTH','Số Ngày\nTrễ ↓','Lý Do','']
    header_row(ws, fmt, row, h2, 'th_t', height=32); row+=1

    DR2=row
    for ri, r in delay.reset_index(drop=True).iterrows():
        odd=ri%2==1; z='s' if odd else 'd'; ws.set_row(DR2+ri, 20)
        tre = r['So_ngay_tre']
        badge_fk = 'err' if tre>=5 else ('war' if tre>0 else 'inf')
        ws.write(DR2+ri, 0,'',fmt[z+'l']); ws.write(DR2+ri,12,'',fmt[z+'l'])
        ws.write(DR2+ri, 1, r['NgayYeuCau_Str'],   fmt[z+'c'])
        ws.write(DR2+ri, 2, r['Store_from'],       fmt[z+'l'])
        ws.write(DR2+ri, 3, r['Store_to'],         fmt[z+'l'])
        ws.write(DR2+ri, 4, r['MaHang'],           fmt[z+'c'])
        ws.write(DR2+ri, 5, r['Size'],             fmt[z+'c'])
        ws.write(DR2+ri, 6, r['Qty_Lenh'],         fmt[z+'i'])
        ws.write(DR2+ri, 7, r['Qty_DaNhapKho'],    fmt[z+'i'])
        ws.write(DR2+ri, 8, r['So_ngay_thuc_hien'],fmt[z+'d'])
        ws.write(DR2+ri, 9, tre,                   fmt[badge_fk])
        ws.write(DR2+ri,10, r['ly_do'],            fmt[z+'l'])

    ws.conditional_format(DR2,9,DR2+len(delay)-1,9,{
        'type':'3_color_scale','min_color':P['lamber'],'mid_color':P['amber'],'max_color':P['red'],
        'min_type':'num','min_value':0,'max_type':'max'})
    ws.freeze_panes(4,0)


# ══════════════════════════════════════════════════════════════════
#  SHEET 5 — CHƯA THỰC HIỆN
# ══════════════════════════════════════════════════════════════════
def sheet_chua_th(wb, df, fmt, month_val, year_val, quarter_val, now_str):
    ws = wb.add_worksheet('CHUA_THUC_HIEN')
    cw = [2, 14, 26, 26, 14, 22, 8, 10, 28, 2]
    chua = df[df['trang_thai_thuc_hien']=='Chưa thực hiện'].copy()
    chua['LyDo_Clean'] = chua['ly_do'].apply(
        lambda x: x.strip() if str(x).strip() not in ['','nan'] else '(Chưa cập nhật lý do)'
    )
    N = len(chua)

    row = setup_sheet(ws, TAB_COLORS['CHUA_THUC_HIEN'], cw,
        f'LỆNH CHƯA THỰC HIỆN — Tháng {month_val:02d}/{year_val}',
        f'Tổng cộng {N} lệnh chưa thực hiện  ·  Tất cả đã Trễ hạn  ·  Root Cause Analysis',
        fmt, month_val, year_val)

    # ── 1. Root Cause ──
    ws.set_row(row,8); row+=1
    section(ws, fmt, row, 1, 5, '1 ·  TỔNG HỢP NGUYÊN NHÂN CHƯA THỰC HIỆN (ROOT CAUSE)')
    row+=1

    h1=['','Lý Do / Nguyên Nhân','Số Lệnh','Tỷ Lệ','Qty SP','Phân Loại Rủi Ro','']
    header_row(ws, fmt, row, h1, height=28); row+=1

    rc = chua.groupby('LyDo_Clean', as_index=False).agg(
        SL=('Qty_Lenh','count'), QL=('Qty_Lenh','sum')
    ).sort_values('SL', ascending=False)
    rc['PCT'] = rc['SL']/N

    def classify(ly):
        l = ly.lower()
        if 'chưa cập nhật' in l or 'không ghi' in l: return ('❓ Chưa xác định', 'war')
        if any(k in l for k in ['hết tồn','hết ko','bán hết','hàng lỗi']): return ('❌ Hết / Lỗi hàng','err')
        if any(k in l for k in ['giữ lại','khách đặt','xuất cho','đặt']): return ('🔄 Giữ hàng','war')
        if any(k in l for k in ['sai tn','xuất sai','sai mã','xuất nhầm','sai cn']): return ('⚡ Lỗi nghiệp vụ','err')
        if any(k in l for k in ['đang sửa','sửa không','sửa chửa']): return ('🔧 Đang sửa chữa','inf')
        return ('⚠ Nguyên nhân khác','war')

    DR=row
    for ri, r in rc.reset_index(drop=True).iterrows():
        odd=ri%2==1; z='s' if odd else 'd'; ws.set_row(DR+ri, 20)
        lbl, fk = classify(r['LyDo_Clean'])
        ws.write(DR+ri,0,'',fmt[z+'l']); ws.write(DR+ri,6,'',fmt[z+'l'])
        ws.write(DR+ri,1, r['LyDo_Clean'], fmt[z+'l'])
        ws.write(DR+ri,2, r['SL'],          fmt[z+'i'])
        ws.write(DR+ri,3, r['PCT'],         fmt[z+'p'])
        ws.write(DR+ri,4, r['QL'],          fmt[z+'i'])
        ws.write(DR+ri,5, lbl,             fmt[fk])

    databar(ws, DR, DR+len(rc)-1, 3, P['red'],   pct=True)
    databar(ws, DR, DR+len(rc)-1, 2, P['amber'], pct=False)


    row = DR+len(rc)+2

    # ── 2. Chi Tiết ──
    ws.set_row(row,8); row+=1
    section(ws, fmt, row, 1, 8,
        f'2 ·  CHI TIẾT {N} LỆNH CHƯA THỰC HIỆN — Sắp xếp: Ngày YC → Cửa hàng → Mã hàng', 'sec2')
    row+=1

    h2=['','Ngày YC','Cửa Hàng Chuyển','Cửa Hàng Nhận','Mã Hàng','Tên Hàng','Size','Qty','Lý Do / Ghi Chú','']
    header_row(ws, fmt, row, h2, 'th_t', height=28); row+=1

    chua_s = chua.sort_values(['NgayYeuCau_Str','Store_from','Store_to'])
    DR2=row
    for ri, r in chua_s.reset_index(drop=True).iterrows():
        odd=ri%2==1; z='s' if odd else 'd'; ws.set_row(DR2+ri, 20)
        ly = r['LyDo_Clean']
        lbl, fk = classify(ly)
        fk_ly = fk if '?' in lbl or '!' in lbl or '⚡' in lbl else z+'l'
        ws.write(DR2+ri,0,'',fmt[z+'l']); ws.write(DR2+ri,9,'',fmt[z+'l'])
        ws.write(DR2+ri,1, r['NgayYeuCau_Str'],   fmt[z+'c'])
        ws.write(DR2+ri,2, r['Store_from'],       fmt[z+'l'])
        ws.write(DR2+ri,3, r['Store_to'],         fmt[z+'l'])
        ws.write(DR2+ri,4, r['MaHang'],           fmt[z+'c'])
        ws.write(DR2+ri,5, r['Report_item_name'], fmt[z+'l'])
        ws.write(DR2+ri,6, r['Size'],             fmt[z+'c'])
        ws.write(DR2+ri,7, r['Qty_Lenh'],         fmt[z+'i'])
        ws.write(DR2+ri,8, ly,                    fmt[z+'l'])

    ws.freeze_panes(row, 0)


# ══════════════════════════════════════════════════════════════════
#  SHEET 6 — DỮ LIỆU CHI TIẾT
# ══════════════════════════════════════════════════════════════════
def sheet_detail(wb, df, fmt, month_val, year_val, quarter_val, now_str):
    ws = wb.add_worksheet('DU_LIEU_CHI_TIET')
    ws.set_tab_color(TAB_COLORS['DU_LIEU_CHI_TIET'])
    ws.hide_gridlines(2)
    ws.set_row(0, 28)

    COLS = ['NgayChungTu_YeuCau','Operation','Store_from','Region_from','Store_to','Region_to',
            'MaHang','Report_item_name','Size','Brand','Group_Report','Gender',
            'Qty_Lenh','Qty_DaChuyen','Qty_DaNhapKho','Qty_DiDuong',
            'trang_thai_thuc_hien','Ngay_thuc_hien','So_ngay_thuc_hien','So_ngay_tre',
            'Danh_gia_han','Qty_TraKho','Qty_ChuyenDiTiep','ChuyenDiTiep_toi','ly_do']
    COLS = [c for c in COLS if c in df.columns]

    INT_C  = {'Qty_Lenh','Qty_DaChuyen','Qty_DaNhapKho','Qty_DiDuong','Qty_TraKho','Qty_ChuyenDiTiep'}
    DEC_C  = {'So_ngay_thuc_hien','So_ngay_tre'}
    DATE_C = {'NgayChungTu_YeuCau','Ngay_thuc_hien'}

    for ci, col in enumerate(COLS):
        ws.write(0, ci, col, fmt['th'])
        ws.set_column(ci, ci, max(10, min(32, len(col)+4)))

    DH_COL = COLS.index('Danh_gia_han')   if 'Danh_gia_han' in COLS else None
    TT_COL = COLS.index('trang_thai_thuc_hien') if 'trang_thai_thuc_hien' in COLS else None

    for ri, row in df.reset_index(drop=True).iterrows():
        r = ri+1; odd=ri%2==1; z='s' if odd else 'd'
        for ci, col in enumerate(COLS):
            val = row[col]
            if col in DATE_C:
                ws.write(r, ci, str(val)[:10] if pd.notna(val) else '—', fmt[z+'c'])
            elif col in INT_C:
                ws.write(r, ci, int(val) if pd.notna(val) else 0, fmt[z+'i'])
            elif col in DEC_C:
                ws.write(r, ci, float(val) if pd.notna(val) else 0.0, fmt[z+'d'])
            else:
                ws.write(r, ci, str(val) if pd.notna(val) else '—', fmt[z+'l'])

    if DH_COL is not None:
        ws.conditional_format(1,DH_COL,len(df),DH_COL,{
            'type':'text','criteria':'containing','value':'Đúng hạn',
            'format': wb.add_format({'bg_color':P['lgreen'],'font_color':P['dgreen'],'bold':True})})
        ws.conditional_format(1,DH_COL,len(df),DH_COL,{
            'type':'text','criteria':'containing','value':'Trễ',
            'format': wb.add_format({'bg_color':P['lred'],'font_color':P['dred'],'bold':True})})
        ws.conditional_format(1,DH_COL,len(df),DH_COL,{
            'type':'text','criteria':'containing','value':'đường',
            'format': wb.add_format({'bg_color':P['lteal'],'font_color':P['dteal'],'bold':True})})

    ws.freeze_panes(1, 0)
    ws.autofilter(0, 0, len(df), len(COLS)-1)


# ══════════════════════════════════════════════════════════════════
#  MAIN ENTRY
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
        ('DASHBOARD_TONG_QUAN', sheet_dashboard),
        ('PHAN_TICH_HANG_HOA',  sheet_hang_hoa),
        ('CUA_HANG',            sheet_cua_hang),
        ('TIEN_DO_VA_SLA',      sheet_sla),
        ('CHUA_THUC_HIEN',      sheet_chua_th),
        ('DU_LIEU_CHI_TIET',    sheet_detail),
    ]:
        fn(*args)
        print(f'  ✓ [{name}]')

    wb.close()
    print(f'→ {output_path}')


def main():
    print('═'*70)
    print('  BÁO CÁO LUÂN CHUYỂN HÀNG HÓA — v3.0 PROFESSIONAL')
    print('═'*70)
    df = load_data(DEFAULT_PARQUET)
    print(f'  Dữ liệu: {len(df):,} dòng  |  {df["NgayYeuCau_Str"].nunique()} đợt  |  '
          f'Tháng {int(df["Month"].iloc[0]):02d}/{int(df["Year"].iloc[0])}')

    y, m = int(df['Year'].iloc[0]), int(df['Month'].iloc[0])
    fn_month  = f'BaoCao_PhanTich_LCHH_{y}_{m:02d}.xlsx'
    fn_latest = 'BaoCao_PhanTich_LCHH_Latest.xlsx'

    print('\n  Đang tạo file Excel chuyên nghiệp v3.0...')
    create_report(df, os.path.join(REPORTS_DIR, fn_month))
    create_report(df, os.path.join(REPORTS_DIR, fn_latest))

    print('\n' + '═'*70)
    print(f'  HOÀN THÀNH!')
    print(f'  📁 {os.path.join(REPORTS_DIR, fn_month)}')
    print(f'  📁 {os.path.join(REPORTS_DIR, fn_latest)}')
    print('═'*70)


if __name__ == '__main__':
    main()

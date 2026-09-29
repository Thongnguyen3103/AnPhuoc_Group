#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Render_Html_Output.py — Stage 5: Đóng gói Payload và render file HTML tự chứa
- GZIP + Base64 payload dữ liệu tổng hợp
- Nhúng style.css, plotly-basic.min.js, segments.js, engine.js vào template.html
- Xuất file duy nhất ra 04.Output/Report_Summary/BaoCao_TongHop.html (< 15 MB)
"""
import os
import sys
import time
import json
import gzip
import base64
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

import Get_Paths

STAGE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = STAGE_DIR
ROOT = os.path.dirname(BACKEND_DIR)

SHELL_DIR = os.path.join(ROOT, 'Template')
DIST_DIR = Get_Paths.thu_muc_ket_qua('Report_Summary')   # 04.Output/Report_Summary
OUT_HTML = os.path.join(DIST_DIR, 'BaoCao_TongHop.html')


def run(ton_payload, ban_payload, shared_dict, ref_year, ref_month):
    t0 = time.time()
    print('=' * 65)
    print('  [STAGE 5] RENDER SELF-CONTAINED HTML (04.Output/Report_Summary/BaoCao_TongHop.html)')
    print('=' * 65)

    os.makedirs(DIST_DIR, exist_ok=True)

    # 1. Đóng gói Payload JSON
    build_time_str = datetime.now().strftime('%d/%m/%Y %H:%M')
    full_payload = {
        'v': 3,
        'built': build_time_str,
        'ref': {
            'year': ref_year,
            'month': ref_month,
            'label': f'T{ref_month}/{ref_year}'
        },
        'dict': shared_dict['list'],
        'ton': ton_payload,
        'ban': ban_payload
    }

    print('   Đang chuyển đổi JSON, nén GZIP và mã hóa Base64...')
    json_bytes = json.dumps(full_payload, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    raw_mb = len(json_bytes) / (1024 * 1024)

    gz_bytes = gzip.compress(json_bytes, compresslevel=9)
    gz_mb = len(gz_bytes) / (1024 * 1024)

    b64_str = base64.b64encode(gz_bytes).decode('ascii')
    b64_mb = len(b64_str) / (1024 * 1024)

    print(f'   - Dung lượng JSON thô: {raw_mb:.2f} MB')
    print(f'   - Dung lượng GZIP:    {gz_mb:.2f} MB (Tỉ lệ nén: {raw_mb/gz_mb:.1f}x)')
    print(f'   - Chuỗi Base64:       {b64_mb:.2f} MB')

    # 2. Đọc các tệp tin vỏ (Shell)
    template_path = os.path.join(SHELL_DIR, 'Report_Template.html')
    style_path = os.path.join(SHELL_DIR, 'Report_Style.css')
    plotly_path = os.path.join(SHELL_DIR, 'Vendor', 'plotly-basic.min.js')
    segments_path = os.path.join(SHELL_DIR, 'Report_Segments.js')
    engine_path = os.path.join(SHELL_DIR, 'Report_Engine.js')

    with open(template_path, 'r', encoding='utf-8') as f:
        html = f.read()

    with open(style_path, 'r', encoding='utf-8') as f:
        css_content = f.read()

    with open(plotly_path, 'r', encoding='utf-8') as f:
        plotly_content = f.read()

    with open(segments_path, 'r', encoding='utf-8') as f:
        segments_content = f.read()

    with open(engine_path, 'r', encoding='utf-8') as f:
        engine_content = f.read()

    # 3. Ghép nối trực tiếp (Inlining không regex)
    print('   Đang nhúng style, script và payload vào khung HTML...')
    # Nhúng CSS
    html = html.replace('<link rel="stylesheet" href="Report_Style.css">', f'<style>\n{css_content}\n</style>')

    # Nhúng Payload Base64
    placeholder = '<!-- PAYLOAD_PLACEHOLDER -->'
    if placeholder not in html:
        raise ValueError('Không tìm thấy placeholder <!-- PAYLOAD_PLACEHOLDER --> trong Report_Template.html!')
    html = html.replace(placeholder, b64_str)

    # Nhúng Scripts
    script_block = f"""
  <script>
{plotly_content}
  </script>
  <script>
{segments_content}
  </script>
  <script>
{engine_content}
  </script>
    """

    old_scripts = """  <script src="Vendor/plotly-basic.min.js"></script>
  <script src="Report_Segments.js"></script>
  <script src="Report_Engine.js"></script>"""
    html = html.replace(old_scripts, script_block)

    # 4. Ghi file thành phẩm ra dist
    with open(OUT_HTML, 'w', encoding='utf-8') as f:
        f.write(html)

    final_mb = os.path.getsize(OUT_HTML) / (1024 * 1024)
    print('=' * 65)
    print(f'   XUẤT BẢN THÀNH CÔNG: {OUT_HTML}')
    print(f'   Kích thước file:      {final_mb:.2f} MB')
    print(f'   Thời gian thực hiện:  {time.time()-t0:.1f}s')
    print('=' * 65)

    if final_mb > 15.0:
        print(f'   [CẢNH BÁO] Kích thước file ({final_mb:.2f} MB) vượt ngưỡng mục tiêu 15 MB!')
    else:
        print(f'   [ĐẠT CHUẨN] File nhẹ, tải nhanh qua Google Drive (< 15 MB).')

    return OUT_HTML


if __name__ == '__main__':
    print('Render stage helper module.')

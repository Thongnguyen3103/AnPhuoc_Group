#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Serve_Lan.py — Chia sẻ báo cáo trong mạng nội bộ (wifi/LAN công ty)
- Phục vụ thư mục 04.Output/Report_Summary trên 0.0.0.0:<port> (mặc định 8765)
- Nén GZIP khi trình duyệt hỗ trợ (file HTML nhúng Base64 -> giảm ~25% đường truyền);
  bản nén được cache theo mtime, build lại báo cáo là tự nén lại.
Chạy: python Core/Serve_Lan.py [port]
"""
import os
import sys
import gzip
import socket
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), '00.Shared'))

import Get_Paths

SERVE_DIR = Get_Paths.thu_muc_ket_qua('Report_Summary')
GZIP_TYPES = ('.html', '.js', '.css', '.json')
_gz_cache = {}   # path -> (mtime, bytes)

# Nhật ký truy cập (IP máy xem) — dùng để chẩn đoán máy ở wifi/dải mạng khác có tới được không
ACCESS_LOG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'Cache', 'Serve_Lan_access.log')


def _gzip_bytes(path):
    mtime = os.path.getmtime(path)
    hit = _gz_cache.get(path)
    if hit and hit[0] == mtime:
        return hit[1]
    with open(path, 'rb') as f:
        data = gzip.compress(f.read(), compresslevel=6)
    _gz_cache[path] = (mtime, data)
    return data


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=SERVE_DIR, **kwargs)

    def send_head(self):
        path = self.translate_path(self.path)
        if (os.path.isfile(path) and path.lower().endswith(GZIP_TYPES)
                and 'gzip' in self.headers.get('Accept-Encoding', '')):
            data = _gzip_bytes(path)
            self.send_response(200)
            self.send_header('Content-Type', self.guess_type(path))
            self.send_header('Content-Encoding', 'gzip')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            if self.command == 'GET':
                self.wfile.write(data)
            return None
        return super().send_head()

    def log_message(self, format, *args):
        line = '%s - [%s] %s' % (self.client_address[0], self.log_date_time_string(), format % args)
        print(line, flush=True)
        try:
            with open(ACCESS_LOG, 'a', encoding='utf-8') as f:
                f.write(line + '\n')
        except OSError:
            pass


def _lan_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(('10.255.255.255', 1))
            return s.getsockname()[0]
    except OSError:
        return '127.0.0.1'


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print(f'Đang chia sẻ: {SERVE_DIR}')
    print(f'Máy khác cùng mạng mở: http://{_lan_ip()}:{port}/BaoCao_TongHop.html')
    print(f'Nhật ký truy cập (IP máy xem): {ACCESS_LOG}')
    print('Máy ở wifi/dải mạng khác không mở được mà nhật ký KHÔNG có IP của máy đó')
    print(f'-> bị chặn trước khi tới máy này: mở cổng TCP {port} trên tường lửa (Kaspersky) / router.', flush=True)
    ThreadingHTTPServer(('0.0.0.0', port), Handler).serve_forever()

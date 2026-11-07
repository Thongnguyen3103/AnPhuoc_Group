#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Chạy Web app Báo cáo Tổng hợp: python run_server.py   (cấu hình trong .env)"""
import sys
from pathlib import Path

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parent))   # chạy được từ thư mục bất kỳ

from app.config import get_settings  # noqa: E402
from app.main import create_app  # noqa: E402

if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    settings = get_settings()
    print(f'Báo cáo Tổng hợp — http://{settings.host}:{settings.port}  (dữ liệu: {settings.data_dir})', flush=True)
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port,
                proxy_headers=False, server_header=False, log_level='info')

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Công cụ quản trị dòng lệnh.

  python manage.py init-db
  python manage.py create-user <ten> [--role admin|viewer] [--full-name "Họ tên"] [--set-password]
  python manage.py reset-password <ten> [--set-password]
  python manage.py list-users
  python manage.py import-snapshot

Mặc định hệ thống sinh mật khẩu tạm (in ra 1 lần, bắt đổi ở lần đăng nhập đầu).
--set-password: tự nhập mật khẩu (ẩn ký tự).
"""
import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))   # chạy được từ thư mục bất kỳ

from app import db  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.repositories import audit, sessions, users  # noqa: E402
from app.security import generate_temp_password, hash_password, validate_new_password  # noqa: E402
from app.services.snapshots import SnapshotError, SnapshotService  # noqa: E402


def _ask_password() -> str:
    while True:
        pw = getpass.getpass('Mật khẩu mới: ')
        err = validate_new_password(pw)
        if err:
            print(err)
            continue
        if pw != getpass.getpass('Nhập lại: '):
            print('Hai lần nhập không khớp.')
            continue
        return pw


def _password(args) -> tuple:
    if args.set_password:
        return _ask_password(), False
    return generate_temp_password(), True


def main() -> int:
    sys.stdout.reconfigure(encoding='utf-8')
    p = argparse.ArgumentParser(description='Quản trị Report_Summary_App')
    sub = p.add_subparsers(dest='cmd', required=True)
    sub.add_parser('init-db')
    c = sub.add_parser('create-user')
    c.add_argument('username')
    c.add_argument('--role', choices=['admin', 'viewer'], default='viewer')
    c.add_argument('--full-name', default='')
    c.add_argument('--set-password', action='store_true')
    r = sub.add_parser('reset-password')
    r.add_argument('username')
    r.add_argument('--set-password', action='store_true')
    sub.add_parser('list-users')
    sub.add_parser('import-snapshot')
    args = p.parse_args()

    settings = get_settings()
    db.migrate(settings.db_path)
    conn = db.connect(settings.db_path)
    try:
        if args.cmd == 'init-db':
            print(f'CSDL sẵn sàng: {settings.db_path}')

        elif args.cmd == 'create-user':
            if users.get_by_username(conn, args.username):
                print(f'Tên đăng nhập "{args.username}" đã tồn tại.')
                return 1
            pw, temp = _password(args)
            with db.transaction(conn):
                users.create(conn, args.username, args.full_name, hash_password(pw), args.role, temp)
                audit.log(conn, 'user.create', None, f'{args.username} ({args.role}) qua CLI', username='cli')
            print(f'Đã tạo {args.username} ({args.role}).')
            if temp:
                print(f'Mật khẩu tạm (chỉ hiện 1 lần, phải đổi khi đăng nhập): {pw}')

        elif args.cmd == 'reset-password':
            row = users.get_by_username(conn, args.username)
            if not row:
                print(f'Không có người dùng "{args.username}".')
                return 1
            pw, temp = _password(args)
            with db.transaction(conn):
                users.update_fields(conn, row['id'], password_hash=hash_password(pw),
                                    must_change_password=int(temp), is_active=1)
                sessions.delete_for_user(conn, row['id'])
                audit.log(conn, 'user.reset_password', None, f'{args.username} qua CLI', username='cli')
            print(f'Đã đặt lại mật khẩu cho {args.username} (và mở khóa nếu đang khóa).')
            if temp:
                print(f'Mật khẩu tạm (chỉ hiện 1 lần): {pw}')

        elif args.cmd == 'list-users':
            for u in users.list_all(conn):
                state = 'hoạt động' if u['is_active'] else 'đã khóa'
                print(f"{u['username']:<24} {u['role']:<7} {state:<10} {u['full_name']}")

        elif args.cmd == 'import-snapshot':
            try:
                row, created = SnapshotService(settings).import_latest(conn)
            except SnapshotError as e:
                print(f'Lỗi: {e}')
                return 1
            print(('Đã nạp' if created else 'Đã có sẵn') + f" snapshot #{row['id']} {row['ref_label']} (build {row['built_at']})")
        return 0
    finally:
        conn.close()


if __name__ == '__main__':
    raise SystemExit(main())

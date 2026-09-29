# -*- coding: utf-8 -*-
"""Đường dẫn dùng chung cho toàn bộ 01.Python_Projects.

Mọi đường dẫn khai báo DUY NHẤT trong 00.Shared/Config_Paths.yaml.

Cách dùng trong project (thêm 00.Shared vào sys.path rồi import thẳng module):

    sys.path.insert(0, os.path.join(<thu muc 01.Python_Projects>, "00.Shared"))
    import Get_Paths

    Get_Paths.ban_le                          # -> D:\\...\\03.Data_Parquest\\01.System_sales
    Get_Paths.lay("region")                   # như trên, dạng hàm
    Get_Paths.lay("region", bat_buoc=True)    # báo lỗi nếu file/thư mục không tồn tại
    Get_Paths.thu_muc_ket_qua("Report_LCHH")  # -> ...\\04.Output\\Report_LCHH (tự tạo)

Chạy trực tiếp để kiểm tra toàn bộ đường dẫn:  python 00.Shared/Get_Paths.py
"""
from __future__ import annotations

import os

SHARED_DIR = os.path.dirname(os.path.abspath(__file__))       # 00.Shared
PROJECTS_ROOT = os.path.dirname(SHARED_DIR)                   # 01.Python_Projects
CONFIG_FILE = os.path.join(SHARED_DIR, "Config_Paths.yaml")


def _parse_simple_yaml(text: str) -> dict:
    """Đọc Config_Paths.yaml khi môi trường không có PyYAML (vd env inventory_env).
    Chỉ hỗ trợ đúng dạng của file: `key: "gia tri"` và 1 cấp lồng (paths:)."""
    cfg: dict = {}
    section = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        value = value.strip()
        if value.startswith(('"', "'")):
            value = value[1:value.index(value[0], 1)]
        elif "#" in value:
            value = value.split("#", 1)[0].strip()
        if line[:1] in (" ", "\t") and section is not None:
            cfg[section][key.strip()] = value
        elif value:
            cfg[key.strip()] = value
            section = None
        else:
            section = key.strip()
            cfg[section] = {}
    return cfg


def _load_config() -> tuple[str, dict[str, str]]:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        text = f.read()
    try:
        import yaml
        cfg = yaml.safe_load(text)
    except ImportError:
        cfg = _parse_simple_yaml(text)
    root = cfg["data_root"]
    paths = {}
    for key, value in (cfg.get("paths") or {}).items():
        value = str(value).replace("${goc}", root).replace("${du_an}", PROJECTS_ROOT)
        paths[key] = os.path.normpath(value)
    return os.path.normpath(root), paths


DATA_ROOT, _PATHS = _load_config()


def lay(key: str, bat_buoc: bool = False) -> str:
    """Lấy đường dẫn theo key trong Config_Paths.yaml.
    bat_buoc=True: báo lỗi nếu file/thư mục không tồn tại trên đĩa."""
    if key not in _PATHS:
        raise KeyError(
            f"Không có đường dẫn '{key}' trong {CONFIG_FILE}. "
            f"Các key có sẵn: {sorted(_PATHS)}"
        )
    path = _PATHS[key]
    if bat_buoc and not os.path.exists(path):
        raise FileNotFoundError(f"Đường dẫn '{key}' không tồn tại: {path}")
    return path


def thu_muc_ket_qua(ten_du_an: str) -> str:
    """Thư mục output của 1 project trong 04.Output (tự tạo nếu chưa có)."""
    path = os.path.join(_PATHS["ket_qua"], ten_du_an)
    os.makedirs(path, exist_ok=True)
    return path


def tat_ca() -> dict[str, str]:
    return dict(_PATHS)


def __getattr__(name: str) -> str:
    # Cho phép viết Get_Paths.ban_le thay cho Get_Paths.lay("ban_le")
    if name in _PATHS:
        return _PATHS[name]
    raise AttributeError(f"module 'Get_Paths' không có '{name}' (xem {CONFIG_FILE})")


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    print(f"Gốc dữ liệu: {DATA_ROOT}\n")
    for k, v in _PATHS.items():
        print(f"  [{'OK ' if os.path.exists(v) else '---'}] {k:<22} {v}")

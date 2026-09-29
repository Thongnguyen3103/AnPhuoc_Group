# -*- coding: utf-8 -*-
"""Đường dẫn dùng chung cho toàn bộ 01.Python_Projects.

Mọi đường dẫn khai báo DUY NHẤT trong dung_chung/cau_hinh.yaml.

Cách dùng trong project:

    from dung_chung import duong_dan

    duong_dan.ban_le                        # -> D:\\...\\03.Data_Parquest\\01.System_sales
    duong_dan.lay("region")                 # như trên, dạng hàm
    duong_dan.lay("region", bat_buoc=True)  # báo lỗi nếu file/thư mục không tồn tại
    duong_dan.thu_muc_ket_qua("BaoCao_LCHH")  # -> ...\\04_KetQua\\BaoCao_LCHH (tự tạo)

Script đặt ở bất kỳ đâu trong 01.Python_Projects cần thêm 1 dòng trước khi import
để Python tìm thấy dung_chung/ (xem HUONG_DAN.md ở thư mục gốc):

    import sys, pathlib; sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "dung_chung").is_dir())))
"""
from __future__ import annotations

import os

THU_MUC_DUNG_CHUNG = os.path.dirname(os.path.abspath(__file__))
THU_MUC_DU_AN = os.path.dirname(THU_MUC_DUNG_CHUNG)          # 01.Python_Projects
FILE_CAU_HINH = os.path.join(THU_MUC_DUNG_CHUNG, "cau_hinh.yaml")


def _doc_yaml_don_gian(text: str) -> dict:
    """Đọc cau_hinh.yaml khi môi trường không có PyYAML (vd env inventory_env).
    Chỉ hỗ trợ đúng dạng của file: `key: "gia tri"` và 1 cấp lồng (duong_dan:)."""
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


def _doc_cau_hinh() -> tuple[str, dict[str, str]]:
    with open(FILE_CAU_HINH, "r", encoding="utf-8") as f:
        text = f.read()
    try:
        import yaml
        cfg = yaml.safe_load(text)
    except ImportError:
        cfg = _doc_yaml_don_gian(text)
    goc = cfg["goc_du_lieu"]
    ds = {}
    for key, value in (cfg.get("duong_dan") or {}).items():
        value = str(value).replace("${goc}", goc).replace("${du_an}", THU_MUC_DU_AN)
        ds[key] = os.path.normpath(value)
    return os.path.normpath(goc), ds


GOC_DU_LIEU, _DUONG_DAN = _doc_cau_hinh()


def lay(key: str, bat_buoc: bool = False) -> str:
    """Lấy đường dẫn theo key trong cau_hinh.yaml.
    bat_buoc=True: báo lỗi nếu file/thư mục không tồn tại trên đĩa."""
    if key not in _DUONG_DAN:
        raise KeyError(
            f"Không có đường dẫn '{key}' trong {FILE_CAU_HINH}. "
            f"Các key có sẵn: {sorted(_DUONG_DAN)}"
        )
    path = _DUONG_DAN[key]
    if bat_buoc and not os.path.exists(path):
        raise FileNotFoundError(f"Đường dẫn '{key}' không tồn tại: {path}")
    return path


def thu_muc_ket_qua(ten_du_an: str) -> str:
    """Thư mục output của 1 project trong 04_KetQua (tự tạo nếu chưa có)."""
    path = os.path.join(_DUONG_DAN["ket_qua"], ten_du_an)
    os.makedirs(path, exist_ok=True)
    return path


def tat_ca() -> dict[str, str]:
    return dict(_DUONG_DAN)


def __getattr__(name: str) -> str:
    # Cho phép viết duong_dan.ban_le thay cho duong_dan.lay("ban_le")
    if name in _DUONG_DAN:
        return _DUONG_DAN[name]
    raise AttributeError(f"module 'duong_dan' không có '{name}' (xem {FILE_CAU_HINH})")


if __name__ == "__main__":
    # Chạy trực tiếp để kiểm tra nhanh toàn bộ đường dẫn
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    print(f"Gốc dữ liệu: {GOC_DU_LIEU}\n")
    for k, v in _DUONG_DAN.items():
        print(f"  [{'OK ' if os.path.exists(v) else '---'}] {k:<22} {v}")

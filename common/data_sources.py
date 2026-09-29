# -*- coding: utf-8 -*-
"""
Nguon du lieu dung chung cho toan bo 01.Python_Projects.

Moi project chi can:

    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "common"))
    # hoac dung ham find_common() ben duoi de tu do tim thu muc common/
    from data_sources import DataSources

    ds = DataSources.load()
    ds.lenh_hhlc        # -> duong dan D:/.../07.Lenh_HHLC
    ds.get("region")    # -> duong dan A_Region.parquet
    ds.require("region")  # -> nhu tren nhung raise loi neu file/thu muc khong ton tai

Chi mot noi duy nhat can sua khi doi vi tri kho du lieu goc:
`common/data_sources.yaml`.
"""
from __future__ import annotations

import os
import yaml

_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_YAML = os.path.join(_HERE, "data_sources.yaml")


class DataSources:
    """Truy cap duong dan du lieu goc (dung chung nhieu project).

    Thuoc tinh duoc sinh tu key trong `data_sources.yaml` (vd: `ds.lenh_hhlc`).
    """

    def __init__(self, root: str, paths: dict):
        self.root = root
        self._paths = paths
        for key, value in paths.items():
            setattr(self, key, value)

    @classmethod
    def load(cls, yaml_path: str | None = None) -> "DataSources":
        yaml_path = yaml_path or _DEFAULT_YAML
        with open(yaml_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)

        root = cfg["root"]
        paths = {k: v.replace("${root}", root) for k, v in cfg["paths"].items()}
        return cls(root=root, paths=paths)

    def get(self, key: str) -> str:
        if key not in self._paths:
            raise KeyError(
                f"Khong co nguon du lieu '{key}' trong data_sources.yaml. "
                f"Cac key co san: {sorted(self._paths)}"
            )
        return self._paths[key]

    def require(self, key: str) -> str:
        """Nhu get(), nhung kiem tra file/thu muc phai ton tai tren dia."""
        path = self.get(key)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Nguon du lieu '{key}' khong ton tai: {path}")
        return path

    def as_dict(self) -> dict:
        return dict(self._paths)

    def __repr__(self) -> str:
        return f"DataSources(root={self.root!r}, keys={sorted(self._paths)})"


def find_common_dir(start: str) -> str:
    """Tu 1 thu muc project con, tu leo len de tim thu muc `common/` dung chung.

    Dung khi project nam sau nhieu cap thu muc va khong muon hardcode so luong '..'.
    """
    cur = os.path.abspath(start)
    while True:
        candidate = os.path.join(cur, "common", "data_sources.yaml")
        if os.path.isfile(candidate):
            return os.path.join(cur, "common")
        parent = os.path.dirname(cur)
        if parent == cur:
            raise FileNotFoundError(
                f"Khong tim thay thu muc 'common/data_sources.yaml' tu {start} tro len."
            )
        cur = parent

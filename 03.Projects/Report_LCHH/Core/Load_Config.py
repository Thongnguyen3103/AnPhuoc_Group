# -*- coding: utf-8 -*-
"""Cau hinh project Report_LCHH (OOP).

`AppConfig` gop 2 nguon:
  1. Duong dan du lieu GOC dung chung toan workspace -> 00.Shared/Config_LCHH.yaml
  2. Cau hinh RIENG cua bao cao LCHH (ky bao cao, nguong SLA, alias...) -> Config_LCHH.yaml
"""
from __future__ import annotations

import datetime
import os
import sys

import yaml

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SRC_DIR)
DEFAULT_PROJECT_YAML = os.path.join(PROJECT_DIR, "Config_LCHH.yaml")

# 00.Shared nam o cap 01.Python_Projects (03.Projects/Report_LCHH/Core -> len 3 cap)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(PROJECT_DIR)), "00.Shared"))
import Get_Paths  # noqa: E402


class AppConfig:
    """Cau hinh tong hop cho Build_Data_LCHH.py / Build_Data_Performance.py."""

    def __init__(self, project_yaml: str = DEFAULT_PROJECT_YAML):
        with open(project_yaml, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        self._raw = raw

        self.paths = {
            "lenh": Get_Paths.lenh_hhlc,
            "history": Get_Paths.lich_su_lc,
            "trakho": Get_Paths.tra_kho,
            "region": Get_Paths.region,
            "sales": Get_Paths.ban_le,
            "inventory": Get_Paths.ton_kho_size,
            "output": raw.get("output_dir") or Get_Paths.thu_muc_ket_qua("Report_LCHH"),
        }

        self.periods_default = [str(p) for p in (raw.get("periods") or [])]
        self.sales_months_ahead = int(raw.get("sales_months_ahead", 3))
        self.sales_noi_dung = set(raw.get("sales_noi_dung") or ["Bán"])
        self.han_thuc_hien_ngay = int(raw.get("han_thuc_hien_ngay", 15))
        self.store_alias = raw.get("store_alias") or {}

    @property
    def output_dir(self) -> str:
        os.makedirs(self.paths["output"], exist_ok=True)
        return self.paths["output"]

    def resolve_periods(self, argv: list[str] | None = None) -> list[tuple[int, int]]:
        """Chon ky bao cao theo thu tu uu tien:
           1) tham so dong lenh:  python Build_Data_LCHH.py 2026-09
           2) tu nhap khi chay (Enter de dung config)
           3) danh sach 'periods' trong Config_LCHH.yaml
        Chap nhan 'YYYY-MM' hoac chi so thang (nam lay tu config / nam hien tai).
        Nhieu thang cach nhau bang dau cach.
        """
        cfg_periods = self.periods_default
        default_year = (int(cfg_periods[0].split("-")[0]) if cfg_periods
                        else datetime.date.today().year)

        argv = sys.argv[1:] if argv is None else argv
        raw = [a for a in argv if not a.startswith("-")]
        if not raw:
            try:
                ans = input(
                    "Nhap thang chay (vd 2026-09 hoac 9; nhieu thang cach nhau dau cach)\n"
                    f"  [Enter = dung config: {', '.join(cfg_periods) or 'trong'}]: ").strip()
            except EOFError:
                ans = ""
            raw = ans.split() if ans else cfg_periods

        if not raw:
            raise SystemExit("Chua chon ky bao cao.")

        out = []
        for tok in raw:
            tok = tok.strip()
            if "-" in tok:
                y, m = tok.split("-")
                out.append((int(y), int(m)))
            else:
                out.append((default_year, int(tok)))
        return out

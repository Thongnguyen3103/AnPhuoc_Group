# -*- coding: utf-8 -*-
"""PerformanceStateStore — Lưu "Hiệu suất kỳ" từng lần chạy (Data/lich_su_hieu_suat_ky.json)
để Lần 3 tính Xu hướng = Hiệu suất kỳ L3 ÷ Hiệu suất kỳ L2 (Mục 12.1)."""
import json
import os

from Config import Config_Parameters as cfg


class PerformanceStateStore:
    """Đọc / ghi file trạng thái JSON. Khoá: 'Combined_PK|Store_name|LanX'."""

    def __init__(self, path):
        self.path = path

    def load(self):
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def save(self, state):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    @staticmethod
    def update_with_hieu_suat_ky(state, df_store):
        for _, r in df_store.iterrows():
            key = f"{r['Combined_PK']}|{r['Store_name']}|{r['Lan_dieu_chuyen']}"
            state[key] = {"hieu_suat_ky": r["Hieu_suat_ky"], "khi_luu": f"{cfg.CURRENT_YEAR}-{cfg.CURRENT_MONTH:02d}"}
        return state

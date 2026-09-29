@echo off
REM Mo giao dien bao cao dieu chuyen hang hoa (ket qua -> 04_KetQua\BaoCao_DieuChuyen)
cd /d "%~dp0"
start "" "%USERPROFILE%\anaconda3\pythonw.exe" bao_cao_dieu_chuyen.py

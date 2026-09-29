@echo off
REM Mo giao dien bao cao Best Seller / Slow Seller -> 04_KetQua\BaoCao_TopSeller
cd /d "%~dp0"
start "" "%USERPROFILE%\anaconda3\pythonw.exe" bao_cao_ban_chay_ban_cham.py

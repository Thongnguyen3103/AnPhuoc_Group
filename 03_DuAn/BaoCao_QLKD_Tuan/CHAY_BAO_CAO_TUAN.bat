@echo off
REM Xuat database bao cao tuan QLKD -> 04_KetQua\BaoCao_QLKD_Tuan
REM Can chay 02_XuLyDuLieu\CHAY_DOANH_THU.bat truoc de cap nhat Report_AP.duckdb
REM Co the truyen thang: CHAY_BAO_CAO_TUAN.bat 2026-09-14 2026-09-20
chcp 65001 > nul
cd /d "%~dp0"
"%USERPROFILE%\anaconda3\python.exe" xuat_du_lieu_tuan.py %*
pause

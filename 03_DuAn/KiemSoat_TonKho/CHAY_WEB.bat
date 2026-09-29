@echo off
REM Mo web duyet lenh dieu chuyen (Flask, chia se mang noi bo). Dung env inventory_env.
REM Database: 04_KetQua\KiemSoat_TonKho\Reallocation_Database.xlsx
chcp 65001 > nul
cd /d "%~dp0app"
"%USERPROFILE%\anaconda3\envs\inventory_env\python.exe" web_duyet_dieu_chuyen.py
pause

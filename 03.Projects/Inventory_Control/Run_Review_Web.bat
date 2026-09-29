@echo off
REM Mo web duyet lenh dieu chuyen (Flask, chia se mang noi bo). Dung env inventory_env.
REM Database: 04.Output\Inventory_Control\Reallocation_Database.xlsx
chcp 65001 > nul
cd /d "%~dp0App"
"%USERPROFILE%\anaconda3\envs\inventory_env\python.exe" Run_Review_Web.py
pause

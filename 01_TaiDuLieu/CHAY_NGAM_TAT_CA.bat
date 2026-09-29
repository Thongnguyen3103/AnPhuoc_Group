@echo off
REM Chay khong giao dien cac muc dang tich trong config\settings.json (dung de dat lich)
chcp 65001 >nul
cd /d "%~dp0"
"%USERPROFILE%\anaconda3\python.exe" src\runner.py %*

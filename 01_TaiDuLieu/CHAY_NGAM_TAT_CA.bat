@echo off
REM Chay khong giao dien cac muc dang tich trong cau_hinh\thiet_lap.json (dung de dat lich)
chcp 65001 >nul
cd /d "%~dp0"
"%USERPROFILE%\anaconda3\python.exe" chay_ngam.py %*

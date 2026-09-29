@echo off
REM Mo giao dien chon muc va chay tool
cd /d "%~dp0"
start "" "%USERPROFILE%\anaconda3\pythonw.exe" src\app.py

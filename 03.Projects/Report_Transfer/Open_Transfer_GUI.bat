@echo off
REM Mo giao dien bao cao dieu chuyen hang hoa (ket qua -> 04.Output\Report_Transfer)
cd /d "%~dp0"
start "" "%USERPROFILE%\anaconda3\pythonw.exe" Open_Transfer_GUI.py

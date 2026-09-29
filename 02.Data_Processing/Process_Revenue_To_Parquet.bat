@echo off
REM Cap nhat doanh thu -> 03.Data_Parquest\10.Revenue (Revenue / Target / Bill_sales .parquet)
chcp 65001 >nul
cd /d "%~dp0"
"%USERPROFILE%\anaconda3\python.exe" Process_Revenue_To_Parquet.py
pause

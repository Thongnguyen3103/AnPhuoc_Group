@echo off
REM Xuat database bao cao tuan QLKD -> 04.Output\Report_QLKD_Weekly
REM Can chay 02.Data_Processing\Process_Revenue_To_Parquet.py truoc de cap nhat 03.Data_Parquest\10.Revenue
REM Co the truyen thang: Export_Weekly_QLKD.bat 2026-09-14 2026-09-20
chcp 65001 > nul
cd /d "%~dp0"
"%USERPROFILE%\anaconda3\python.exe" Export_Weekly_QLKD.py %*
pause

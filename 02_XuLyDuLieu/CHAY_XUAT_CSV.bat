@echo off
REM Xuat Parquet -> CSV (05.Data_Csv) cho Power BI
chcp 65001 >nul
cd /d "%~dp0"
"%USERPROFILE%\anaconda3\python.exe" xuat_csv_data_ap.py

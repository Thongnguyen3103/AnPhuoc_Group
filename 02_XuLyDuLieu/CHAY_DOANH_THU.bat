@echo off
REM Cap nhat DuckDB doanh thu (revenue, target, bill_sales) -> Report_AP.duckdb
chcp 65001 >nul
cd /d "%~dp0"
"%USERPROFILE%\anaconda3\python.exe" doanh_thu.py
pause

@echo off
REM Mo giao dien bao cao Best Seller / Slow Seller -> 04.Output\Report_TopSeller
cd /d "%~dp0"
start "" "%USERPROFILE%\anaconda3\pythonw.exe" Build_Best_Slow_Seller.py

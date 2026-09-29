@echo off
REM ================================================================
REM  BAO CAO BEST SELLER / SLOW SELLER  -> 04.Output\Report_TopSeller
REM  Chay duoc tren may khac: tu tim Python (Anaconda/Miniconda/PATH).
REM  Yeu cau: thu muc 01.Python_Projects giu nguyen cau truc
REM           (can 00.Shared) va kho du lieu dung duong dan trong
REM           00.Shared\Config_Paths.yaml (data_root).
REM ================================================================
chcp 65001 >nul
cd /d "%~dp0"

set "PY="
for %%P in (
    "%USERPROFILE%\anaconda3\python.exe"
    "%USERPROFILE%\miniconda3\python.exe"
    "%LOCALAPPDATA%\anaconda3\python.exe"
    "%ProgramData%\anaconda3\python.exe"
    "%ProgramData%\miniconda3\python.exe"
) do if not defined PY if exist %%P set "PY=%%~P"

if not defined PY (
    for /f "delims=" %%P in ('where python 2^>nul') do if not defined PY set "PY=%%P"
)

if not defined PY (
    echo [LOI] Khong tim thay Python tren may nay.
    echo       Cai Anaconda: https://www.anaconda.com/download  roi chay lai file nay.
    pause
    exit /b 1
)
echo Python: %PY%

"%PY%" -c "import pandas, numpy, pyarrow, xlsxwriter, tkinter" 2>nul
if errorlevel 1 (
    echo [LOI] Thieu thu vien. Chay lenh sau roi mo lai file nay:
    echo       "%PY%" -m pip install pandas numpy pyarrow xlsxwriter
    pause
    exit /b 1
)

"%PY%" Build_Best_Slow_Seller.py %*
if errorlevel 1 pause

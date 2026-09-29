@echo off
REM Tao KQ_LCHH.parquet + KQ_LCHH_HieuSuat.parquet (hoi thang chay; Enter = dung Config_LCHH.yaml)
REM Co the truyen thang: Build_Data_LCHH.bat 2026-09
chcp 65001 > nul
cd /d "%~dp0"
"%USERPROFILE%\anaconda3\python.exe" Build_Data_LCHH.py %*
"%USERPROFILE%\anaconda3\python.exe" Build_Data_Performance.py %*
pause

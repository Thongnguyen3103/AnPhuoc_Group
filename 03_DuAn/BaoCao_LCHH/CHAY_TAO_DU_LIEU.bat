@echo off
REM Tao KQ_LCHH.parquet + KQ_LCHH_HieuSuat.parquet (hoi thang chay; Enter = dung cau_hinh.yaml)
REM Co the truyen thang: CHAY_TAO_DU_LIEU.bat 2026-09
chcp 65001 > nul
cd /d "%~dp0"
"%USERPROFILE%\anaconda3\python.exe" tao_du_lieu_lchh.py %*
"%USERPROFILE%\anaconda3\python.exe" tao_du_lieu_hieu_suat.py %*
pause

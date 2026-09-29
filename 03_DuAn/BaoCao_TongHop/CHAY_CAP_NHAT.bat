@echo off
REM Build bao cao tong hop -> 04_KetQua\BaoCao_TongHop\BaoCao_TongHop.html
REM Ep dung lai cache tu dau: CHAY_CAP_NHAT.bat --force-cache
chcp 65001 > nul
cd /d "%~dp0"
"%USERPROFILE%\anaconda3\python.exe" xu_ly\cap_nhat_bao_cao.py %*
pause

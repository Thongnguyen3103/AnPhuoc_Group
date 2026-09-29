@echo off
chcp 65001 > nul
echo ================================================================
echo   LCHH - DONG BO VA TAO MOI BAO CAO EXCEL PHAN TICH
echo ================================================================
echo.
echo Dang doc du lieu tu 04_KetQua\BaoCao_LCHH\KQ_LCHH.parquet...
echo Dang phan tich va tao Dashboard Excel...
echo.

"%USERPROFILE%\anaconda3\python.exe" "%~dp0bao_cao\xuat_excel_lchh.py"
"%USERPROFILE%\anaconda3\python.exe" "%~dp0bao_cao\xuat_excel_hieu_suat.py"

echo.
echo ================================================================
echo   HOAN TAT! KET QUA: 04_KetQua\BaoCao_LCHH\bao_cao_excel
echo ================================================================
pause

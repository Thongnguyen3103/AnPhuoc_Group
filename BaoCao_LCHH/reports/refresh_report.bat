@echo off
chcp 65001 > nul
echo ================================================================
echo   LCHH - DONG BO VA TAO MOI BAO CAO EXCEL PHAN TICH
echo ================================================================
echo.
echo Dang doc du lieu tu output/KQ_LCHH.parquet...
echo Dang phan tich va tao Dashboard Excel...
echo.

"C:\Users\THONG SL\anaconda3\python.exe" "%~dp0excel_lchh.py"
"C:\Users\THONG SL\anaconda3\python.exe" "%~dp0excel_hieusuat.py"

echo.
echo ================================================================
echo   HOAN TAT! MO THU MUC REPORTS DE XEM KET QUA.
echo ================================================================
pause

@echo off
chcp 65001 > nul
echo ================================================================
echo   LCHH - DONG BO VA TAO MOI BAO CAO EXCEL PHAN TICH
echo ================================================================
echo.
echo Dang doc du lieu tu 04.Output\Report_LCHH\KQ_LCHH.parquet...
echo Dang phan tich va tao Dashboard Excel...
echo.

"%USERPROFILE%\anaconda3\python.exe" "%~dp0Excel\Export_Excel_LCHH.py"
"%USERPROFILE%\anaconda3\python.exe" "%~dp0Excel\Export_Excel_Performance.py"

echo.
echo ================================================================
echo   HOAN TAT! KET QUA: 04.Output\Report_LCHH\Excel_Reports
echo ================================================================
pause

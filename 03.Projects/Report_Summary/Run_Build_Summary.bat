@echo off
REM Build bao cao tong hop -> 04.Output\Report_Summary\BaoCao_TongHop.html
REM Ep dung lai cache tu dau: Run_Build_Summary.bat --force-cache
chcp 65001 > nul
cd /d "%~dp0"
"%USERPROFILE%\anaconda3\python.exe" Core\Run_Build_Summary.py %*
pause

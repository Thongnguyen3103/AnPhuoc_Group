@echo off
REM Tao lai Data\ViTri_DiaLy_CuaHang.csv (toa do cua hang) tu A_Region
chcp 65001 > nul
cd /d "%~dp0"
"%USERPROFILE%\anaconda3\python.exe" Generate_Store_Coordinates.py
pause

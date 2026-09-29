@echo off
REM Menu chon nguon du lieu can xu ly: 01.Source -> 03.Data_Parquest / 02.Master
chcp 65001 >nul
cd /d "%~dp0"
"%USERPROFILE%\anaconda3\python.exe" chay_tat_ca.py

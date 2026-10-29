@echo off
setlocal
cd /d "%~dp0"
title QX Podborshchik - Modern
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0portable\start_qx.ps1"
if errorlevel 1 (
 echo.
 echo QX could not start. Read the error above and portable\README_PORTABLE_RU.txt
 pause
 exit /b 1
)
exit /b 0

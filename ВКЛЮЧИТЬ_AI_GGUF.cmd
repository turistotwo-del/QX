@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0portable\enable_gguf.ps1"
if errorlevel 1 (
 echo.
 echo Could not enable local AI. The standard QX parser is still available.
)
echo.
pause

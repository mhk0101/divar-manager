@echo off
setlocal EnableExtensions
cd /d "%~dp0" || exit /b 1

if not exist ".venv\Scripts\python.exe" (
    echo Virtual environment was not found. Running one-click setup...
    call "%~dp0setup_and_run.bat"
    exit /b %ERRORLEVEL%
)

".venv\Scripts\python.exe" "ui\main.py"

echo.
echo ---------------------------------------
echo Application closed.
pause

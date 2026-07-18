@echo off
cd /d "%~dp0"

call .venv\Scripts\activate.bat

.venv\Scripts\python.exe ui\main.py

echo.
echo ---------------------------------------
echo برنامه بسته شد.
pause
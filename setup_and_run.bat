@echo off
setlocal EnableExtensions
cd /d "%~dp0" || exit /b 1

title Divar and Sheypoor Manager - Setup and Run

echo ============================================================
echo  Divar and Sheypoor Manager - One Click Setup and Run
echo ============================================================
echo.

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)

if not defined PY (
    echo [ERROR] Python was not found in PATH.
    echo Please install Python 3.10 or 3.11 and enable "Add Python to PATH".
    echo Download: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/6] Checking Python...
%PY% --version
if errorlevel 1 (
    echo [ERROR] Python is not runnable.
    pause
    exit /b 1
)

echo.
echo [2/6] Creating virtual environment if needed...
if not exist ".venv\Scripts\python.exe" (
    %PY% -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

echo.
echo [3/6] Upgrading pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 (
    echo [WARNING] Pip upgrade failed. Continuing...
)

echo.
echo [4/6] Installing project dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.txt -r requirements_gui.txt
if errorlevel 1 (
    echo [ERROR] Dependency installation failed.
    echo Check your internet connection and run this file again.
    pause
    exit /b 1
)

echo.
echo [5/6] Installing Playwright Chromium browser...
".venv\Scripts\python.exe" -m playwright install chromium
if errorlevel 1 (
    echo [ERROR] Playwright Chromium installation failed.
    echo Check your internet connection and run this file again.
    pause
    exit /b 1
)

echo.
echo [6/6] Checking bundled data files...
if not exist "data\cities.json" echo [WARNING] data\cities.json was not found.
if not exist "data\categories.json" echo [WARNING] data\categories.json was not found.
if not exist "data\sheypoor_cities.json" echo [WARNING] data\sheypoor_cities.json was not found.
if not exist "data\sheypoor_categories.json" echo [WARNING] data\sheypoor_categories.json was not found.

echo.
echo ============================================================
echo  Setup is complete. Starting application...
echo ============================================================
echo.
".venv\Scripts\python.exe" "ui\main.py"

echo.
echo ---------------------------------------
echo Application closed.
pause

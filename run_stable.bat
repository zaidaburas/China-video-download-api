@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

title Video Download API Server - Windows Production

echo ==========================================
echo   Video Download API - Windows Server
echo ==========================================
echo [*] Start time: %date% %time%
echo ==========================================
echo.

REM Check Python
echo [*] Checking Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Please install Python 3.8+
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo [OK] Python version: %PYTHON_VERSION%

REM Check dependencies
echo [*] Checking dependencies...
python -c "import fastapi, uvicorn, yt_dlp" >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARN] Dependencies missing, installing...
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo [ERROR] Installation failed
        pause
        exit /b 1
    )
    echo [OK] Dependencies installed
) else (
    echo [OK] Dependencies check passed
)

REM Check FFmpeg (optional)
ffmpeg -version >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARN] FFmpeg not installed
) else (
    echo [OK] FFmpeg installed
)

REM Check core files
echo [*] Checking core files...
if not exist "start_production.py" (
    echo [ERROR] Missing file: start_production.py
    pause
    exit /b 1
)

if not exist "api\main.py" (
    echo [ERROR] Missing file: api\main.py
    pause
    exit /b 1
)

echo [OK] Core files check passed

REM Create log directory
if not exist "logs" mkdir logs

echo.
echo ==========================================
echo [*] Starting server...
echo [*] Port: 8001
echo [*] Access: http://localhost:8001
echo [*] API Docs: http://localhost:8001/docs
echo [*] Press Ctrl+C to stop
echo ==========================================
echo.

:RESTART_LOOP
python start_production.py
set EXIT_CODE=%errorlevel%

if %EXIT_CODE% neq 0 (
    echo.
    echo [WARN] Service exited with code: %EXIT_CODE%
    echo.
    set /p RESTART="Restart? (y/N): "
    if /i "!RESTART!"=="y" (
        echo [*] Restarting...
        echo.
        goto RESTART_LOOP
    )
) else (
    echo [OK] Service stopped normally
)

echo.
pause

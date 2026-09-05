@echo off
setlocal EnableDelayedExpansion
title Vivy AI — Windows Node
color 0B

echo.
echo  =====================================================
echo     Vivy AI - Windows Node
echo     One AI. Every Device.
echo  =====================================================
echo.

REM ── Locate Python ─────────────────────────────────────────────────────────
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERROR] Python not found in PATH.
    echo  Please install Python 3.10 or newer from https://python.org
    echo  and ensure "Add Python to PATH" is checked during installation.
    pause
    exit /b 1
)

REM ── Check Python version ───────────────────────────────────────────────────
python -c "import sys; exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if %errorlevel% neq 0 (
    echo  [WARNING] Python 3.10+ is recommended. Some features may not work.
)

REM ── Install minimal node dependencies ─────────────────────────────────────
echo  Checking Vivy Node dependencies...
python -c "import websockets" >nul 2>&1
if %errorlevel% neq 0 (
    echo  Installing minimal dependencies (this may take a minute)...
    pip install -r "%~dp0vivy_windows_node\requirements_node.txt" --quiet
    if %errorlevel% neq 0 (
        echo  [ERROR] Dependency installation failed. Check your internet connection.
        pause
        exit /b 1
    )
    echo  Dependencies installed.
) else (
    echo  Dependencies OK.
)

echo.
echo  Starting Vivy Node Agent...
echo  Status dashboard will be available at: http://127.0.0.1:8801
echo.
echo  Press Ctrl+C to disconnect.
echo.

REM ── Launch the node agent ──────────────────────────────────────────────────
cd /d "%~dp0"
python -m vivy_windows_node.node_agent

if %errorlevel% neq 0 (
    echo.
    echo  [ERROR] Node agent exited with an error.
)

pause

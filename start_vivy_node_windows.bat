@echo off
setlocal EnableExtensions

title Vivy Node - Windows

cd /d D:\Vivy

echo ==============================================
echo          VIVY NODE - WINDOWS CLIENT
echo ==============================================
echo.

if not exist ".\venv\Scripts\python.exe" (
    echo [ERROR] Vivy virtual environment not found.
    echo Expected:
    echo D:\Vivy\venv\Scripts\python.exe
    echo.
    pause
    exit /b 1
)

if not exist ".\hub\node_prototype\node_client.py" (
    echo [ERROR] Existing node_client.py was not found.
    echo Expected:
    echo D:\Vivy\hub\node_prototype\node_client.py
    echo.
    pause
    exit /b 1
)

set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

echo [INFO] Starting existing Vivy Node client...
echo [INFO] Hub discovery/authentication/capabilities are handled
echo       by the existing node_prototype implementation.
echo.

".\venv\Scripts\python.exe" ".\hub\node_prototype\node_client.py"

set EXITCODE=%ERRORLEVEL%

echo.
echo ==============================================
echo Vivy Node exited with code %EXITCODE%
echo ==============================================

if not "%EXITCODE%"=="0" (
    echo.
    echo [ERROR] The Vivy Node stopped unexpectedly.
)

pause
exit /b %EXITCODE%

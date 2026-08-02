@echo off
title Vivy Avatar WebSocket Bridge
echo =====================================================
echo Starting Vivy Avatar WebSocket Bridge Server...
echo Address: ws://127.0.0.1:8765
echo =====================================================
cd /d "%~dp0"
venv_avatar\Scripts\python.exe avatar_bridge.py
pause

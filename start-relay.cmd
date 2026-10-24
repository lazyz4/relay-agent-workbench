@echo off
title Relay Workbench - Keep this window open
cd /d "%~dp0"
echo Starting Relay on http://127.0.0.1:8875/
echo Keep this window open. Press Ctrl+C to stop.
py -3 --version >nul 2>nul
if not errorlevel 1 goto launcher
python --version >nul 2>nul
if not errorlevel 1 goto python
echo Python 3.10 or newer is required. Install Python and enable its launcher or PATH.
goto finish
:launcher
py -3 -X utf8 launch.py
goto finish
:python
python -X utf8 launch.py
:finish
pause

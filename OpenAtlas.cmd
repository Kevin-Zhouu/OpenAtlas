@echo off
cd /d "%~dp0"
python scripts\start.py
if errorlevel 1 pause

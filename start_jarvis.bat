@echo off
REM Double-click to start Jarvis. It updates itself, checks his key, and opens Chrome.
cd /d "%~dp0"
".venv\Scripts\python.exe" scripts\launch.py
pause

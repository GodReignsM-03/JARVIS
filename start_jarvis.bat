@echo off
REM Double-click to start Jarvis on this computer, then open http://localhost:4700 in Chrome.
cd /d "%~dp0"
echo Starting Jarvis... leave this window open. Close it to stop him.
start "" "http://localhost:4700"
".venv\Scripts\python.exe" -m uvicorn server.app:app --host 127.0.0.1 --port 4700
pause

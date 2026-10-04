@echo off
REM ============================================================
REM Start the NiceGUI agent web terminal (bilingual filename;
REM content kept ASCII except the venv path on purpose)
REM   http://127.0.0.1:8502
REM Prereq: ai-agent-server 8091 (with MySQL for history/KB),
REM         main service 8080 for login
REM ============================================================

set "PYTHON=%~dp0..\..\env\venv-虚拟环境\Scripts\python.exe"

start "agent-web-8502" cmd /k "cd /d %~dp0 && "%PYTHON%" main.py"

echo.
echo NiceGUI agent terminal started in a new window (8502).
echo Open http://127.0.0.1:8502 in your browser.
pause

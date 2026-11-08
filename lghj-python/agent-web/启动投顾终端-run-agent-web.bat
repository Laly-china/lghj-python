@echo off
REM ============================================================
REM Start the NiceGUI agent web terminal (bilingual filename;
REM content kept pure ASCII on purpose: cmd parses non-ASCII .bat
REM unreliable, and the venv folder is located by wildcard)
REM   http://127.0.0.1:8502
REM Prereq: ai-agent-server 8091 (with MySQL for history/KB),
REM         main service 8080 for login
REM ============================================================

set "PYTHON="
for /d %%D in ("%~dp0..\..\env\venv-*") do set "PYTHON=%%~fD\Scripts\python.exe"
if not exist "%PYTHON%" echo [ERROR] venv python.exe not found - run the env setup script first, then retry.
if not exist "%PYTHON%" pause
if not exist "%PYTHON%" exit /b 1

start "agent-web-8502" cmd /k "cd /d %~dp0 && "%PYTHON%" main.py"

echo.
echo NiceGUI agent terminal started in a new window (8502).
echo Open http://127.0.0.1:8502 in your browser.
pause

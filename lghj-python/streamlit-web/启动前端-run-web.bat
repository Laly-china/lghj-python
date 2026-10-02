@echo off
REM ============================================================
REM Start the Streamlit web frontend (bilingual filename; content
REM kept ASCII except the venv path on purpose)
REM   http://127.0.0.1:8501
REM Prereq: MySQL/Redis via env/ setup script, and the 3 backend
REM services (8080/8091/8001) started by run-all-services.bat
REM Paths are RELATIVE to this file's folder.
REM ============================================================

set "PYTHON=%~dp0..\..\env\venv-ÐéÄâ»·¾³\Scripts\python.exe"

start "streamlit-web-8501" cmd /k "cd /d %~dp0 && "%PYTHON%" -m streamlit run streamlit_app.py --server.port 8501 --server.headless true"

echo.
echo Streamlit frontend started in a new window (8501).
echo Open http://127.0.0.1:8501 in your browser.
pause

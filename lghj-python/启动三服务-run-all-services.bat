@echo off
REM ============================================================
REM Start all 3 services (bilingual filename; content kept ASCII
REM except the venv path on purpose)
REM   lghj-server        http://127.0.0.1:8080
REM   ai-agent-server    http://127.0.0.1:8091
REM   prediction-server  http://127.0.0.1:8001
REM Prereq: MySQL(3306)/Redis(6379,db8) started via env/setup script
REM Stop:  run stop-all-services.bat or close the cmd windows
REM All paths RELATIVE to this folder (project movable anywhere;
REM env/ sits next to lghj-python/)
REM ============================================================

set "ROOT=%~dp0"
set "PYTHON=%~dp0..\env\venv-虚拟环境\Scripts\python.exe"

REM internal API token, must match between 8080 and 8091
REM (empty on both sides = no check, also a legal contract)
set LGHJ_INTERNAL_API_TOKEN=phase7-internal-token

start "lghj-server-8080" cmd /k "cd /d %ROOT%lghj-server && "%PYTHON%" -m uvicorn app.main:app --host 127.0.0.1 --port 8080"
start "ai-agent-server-8091" cmd /k "cd /d %ROOT%ai-agent-server && "%PYTHON%" -m uvicorn app.main:app --host 127.0.0.1 --port 8091"
start "prediction-server-8001" cmd /k "cd /d %ROOT%prediction-server && "%PYTHON%" -m uvicorn main:app --host 127.0.0.1 --port 8001"

echo.
echo 3 services started in new windows (8080 / 8091 / 8001).
echo Ready check : 8080 GET /api/user/stock/search?keyword=600519
echo              8091 GET /act/health      8001 GET /health
echo Contract test: cd lghj-python, then run
echo   "..\env\venv-虚拟环境\Scripts\python.exe" -m pytest tests -v
pause

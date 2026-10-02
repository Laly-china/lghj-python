@echo off
REM ============================================================
REM Stop all 3 services by port (bilingual filename, ASCII
REM content on purpose: cmd parses GBK comments unreliably)
REM   lghj-server 8080 / ai-agent-server 8091 / prediction 8001
REM ============================================================

for %%P in (8080 8091 8001) do (
    echo stopping port %%P ...
    for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":%%P " ^| findstr "LISTENING"') do (
        taskkill /f /pid %%a >nul 2>&1
    )
)

echo done. services on 8080/8091/8001 stopped.
pause

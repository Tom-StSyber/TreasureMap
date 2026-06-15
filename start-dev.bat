@echo off
REM TreasureMap — quick dev launcher (hot-reload backend + frontend)
REM Run from anywhere: double-click or call from PowerShell

setlocal
set ROOT=D:\Home-Lab\TreasureMap

echo === TreasureMap Dev Launcher ===
echo.

REM ── Backend (must run from backend/ so bare imports resolve) ──
echo Starting backend  (http://localhost:8000) ...
start "TreasureMap API" cmd /k "cd /d %ROOT%\backend && ..\.venv\Scripts\uvicorn main:app --reload"

REM ── Frontend ──────────────────────────────────────────────────
echo Starting frontend (http://localhost:5173) ...
start "TreasureMap UI"  cmd /k "cd /d %ROOT%\frontend && npm run dev"

echo.
echo Two windows opened.  Close them to stop the servers.
echo  API:    http://localhost:8000/docs
echo  UI:     http://localhost:5173
echo.
pause

@echo off
REM TreasureMap — Windows setup script
REM Install location: D:\Home-Lab\TreasureMap
REM Requires: Docker Desktop, Python 3.12+, Node 20+

setlocal
set ROOT=D:\Home-Lab\TreasureMap
if not exist "%ROOT%" (
    echo ERROR: Project directory not found: %ROOT%
    echo Copy the TreasureMap folder to D:\Home-Lab\TreasureMap and re-run.
    exit /b 1
)
cd /d "%ROOT%"

echo ======================================
echo  TreasureMap Setup
echo ======================================

REM 1. Start Elasticsearch + Kibana + API + Frontend
echo [1/4] Starting Docker services...
docker compose up -d --build
if errorlevel 1 (
    echo ERROR: docker compose failed. Is Docker Desktop running?
    exit /b 1
)

REM 2. Wait for Elasticsearch
echo [2/4] Waiting for Elasticsearch to be healthy...
:wait_es
curl -sf http://localhost:9200/_cluster/health >nul 2>&1
if errorlevel 1 (
    timeout /t 5 /nobreak >nul
    goto wait_es
)
echo   Elasticsearch is up.

REM 3. Load sample data
echo [3/4] Loading sample network data...
cd backend
pip install -r requirements.txt --quiet
python ingest.py
if errorlevel 1 (
    echo ERROR: ingest.py failed. Check Elasticsearch connection.
    exit /b 1
)
cd ..

echo [4/4] All done!
echo.
echo  UI:            http://localhost:3000
echo  API docs:      http://localhost:8000/docs
echo  Kibana:        http://localhost:5601
echo.
echo  For local dev (hot-reload):
echo    cd D:\Home-Lab\TreasureMap\frontend ^&^& npm install ^&^& npm run dev
echo    cd D:\Home-Lab\TreasureMap\backend  ^&^& uvicorn main:app --reload
echo.

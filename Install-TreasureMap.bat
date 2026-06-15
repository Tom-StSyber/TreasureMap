@echo off
:: TreasureMap — Windows installer entry point
:: Double-click this file to install TreasureMap on Windows 11.
:: Prefers Docker Desktop if available; falls back to native install.

title TreasureMap Installer
setlocal

echo.
echo  ======================================================
echo   TreasureMap — Windows Installer
echo  ======================================================
echo.

:: Detect Docker
docker info >nul 2>&1
if %errorlevel% equ 0 (
    echo  [FOUND] Docker Desktop is running. Using Docker Compose install.
    echo.
    PowerShell -NoProfile -ExecutionPolicy Bypass -Command ^
        "cd '%~dp0'; docker compose up -d --build; Write-Host 'Waiting for Elasticsearch...' -ForegroundColor Cyan; $t=0; while($t -lt 120){Start-Sleep 5;$t+=5;try{$h=(Invoke-WebRequest 'http://localhost:9200/_cluster/health' -UseBasicParsing -TimeoutSec 3).Content|ConvertFrom-Json; if($h.status -ne 'red'){break}}catch{};Write-Host '.' -NoNewline}; Write-Host ''; $lab=('%~dp0data\synthetic-lab' -replace '\\','/'); Invoke-WebRequest -Uri ('http://localhost:8000/ingest/stream?folder_path='+$lab+'&wipe=true') -UseBasicParsing -TimeoutSec 120 | Out-Null; Start-Process 'http://localhost:3000'; Write-Host 'Done! Open http://localhost:3000' -ForegroundColor Green"
) else (
    echo  [INFO] Docker Desktop not found. Using native install (no Docker required).
    echo.
    PowerShell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\native-install.ps1"
)

echo.
pause

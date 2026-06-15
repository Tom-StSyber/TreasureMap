@echo off
:: TreasureMap — stop all services
title TreasureMap — Stopping

docker info >nul 2>&1
if %errorlevel% equ 0 (
    echo  Stopping Docker Compose services...
    docker compose down
) else (
    PowerShell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\stop-native.ps1"
)
pause

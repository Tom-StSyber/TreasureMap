@echo off
:: TreasureMap — quick-start (run after installation)
title TreasureMap Launcher

docker info >nul 2>&1
if %errorlevel% equ 0 (
    echo  Starting via Docker Compose...
    docker compose up -d
    timeout /t 5 /nobreak >nul
    start "" "http://localhost:3000"
) else (
    PowerShell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\start-native.ps1"
)

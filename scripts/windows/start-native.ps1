#Requires -Version 5.1
<#
.SYNOPSIS
    Start all TreasureMap services (native Windows, no Docker).
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ROOT     = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$ES_VER   = "8.13.0"
$ES_DIR   = "$ROOT\elasticsearch\server\elasticsearch-$ES_VER"
$VENV     = "$ROOT\backend\.venv"

function Info { param($m) Write-Host "  [>>]  $m" -ForegroundColor Cyan  }
function OK   { param($m) Write-Host "  [OK]  $m" -ForegroundColor Green }
function Err  { param($m) Write-Host "  [!!]  $m" -ForegroundColor Red; exit 1 }

Write-Host "`n  Starting TreasureMap…`n" -ForegroundColor Magenta

# ── Prerequisite checks ───────────────────────────────────────────────────────
if (-not (Test-Path "$ES_DIR\bin\elasticsearch.bat")) {
    Err "Elasticsearch not found. Run Install-TreasureMap.bat first."
}
if (-not (Test-Path "$VENV\Scripts\uvicorn.exe")) {
    Err "Python venv not found. Run Install-TreasureMap.bat first."
}
if (-not (Test-Path "$ROOT\frontend\node_modules")) {
    Err "node_modules not found. Run Install-TreasureMap.bat first."
}

# ── Elasticsearch ─────────────────────────────────────────────────────────────
$esUp = $false
try { Invoke-WebRequest "http://localhost:9200" -UseBasicParsing -TimeoutSec 2 -EA Stop | Out-Null; $esUp = $true } catch {}

if (-not $esUp) {
    Info "Starting Elasticsearch…"
    $env:ES_JAVA_OPTS = "-Xms1g -Xmx1g"
    Start-Process -FilePath "$ES_DIR\bin\elasticsearch.bat" `
                  -WorkingDirectory $ES_DIR `
                  -WindowStyle Hidden
    $t = 0
    while ($t -lt 90) {
        Start-Sleep 5; $t += 5
        try {
            $h = Invoke-WebRequest "http://localhost:9200/_cluster/health" -UseBasicParsing -TimeoutSec 3 -EA Stop
            if (($h.Content | ConvertFrom-Json).status -ne "red") { break }
        } catch {}
        Write-Host "." -NoNewline
    }
    Write-Host ""
    OK "Elasticsearch running  →  http://localhost:9200"
} else {
    OK "Elasticsearch already running"
}

# ── Backend ───────────────────────────────────────────────────────────────────
Info "Starting API (uvicorn --reload)…"
Start-Process -FilePath "cmd.exe" `
    -ArgumentList "/k title TreasureMap API && cd /d `"$ROOT\backend`" && `"..\..\.venv\Scripts\uvicorn`" main:app --reload --host 0.0.0.0 --port 8000" `
    -WorkingDirectory "$ROOT\backend"
Start-Sleep 3
OK "Backend running  →  http://localhost:8000"

# ── Frontend ──────────────────────────────────────────────────────────────────
Info "Starting frontend (Vite dev server)…"
Start-Process -FilePath "cmd.exe" `
    -ArgumentList "/k title TreasureMap UI && cd /d `"$ROOT\frontend`" && npm run dev" `
    -WorkingDirectory "$ROOT\frontend"
Start-Sleep 4
OK "Frontend running  →  http://localhost:5173"

# ── Open browser ──────────────────────────────────────────────────────────────
Start-Process "http://localhost:5173"

Write-Host @"

  TreasureMap is running!
    UI       →  http://localhost:5173
    API docs →  http://localhost:8000/docs
    ES       →  http://localhost:9200

  Close the two cmd windows (TreasureMap API / TreasureMap UI) to stop.
  Or run Stop-TreasureMap.bat.

"@ -ForegroundColor Green

#Requires -Version 5.1
<#
.SYNOPSIS
    TreasureMap — native Windows installer (no Docker required).

.DESCRIPTION
    Installs Python 3.12, Node.js 20 LTS, and Elasticsearch 8.13.0 locally
    within the TreasureMap directory, then wires up and ingests the synthetic
    lab dataset so the application is ready to run.

.NOTES
    Run via the root Install-TreasureMap.bat — do not run this script directly
    unless you know what you are doing.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ── Resolve project root ──────────────────────────────────────────────────────
$ROOT = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $ROOT

# ── Colour helpers ────────────────────────────────────────────────────────────
function Info  { param($m) Write-Host "  [INFO]  $m" -ForegroundColor Cyan    }
function OK    { param($m) Write-Host "  [ OK ]  $m" -ForegroundColor Green   }
function Warn  { param($m) Write-Host "  [WARN]  $m" -ForegroundColor Yellow  }
function Err   { param($m) Write-Host "  [FAIL]  $m" -ForegroundColor Red; exit 1 }
function Head  { param($m) Write-Host "`n══ $m ══" -ForegroundColor Magenta   }

# ── Banner ────────────────────────────────────────────────────────────────────
Write-Host @"

  ████████╗██████╗ ███████╗ █████╗ ███████╗██╗   ██╗██████╗ ███████╗███╗   ███╗ █████╗ ██████╗
     ██╔══╝██╔══██╗██╔════╝██╔══██╗██╔════╝██║   ██║██╔══██╗██╔════╝████╗ ████║██╔══██╗██╔══██╗
     ██║   ██████╔╝█████╗  ███████║███████╗██║   ██║██████╔╝█████╗  ██╔████╔██║███████║██████╔╝
     ██║   ██╔══██╗██╔══╝  ██╔══██║╚════██║██║   ██║██╔══██╗██╔══╝  ██║╚██╔╝██║██╔══██║██╔═══╝
     ██║   ██║  ██║███████╗██║  ██║███████║╚██████╔╝██║  ██║███████╗██║ ╚═╝ ██║██║  ██║██║
     ╚═╝   ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚══════╝╚═╝     ╚═╝╚═╝  ╚═╝╚═╝

  Network Topology Visualiser — Windows Native Installer
  Project root: $ROOT

"@ -ForegroundColor Cyan

# ── Constants ─────────────────────────────────────────────────────────────────
$ES_VERSION   = "8.13.0"
$ES_URL       = "https://artifacts.elastic.co/downloads/elasticsearch/elasticsearch-$ES_VERSION-windows-x86_64.zip"
$ES_DIR       = "$ROOT\elasticsearch\server\elasticsearch-$ES_VERSION"
$ES_DATA      = "$ROOT\elasticsearch\data"
$ES_LOGS      = "$ROOT\elasticsearch\logs"
$ES_ZIP       = "$ROOT\elasticsearch\elasticsearch-$ES_VERSION-windows-x86_64.zip"
$BACKEND_ENV  = "$ROOT\backend\.env"
$VENV         = "$ROOT\backend\.venv"
$PYTHON_MIN   = [Version]"3.11"

# ─────────────────────────────────────────────────────────────────────────────
Head "Step 1 — Python"
# ─────────────────────────────────────────────────────────────────────────────

function Find-Python {
    foreach ($cmd in @("python", "python3", "py")) {
        $p = Get-Command $cmd -ErrorAction SilentlyContinue
        if ($p) {
            $ver = & $cmd --version 2>&1 | Select-String -Pattern '(\d+\.\d+)' | ForEach-Object { $_.Matches[0].Groups[1].Value }
            if ($ver -and [Version]$ver -ge $PYTHON_MIN) { return $cmd }
        }
    }
    return $null
}

$python = Find-Python
if (-not $python) {
    Warn "Python $PYTHON_MIN+ not found. Attempting install via winget…"
    $wg = Get-Command winget -ErrorAction SilentlyContinue
    if ($wg) {
        winget install --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements -e
        # Refresh PATH
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
                    [System.Environment]::GetEnvironmentVariable("Path","User")
        $python = Find-Python
        if (-not $python) { Err "Python install succeeded but binary not found. Open a new terminal and re-run." }
    } else {
        Err "winget not available. Install Python 3.12+ from https://www.python.org/downloads/ then re-run."
    }
}
OK "Python: $(& $python --version 2>&1)"

# ─────────────────────────────────────────────────────────────────────────────
Head "Step 2 — Node.js"
# ─────────────────────────────────────────────────────────────────────────────

$node = Get-Command node -ErrorAction SilentlyContinue
if (-not $node) {
    Warn "Node.js not found. Attempting install via winget…"
    $wg = Get-Command winget -ErrorAction SilentlyContinue
    if ($wg) {
        winget install --id OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements -e
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
                    [System.Environment]::GetEnvironmentVariable("Path","User")
        $node = Get-Command node -ErrorAction SilentlyContinue
        if (-not $node) { Err "Node install succeeded but binary not found. Open a new terminal and re-run." }
    } else {
        Err "winget not available. Install Node.js 20 LTS from https://nodejs.org/ then re-run."
    }
}
OK "Node.js: $(node --version)  |  npm: $(npm --version)"

# ─────────────────────────────────────────────────────────────────────────────
Head "Step 3 — Elasticsearch $ES_VERSION"
# ─────────────────────────────────────────────────────────────────────────────

if (-not (Test-Path "$ES_DIR\bin\elasticsearch.bat")) {
    New-Item -ItemType Directory -Force -Path "$ROOT\elasticsearch\server" | Out-Null
    New-Item -ItemType Directory -Force -Path $ES_DATA | Out-Null
    New-Item -ItemType Directory -Force -Path $ES_LOGS | Out-Null

    if (-not (Test-Path $ES_ZIP)) {
        Info "Downloading Elasticsearch $ES_VERSION (~330 MB)…"
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $wc = New-Object System.Net.WebClient
        $wc.DownloadFile($ES_URL, $ES_ZIP)
    }
    Info "Extracting…"
    Expand-Archive -Path $ES_ZIP -DestinationPath "$ROOT\elasticsearch\server" -Force
    Remove-Item $ES_ZIP -Force
    OK "Elasticsearch extracted to $ES_DIR"
} else {
    OK "Elasticsearch already present at $ES_DIR"
}

# Write elasticsearch.yml with real data/log paths
$ymSrc  = "$ROOT\elasticsearch\config\elasticsearch.yml"
$ymDest = "$ES_DIR\config\elasticsearch.yml"
$esDataEsc = $ES_DATA -replace '\\', '\\'
$esLogsEsc = $ES_LOGS -replace '\\', '\\'
(Get-Content $ymSrc) `
    -replace '__ES_DATA_PATH__', ($ES_DATA -replace '\\', '/') `
    -replace '__ES_LOGS_PATH__', ($ES_LOGS -replace '\\', '/') |
    Set-Content $ymDest
OK "elasticsearch.yml written"

# ─────────────────────────────────────────────────────────────────────────────
Head "Step 4 — Backend Python environment"
# ─────────────────────────────────────────────────────────────────────────────

if (-not (Test-Path "$VENV\Scripts\python.exe")) {
    Info "Creating virtual environment…"
    & $python -m venv $VENV
}
OK "Virtual environment: $VENV"

Info "Installing Python dependencies…"
& "$VENV\Scripts\pip" install --quiet --upgrade pip
& "$VENV\Scripts\pip" install --quiet -r "$ROOT\backend\requirements.txt"
OK "Python dependencies installed"

# ── Create .env if missing ────────────────────────────────────────────────────
if (-not (Test-Path $BACKEND_ENV)) {
    Copy-Item "$ROOT\.env.example" $BACKEND_ENV
    OK ".env created from template"
} else {
    OK ".env already exists — not overwritten"
}

# ─────────────────────────────────────────────────────────────────────────────
Head "Step 5 — Frontend npm packages"
# ─────────────────────────────────────────────────────────────────────────────

Push-Location "$ROOT\frontend"
npm install --silent
Pop-Location
OK "npm packages installed"

# ─────────────────────────────────────────────────────────────────────────────
Head "Step 6 — Start Elasticsearch"
# ─────────────────────────────────────────────────────────────────────────────

$esRunning = $false
try {
    $r = Invoke-WebRequest -Uri "http://localhost:9200" -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
    $esRunning = $true
    OK "Elasticsearch already running"
} catch {}

if (-not $esRunning) {
    $env:ES_JAVA_OPTS = "-Xms1g -Xmx1g"
    Info "Starting Elasticsearch (this can take 30-60 s on first boot)…"
    $esProc = Start-Process -FilePath "$ES_DIR\bin\elasticsearch.bat" `
                            -WorkingDirectory $ES_DIR `
                            -WindowStyle Hidden `
                            -PassThru

    $timeout = 120
    $elapsed = 0
    while ($elapsed -lt $timeout) {
        Start-Sleep 5; $elapsed += 5
        try {
            $h = Invoke-WebRequest -Uri "http://localhost:9200/_cluster/health" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
            $status = ($h.Content | ConvertFrom-Json).status
            if ($status -ne "red") { break }
        } catch {}
        Write-Host "." -NoNewline
    }
    Write-Host ""
    if ($elapsed -ge $timeout) { Err "Elasticsearch did not start within $timeout s. Check logs at $ES_LOGS" }
    OK "Elasticsearch healthy"
}

# ─────────────────────────────────────────────────────────────────────────────
Head "Step 7 — Ingest synthetic lab data"
# ─────────────────────────────────────────────────────────────────────────────

Info "Starting API server briefly for ingest…"
$apiProc = Start-Process -FilePath "$VENV\Scripts\uvicorn.exe" `
                         -ArgumentList "main:app --host 127.0.0.1 --port 8000" `
                         -WorkingDirectory "$ROOT\backend" `
                         -WindowStyle Hidden `
                         -PassThru
Start-Sleep 6

Info "Triggering ingest of synthetic lab configs…"
$labDir = "$ROOT\data\synthetic-lab" -replace '\\', '/'
$ingestUrl = "http://localhost:8000/ingest/stream?folder_path=$labDir&wipe=true"
try {
    $result = Invoke-WebRequest -Uri $ingestUrl -UseBasicParsing -TimeoutSec 120 -ErrorAction Stop
    $done = $result.Content | Select-String -Pattern '"type": "done"'
    if ($done) {
        $summary = $result.Content | Select-String -Pattern '"summary":\{[^}]+\}' |
                   ForEach-Object { $_.Matches[0].Value }
        OK "Ingest complete — $summary"
    } else {
        Warn "Ingest returned unexpected output. Check API logs."
    }
} catch {
    Warn "Ingest request failed: $_. You can re-run ingest from the UI."
}

Stop-Process -Id $apiProc.Id -Force -ErrorAction SilentlyContinue

# ─────────────────────────────────────────────────────────────────────────────
Head "Installation complete!"
# ─────────────────────────────────────────────────────────────────────────────
Write-Host @"

  Everything is installed. To start TreasureMap:

    Double-click:  Start-TreasureMap.bat     (in the project root)
    — or manually —
    Backend:  cd backend && ..\.venv\Scripts\uvicorn main:app --reload
    Frontend: cd frontend && npm run dev

  URLs:
    UI       →  http://localhost:5173
    API docs →  http://localhost:8000/docs

"@ -ForegroundColor Green

$start = Read-Host "Start TreasureMap now? [Y/n]"
if ($start -ne 'n' -and $start -ne 'N') {
    & "$ROOT\scripts\windows\start-native.ps1"
}

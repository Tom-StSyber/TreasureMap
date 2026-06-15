# TreasureMap — Installation Guide

This guide covers every installation path in detail. If you just want to get running quickly, use the [Quick Start](#quick-start) in the README.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Path A — Docker Compose (recommended)](#2-path-a--docker-compose-recommended)
3. [Path B — Native Windows 11](#3-path-b--native-windows-11)
4. [Path C — Native Ubuntu 24.04](#4-path-c--native-ubuntu-2404)
5. [First Run — Ingesting Data](#5-first-run--ingesting-data)
6. [Verifying the Installation](#6-verifying-the-installation)
7. [Uninstalling](#7-uninstalling)

---

## 1. Prerequisites

### All paths

- 4 GB RAM minimum (8 GB recommended — Elasticsearch uses 1 GB heap by default)
- 3 GB free disk space
- Internet access during installation (for package downloads)

### Docker path (Path A)

- Docker Desktop 24+ (Windows) or Docker Engine 24+ + Docker Compose v2 (Ubuntu)
- **Windows**: Docker Desktop requires WSL 2. Enable it: `wsl --install` then reboot.
- **Ubuntu**: `curl -fsSL https://get.docker.com | bash`

### Native paths (B and C)

- **Windows 11**: `winget` (built-in on Windows 11 22H2+). The installer uses it to pull Python and Node.js. Check: `winget --version`
- **Ubuntu 24.04**: `sudo` access for `apt`. The script will prompt.

---

## 2. Path A — Docker Compose (recommended)

Docker Compose is the easiest path. It starts Elasticsearch, the FastAPI backend, the built React frontend, and Kibana as managed containers.

### Windows

```batch
REM 1. Ensure Docker Desktop is running (whale icon in system tray)
REM 2. Double-click:
Install-TreasureMap.bat
```

The script detects Docker and automatically runs `docker compose up -d --build`.

### Ubuntu

```bash
./Install-TreasureMap.sh
```

### What the Docker installer does

1. `docker compose up -d --build` — builds backend/frontend images and starts all four containers
2. Polls `http://localhost:9200/_cluster/health` until Elasticsearch is healthy (up to 2 minutes)
3. Calls `GET /ingest/stream?folder_path=./data/synthetic-lab&wipe=true` to populate the database
4. Opens `http://localhost:3000` in your browser

### Service URLs (Docker)

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| API | http://localhost:8000 |
| API docs (Swagger) | http://localhost:8000/docs |
| Kibana | http://localhost:5601 |
| Elasticsearch | http://localhost:9200 |

### Managing Docker services

```bash
docker compose up -d        # start (detached)
docker compose down         # stop and remove containers
docker compose logs -f api  # stream logs from the API container
docker compose restart api  # restart just the backend
```

---

## 3. Path B — Native Windows 11

Use this path when Docker Desktop is not installed or not wanted.

### What gets installed

| Component | Location |
|-----------|----------|
| Python 3.12 | System (via winget, per-user) |
| Node.js 20 LTS | System (via winget, per-user) |
| Elasticsearch 8.13.0 | `TreasureMap\elasticsearch\server\` |
| Python venv | `TreasureMap\backend\.venv\` |
| npm packages | `TreasureMap\frontend\node_modules\` |

### Step-by-step

**1. Open the project folder and double-click `Install-TreasureMap.bat`**

A terminal window opens. The script will:

- Check for Python 3.11+ (`py`, `python3`, `python` — tries all three)
- If not found: runs `winget install Python.Python.3.12` and refreshes PATH
- Check for Node.js 20+
- If not found: runs `winget install OpenJS.NodeJS.LTS`
- Download Elasticsearch 8.13.0 (~330 MB zip) to `elasticsearch\`
- Extract it to `elasticsearch\server\elasticsearch-8.13.0\`
- Copy `elasticsearch\config\elasticsearch.yml` (dev config with no auth)
- Create `backend\.venv\` and install Python packages
- Run `npm install` in `frontend\`
- Start Elasticsearch in the background
- Wait for Elasticsearch to become healthy
- Start the API briefly, trigger ingest, then stop it

**2. When prompted "Start TreasureMap now? [Y/n]" — press Enter**

This calls `scripts\windows\start-native.ps1`, which opens two `cmd` windows:
- `TreasureMap API` — uvicorn with `--reload`
- `TreasureMap UI` — Vite dev server

**3. Open http://localhost:5173**

### Running after initial install

```batch
:: Quick start (detects Docker vs native automatically)
Start-TreasureMap.bat

:: Or call the native script directly
PowerShell -ExecutionPolicy Bypass -File scripts\windows\start-native.ps1
```

### Stopping

```batch
Stop-TreasureMap.bat
```

Or simply close the two `TreasureMap API` and `TreasureMap UI` cmd windows, then stop Elasticsearch:

```powershell
# Stop Elasticsearch (if you need to free the 1 GB heap)
Stop-Process -Name java -Force
```

### PowerShell execution policy

If Windows blocks the `.ps1` scripts, run this once:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

---

## 4. Path C — Native Ubuntu 24.04

### What gets installed

| Component | Method |
|-----------|--------|
| Python 3.12 + venv | `apt` |
| Node.js 20 LTS | NodeSource repository |
| curl, wget, unzip, jq | `apt` |
| Elasticsearch 8.13.0 | tar.gz extracted to `elasticsearch/server/` |
| Python venv | `TreasureMap/backend/.venv/` |
| npm packages | `TreasureMap/frontend/node_modules/` |

### Step-by-step

```bash
# 1. Clone the repository
git clone https://github.com/Tom-StSyber/TreasureMap.git
cd TreasureMap

# 2. Make installer executable
chmod +x Install-TreasureMap.sh

# 3. Run
./Install-TreasureMap.sh
```

The script will ask for your sudo password when installing system packages.

> **Note**: Elasticsearch cannot run as the root user. Run the installer as your regular user account (with sudo available), not as root.

### What the script does

1. `apt-get update` and installs Python 3.12, Node.js 20, curl, wget, unzip, jq
2. Downloads Elasticsearch 8.13.0 tarball (~330 MB)
3. Extracts to `elasticsearch/server/elasticsearch-8.13.0/`
4. Writes `elasticsearch.yml` with absolute data/logs paths
5. Creates Python venv and installs pip packages
6. `npm install` in `frontend/`
7. Starts Elasticsearch via `nohup`; saves PID to `elasticsearch/es.pid`
8. Polls health endpoint until green/yellow
9. Starts the API briefly, ingests synthetic lab data, stops it
10. Offers to start all services

### Running after initial install

```bash
./Start-TreasureMap.sh
```

### Stopping

```bash
./Stop-TreasureMap.sh
```

### Running as a systemd service (optional)

If you want TreasureMap to start on boot:

```bash
# Create a simple service file
sudo tee /etc/systemd/system/treasuremap.service << SERVICE
[Unit]
Description=TreasureMap Network Topology Visualiser
After=network.target

[Service]
Type=forking
User=$USER
WorkingDirectory=$(pwd)
ExecStart=$(pwd)/Start-TreasureMap.sh
ExecStop=$(pwd)/Stop-TreasureMap.sh
Restart=on-failure

[Install]
WantedBy=multi-user.target
SERVICE

sudo systemctl daemon-reload
sudo systemctl enable treasuremap
sudo systemctl start treasuremap
```

---

## 5. First Run — Ingesting Data

The installer pre-loads the **33-device synthetic lab** automatically. To load your own device configs after installation:

### Via the UI

1. Open http://localhost:5173
2. Click **Ingest** in the navigation
3. Enter the absolute path to your config directory
4. Click **Run Ingest**

### Via the API

```bash
# Replace /path/to/your/configs with the real directory
curl "http://localhost:8000/ingest/stream?folder_path=/path/to/your/configs&wipe=true"
```

On Windows PowerShell:

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/ingest/stream?folder_path=C:/path/to/configs&wipe=true"
```

The `wipe=true` parameter drops all existing data first. Omit it to add to existing data.

---

## 6. Verifying the Installation

Check each component manually if something seems off:

```bash
# Elasticsearch
curl http://localhost:9200/_cluster/health

# API health
curl http://localhost:8000/health

# Device count
curl http://localhost:8000/devices | python3 -m json.tool | grep '"name"' | wc -l

# Connections
curl http://localhost:8000/topology | python3 -m json.tool | grep '"edges"'
```

Expected responses:
- Elasticsearch: `{"status":"green",...}`
- API health: `{"status":"ok","elasticsearch":"8.13.0"}`
- Devices after synthetic lab ingest: 33
- Connections: 39

---

## 7. Uninstalling

### Docker

```bash
docker compose down -v   # remove containers AND the esdata volume
docker rmi tm-api tm-frontend
```

### Native (Windows)

1. Delete the `TreasureMap` folder
2. Python and Node.js remain installed (they're system packages); remove via Apps & Features if desired

### Native (Ubuntu)

```bash
# Stop services first
./Stop-TreasureMap.sh

# Delete the project (includes ES binaries, venv, node_modules)
cd .. && rm -rf TreasureMap
```

Python 3.12 and Node.js remain system packages; remove with `sudo apt remove python3.12 nodejs` if desired.

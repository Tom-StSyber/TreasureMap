# TreasureMap — Installation Guide

**Target platform:** Ubuntu 24.04 LTS (amd64)
**Deployment model:** Docker Compose (all services containerized)
**Time to install:** ~10–15 minutes on a fresh VM with internet access

---

## Overview

TreasureMap runs as four Docker containers:

| Container | Purpose | Port |
|---|---|---|
| `tm-elasticsearch` | Graph database | 9200 |
| `tm-kibana` | Dev data browser | 5601 |
| `tm-api` | FastAPI backend | 8000 |
| `tm-frontend` | React UI (nginx) | 3000 |

The install script handles everything: Docker Engine, Node.js 20, Python
dependencies, container builds, and data seeding. You run it once. Then you
clone the VM for each analyst.

---

## Prerequisites

A clean Ubuntu 24.04 LTS VM with:

- At least **4 GB RAM** (Elasticsearch is the hungry one; 2 GB min, 4 GB recommended)
- At least **20 GB disk** (container images + ES data)
- A non-root user account with `sudo` rights
- Internet access (only needed during this install; cloned VMs run offline)

---

## Step 1 — Clone the repository

Open a terminal and run:

```bash
git clone https://github.com/YOUR_ORG/TreasureMap.git ~/TreasureMap
cd ~/TreasureMap
```

Replace `YOUR_ORG` with the actual GitHub organization or user name.

---

## Step 2 — Run the installer

```bash
chmod +x scripts/Install-TreasureMap.sh
./scripts/Install-TreasureMap.sh
```

The script will:

1. Install `curl`, `git`, `python3`, and other apt prerequisites
2. Add Docker's official apt repository and install Docker Engine + the Compose plugin
3. Add NodeSource's apt repository and install Node.js 20 LTS
4. Run `npm install` inside `frontend/` (exact pinned versions — no surprises)
5. Create a Python virtual environment under `backend/.venv` and install pip packages
6. Build and start all four Docker containers (`docker compose up -d --build`)
7. Wait for Elasticsearch to report a healthy status
8. Seed the database with sample network configs (`ingest.py`)

You will be prompted for your `sudo` password at the start. After that it runs
unattended.

**If the script adds you to the `docker` group for the first time**, it will
warn you. You can either log out and back in, or run `newgrp docker` in your
current shell. Re-running the script after that will work without `sudo docker`.

---

## Step 3 — Verify the installation

Once the script finishes, open a browser on the VM (or SSH tunnel to it) and
check each endpoint:

| What to check | URL | Expected result |
|---|---|---|
| UI loads | http://localhost:3000 | TreasureMap topology graph |
| API is alive | http://localhost:8000/docs | FastAPI Swagger UI |
| ES is healthy | http://localhost:9200/_cluster/health | `"status":"green"` or `"yellow"` |
| Kibana loads | http://localhost:5601 | Kibana welcome screen |

You can also verify from the terminal:

```bash
# All four containers should show "Up" or "healthy"
docker compose ps

# Elasticsearch cluster health
curl -s http://localhost:9200/_cluster/health | python3 -m json.tool

# Count ingested devices
curl -s http://localhost:8000/api/topology/summary
```

---

## Step 4 — Create the golden VM image

Once everything is verified:

1. **Stop the VM cleanly** — do not force-power-off while ES is writing.
   ```bash
   cd ~/TreasureMap
   docker compose down          # stop containers gracefully
   sudo shutdown -h now
   ```
2. **Take a snapshot or export the VM** using your hypervisor (VMware, VirtualBox,
   Proxmox, KVM/libvirt, etc.).
3. **Distribute the clone** to each analyst. When they boot it, all four
   containers start automatically (`restart: unless-stopped` is set in
   `docker-compose.yml`).

Analysts never need to run the install script. They just boot the VM.

---

## Day-to-day operations

### Start / stop

```bash
cd ~/TreasureMap

# Start everything
docker compose up -d

# Stop everything (data is preserved in the esdata Docker volume)
docker compose down

# Restart a single service
docker compose restart api
```

### View logs

```bash
# All services
docker compose logs -f

# One service
docker compose logs -f elasticsearch
docker compose logs -f api
```

### Update TreasureMap

```bash
cd ~/TreasureMap
git pull
docker compose up -d --build     # rebuilds api and frontend containers
```

---

## Development mode (hot-reload, outside Docker)

If you want to edit code and see changes instantly without rebuilding containers:

**Frontend** (runs on port 5173, proxies `/api` to the backend container on 8000):

```bash
cd ~/TreasureMap/frontend
npm run dev
```

Open http://localhost:5173 instead of :3000.

**Backend** (runs on port 8000 directly, replacing the `tm-api` container):

```bash
# Stop the Docker api container first so there's no port conflict
docker compose stop api

cd ~/TreasureMap/backend
source .venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

---

## Troubleshooting

### "docker: command not found" after running the script

The script added you to the `docker` group but your current session hasn't
picked it up yet. Run:

```bash
newgrp docker
```

Or log out and back in.

### Elasticsearch never becomes healthy

The most common cause is insufficient RAM. Check:

```bash
docker compose logs elasticsearch | tail -40
```

If you see `OutOfMemoryError` or the container keeps restarting, increase the
VM's RAM to at least 4 GB. You can also reduce the ES heap (edit
`docker-compose.yml`, change `ES_JAVA_OPTS=-Xms1g -Xmx1g` to `Xms512m -Xmx512m`
for a 2 GB VM).

### npm error about vite or missing package.json

You are running `npm` from the wrong directory. **All npm commands must be run
from `frontend/`**, not from the project root. There is no `package.json` at the
root level.

```bash
cd ~/TreasureMap/frontend
npm install    # correct
```

### "ERESOLVE could not resolve" npm errors

This happens if someone has manually run `npm i -D vite` or `npm init -y` in
the wrong directory. Clean up and start fresh:

```bash
cd ~/TreasureMap/frontend
rm -rf node_modules package-lock.json
npm install
```

Do **not** run `npm install --force` — it silently installs broken dependency
combinations.

### Frontend container builds but the UI shows a blank page

Check the browser console for import errors. The most likely cause is a stale
`node_modules` inside the frontend Docker build. Force a clean rebuild:

```bash
docker compose build --no-cache frontend
docker compose up -d frontend
```

### ingest.py fails during install

Not fatal. You can re-run it any time:

```bash
cd ~/TreasureMap
docker compose exec api python3 ingest.py
```

Or to add a specific config file:

```bash
docker compose exec -T api python3 ingest.py /path/to/config.txt
```

---

## Architecture notes for analysts

- All network data lives in the Elasticsearch `esdata` Docker volume. This
  persists across container restarts and VM reboots.
- To wipe all data and start fresh: `docker compose down -v` (the `-v` removes
  volumes).
- The UI and API use no authentication during testing. Active Directory
  integration is planned for a later phase.
- The backend API is documented at http://localhost:8000/docs — useful for
  scripting or curl-based data queries.

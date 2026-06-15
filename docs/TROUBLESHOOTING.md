# TreasureMap — Troubleshooting

---

## Quick Diagnostics

Run this to check all services at once:

```bash
# Linux
curl -s http://localhost:9200/_cluster/health | python3 -m json.tool
curl -s http://localhost:8000/health
curl -s http://localhost:5173 | head -5
```

```powershell
# Windows PowerShell
Invoke-RestMethod http://localhost:9200/_cluster/health
Invoke-RestMethod http://localhost:8000/health
```

---

## Elasticsearch Issues

### "Elasticsearch did not start within 120 s"

**Cause 1 — Not enough memory**

Elasticsearch defaults to a 1 GB heap. If the system has less than 2 GB free RAM, it will fail to start.

Fix:
```bash
# Linux — reduce heap before starting
export ES_JAVA_OPTS="-Xms512m -Xmx512m"
./elasticsearch/server/elasticsearch-8.13.0/bin/elasticsearch

# Windows PowerShell
$env:ES_JAVA_OPTS = "-Xms512m -Xmx512m"
& ".\elasticsearch\server\elasticsearch-8.13.0\bin\elasticsearch.bat"
```

**Cause 2 — Port 9200 already in use**

```bash
# Linux
sudo lsof -i :9200
sudo ss -tlnp | grep 9200

# Windows PowerShell
netstat -ano | findstr :9200
```

If another process is using port 9200, stop it or change the ES port in `elasticsearch/config/elasticsearch.yml` (and update `ELASTICSEARCH_URL` in `backend/.env`).

**Cause 3 — vm.max_map_count too low (Linux only)**

Elasticsearch requires a kernel parameter of at least 262144.

```bash
sudo sysctl -w vm.max_map_count=262144
# Make permanent:
echo 'vm.max_map_count=262144' | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

**Cause 4 — Elasticsearch running as root (Linux only)**

Elasticsearch refuses to run as root. Always run as a regular user.

```bash
whoami   # must NOT print "root"
```

### "Connection refused" on port 9200

The Elasticsearch process exited after starting. Check the log:

```bash
# Linux
tail -100 elasticsearch/logs/elasticsearch.log

# Windows — logs are in the ES install directory
type elasticsearch\server\elasticsearch-8.13.0\logs\treasuremap.log
```

Common log messages and fixes:

| Log message | Fix |
|-------------|-----|
| `max virtual memory areas vm.max_map_count [65530] is too low` | See vm.max_map_count above |
| `failed to obtain node locks` | Another ES instance is already running. Kill it: `pkill -f elasticsearch` |
| `Native controller process has stopped` | Low disk space. Free at least 1 GB. |
| `OutOfMemoryError` | Reduce heap: `ES_JAVA_OPTS="-Xms512m -Xmx512m"` |

---

## Python / Backend Issues

### "pydantic-core … no matching distribution found"

This means you're on Python 3.14+ and the pinned pydantic-core version has no pre-built wheel. The `requirements.txt` in this repo pins `pydantic==2.13.4` + `pydantic-core==2.46.4` which have cp314 wheels. If you see this error:

```bash
pip install pydantic==2.13.4 pydantic-core==2.46.4
```

If that still fails, your pip may be resolving an incompatible combination:

```bash
pip install "pydantic>=2.13" "pydantic-core>=2.46"
```

### "ModuleNotFoundError: No module named 'uvicorn'"

The virtual environment is not activated or was created with a different Python.

```bash
# Linux — recreate venv
rm -rf backend/.venv
python3.12 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt

# Windows
Remove-Item -Recurse -Force backend\.venv
python -m venv backend\.venv
backend\.venv\Scripts\pip install -r backend\requirements.txt
```

### "ImportError: cannot import name 'build_subnet_connections'"

Stale `.pyc` bytecode cache. Fix:

```bash
# Linux
touch backend/routers/ingest.py

# Windows PowerShell
(Get-Item backend\routers\ingest.py).LastWriteTime = Get-Date
```

Then restart the API.

### API returns 500 on ingest

1. Check the uvicorn terminal for a Python traceback.
2. Common causes:
   - Elasticsearch is down — verify with `curl http://localhost:9200`
   - A config file has a syntax error — check which file caused the error in the SSE stream output
   - `link_type` validation error — only `routed, trunk, access, uplink, crosslink, bgp` are valid

### "Not Found" on ingest endpoint

The ingest endpoint is `GET /ingest/stream`, not `POST /api/ingest/generate`. On PowerShell, use:

```powershell
Invoke-RestMethod -Method GET -Uri "http://localhost:8000/ingest/stream?folder_path=D:/path/to/configs&wipe=true"
```

PowerShell's `curl` is an alias for `Invoke-WebRequest`, not real curl — the flags are different.

---

## Frontend / Vite Issues

### Topology shows nodes but no icons

The SVG icons are served from `/icons/` by the Vite dev server. If they 404:

1. Confirm the files exist: `ls frontend/public/icons/`  
   Expected: `router.svg  switch.svg  firewall.svg  server.svg  host.svg`

2. Check browser DevTools → Network for 404s on `/icons/*.svg`

3. If you built the frontend (`npm run build`) instead of running dev, serve the `dist/` folder with a proper web server or use `npm run preview`.

### Cytoscape layout is scrambled with 30+ nodes

Dagre struggles with very dense graphs. In `frontend/src/components/TopologyGraph.jsx`, try increasing spacing:

```javascript
cy.layout({
  name: 'dagre',
  rankDir: 'TB',
  nodeSep: 60,    // increase if nodes overlap
  rankSep: 150,   // increase vertical spacing
  ranker: 'tight-tree',
}).run()
```

### "CORS error" in browser console

The backend is not running, or it's running on a different port than the Vite proxy expects.

1. Confirm the backend is running: `curl http://localhost:8000/health`
2. Check `frontend/vite.config.js` — the proxy target must match the backend port:
   ```javascript
   proxy: { '/api': { target: 'http://localhost:8000' } }
   ```

---

## Docker Issues

### "docker compose up" fails with "no such file or directory"

You ran `docker compose` from the wrong directory. Always run from the `TreasureMap/` root:

```bash
cd TreasureMap
docker compose up -d --build
```

### Elasticsearch container exits immediately

Check logs:

```bash
docker compose logs elasticsearch
```

Common cause: `vm.max_map_count` (see above). Fix on the Docker host:

```bash
sudo sysctl -w vm.max_map_count=262144
```

### "port is already allocated"

A previous container or native service is still using port 9200, 8000, or 3000.

```bash
# Find and stop conflicting containers
docker ps -a
docker stop <container_name>

# Or stop native services first
./Stop-TreasureMap.sh  # or Stop-TreasureMap.bat
```

---

## Ingest / Parser Issues

### Device parsed as "Cisco/IOS" when it should be "Cisco/NX-OS"

The NX-OS detector requires the string `nxos` (no dash) somewhere in the config AND at least one `feature` line. Check your config for:

```
boot nxos bootflash:///nxos64-cs.10.x.x.bin
feature ospf
```

Without these, the parser falls through to generic IOS detection.

### ACLs show 0 on NX-OS devices

NX-OS uses `ip access-list extended NAME` (with `extended` keyword). If your config has `ip access-list NAME` (without `extended`), fix it:

```bash
sed -i 's/^ip access-list \([A-Z][A-Z0-9_-]*\)$/ip access-list extended \1/' your-config.cfg
```

### Servers / workstations not appearing in topology

Stub configs need three things:
1. `! device-type: server` or `! device-type: host` comment
2. `hostname <name>` line
3. `interface <name>` block with at least one line

Minimal valid stub:
```
! device-type: server
! vendor: Microsoft
! os: Windows Server 2022
hostname my-server
interface Ethernet0
 ip address 10.0.1.50 255.255.255.0
```

### 0 connections after ingest

Check which detection passes ran:

1. **BGP peers**: Requires `router bgp <AS>` + `neighbor <IP> remote-as <AS>` lines
2. **Subnet detection**: Requires two devices with interfaces on the same `/29` or `/30` subnet
3. **Description matching**: Requires interface descriptions that contain another device's hostname as a substring

If none of these apply, devices appear as disconnected nodes. Add interface descriptions referencing peer hostnames to enable link detection.

---

## Windows-Specific Issues

### "The term '.\.venv\Scripts\python' is not recognized"

The `.venv` directory does not exist — the installer did not run or failed partway through. Re-run:

```batch
Install-TreasureMap.bat
```

### "Cannot bind parameter 'Headers'" with curl

PowerShell's `curl` is an alias for `Invoke-WebRequest`, not the Unix `curl` binary. Use `Invoke-RestMethod` instead:

```powershell
Invoke-RestMethod -Method GET -Uri "http://localhost:8000/health"
```

### winget fails to install Python or Node

1. Ensure winget is up to date: open Microsoft Store → search "App Installer" → Update
2. If behind a corporate proxy, winget may fail. Download installers manually:
   - Python 3.12: https://www.python.org/downloads/
   - Node.js 20 LTS: https://nodejs.org/en/download
3. After manual install, re-run `Install-TreasureMap.bat`

---

## Still Stuck?

1. Open an issue at https://github.com/Tom-StSyber/TreasureMap/issues
2. Include:
   - Your OS and version
   - Installation path used (Docker / Windows native / Ubuntu native)
   - The exact error message
   - Output of `curl http://localhost:9200/_cluster/health` and `curl http://localhost:8000/health`

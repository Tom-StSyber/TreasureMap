# TreasureMap 🗺️

**Network topology visualiser for Cisco IOS / IOS-XE / NX-OS environments.**

TreasureMap ingests running-config files from your network devices, parses them into a structured graph, stores the data in Elasticsearch, and renders an interactive topology diagram in the browser. It detects BGP peers, shared /30 subnets, interface-description cross-links, VLANs, ACLs, and HSRP/VPC relationships — building a complete picture of your network without any agents or SNMP.

---

![TreasureMap topology overview](https://github.com/user-attachments/assets/306f6ea8-0adb-481f-bc9b-d0fcc1aaf4be)
---

## Quick Start

### Windows 11

```
1. Clone or download this repository
2. Double-click  Install-TreasureMap.bat
3. Open          http://localhost:5173  (native)  or  http://localhost:3000  (Docker)
```

### Ubuntu 24.04

```bash
git clone https://github.com/Tom-StSyber/TreasureMap.git
cd TreasureMap
chmod +x Install-TreasureMap.sh
./Install-TreasureMap.sh
# Open http://localhost:5173
```

The installer automatically detects Docker Desktop / Docker Engine.  
If Docker is present it uses **Docker Compose** (recommended).  
If Docker is absent it performs a **native install** — no Docker needed.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  Browser (React + Cytoscape.js)                   localhost:5173    │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  Topology view  │  Device detail  │  Path-find  │  Ingest UI  │  │
│  └───────────────────────────────────────────────────────────────┘  │
└────────────────────────────┬────────────────────────────────────────┘
                             │ HTTP / SSE  (Vite proxy → :8000)
┌────────────────────────────▼────────────────────────────────────────┐
│  FastAPI + Uvicorn                                localhost:8000    │
│  ┌──────────────┐  ┌───────────────┐  ┌──────────────────────────┐ │
│  │ /topology    │  │ /ingest/stream│  │ /pathfind                │ │
│  │ /devices     │  │  (SSE)        │  │ (NetworkX BFS/Dijkstra)  │ │
│  └──────────────┘  └───────┬───────┘  └──────────────────────────┘ │
│                             │ parse                                  │
│  ┌──────────────────────────▼────────────────────────────────────┐  │
│  │  Parser  (parsers/ios_config.py)                              │  │
│  │  • Cisco IOS / IOS-XE / NX-OS running-config                 │  │
│  │  • Server / workstation stub configs                          │  │
│  │  • BGP peer detection                                         │  │
│  │  • Shared /30 subnet P2P link detection                       │  │
│  │  • Interface description hostname cross-linking               │  │
│  └───────────────────────────────────────────────────────────────┘  │
└────────────────────────────┬────────────────────────────────────────┘
                             │ Elasticsearch client
┌────────────────────────────▼────────────────────────────────────────┐
│  Elasticsearch 8.x                                localhost:9200    │
│  Indices: treasuremap_devices  _interfaces  _connections  _acls     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Features

- **Multi-vendor parsing** — Cisco IOS, IOS-XE, NX-OS; stub support for Windows/Linux servers
- **Automatic connection detection** — BGP peers, shared /30 subnets, description-based cross-links
- **ACL visualisation** — Extended ACL rules with source/dest/port/action breakdown
- **HSRP / VPC awareness** — Redundancy groups surfaced in the topology
- **Path-finding** — BFS shortest-path between any two devices
- **Synthetic lab** — 33-device corporate lab (8 Cisco + 7 Windows servers + 8 Linux servers + 10 workstations) included for instant testing
- **SVG device icons** — Cisco-style icons for router, switch, firewall, server, host
- **Live ingest stream** — Server-Sent Events feed for real-time parsing progress

---

## Project Structure

```
TreasureMap/
├── Install-TreasureMap.bat     # Windows double-click installer
├── Install-TreasureMap.sh      # Ubuntu double-click installer
├── Start-TreasureMap.bat/.sh   # Start all services
├── Stop-TreasureMap.bat/.sh    # Stop all services
├── docker-compose.yml          # Docker Compose (all services)
├── .env.example                # Environment variable template
├── backend/                    # FastAPI application
│   ├── main.py
│   ├── config.py
│   ├── es_client.py
│   ├── models.py
│   ├── parsers/
│   │   └── ios_config.py       # Cisco config parser
│   ├── routers/
│   │   ├── devices.py
│   │   ├── topology.py
│   │   ├── pathfind.py
│   │   └── ingest.py           # SSE ingest endpoint
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/                   # React + Vite + Cytoscape.js
│   ├── src/
│   │   ├── components/
│   │   │   └── TopologyGraph.jsx
│   │   └── App.jsx
│   ├── public/icons/           # Cisco SVG device icons
│   ├── package.json
│   └── Dockerfile
├── data/
│   └── synthetic-lab/          # 33 synthetic device configs
├── elasticsearch/
│   └── config/
│       └── elasticsearch.yml   # Dev config (no auth, single-node)
├── scripts/
│   ├── windows/
│   │   ├── native-install.ps1
│   │   ├── start-native.ps1
│   │   └── stop-native.ps1
│   └── ubuntu/
│       ├── native-install.sh
│       ├── start-native.sh
│       └── stop-native.sh
└── docs/
    ├── INSTALLATION.md
    ├── TROUBLESHOOTING.md
    ├── ARCHITECTURE.md
    └── DEVELOPMENT.md
```

---

## Requirements

| Component | Version | Notes |
|-----------|---------|-------|
| Python | 3.11 – 3.14 | 3.12 recommended |
| Node.js | 20 LTS+ | |
| Elasticsearch | 8.13.0 | Provided by installer or Docker |
| Docker Desktop | 24+ | Optional — native install works without it |
| Windows | 11 (22H2+) | winget required for auto-install of deps |
| Ubuntu | 24.04 LTS | Other Debian-based distros likely work |

---

## Manual Startup (after installation)

```bash
# Terminal 1 — Elasticsearch (native only, skip if using Docker)
export ES_JAVA_OPTS="-Xms1g -Xmx1g"
./elasticsearch/server/elasticsearch-8.13.0/bin/elasticsearch

# Terminal 2 — Backend
cd backend
../.venv/bin/uvicorn main:app --reload        # Linux/Mac
.\.venv\Scripts\uvicorn main:app --reload      # Windows

# Terminal 3 — Frontend
cd frontend
npm run dev
```

---

## Ingesting Your Own Configs

Place Cisco running-config files (`.cfg`, `.conf`, or `.txt`) in any directory, then call the ingest endpoint:

```bash
# Linux / Mac
curl "http://localhost:8000/ingest/stream?folder_path=/path/to/configs&wipe=true"

# Windows PowerShell
Invoke-RestMethod -Uri "http://localhost:8000/ingest/stream?folder_path=C:/path/to/configs&wipe=true"
```

The `wipe=true` parameter clears existing data before re-ingesting. Omit it to merge.

For non-Cisco devices (servers, workstations), create a stub `.cfg` with the following header and a `hostname` + `interface` line to satisfy the parser:

```
! device-type: server
! vendor: Microsoft
! os: Windows Server 2022
hostname my-server
interface Ethernet0
 ip address 10.0.1.50 255.255.255.0
```

---

## Documentation

- [Installation Guide](docs/INSTALLATION.md) — step-by-step for both paths
- [Troubleshooting](docs/TROUBLESHOOTING.md) — common errors and fixes
- [Architecture](docs/ARCHITECTURE.md) — design decisions and data model
- [Development Guide](docs/DEVELOPMENT.md) — adding pars
# TreasureMap 🗺️

**Multi-vendor network topology visualiser — from configs to interactive graph in minutes.**

TreasureMap ingests running-configuration files from network devices, parses them into a structured graph, stores the data in Elasticsearch, and renders an interactive topology diagram in the browser. A one-click **Discover** pass infers the links between devices from shared IP subnets, interface descriptions, and CDP/LLDP neighbor data, while parsing also picks up VLANs and ACLs — building a complete picture of your network with no agents, no SNMP, and no proprietary collectors.

![TreasureMap topology overview](https://github.com/user-attachments/assets/ab5bb19a-e9a4-482d-9397-a57f5d9b3a15)
![TreasureMap path-query overview](https://github.com/user-attachments/assets/8e40c496-9e0f-41de-9c30-0f901c2ed368)
---

## Supported Vendors

| Vendor | Platform | Parser | Status |
|--------|----------|--------|--------|
| Cisco | IOS / IOS-XE / NX-OS | `parsers/cisco.py` | ✅ Wired in |
| Juniper | JunOS (hierarchical and set-format) | `parsers/juniper.py` | ✅ Wired in |
| Huawei | VRP | `parsers/huawei.py` | ✅ Wired in |
| Dell | OS10 / Enterprise SONiC (PowerSwitch) | `parsers/dell.py` | 🚧 Parser written, not yet connected to the ingest pipeline (its output schema doesn't match `Device`/`Interface`/`Acl` yet — needs adapting, plus ACL-rule extraction) |
| HPE | Aruba OS-CX | `parsers/hpe.py` | 🚧 Same as Dell — file exists, not wired in |

Auto-detect is the default (`_detect_vendor` in `routers/ingest.py`). It also fingerprints Extreme EXOS and Nokia SR-OS, but there's no parser for either yet — those currently fall through to the Cisco parser, which will not produce useful output. Only pick Cisco/Juniper/Huawei as an explicit vendor hint for now.

---

## Quick Start (Docker — recommended)

**Prerequisites:** [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows/Mac) or Docker Engine + Compose plugin (Linux), and `git`.

```bash
git clone https://github.com/Tom-StSyber/TreasureMap.git
cd TreasureMap
docker compose up -d --build
```

Wait ~30 seconds for Elasticsearch to initialise, then open:

- **TreasureMap UI** → http://localhost:3000
- **FastAPI docs** → http://localhost:8000/docs
- **Kibana** (optional) → http://localhost:5601

> **Note:** The first `docker compose up --build` compiles the React frontend inside the `frontend` container and may take 2–3 minutes. Subsequent starts are fast.

---

## From Zero to Useful — Step by Step

### 1  Clone and start

```bash
git clone https://github.com/Tom-StSyber/TreasureMap.git
cd TreasureMap
docker compose up -d --build
```

### 2  Verify services are healthy

```bash
docker compose ps
# All four services (elasticsearch, api, frontend, kibana) should show "Up" or "healthy"
```

### 3  Ingest sample configs (included in the repo)

Open http://localhost:3000 and click **📂 Ingest Config Files**. There are two tabs:

- **Single File** — pick one config, optionally override the hostname or vendor, click **Upload & Parse**.
- **Folder / Multiple** — either use the folder picker (browser-native, requires a Chromium-based browser for the `webkitdirectory` folder select) or select several files individually. Every matching file is POSTed one at a time to the backend with a live per-file progress bar.

Supported extensions in the picker: **`.txt`, `.conf`, `.cfg`, `.log`, `.config`**.

To load the bundled sample data, use the folder picker on `backend/data/` (mounted at `/app/data` in the container, but the picker reads from your host filesystem, so point it at the repo's `backend/data/` folder directly) — it contains sample Juniper and Huawei configs, plus the built-in synthetic sample network is loaded automatically the first time the API starts.

> **Note:** There's also a more advanced ingest UI (`frontend/src/components/IngestModal.jsx`) with drag-and-drop, a server-side "Folder Scan" path input, and SSE-driven live progress — but it isn't wired up yet. It posts to `/api/ingest/upload` and `/api/ingest/stream`, neither of which exist in `routers/ingest.py`, and `App.jsx` doesn't import it. Treat it as an in-progress redesign, not the current UI.

### 4  Ingest your own configs

Same **📂 Ingest Config Files** panel as above — either upload a single file or select/drop multiple files (`.txt`, `.conf`, `.cfg`, `.log`, `.config`). Vendor is auto-detected from file content unless you override it.

Ingest always **upserts** by device name — it merges new devices into whatever's already in Elasticsearch rather than replacing it. If you want to start over with a clean map instead of merging (e.g. importing a different network's configs), click **🗑 Clear Map** in the top toolbar first. It asks for confirmation, then deletes every device, interface, connection, and ACL currently indexed — this is irreversible, there's no undo, so re-ingest from your original files if you clear the wrong thing.

For bulk loading from the command line instead of the browser (useful for large batches or scripting), run inside the API container or a local Python env:

```bash
python ingest.py --config-dir /path/to/configs
```

This scans the given directory for the same five extensions and ingests everything it finds.

### 5  Discover connections

Devices and interfaces alone don't give you a topology — you need the links between them. Click **🔗 Discover** in the top toolbar to run the connection-discovery engine (`backend/connection_discovery.py`) against everything currently in Elasticsearch. It runs three strategies, in order of confidence, and never overwrites or duplicates an existing connection:

1. **Subnet matching** — interface pairs sharing an IP subnet of `/29` or smaller (i.e. `/29`–`/31`) are inferred as a point-to-point link. Highest confidence, no manual input needed.
2. **Description matching** — scans interface descriptions for text naming another known device (`"uplink to sw-dist-01 Gi0/1"`, `"link → fw-01"`, etc.), including recognizing abbreviated interface names (`Gi`, `Te`, `Fa`, Juniper `ge-`/`xe-`, and bare `slot/port` forms).
3. **CDP/LLDP parsing** — if your config export includes `show cdp neighbors detail` or `show lldp neighbors detail` output appended to the file, this strategy parses it directly for neighbor device, local interface, and remote port. Highest confidence of the three, but only runs if that output is present.

The result notification shows how many new connections were found, broken down by strategy, and the running total in the topology. Re-running Discover after ingesting more devices is safe — it only adds connections it hasn't seen before.

### 6  Explore the topology

- **Click** any node to see device details (vendor, OS, interfaces, ACLs)
- **Right-click** a node to start a path-find query or assign it to a POP
- **Click** an edge to see link details (type, VLANs, ACL status)
- Use the **Path Search** panel (with fuzzy autocomplete via `/pathfind/search`) to trace a route between any two devices, IPs, or "internet", and check whether a specific protocol/port is authorized along the way

---

## Volume Mounts

By default, `backend/data/` on your host is mounted to `/app/data` inside the API container. To use a different location, set `DATA_PATH` before running `docker compose up`:

```bash
# Windows PowerShell
$env:DATA_PATH = "C:\Users\you\network-configs"
docker compose up -d

# Linux / Mac
DATA_PATH=/home/you/network-configs docker compose up -d
```

Or edit `docker-compose.yml` directly:

```yaml
  api:
    volumes:
      - ./backend:/app
      - /your/custom/path:/external-data   # then use /external-data in the UI
```

---

## Rebuilding After Code Changes

Python changes (parsers, routers) — restart the API container only:

```bash
docker restart tm-api
```

React / JSX / CSS changes — rebuild and restart the frontend:

```bash
docker compose build frontend && docker compose up -d frontend
```

Full rebuild:

```bash
docker compose up -d --build
```

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│  Browser (React + Cytoscape.js)                    localhost:3000    │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  Topology graph │ Device detail │ Path search │ Ingest panel  │  │
│  │                          │ 🔗 Discover button                 │  │
│  └────────────────────────────────────────────────────────────────┘  │
└────────────────────────────┬─────────────────────────────────────────┘
                             │ HTTP  (Nginx proxy → :8000)
┌────────────────────────────▼─────────────────────────────────────────┐
│  FastAPI + Uvicorn                                 localhost:8000    │
│  ┌─────────────┐ ┌────────────────────┐ ┌────────────────────────┐  │
│  │ /topology   │ │ /ingest/config     │ │ /pathfind              │  │
│  │ /devices    │ │ /ingest/discover-  │ │ /pathfind/search       │  │
│  │             │ │  connections       │ │ (NetworkX-free BFS)    │  │
│  │             │ │ /ingest/wipe (DEL) │ │                        │  │
│  └─────────────┘ └─────────┬──────────┘ └────────────────────────┘  │
│                             │ _parse_config()                        │
│  ┌──────────────────────────▼────────────────────────────────────┐   │
│  │  Parser dispatcher  (routers/ingest.py)                       │   │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────┐              │   │
│  │  │ cisco        │ │  juniper     │ │  huawei  │  ← wired in  │   │
│  │  └──────────────┘ └──────────────┘ └──────────┘              │   │
│  │  dell.py / hpe.py exist but are not connected yet             │   │
│  └───────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  connection_discovery.py — subnet / description / CDP-LLDP matching   │
└────────────────────────────┬─────────────────────────────────────────┘
                             │ Elasticsearch Python client
┌────────────────────────────▼─────────────────────────────────────────┐
│  Elasticsearch 8.13                                localhost:9200    │
│  Indices: treasuremap_devices  _interfaces  _connections  _acls      │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Features

- **Three vendor parsers wired in** — Cisco IOS/IOS-XE/NX-OS, Juniper JunOS (hierarchical + set-format), Huawei VRP. Dell OS10 and HPE Aruba OS-CX parsers exist in `backend/parsers/` but aren't connected to the ingest pipeline yet.
- **Auto-detect** — vendor detected from config fingerprints (`routers/ingest.py::_detect_vendor`); explicit hint overrides. Extreme and Nokia are fingerprinted but have no parser yet.
- **🔗 Discover — connection discovery** — one click runs three strategies against everything in Elasticsearch: IP subnet matching (`/29`–`/31`), interface-description text matching, and CDP/LLDP neighbor-block parsing. Deduplicates against existing connections; safe to re-run. See [step 5](#5--discover-connections) above for details.
- **ACL visualisation** — extended ACL rules with source/dest/port/action breakdown
- **Path-finding with authorization check** — BFS shortest-path between any two devices, IPs, or "internet", evaluating ACL/firewall rules hop-by-hop to return a PERMIT/DENY verdict for a given protocol and port. Fuzzy autocomplete via `/pathfind/search`.
- **POP detection** — `{site}-{loc}-{role}-{seq}` hostname convention auto-assigns Point of Presence and role
- **🗑 Clear Map** — one click (with a confirmation prompt) wipes all devices, interfaces, connections, and ACLs via `DELETE /ingest/wipe`, for starting fresh instead of merging into existing data
- **3D device icons** — Cisco photorealistic PNG icons (router, switch, firewall, server, host) committed in the repo; gradient SVG originals also included

---

## Project Structure

```
TreasureMap/
├── docker-compose.yml          # All four services (ES, API, Frontend, Kibana)
├── .gitignore
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py                 # FastAPI app entry point
│   ├── config.py               # Index name constants
│   ├── es_client.py            # Elasticsearch client + index bootstrap
│   ├── models.py               # Pydantic models (Device, Interface, Connection, Acl)
│   ├── pop_detector.py         # Hostname → POP / role detection
│   ├── create_indices.py       # Standalone index creation script
│   ├── connection_discovery.py # 🔗 Discover — subnet/description/CDP-LLDP matching
│   ├── ingest.py               # CLI bulk ingest: python ingest.py --config-dir PATH
│   ├── ingest_batfish.py       # Standalone experiment — parses Batfish sample data
│   │                           #   into a separate "network-configs" ES index; not
│   │                           #   part of the main app (not imported by main.py)
│   ├── topology.py             # Standalone experiment, same Batfish sandbox as above
│   │                           #   (distinct from routers/topology.py, which IS live)
│   ├── parsers/
│   │   ├── __init__.py         # Only exports juniper, huawei, cisco — see below
│   │   ├── cisco.py            # ✅ Cisco IOS / IOS-XE / NX-OS — wired in
│   │   ├── juniper.py          # ✅ Juniper JunOS (hierarchical + set-format) — wired in
│   │   ├── huawei.py           # ✅ Huawei VRP — wired in
│   │   ├── dell.py             # 🚧 Dell OS10 / Enterprise SONiC — written, not wired in
│   │   ├── hpe.py              # 🚧 HPE Aruba OS-CX — written, not wired in
│   │   └── ios_config.py       # 🚧 Standalone Cisco parser used only by ingest_batfish.py,
│   │                           #   unrelated to parsers/cisco.py
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── devices.py          # /devices CRUD
│   │   ├── topology.py         # /topology graph builder (the live one)
│   │   ├── pathfind.py         # /pathfind BFS + /pathfind/search autocomplete
│   │   └── ingest.py           # /ingest/config, /ingest/discover-connections,
│   │                           #   /ingest/pops, /ingest/devices/{name}/pop
│   └── data/                   # Sample configs (mounted at /app/data in Docker)
│       ├── sample_junos.txt
│       ├── sample_junos_set.txt
│       ├── sample_huawei.txt
│       ├── sample_dell.txt     # 🚧 Present, but Dell parser isn't wired in yet
│       ├── sample_hpe.txt      # 🚧 Present, but HPE parser isn't wired in yet
│       └── sample_network.py   # Built-in synthetic sample network, loaded on startup
├── frontend/
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── package.json
│   ├── vite.config.js
│   ├── public/
│   │   └── icons/              # PNG + SVG device icons (committed), plus the full
│   │                           #   Cisco EPS icon pack the PNGs were rendered from
│   └── src/
│       ├── App.jsx             # Owns the live ingest panel + 🔗 Discover button
│       ├── TopologyMap.jsx     # 🚧 Not imported anywhere — orphaned earlier draft
│       └── components/
│           ├── TopologyGraph.jsx   # ✅ live — imported by App.jsx
│           ├── DeviceDetails.jsx   # ✅ live
│           ├── PathSearch.jsx      # ✅ live
│           ├── PopAssignModal.jsx  # ✅ live
│           ├── TextualView.jsx     # ✅ live
│           └── IngestModal.jsx     # 🚧 not imported by App.jsx — calls
│                                   #   /api/ingest/upload and /api/ingest/stream,
│                                   #   neither of which exist in routers/ingest.py
├── elasticsearch/
│   └── config/
│       └── elasticsearch.yml   # Single-node, no auth (dev)
└── docs/
    ├── ARCHITECTURE.md
    ├── DEVELOPMENT.md
    ├── INSTALLATION.md
    └── TROUBLESHOOTING.md
```

> The 🚧 items above are real files in the repo, not placeholders — they're just not connected to the running application yet. Worth a future session to either finish wiring them in or remove them so the structure isn't misleading.

---

## Config File Format by Vendor

### Cisco IOS / IOS-XE / NX-OS

Standard `show running-config` output. Files with `.txt`, `.conf`, `.cfg`, `.log`, or `.config` extensions are picked up by both the UI ingest panel and the `ingest.py --config-dir` CLI scan.

```
hostname nyc-core-rtr-01
interface GigabitEthernet0/0/0
 description uplink-to-pe
 ip address 10.0.0.1 255.255.255.252
!
router bgp 65001
 neighbor 10.0.0.2 remote-as 65000
```

### Juniper JunOS — hierarchical

```
system {
    host-name eqx-nyc-pe-01;
}
interfaces {
    ge-0/0/0 {
        description "uplink";
        unit 0 { family inet { address 10.0.0.1/30; } }
    }
}
protocols {
    bgp {
        group EBGP {
            neighbor 10.0.0.2 { peer-as 65000; }
        }
    }
}
```

### Juniper JunOS — set-format

```
set system host-name eqx-nyc-sw-01
set interfaces ge-0/0/0 unit 0 family ethernet-switching interface-mode trunk
set interfaces ge-0/0/0 unit 0 family ethernet-switching vlan members 10-20
```

### Huawei VRP

```
sysname chi-dc-sw-01
interface GigabitEthernet0/0/1
 description uplink
 ip address 10.1.0.1 255.255.255.252
bgp 65002
 peer 10.1.0.2 as-number 65000
```

### Dell OS10 🚧 *(parser exists, not yet wired into ingest — uploading one of these today will be parsed as Cisco and produce garbage)*

Detection requires `hostname` **and** at least one `interface ethernet` line.

```
hostname dal-tor-sw-01
interface ethernet1/1/1
 description uplink
 switchport mode trunk
 switchport trunk allowed vlan 10,20,30
```

### HPE Aruba OS-CX 🚧 *(parser exists, not yet wired into ingest — same caveat as Dell above)*

Detection requires `hostname` **and** at least one `interface N/N/N` (digit/digit/digit) line, plus either `vlan trunk/access` syntax or `vrf mgmt`.

```
hostname ord-agg-sw-01
interface 1/1/1
    description uplink
    vlan trunk allowed 10,20,30
    vlan trunk native 1
router bgp 65003
    neighbor 10.2.0.2 remote-as 65000
```

### Stub configs (servers / workstations)

Use Cisco-parser stub format for hosts that don't have a real running-config:

```
! device-type: server
! vendor: Linux
! os: Ubuntu 22.04
hostname web-server-01
interface eth0
 ip address 10.0.1.10 255.255.255.0
```

---

## Device Icons

Cisco photorealistic PNG icons (`router.png`, `switch.png`, `firewall.png`, `server.png`, `host.png`) are committed in `frontend/public/icons/` — no extra steps required. They were generated from the official [Cisco Network Topology Icons](https://www.cisco.com/c/en/us/about/brand-center/network-topology-icons.html) EPS pack at 256×256px using Ghostscript + Pillow. The source SVGs (3D gradient style) are also committed as `*.svg` in the same folder.

---

## Manual / Native Setup (no Docker)

Use this if Docker is unavailable. Requires Python 3.11+, Node.js 20 LTS, and a locally running Elasticsearch 8.13.

```bash
# 1. Elasticsearch — download and run
# https://www.elastic.co/downloads/elasticsearch
# Set discovery.type=single-node and xpack.security.enabled=false in elasticsearch.yml

# 2. Backend
cd backend
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# 3. Frontend (separate terminal)
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

---

## Requirements

| Component | Version | Notes |
|-----------|---------|-------|
| Docker Desktop / Engine | 24+ | Recommended install path |
| Python | 3.11 – 3.14 | Required for native install |
| Node.js | 20 LTS+ | Required for native install |
| Elasticsearch | 8.13.0 | Provided by Docker Compose |

---

## Documentation

- [Installation Guide](docs/INSTALLATION.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Development Guide](docs/DEVELOPMENT.md)

# TreasureMap 🗺️

**Multi-vendor network topology visualiser — from configs to interactive graph in minutes.**

TreasureMap ingests running-configuration files from network devices, parses them into a structured graph, stores the data in Elasticsearch, and renders an interactive topology diagram in the browser. It detects BGP peers, shared /30 subnets, interface-description cross-links, VLANs, and ACLs — building a complete picture of your network with no agents, no SNMP, and no proprietary collectors.

![TreasureMap topology overview](https://github.com/user-attachments/assets/306f6ea8-0adb-481f-bc9b-d0fcc1aaf4be)

---

## Supported Vendors

| Vendor | Platform | Parser |
|--------|----------|--------|
| Cisco | IOS / IOS-XE / NX-OS / ASA | `parsers/ios_config.py` |
| Juniper | JunOS (hierarchical and set-format) | `parsers/juniper.py` |
| Huawei | VRP V2 / V5 / V8 | `parsers/huawei.py` |
| Dell | OS10 / Enterprise SONiC (PowerSwitch) | `parsers/dell.py` |
| HPE | Aruba OS-CX | `parsers/hpe.py` |

Auto-detect is the default. You can also specify the vendor explicitly when uploading a single file via the UI.

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

Open http://localhost:3000, click **⚙ Ingest**, choose **Folder Scan**, and enter:

```
/app/data
```

This scans `backend/data/` (mounted into the container), which contains sample configs for all five supported vendors. Click **▶ Start Ingest**.

### 4  Ingest your own configs

**Option A — Upload File** (single device, any vendor):
1. Click **⚙ Ingest → Upload File**
2. Drop your `.cfg` / `.conf` / `.txt` file
3. Select a vendor hint or leave it as Auto-detect
4. Click **⬆ Upload & Parse**

**Option B — Folder Scan** (batch, one folder at a time):
1. Copy your config files into `backend/data/` on the Docker host (or mount a different path — see [Volume Mounts](#volume-mounts) below)
2. Click **⚙ Ingest → Folder Scan** and enter the path inside the container

### 5  Explore the topology

- **Click** any node to see device details (vendor, OS, interfaces, ACLs, BGP peers)
- **Right-click** a node to start a path-find query or assign it to a POP
- **Click** an edge to see link details (type, VLANs, ACL status)
- Use the **Path Search** panel to trace a route between any two devices

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
│  │  Topology graph │  Device detail │  Path-find │  Ingest UI     │  │
│  └────────────────────────────────────────────────────────────────┘  │
└────────────────────────────┬─────────────────────────────────────────┘
                             │ HTTP / SSE  (Nginx proxy → :8000)
┌────────────────────────────▼─────────────────────────────────────────┐
│  FastAPI + Uvicorn                                 localhost:8000    │
│  ┌─────────────┐  ┌──────────────────┐  ┌───────────────────────┐   │
│  │ /topology   │  │ /ingest/stream   │  │ /pathfind             │   │
│  │ /devices    │  │  (SSE batch)     │  │ (NetworkX BFS)        │   │
│  └─────────────┘  └────────┬─────────┘  └───────────────────────┘   │
│                             │ _dispatch_parser()                      │
│  ┌──────────────────────────▼────────────────────────────────────┐   │
│  │  Parser dispatcher  (routers/ingest.py)                       │   │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────┐              │   │
│  │  │ ios_config   │ │  juniper     │ │  huawei  │              │   │
│  │  └──────────────┘ └──────────────┘ └──────────┘              │   │
│  │  ┌──────────────┐ ┌──────────────┐                           │   │
│  │  │ dell (OS10)  │ │ hpe (OS-CX)  │  ← auto-detect or hint   │   │
│  │  └──────────────┘ └──────────────┘                           │   │
│  └───────────────────────────────────────────────────────────────┘   │
└────────────────────────────┬─────────────────────────────────────────┘
                             │ Elasticsearch Python client
┌────────────────────────────▼─────────────────────────────────────────┐
│  Elasticsearch 8.13                                localhost:9200    │
│  Indices: treasuremap_devices  _interfaces  _connections  _acls      │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Features

- **Five vendor parsers** — Cisco IOS/IOS-XE/NX-OS/ASA, Juniper JunOS (hierarchical + set-format), Huawei VRP, Dell OS10, HPE Aruba OS-CX
- **Auto-detect** — vendor/OS detected from config fingerprints; explicit hint overrides
- **Automatic connection detection** — BGP peers, shared /30 subnets, interface-description cross-links
- **ACL visualisation** — extended ACL rules with source/dest/port/action breakdown
- **Path-finding** — BFS shortest-path between any two devices with ACL evaluation
- **POP detection** — `{site}-{loc}-{role}-{seq}` hostname convention auto-assigns Point of Presence and role
- **Live ingest stream** — Server-Sent Events feed shows per-file parsing progress in real time
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
│   ├── parsers/
│   │   ├── __init__.py
│   │   ├── ios_config.py       # Cisco IOS / IOS-XE / NX-OS / ASA
│   │   ├── juniper.py          # Juniper JunOS (hierarchical + set-format)
│   │   ├── huawei.py           # Huawei VRP
│   │   ├── dell.py             # Dell OS10 / Enterprise SONiC
│   │   └── hpe.py              # HPE Aruba OS-CX
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── devices.py          # /devices CRUD
│   │   ├── topology.py         # /topology graph builder
│   │   ├── pathfind.py         # /pathfind BFS
│   │   └── ingest.py           # /ingest/stream (SSE) + /ingest/upload
│   └── data/                   # Sample configs (mounted at /app/data in Docker)
│       ├── sample_ios.cfg
│       ├── sample_junos.txt
│       ├── sample_junos_set.txt
│       ├── sample_huawei.txt
│       ├── sample_dell.txt
│       └── sample_hpe.txt
├── frontend/
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── package.json
│   ├── vite.config.js
│   ├── public/
│   │   └── icons/              # SVG device icons (committed)
│   │       ├── router.svg
│   │       ├── switch.svg
│   │       ├── firewall.svg
│   │       ├── server.svg
│   │       └── host.svg
│   └── src/
│       ├── App.jsx
│       └── components/
│           ├── TopologyGraph.jsx
│           ├── DeviceDetails.jsx
│           ├── IngestModal.jsx
│           ├── PathSearch.jsx
│           ├── PopAssignModal.jsx
│           └── TextualView.jsx
├── elasticsearch/
│   └── config/
│       └── elasticsearch.yml   # Single-node, no auth (dev)
└── docs/
    ├── ARCHITECTURE.md
    ├── DEVELOPMENT.md
    ├── INSTALLATION.md
    └── TROUBLESHOOTING.md
```

---

## Config File Format by Vendor

### Cisco IOS / IOS-XE / NX-OS

Standard `show running-config` output. Files with `.cfg`, `.conf`, or `.txt` extensions are scanned automatically by the folder ingester.

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

### Dell OS10

Detection requires `hostname` **and** at least one `interface ethernet` line.

```
hostname dal-tor-sw-01
interface ethernet1/1/1
 description uplink
 switchport mode trunk
 switchport trunk allowed vlan 10,20,30
```

### HPE Aruba OS-CX

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

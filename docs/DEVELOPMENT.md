# TreasureMap — Development Guide

---

## Local Dev Setup (hot-reload)

```bash
# Terminal 1 — Elasticsearch (native) or use Docker:
#   docker compose up -d elasticsearch
export ES_JAVA_OPTS="-Xms512m -Xmx512m"
./elasticsearch/server/elasticsearch-8.13.0/bin/elasticsearch

# Terminal 2 — Backend (auto-reloads on .py changes)
cd backend
../.venv/bin/uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Terminal 3 — Frontend (HMR)
cd frontend
npm run dev
```

---

## Adding a New Device Parser

### 1. Identify the config format

Collect a real `show running-config` output. Check whether `is_ios_running_config()` would accept it (needs `hostname X` and `interface X` lines).

### 2. Update `detect_vendor_os()`

Add a new detection block **before** the IOS fallback in `backend/parsers/ios_config.py`:

```python
# Example: Aruba AOS-CX
if re.search(r"^hostname\s+\S+", text, re.MULTILINE) and "aos-cx" in low:
    return "Aruba", "AOS-CX", "switch"
```

### 3. Extend the parser

The main parser function `parse_ios_running_config()` returns a dict. Extend it by adding a new block under the relevant `vendor/os` check:

```python
if parsed["os"] == "AOS-CX":
    parsed["interfaces"] = _parse_aoscx_interfaces(text)
    # etc.
```

Or for small differences, add regex branches inside the existing parsers.

### 4. Write a test

Add a minimal config fixture to `backend/data/test-fixtures/` and a test in `backend/test_parse.py`:

```python
def test_aruba_aoscx():
    text = Path("data/test-fixtures/aruba-switch.cfg").read_text()
    result = parse_ios_running_config(text, Path("aruba-switch.cfg"))
    assert result["vendor"] == "Aruba"
    assert result["os"] == "AOS-CX"
    assert len(result["interfaces"]) > 0
```

---

## Adding a New Connection Detection Pass

Edit `backend/routers/ingest.py`. New passes go after the existing three in `generate()`:

```python
# Pass 4: LLDP neighbour table cross-linking
connections += build_lldp_connections(all_parsed_ifaces, known_devices, seen_pairs)
```

The function signature should match:
```python
def build_lldp_connections(
    all_ifaces: list[dict],
    known_devices: set[str],
    seen: set[frozenset],
) -> list[Connection]:
    ...
```

`seen` is passed by reference and should be updated to prevent duplicates across passes.

---

## Adding a Frontend Feature

### New node detail field

1. Add the field to the Elasticsearch mapping in `es_client.py` → `MAPPINGS[IDX_DEVICES]`
2. Populate it in `ingest.py` → `_build_device()`
3. Expose it in `routers/devices.py` (it will be included automatically if mapped)
4. Display it in `App.jsx` wherever the device detail panel is rendered

### New edge type

1. Add the new `link_type` value to the `Connection.link_type` Pydantic literal in `models.py`:
   ```python
   link_type: Literal['routed','trunk','access','uplink','crosslink','bgp','your_new_type']
   ```
2. Add a stylesheet entry in `TopologyGraph.jsx`:
   ```javascript
   { selector: '.edge-your-new-type', style: { 'line-color': '#hex', ... } },
   ```
3. Add the CSS class in `App.jsx` where edges are converted to Cytoscape elements.

### New SVG icon

Drop a new `<device_type>.svg` into `frontend/public/icons/`. Use white strokes on a transparent background — the node's `background-color` (set per `.node-<type>` class) provides the coloured backing.

Update the stylesheet entry in `TopologyGraph.jsx`:
```javascript
{ selector: '.node-mytype', style: {
    'background-color': '#1d4ed8',
    'border-color': '#60a5fa',
    'background-image': 'url(/icons/mytype.svg)',
}},
```

---

## API Reference

The FastAPI Swagger UI is at http://localhost:8000/docs. Key endpoints:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Elasticsearch + API status |
| GET | `/devices` | All devices (optional `?q=hostname`) |
| GET | `/devices/{id}` | Single device + its interfaces and ACLs |
| GET | `/topology` | All nodes + edges for Cytoscape |
| GET | `/topology/connections` | Raw connection list |
| GET | `/pathfind?src=fw-01&dst=dc-01` | BFS shortest path |
| GET | `/ingest/stream?folder_path=...&wipe=true` | SSE ingest stream |

---

## Environment Variables

All env vars are read in `backend/config.py`. Copy `.env.example` to `backend/.env` to override defaults.

| Variable | Default | Description |
|----------|---------|-------------|
| `ELASTICSEARCH_URL` | `http://localhost:9200` | Elasticsearch endpoint |
| `ES_INDEX_PREFIX` | `treasuremap` | Index name prefix |
| `API_HOST` | `0.0.0.0` | Uvicorn bind address |
| `API_PORT` | `8000` | Uvicorn port |
| `CORS_ORIGINS` | `http://localhost:5173,...` | Comma-separated allowed origins |

---

## Running Tests

```bash
cd backend

# Parse tests (no Elasticsearch required)
.venv/bin/python -m pytest test_parse.py -v

# Integration tests (Elasticsearch must be running)
.venv/bin/python test_es.py
```

---

## Adding Synthetic Lab Devices

Synthetic device configs live in `data/synthetic-lab/`. To add a new device:

1. Create `data/synthetic-lab/<hostname>.cfg`
2. For Cisco devices: include a full running-config with `hostname`, `interface`, and optionally `router bgp` / `ip access-list` blocks
3. For servers/workstations: use the stub format:
   ```
   ! device-type: server
   ! vendor: Microsoft
   ! os: Windows Server 2022
   hostname new-server-01
   interface Ethernet0
    ip address 10.0.1.x 255.255.255.0
   ```
4. Add an `interface description` on the access switch port pointing to this server (triggers description-based connection detection)
5. Re-ingest: `curl "http://localhost:8000/ingest/stream?folder_path=$(pwd)/data/synthetic-lab&wipe=true"`

---

## Code Style

- **Python**: PEP 8. Type hints on all function signatures. No bare `except`.
- **JavaScript**: Standard ES2022. No TypeScript (keeping it approachable). Functional components only.
- **Commits**: `<type>: <short description>` — types: `feat`, `fix`, `docs`, `refactor`, `test`

---

## Building for Production

```bash
# Build the React app
cd frontend
npm run build
# Output: frontend/dist/

# Serve with the preview server (for testing the build)
npm run preview

# Or run the full Docker stack (builds + serves via Nginx)
docker compose up -d --build
```

The production Docker frontend container uses Nginx to serve the built `dist/` and proxy API calls to the `api` container.

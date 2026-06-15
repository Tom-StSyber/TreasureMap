# TreasureMap — Architecture

---

## Overview

TreasureMap is a three-tier application:

```
[ React + Cytoscape.js ]  ←→  [ FastAPI + NetworkX ]  ←→  [ Elasticsearch 8.x ]
       Port 5173                     Port 8000                   Port 9200
    (Vite dev server)              (uvicorn)                (single-node cluster)
```

The frontend never talks directly to Elasticsearch. All reads and writes go through the FastAPI backend, which owns the data model and business logic.

---

## Data Model

### Indices

All indices are prefixed with `treasuremap_` (configurable via `ES_INDEX_PREFIX`).

#### `treasuremap_devices`

One document per network device or host.

| Field | Type | Description |
|-------|------|-------------|
| `id` | keyword | Deterministic UUID: `uuid5(DNS, "tm.device.<hostname>")` |
| `name` | keyword | Hostname (lowercase) |
| `hostname` | keyword | Hostname as parsed |
| `management_ip` | ip | First non-loopback interface IP |
| `vendor` | keyword | `Cisco`, `Microsoft`, `Linux`, `Juniper`, etc. |
| `os` | keyword | `IOS-XE`, `NX-OS`, `Windows Server 2022`, etc. |
| `device_type` | keyword | `router`, `switch`, `firewall`, `server`, `host` |
| `model` | keyword | Hardware model (if parseable from config) |
| `location` | keyword | Site/rack (from config comments) |
| `tags` | keyword[] | Free-form tags |

#### `treasuremap_interfaces`

One document per physical or logical interface.

| Field | Type | Description |
|-------|------|-------------|
| `id` | keyword | `uuid5(DNS, "tm.iface.<hostname>.<ifname>")` |
| `device_id` | keyword | Parent device ID |
| `device_name` | keyword | Parent device hostname |
| `name` | keyword | Interface name (e.g. `GigabitEthernet0/0/1`) |
| `description` | text | Interface description |
| `ip_address` | ip | IPv4 address |
| `prefix_length` | integer | Subnet prefix length |
| `admin_status` | keyword | `up` or `down` |
| `vlan_mode` | keyword | `access`, `trunk`, or `none` |
| `vlan_id` | integer | Access VLAN |
| `trunk_vlans` | integer[] | Allowed VLANs (trunk) |
| `acl_in` / `acl_out` | keyword | Applied ACL names |

#### `treasuremap_connections`

One document per link (logical or physical) between two devices.

| Field | Type | Description |
|-------|------|-------------|
| `id` | keyword | `uuid5(DNS, "tm.conn.<src>.<dst>")` |
| `src_device_name` | keyword | Source device hostname |
| `src_interface` | keyword | Source interface name |
| `dst_device_name` | keyword | Destination device hostname |
| `dst_interface` | keyword | Destination interface name |
| `link_type` | keyword | `routed`, `trunk`, `access`, `uplink`, `crosslink`, `bgp` |
| `status` | keyword | `up` or `down` |
| `has_acl` | boolean | ACL applied to this link |
| `has_firewall` | boolean | Traverses a firewall |

#### `treasuremap_acls`

One document per ACL (with rules embedded as a nested object).

| Field | Type | Description |
|-------|------|-------------|
| `id` | keyword | `uuid5(DNS, "tm.acl.<hostname>.<aclname>")` |
| `device_name` | keyword | Device the ACL belongs to |
| `name` | keyword | ACL name |
| `acl_type` | keyword | `extended` or `standard` |
| `rules` | object (disabled) | Array of rule objects stored as raw JSON |

---

## Parser Design

### Entry point: `parse_ios_running_config(text, path)`

Returns a dictionary with keys: `hostname`, `vendor`, `os`, `device_type`, `interfaces`, `bgp_peers`, `acls`.

### Detection pipeline (`detect_vendor_os`)

Priority order — first match wins:

1. **Stub metadata comment** — `! device-type: server|host`  
   Returns immediately with vendor/OS from `! vendor:` / `! os:` comments.  
   Used for servers and workstations that don't run IOS.

2. **Juniper JunOS** — `version X.YRZ` pattern, or `interfaces {` + `routing-options {`

3. **Cisco ASA/PIX** — `asa version` or `pix version` keywords

4. **Cisco NX-OS** — `feature <word>` line AND `nxos` substring  
   The `nxos` string must appear literally (e.g. in a `boot nxos` line).  
   NX-OS versions use `nxos` (no hyphen); the string `nx-os` does NOT match.

5. **Cisco IOS-XE** — `version 16.x` or `17.x`

6. **Cisco IOS** — `version 12.x` or `15.x`

7. **Fallback** — `Cisco/IOS/router`

### Connection building (three passes)

After all files are parsed, `generate()` in `ingest.py` runs three independent passes and deduplicates with a `seen_pairs: set[frozenset]`:

**Pass 1 — BGP peers**  
Reads `bgp_map[device] = [{peer_ip, local_as, remote_as}]` and resolves each peer IP against `ip_to_device`. Creates `link_type=bgp` connections.

**Pass 2 — Shared /30–/29 subnets**  
Groups all interface IPs by their network address. Any network with exactly 2 devices on it (and prefix ≥ 29) becomes a `link_type=routed` P2P connection.

**Pass 3 — Interface description hostname matching**  
Scans every interface description. If a known device hostname appears as a substring, creates a connection. Link type is `trunk` if the interface is in trunk mode, `access` otherwise.

---

## Frontend Architecture

### Component tree

```
App.jsx
├── Sidebar (device/edge detail panel)
├── IngestPanel (file path input + SSE stream display)
├── PathfindPanel (src/dst selection + result highlight)
└── TopologyGraph.jsx  (Cytoscape.js canvas)
```

### Cytoscape.js integration

Nodes and edges are built in `App.jsx` from the `/topology` API response and passed as `elements` to `TopologyGraph`. The graph is re-rendered (new dagre layout) whenever `elements` changes, but path highlights are applied without re-running layout to avoid positional jumps.

**Node classes** control appearance via stylesheet:
- `.node-router` — blue background, router SVG icon
- `.node-switch` — green background, switch SVG icon
- `.node-firewall` — orange/red background, shield SVG icon
- `.node-server` — indigo background, rack server SVG icon
- `.node-host` — purple background, monitor SVG icon

**Edge classes:**
- `.edge-up` — green solid (normal routed link)
- `.edge-trunk` — thick blue solid (802.1Q trunk)
- `.edge-bgp` — purple dashed (BGP session)
- `.edge-acl` — orange solid (ACL or firewall policy applied)
- `.edge-disabled` — grey dashed (admin down)

### Vite proxy

The dev server at port 5173 proxies `/api/*` to `http://localhost:8000/*`. This means frontend code calls `/api/topology` and Vite rewrites it to `http://localhost:8000/topology`.

In the production Docker build, Nginx performs the same proxy (see `frontend/nginx.conf`).

---

## Deterministic IDs

All IDs are computed with `uuid.uuid5(uuid.NAMESPACE_DNS, "tm.<type>.<identifier>")`:

```python
_id("device.fw-01")          # always the same UUID for fw-01
_id("iface.fw-01.Gi0/0/0")   # always the same UUID for this interface
_id("conn.fw-01.corp-rtr-01") # always the same UUID for this connection
```

This means re-ingesting the same configs is idempotent at the document level — Elasticsearch upserts by ID rather than creating duplicates.

---

## Path-Finding

`routers/pathfind.py` builds an in-memory NetworkX `Graph` from the connection index on each request (or from a cached version). BFS (`nx.shortest_path`) finds the shortest hop path between two devices. The response includes:

- `path` — ordered list of device names
- `edges` — list of edge IDs to highlight
- `found` — boolean
- `hops` — path length

---

## Security Notes

This is a **development/home-lab tool**. The default configuration deliberately disables Elasticsearch authentication and TLS. Do not expose port 9200, 8000, or 5173 on an internet-facing interface. Before deploying to any shared network:

1. Enable `xpack.security.enabled: true` in Elasticsearch and create a user
2. Set `ELASTICSEARCH_URL=https://user:password@localhost:9200` in `backend/.env`
3. Put the frontend and API behind a reverse proxy with HTTPS and authentication

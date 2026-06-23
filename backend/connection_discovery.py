"""
TreasureMap — Connection Discovery Engine

Infers physical/logical connections between devices using three strategies,
run in order of confidence (highest first):

  1. subnet    — Interface pairs sharing a /29, /30, or /31 subnet are almost
                 always point-to-point links.  No false positives on properly
                 addressed networks.

  2. description — Interface descriptions often name the connected device, e.g.
                 "uplink to sw-dist-01 Gi1/0/1" or "link:fw-01:Gi0/0".
                 Scans all known device names against the description text.

  3. cdp_lldp  — Sections of show-tech/show-cdp/show-lldp output appended to
                 the config export are parsed for neighbor Device-ID, local
                 interface, and remote port information.  Highest confidence
                 but requires the operator to include that output in the export.

All three strategies share the same deduplication layer: a connection between
(A, iface_x) and (B, iface_y) is never written twice regardless of which
strategy found it first, and existing ES records are never overwritten.
"""
from __future__ import annotations

import ipaddress
import logging
import re
import uuid
from typing import Optional

log = logging.getLogger(__name__)

# ── Abbreviated interface name patterns ───────────────────────────────────────
# Used to recognise interface references embedded in description text.
# e.g. "uplink to sw-dist-01 Gi0/1"  →  "GigabitEthernet0/1"
_IFACE_ABBREVS = [
    (r"\bGi(\d[\d/\.]*)", "GigabitEthernet"),
    (r"\bGe(\d[\d/\.]*)", "ge-"),          # Juniper ge-
    (r"\bXe(\d[\d/\.]*)", "xe-"),          # Juniper xe-
    (r"\bEt(\d[\d/\.]*)", "Ethernet"),
    (r"\bFa(\d[\d/\.]*)", "FastEthernet"),
    (r"\bTe(\d[\d/\.]*)", "TenGigabitEthernet"),
    (r"\bHu(\d[\d/\.]*)", "HundredGigE"),
    (r"\bMg(\d[\d/\.]*)", "Management"),
    (r"\b(\d+/\d+/\d+)\b", ""),            # bare slot/module/port
    (r"\b(\d+/\d+)\b",     ""),            # bare module/port
]

# Common words that must NOT be treated as device-name matches
_STOP_WORDS = {
    "uplink", "downlink", "link", "to", "from", "via", "port", "interface",
    "trunk", "access", "vlan", "wan", "lan", "mgmt", "management",
    "connected", "connection", "toward", "toward", "peer", "neighbour",
    "neighbor", "network", "subnet", "transit", "core", "dist", "acc",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fetch_all(es, index: str, size: int = 2000) -> list[dict]:
    """Return all documents from an ES index (up to `size`)."""
    try:
        resp = es.search(index=index, body={"query": {"match_all": {}}, "size": size})
        return [h["_source"] for h in resp["hits"]["hits"]]
    except Exception as exc:
        log.warning("Could not fetch from %s: %s", index, exc)
        return []


def _conn_key(src_dev: str, src_iface: str, dst_dev: str, dst_iface: str) -> str:
    """Canonical direction-agnostic key for a connection."""
    a = (src_dev.lower(), src_iface.lower())
    b = (dst_dev.lower(), dst_iface.lower())
    lo, hi = (a, b) if a <= b else (b, a)
    return f"{lo[0]}:{lo[1]}|{hi[0]}:{hi[1]}"


def _device_pair_key(dev_a: str, dev_b: str) -> str:
    """Direction-agnostic key for a device pair (ignores interfaces)."""
    lo, hi = (dev_a.lower(), dev_b.lower()) if dev_a.lower() <= dev_b.lower() else (dev_b.lower(), dev_a.lower())
    return f"{lo}|{hi}"


def _link_type(src: dict, dst: dict) -> str:
    if src.get("vlan_mode") == "trunk" or dst.get("vlan_mode") == "trunk":
        return "trunk"
    if src.get("ip_address") and dst.get("ip_address"):
        return "routed"
    if src.get("vlan_mode") == "access" or dst.get("vlan_mode") == "access":
        return "access"
    return "routed"


def _link_status(src: dict, dst: dict) -> str:
    if src.get("admin_status") == "disabled" or dst.get("admin_status") == "disabled":
        return "disabled"
    return "up"


def _make_conn(
    src_dev: dict, src_iface: dict,
    dst_dev: dict, dst_iface: dict,
    method: str, description: Optional[str] = None,
) -> dict:
    return {
        "id":             str(uuid.uuid4()),
        "src_device_id":   src_dev["id"],
        "src_device_name": src_dev["name"],
        "src_interface":   src_iface["name"],
        "dst_device_id":   dst_dev["id"],
        "dst_device_name": dst_dev["name"],
        "dst_interface":   dst_iface["name"],
        "link_type":       _link_type(src_iface, dst_iface),
        "status":          _link_status(src_iface, dst_iface),
        "has_acl":         bool(src_iface.get("acl_in") or src_iface.get("acl_out")
                                or dst_iface.get("acl_in") or dst_iface.get("acl_out")),
        "has_firewall":    bool(src_iface.get("firewall_policy") or dst_iface.get("firewall_policy")),
        "bandwidth_mbps":  src_iface.get("speed_mbps") or dst_iface.get("speed_mbps"),
        "description":     description or f"Discovered via {method}",
    }


# ── Strategy 1: Subnet matching ───────────────────────────────────────────────

def _by_subnet(
    devices: list[dict],
    interfaces: list[dict],
    min_prefix: int = 29,
) -> list[dict]:
    """
    Find point-to-point links by matching interfaces on the same IP subnet.

    Only considers prefix lengths >= min_prefix (default /29) to avoid
    false positives on broad management or transit subnets.
    """
    dev_by_name = {d["name"]: d for d in devices}

    # Group interfaces by their network address
    subnet_map: dict[str, list[dict]] = {}
    for iface in interfaces:
        ip  = iface.get("ip_address")
        pfx = iface.get("prefix_length")
        if not ip or pfx is None or pfx < min_prefix:
            continue
        try:
            network = str(ipaddress.ip_interface(f"{ip}/{pfx}").network)
            subnet_map.setdefault(network, []).append(iface)
        except ValueError:
            pass

    connections = []
    for subnet, ifaces in subnet_map.items():
        # Group by device — only connect interfaces on DIFFERENT devices
        by_dev: dict[str, list[dict]] = {}
        for iface in ifaces:
            by_dev.setdefault(iface["device_name"], []).append(iface)

        dev_names = list(by_dev.keys())
        for i in range(len(dev_names)):
            for j in range(i + 1, len(dev_names)):
                a_name, b_name = dev_names[i], dev_names[j]
                dev_a = dev_by_name.get(a_name)
                dev_b = dev_by_name.get(b_name)
                if not dev_a or not dev_b:
                    continue
                iface_a = by_dev[a_name][0]
                iface_b = by_dev[b_name][0]
                conn = _make_conn(
                    dev_a, iface_a, dev_b, iface_b, "subnet-match",
                    description=f"Subnet {subnet} — point-to-point (auto-discovered)"
                )
                connections.append(conn)
                log.info(
                    "[subnet] %s:%s (%s) ↔ %s:%s (%s) on %s",
                    a_name, iface_a["name"], iface_a["ip_address"],
                    b_name, iface_b["name"], iface_b["ip_address"],
                    subnet,
                )
    return connections


# ── Strategy 2: Interface description matching ────────────────────────────────

def _expand_iface_abbrev(token: str) -> Optional[str]:
    """
    Try to expand an abbreviated interface name token.
    Returns the expanded name or None if it doesn't look like an interface.
    """
    for pattern, prefix in _IFACE_ABBREVS:
        m = re.fullmatch(pattern, token, re.I)
        if m:
            return (prefix + m.group(1)) if prefix else m.group(1)
    return None


def _find_iface_in_desc(desc: str, iface_map: dict[str, dict]) -> Optional[dict]:
    """
    Try to find a specific interface mentioned in a description string.
    Checks abbreviated and full names against iface_map keys.
    Returns the matching interface dict or None.
    """
    # Try each word in the description as a potential interface name
    words = re.split(r"[\s,;:|→\-]+", desc)
    for word in words:
        word = word.strip()
        if not word:
            continue
        # Exact match
        if word in iface_map:
            return iface_map[word]
        # Case-insensitive exact
        for name, iface in iface_map.items():
            if word.lower() == name.lower():
                return iface
        # Try expansion
        expanded = _expand_iface_abbrev(word)
        if expanded:
            for name, iface in iface_map.items():
                if expanded.lower() in name.lower() or name.lower().startswith(expanded.lower()):
                    return iface
    return None


def _find_back_ref(iface_map: dict[str, dict], target_dev: str) -> Optional[dict]:
    """Find an interface on target device whose description mentions target_dev."""
    for iface in iface_map.values():
        desc = (iface.get("description") or "").lower()
        if target_dev.lower() in desc:
            return iface
    return None


def _by_description(
    devices: list[dict],
    interfaces: list[dict],
) -> list[dict]:
    """
    Match interface descriptions against known device names.

    Handles patterns like:
      "uplink to sw-dist-01"
      "to:router-core-01:Gi0/0/0"
      "link → fw-01 GigabitEthernet0/1"
      "connected to server-01 (eth0)"
    """
    dev_by_name = {d["name"]: d for d in devices}

    # Build interface lookup: device_name → {iface_name: iface}
    iface_by_dev: dict[str, dict[str, dict]] = {}
    for iface in interfaces:
        iface_by_dev.setdefault(iface["device_name"], {})[iface["name"]] = iface

    # Sort device names longest-first so "router-core-01" matches before "core"
    dev_names_sorted = sorted(dev_by_name.keys(), key=len, reverse=True)

    connections = []
    # Track which (src_dev, src_iface) → dst_dev we've already handled
    handled: set[str] = set()

    for iface in interfaces:
        desc = (iface.get("description") or "").strip()
        if not desc:
            continue

        src_dev_name  = iface["device_name"]
        src_iface_name = iface["name"]

        # Search for the first known device name in the description
        matched_dev = None
        matched_pos = len(desc) + 1

        for dev_name in dev_names_sorted:
            if dev_name == src_dev_name:
                continue
            # Skip if the device name is shorter than 3 chars (too ambiguous)
            if len(dev_name) < 3:
                continue
            m = re.search(re.escape(dev_name), desc, re.I)
            if m and m.start() < matched_pos:
                matched_dev = dev_name
                matched_pos = m.start()

        if not matched_dev:
            continue

        handle_key = f"{src_dev_name}:{src_iface_name}"
        if handle_key in handled:
            continue
        handled.add(handle_key)

        src_dev = dev_by_name.get(src_dev_name)
        dst_dev = dev_by_name.get(matched_dev)
        if not src_dev or not dst_dev:
            continue

        dst_ifaces = iface_by_dev.get(matched_dev, {})
        if not dst_ifaces:
            continue

        # Try to find the specific remote interface mentioned in the description
        dst_iface = (
            _find_iface_in_desc(desc, dst_ifaces)
            or _find_back_ref(dst_ifaces, src_dev_name)
            or next(iter(dst_ifaces.values()))
        )

        conn = _make_conn(
            src_dev, iface, dst_dev, dst_iface, "description-match",
            description=f"Description: \"{desc}\" (auto-discovered)"
        )
        connections.append(conn)
        log.info(
            "[desc] %s:%s → %s:%s (desc=%r)",
            src_dev_name, src_iface_name,
            matched_dev, dst_iface["name"],
            desc[:60],
        )

    return connections


# ── Strategy 3: CDP / LLDP neighbor parsing ───────────────────────────────────

# CDP "show cdp neighbors detail" block
_CDP_DEVICE_RE  = re.compile(r"Device ID:\s*(\S+)", re.I)
_CDP_LOCAL_RE   = re.compile(r"Interface:\s*(\S+?),", re.I)
_CDP_REMOTE_RE  = re.compile(r"Port ID\s*\(outgoing port\):\s*(\S+)", re.I)
_CDP_IP_RE      = re.compile(r"IP\s*[Aa]ddress:\s*(\d+\.\d+\.\d+\.\d+)", re.I)

# LLDP "show lldp neighbors detail" block
_LLDP_SYSNAME_RE = re.compile(r"System Name:\s*(\S+)", re.I)
_LLDP_LOCAL_RE   = re.compile(r"Local\s+(?:Intf|Interface):\s*(\S+)", re.I)
_LLDP_PORT_RE    = re.compile(r"Port (?:id|ID):\s*(\S+)", re.I)
_LLDP_MGMT_RE    = re.compile(r"Management [Aa]ddress(?:es)?:\s*(\d+\.\d+\.\d+\.\d+)", re.I)


def _parse_cdp_block(text: str) -> list[dict]:
    """
    Extract neighbor entries from a CDP neighbors-detail block.
    Returns list of {remote_device, local_iface, remote_iface, remote_ip}.
    """
    neighbors = []
    # Split on the separator line (------ or Device ID header)
    blocks = re.split(r"(?:^-{3,}|\n\n(?=Device ID:))", text, flags=re.M)
    for block in blocks:
        dev_m   = _CDP_DEVICE_RE.search(block)
        local_m = _CDP_LOCAL_RE.search(block)
        remote_m = _CDP_REMOTE_RE.search(block)
        if dev_m and local_m:
            neighbors.append({
                "remote_device": dev_m.group(1).split(".")[0],  # strip FQDN
                "local_iface":   local_m.group(1).rstrip(","),
                "remote_iface":  remote_m.group(1) if remote_m else None,
                "remote_ip":     next(
                    (m.group(1) for m in _CDP_IP_RE.finditer(block)), None
                ),
            })
    return neighbors


def _parse_lldp_block(text: str) -> list[dict]:
    """
    Extract neighbor entries from an LLDP neighbors-detail block.
    Returns list of {remote_device, local_iface, remote_iface, remote_ip}.
    """
    neighbors = []
    blocks = re.split(r"(?:^-{3,}|\n\n(?=Local))", text, flags=re.M)
    for block in blocks:
        sysname_m = _LLDP_SYSNAME_RE.search(block)
        local_m   = _LLDP_LOCAL_RE.search(block)
        port_m    = _LLDP_PORT_RE.search(block)
        if sysname_m and local_m:
            neighbors.append({
                "remote_device": sysname_m.group(1).split(".")[0],
                "local_iface":   local_m.group(1),
                "remote_iface":  port_m.group(1) if port_m else None,
                "remote_ip":     next(
                    (m.group(1) for m in _LLDP_MGMT_RE.finditer(block)), None
                ),
            })
    return neighbors


def _by_cdp_lldp(
    raw_configs: dict[str, str],  # device_name → raw config text
    devices: list[dict],
    interfaces: list[dict],
) -> list[dict]:
    """
    Parse CDP/LLDP neighbor data embedded in raw configs.

    raw_configs is a dict of device_name → full config text.  The caller is
    responsible for supplying this; it is optional (returns [] if empty).
    """
    if not raw_configs:
        return []

    dev_by_name = {d["name"]: d for d in devices}
    dev_by_short = {d["name"].split(".")[0].lower(): d for d in devices}

    iface_by_dev: dict[str, dict[str, dict]] = {}
    for iface in interfaces:
        iface_by_dev.setdefault(iface["device_name"], {})[iface["name"]] = iface

    connections = []
    for src_dev_name, raw in raw_configs.items():
        src_dev = dev_by_name.get(src_dev_name)
        if not src_dev:
            continue
        src_ifaces = iface_by_dev.get(src_dev_name, {})

        # Extract CDP section
        cdp_m = re.search(
            r"(?:show cdp neighbors detail|cdp neighbor.*?detail)"
            r"[\s\S]*?(?=\n[a-z#>]|\Z)",
            raw, re.I | re.M,
        )
        neighbors = _parse_cdp_block(cdp_m.group(0)) if cdp_m else []

        # Extract LLDP section
        lldp_m = re.search(
            r"(?:show lldp neighbors detail|lldp neighbor.*?detail)"
            r"[\s\S]*?(?=\n[a-z#>]|\Z)",
            raw, re.I | re.M,
        )
        neighbors += _parse_lldp_block(lldp_m.group(0)) if lldp_m else []

        for nb in neighbors:
            remote_short = nb["remote_device"].lower().split(".")[0]
            dst_dev = dev_by_name.get(nb["remote_device"]) or dev_by_short.get(remote_short)
            if not dst_dev:
                log.debug("[cdp/lldp] Unknown remote device %r — skipping", nb["remote_device"])
                continue

            dst_ifaces = iface_by_dev.get(dst_dev["name"], {})

            # Match local interface
            src_iface = (
                src_ifaces.get(nb["local_iface"])
                or _find_iface_in_desc(nb["local_iface"], src_ifaces)
                or (next(iter(src_ifaces.values())) if src_ifaces else None)
            )
            # Match remote interface
            dst_iface = (
                (dst_ifaces.get(nb["remote_iface"]) if nb["remote_iface"] else None)
                or (dst_ifaces.get(nb["remote_iface"]) if nb.get("remote_iface") else None)
                or (next(iter(dst_ifaces.values())) if dst_ifaces else None)
            )
            if not src_iface or not dst_iface:
                continue

            conn = _make_conn(
                src_dev, src_iface, dst_dev, dst_iface, "cdp-lldp",
                description=(
                    f"CDP/LLDP: {src_dev_name}:{nb['local_iface']}"
                    f" ↔ {dst_dev['name']}:{nb.get('remote_iface', '?')}"
                )
            )
            connections.append(conn)
            log.info(
                "[cdp/lldp] %s:%s ↔ %s:%s",
                src_dev_name, nb["local_iface"],
                dst_dev["name"], nb.get("remote_iface", "?"),
            )

    return connections


# ── Public entry point ────────────────────────────────────────────────────────

def discover_connections(
    raw_configs: Optional[dict[str, str]] = None,
) -> dict:
    """
    Run all three discovery strategies and write new connections to Elasticsearch.

    Args:
        raw_configs: Optional dict of {device_name: raw_config_text} for
                     CDP/LLDP strategy.  If omitted, that strategy is skipped.

    Returns:
        {discovered, written, skipped, existing, total,
         by_method: {subnet, description, cdp_lldp}}
    """
    from es_client import get_es
    from config import IDX_DEVICES, IDX_INTERFACES, IDX_CONNECTIONS

    es = get_es()

    devices    = _fetch_all(es, IDX_DEVICES)
    interfaces = _fetch_all(es, IDX_INTERFACES)
    existing   = _fetch_all(es, IDX_CONNECTIONS)

    if not devices:
        return {"error": "No devices in Elasticsearch — run ingest first"}

    # Build existing-key set to avoid duplicates
    existing_keys: set[str] = set()
    for c in existing:
        existing_keys.add(_conn_key(
            c["src_device_name"], c["src_interface"],
            c["dst_device_name"], c["dst_interface"],
        ))

    all_new: list[dict] = []
    seen_keys: set[str] = set()
    by_method: dict[str, int] = {"subnet": 0, "description": 0, "cdp_lldp": 0}

    def _add_all(candidates: list[dict], method_key: str):
        for conn in candidates:
            key = _conn_key(
                conn["src_device_name"], conn["src_interface"],
                conn["dst_device_name"], conn["dst_interface"],
            )
            if key in existing_keys or key in seen_keys:
                continue
            seen_keys.add(key)
            all_new.append(conn)
            by_method[method_key] += 1

    # Strategy 1 — highest confidence, run first
    _add_all(_by_subnet(devices, interfaces), "subnet")

    # Strategy 2 — description matching
    _add_all(_by_description(devices, interfaces), "description")

    # Strategy 3 — CDP/LLDP (only if raw config text was provided)
    if raw_configs:
        _add_all(_by_cdp_lldp(raw_configs, devices, interfaces), "cdp_lldp")

    # Write to Elasticsearch
    written = 0
    for conn in all_new:
        try:
            es.index(
                index=IDX_CONNECTIONS,
                id=conn["id"],
                document=conn,
                refresh=True,
            )
            written += 1
        except Exception as exc:
            log.error("Failed to write connection %s: %s", conn["id"], exc)

    log.info(
        "Connection discovery complete: %d new connections written "
        "(subnet=%d, description=%d, cdp_lldp=%d), %d existing",
        written, by_method["subnet"], by_method["description"],
        by_method["cdp_lldp"], len(existing),
    )

    return {
        "discovered": len(all_new),
        "written":    written,
        "skipped":    len(all_new) - written,
        "existing":   len(existing),
        "total":      len(existing) + written,
        "by_method":  by_method,
    }

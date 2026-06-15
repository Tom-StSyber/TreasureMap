"""
topology.py — Assemble a device/link graph from the network-configs ES index.

Three query passes:
  1. show version            → device nodes (hostname, platform, version, hardware)
  2. show interfaces         → interface inventory, attached to devices by source_file
  3. show cdp neighbors detail → directed links between devices

Correlation strategy
--------------------
ES docs don't carry a shared device key across commands — the test data is
disjoint per .raw file.  We use a two-level ID scheme:

  canonical_id = hostname (from show version records)  when available
  fallback_id  = source_file stem                      otherwise

CDP docs produce links where the *source* device is identified by the CDP
doc's source_file and the *target* is the neighbor_name field.  Both sides
are resolved against the canonical_id map where possible.
"""

from __future__ import annotations

import logging
from typing import Any

from elasticsearch import Elasticsearch

log = logging.getLogger("topology")

INDEX = "network-configs"
MAX_DOCS = 5000   # upper bound per query — raise when ingesting real data


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _scroll_command(es: Elasticsearch, index: str, command: str) -> list[dict]:
    """Return all ES docs whose 'command' field matches *command*."""
    resp = es.search(
        index=index,
        body={
            "query": {"term": {"command": command}},
            "size": MAX_DOCS,
        },
    )
    return [hit["_source"] for hit in resp["hits"]["hits"]]


def _str(val, default: str = "") -> str:
    """Safely coerce any ntc-templates value to a stripped string.

    ntc-templates ``Value List`` fields come back as lists; scalar fields
    come back as strings.  ES dynamic mapping can also store things
    unexpectedly.  This helper handles both so callers never see
    AttributeError: 'list' object has no attribute 'strip'.
    """
    if isinstance(val, list):
        return " ".join(str(v) for v in val).strip() if val else default
    if val is None:
        return default
    return str(val).strip() or default


def _iface_ip(record: dict) -> str:
    """Combine ip_address + prefix_length into CIDR notation, or return ''."""
    ip = _str(record.get("ip_address"))
    pfx = _str(record.get("prefix_length"))
    if not ip:
        return ""
    return f"{ip}/{pfx}" if pfx else ip


def _stem(source_file: str) -> str:
    """Strip .raw extension from a filename."""
    return source_file.removesuffix(".raw")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_topology(es: Elasticsearch, index: str = INDEX) -> dict[str, Any]:
    """
    Return:
        {
          "devices": [ {id, hostname, platform, version, hardware, interfaces: [...]} ],
          "links":   [ {source, source_interface, target, target_interface, mgmt_address} ]
        }
    """
    devices: dict[str, dict] = {}   # canonical_id → device node
    # Maps source_file_stem → canonical_id (so we can resolve CDP source side)
    file_to_id: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Pass 1: show version → device nodes
    # ------------------------------------------------------------------
    for doc in _scroll_command(es, index, "show version"):
        src_file = doc.get("source_file", "unknown")
        stem = _stem(src_file)

        for rec in doc.get("records", []):
            hostname = _str(rec.get("hostname")) or stem
            canonical_id = hostname

            if canonical_id not in devices:
                devices[canonical_id] = {
                    "id": canonical_id,
                    "hostname": hostname,
                    "platform": doc.get("platform", ""),
                    "version": rec.get("version", ""),
                    "hardware": rec.get("hardware", []),
                    "serial": rec.get("serial", []),
                    "uptime": rec.get("uptime", ""),
                    "interfaces": [],
                }

            file_to_id[stem] = canonical_id
            break   # show version yields exactly one record

    # ------------------------------------------------------------------
    # Pass 2: show interfaces → enrich devices with interface inventory
    # ------------------------------------------------------------------
    # Group interface records by source_file so we can attach them together
    iface_groups: dict[str, list[dict]] = {}
    for doc in _scroll_command(es, index, "show interfaces"):
        stem = _stem(doc.get("source_file", "unknown"))
        ifaces = []
        for rec in doc.get("records", []):
            ifaces.append({
                "name": _str(rec.get("interface")),
                "ip": _iface_ip(rec),
                "mac": _str(rec.get("mac_address")),
                "status": _str(rec.get("link_status")),
                "protocol": _str(rec.get("protocol_status")),
                "description": _str(rec.get("description")),
                "speed": _str(rec.get("speed")),
                "mtu": _str(rec.get("mtu")),
            })
        if ifaces:
            iface_groups[stem] = ifaces

    # Attach interfaces to an existing device, or create a stub device
    for stem, ifaces in iface_groups.items():
        canonical_id = file_to_id.get(stem)
        if canonical_id and canonical_id in devices:
            # Merge — don't duplicate if already populated (idempotent)
            existing_names = {i["name"] for i in devices[canonical_id]["interfaces"]}
            for iface in ifaces:
                if iface["name"] not in existing_names:
                    devices[canonical_id]["interfaces"].append(iface)
        else:
            # No matching show version doc — create a stub device keyed by stem
            stub_id = stem
            if stub_id not in devices:
                devices[stub_id] = {
                    "id": stub_id,
                    "hostname": stem,
                    "platform": "",
                    "version": "",
                    "hardware": [],
                    "serial": [],
                    "uptime": "",
                    "interfaces": ifaces,
                }
                file_to_id[stem] = stub_id

    # ------------------------------------------------------------------
    # Pass 3: show cdp neighbors detail → links
    # ------------------------------------------------------------------
    links: list[dict] = []
    seen_links: set[frozenset] = set()   # deduplicate bidirectional pairs

    for doc in _scroll_command(es, index, "show cdp neighbors detail"):
        src_stem = _stem(doc.get("source_file", "unknown"))
        source_device = file_to_id.get(src_stem, src_stem)

        # Ensure the source device node exists (may not have a show version doc)
        if source_device not in devices:
            devices[source_device] = {
                "id": source_device,
                "hostname": source_device,
                "platform": doc.get("platform", ""),
                "version": "",
                "hardware": [],
                "serial": [],
                "uptime": "",
                "interfaces": [],
            }

        for rec in doc.get("records", []):
            target_device = _str(rec.get("neighbor_name")) or "unknown"
            local_iface = _str(rec.get("local_interface"))
            remote_iface = _str(rec.get("neighbor_interface"))
            mgmt_addr = _str(rec.get("mgmt_address"))

            # Ensure the target device node exists
            if target_device not in devices:
                devices[target_device] = {
                    "id": target_device,
                    "hostname": target_device,
                    "platform": rec.get("platform", ""),
                    "version": "",
                    "hardware": [],
                    "serial": [],
                    "uptime": "",
                    "interfaces": [],
                }

            # Deduplicate: treat A↔B same as B↔A at same interfaces
            link_key = frozenset([
                f"{source_device}:{local_iface}",
                f"{target_device}:{remote_iface}",
            ])
            if link_key not in seen_links:
                seen_links.add(link_key)
                links.append({
                    "source": source_device,
                    "source_interface": local_iface,
                    "target": target_device,
                    "target_interface": remote_iface,
                    "mgmt_address": mgmt_addr,
                })

    # ------------------------------------------------------------------
    # Pass 4: running-config (batfish) → richer device + BGP links
    # ------------------------------------------------------------------
    # Build an IP → device_id lookup so we can resolve BGP peer IPs
    # to named devices after all running-config docs are loaded.
    ip_to_device: dict[str, str] = {}

    for doc in _scroll_command(es, index, "running-config"):
        parsed = doc.get("records", {})
        if not isinstance(parsed, dict):
            continue

        hostname = _str(parsed.get("hostname")) or _stem(doc.get("source_file", "unknown"))
        canonical_id = hostname

        # Upsert device node — running-config data wins over stub nodes
        node = devices.setdefault(canonical_id, {
            "id": canonical_id,
            "hostname": hostname,
            "platform": doc.get("platform", "cisco_ios"),
            "version": "",
            "hardware": [],
            "serial": [],
            "uptime": "",
            "interfaces": [],
        })
        node["hostname"] = hostname
        node["platform"] = doc.get("platform", node.get("platform", ""))
        if not node.get("version"):
            node["version"] = _str(parsed.get("version"))

        # Merge interfaces
        existing_iface_names = {i["name"] for i in node["interfaces"]}
        for iface in parsed.get("interfaces", []):
            name = _str(iface.get("name"))
            if not name or name in existing_iface_names:
                continue
            ip = _str(iface.get("ip"))
            pfx = _str(iface.get("prefix_length"))
            node["interfaces"].append({
                "name": name,
                "ip": f"{ip}/{pfx}" if ip and pfx else ip,
                "mac": "",
                "status": "shutdown" if iface.get("shutdown") else "up",
                "protocol": "",
                "description": _str(iface.get("description")),
                "speed": "",
                "mtu": "",
            })
            existing_iface_names.add(name)

            # Register every interface IP so we can resolve BGP peers
            if ip:
                ip_to_device[ip] = canonical_id

        file_to_id[_stem(doc.get("source_file", ""))] = canonical_id

    # Second sub-pass: BGP peer links (needs ip_to_device to be fully built)
    for doc in _scroll_command(es, index, "running-config"):
        parsed = doc.get("records", {})
        if not isinstance(parsed, dict):
            continue
        bgp = parsed.get("bgp")
        if not bgp:
            continue

        hostname = _str(parsed.get("hostname")) or _stem(doc.get("source_file", "unknown"))
        source_device = hostname

        for peer in bgp.get("peers", []):
            peer_ip = _str(peer.get("ip"))
            remote_as = peer.get("remote_as")
            target_device = ip_to_device.get(peer_ip, peer_ip)  # fallback to raw IP

            link_key = frozenset([
                f"{source_device}:bgp:{peer_ip}",
                f"{target_device}:bgp:{peer_ip}",
            ])
            if link_key not in seen_links:
                seen_links.add(link_key)
                links.append({
                    "source": source_device,
                    "source_interface": f"BGP (AS {bgp.get('local_as', '?')})",
                    "target": target_device,
                    "target_interface": f"BGP (AS {remote_as or '?'})",
                    "mgmt_address": peer_ip,
                    "link_type": "bgp",
                })

    log.info(
        "Topology built: %d devices, %d links", len(devices), len(links)
    )

    return {
        "devices": list(devices.values()),
        "links": links,
    }

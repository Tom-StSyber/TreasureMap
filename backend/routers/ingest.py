"""
TreasureMap — /ingest endpoint.

GET  /ingest/stream?folder_path=<path>&wipe=<bool>
  Server-Sent Events stream for batch folder ingestion.

POST /ingest/upload
  Accepts a single config file upload with an optional vendor hint.
  Returns parsed device metadata (hostname, pop, role, interface count, etc.)
  and indexes the device + interfaces into Elasticsearch.
"""
from __future__ import annotations

import ipaddress
import json
import logging
import re
import uuid
from pathlib import Path
from typing import AsyncIterator, Optional

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse

from config import IDX_DEVICES, IDX_INTERFACES, IDX_CONNECTIONS, IDX_ACLS
from es_client import get_es, wipe_indices, bootstrap_indices
from models import Device, Interface, Connection, Acl, AclRule
from parsers.ios_config import parse_ios_running_config, scan_folder
from parsers.juniper import parse_junos_config, is_junos_config
from parsers.huawei import parse_huawei_config, is_huawei_config
from parsers.dell import parse_dell_os10_config, is_dell_os10
from parsers.hpe import parse_hpe_aruba_cx_config, is_hpe_aruba_cx
from pop_detector import enrich_parsed

router = APIRouter(prefix="/ingest", tags=["ingest"])
log = logging.getLogger("ingest")


# ──────────────────────────────────────────────────────────────────────────────
# ID helpers (deterministic so re-ingesting the same file is idempotent)
# ──────────────────────────────────────────────────────────────────────────────

def _id(seed: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"tm.{seed}"))


# ──────────────────────────────────────────────────────────────────────────────
# ES bulk helpers
# ──────────────────────────────────────────────────────────────────────────────

def _bulk_index(es, index: str, docs: list) -> int:
    if not docs:
        return 0
    ops = []
    for doc in docs:
        d = doc.model_dump() if hasattr(doc, "model_dump") else dict(doc)
        ops.append({"index": {"_index": index, "_id": d["id"]}})
        ops.append(d)
    result = es.bulk(body=ops, refresh=True)
    errors = [item for item in result["items"] if "error" in item.get("index", {})]
    if errors:
        log.warning("Bulk errors in %s: %s", index, errors[:3])
    return len(docs) - len(errors)


# ──────────────────────────────────────────────────────────────────────────────
# Model builders
# ──────────────────────────────────────────────────────────────────────────────

def _build_device(parsed: dict) -> Device:
    hostname = parsed["hostname"]
    return Device(
        id=_id(f"device.{hostname}"),
        name=hostname,
        hostname=hostname,
        management_ip=_mgmt_ip(parsed["interfaces"]) or "0.0.0.0",
        vendor=parsed["vendor"],
        model=parsed.get("model") or "",
        os=parsed["os"],
        device_type=parsed.get("device_type", "switch"),
        tags=[parsed["vendor"].lower(), parsed["os"].lower()],
        pop=parsed.get("pop"),
        role=parsed.get("role"),
    )


def _dispatch_parser(text: str, source_path: Path, vendor_hint: str = "") -> dict:
    """
    Auto-detect config format and parse.  vendor_hint overrides auto-detection
    when the user explicitly selects a vendor (e.g. from the upload UI).
    Always enriches the result with POP/role via pop_detector.
    """
    hint = vendor_hint.lower()
    if hint in ("juniper", "junos"):
        parsed = parse_junos_config(text, source_path)
    elif hint in ("huawei", "vrp"):
        parsed = parse_huawei_config(text, source_path)
    elif hint in ("dell", "os10"):
        parsed = parse_dell_os10_config(text, source_path)
    elif hint in ("hpe", "aruba", "aruba-cx", "arubacx"):
        parsed = parse_hpe_aruba_cx_config(text, source_path)
    elif hint in ("cisco", "ios"):
        parsed = parse_ios_running_config(text, source_path)
    else:
        # Auto-detect — order matters: most distinctive signatures first
        if is_junos_config(text):
            parsed = parse_junos_config(text, source_path)
        elif is_huawei_config(text):
            parsed = parse_huawei_config(text, source_path)
        elif is_dell_os10(text):
            parsed = parse_dell_os10_config(text, source_path)
        elif is_hpe_aruba_cx(text):
            parsed = parse_hpe_aruba_cx_config(text, source_path)
        else:
            parsed = parse_ios_running_config(text, source_path)
    enrich_parsed(parsed)
    return parsed


def _mgmt_ip(interfaces: list[dict]) -> str:
    """Best-effort management IP: prefer Management / Loopback0, else first IP."""
    candidates = []
    for iface in interfaces:
        ip = iface.get("ip_address")
        if not ip:
            continue
        name_low = iface["name"].lower()
        if "management" in name_low or "mgmt" in name_low:
            return ip
        if "loopback0" == name_low:
            return ip
        candidates.append(ip)
    return candidates[0] if candidates else ""


def _build_interfaces(parsed: dict, device: Device) -> list[Interface]:
    ifaces: list[Interface] = []
    for iface in parsed["interfaces"]:
        name = iface["name"]
        ifaces.append(Interface(
            id=_id(f"iface.{device.name}.{name}"),
            device_id=device.id,
            device_name=device.name,
            name=name,
            description=iface.get("description"),
            ip_address=iface.get("ip_address"),
            prefix_length=iface.get("prefix_length"),
            admin_status=iface.get("admin_status", "up"),
            oper_status="up" if iface.get("admin_status", "up") == "up" else "down",
            vlan_mode=iface.get("vlan_mode") or "none",
            vlan_id=iface.get("vlan_id"),
            trunk_vlans=iface.get("trunk_vlans", []),
            native_vlan=iface.get("native_vlan"),
            acl_in=iface.get("acl_in"),
            acl_out=iface.get("acl_out"),
        ))
    return ifaces


def _build_acls(parsed: dict, device: Device) -> list[Acl]:
    acls: list[Acl] = []
    for acl_data in parsed.get("acls", []):
        rules = [
            AclRule(
                sequence=r["sequence"],
                action=r["action"],
                protocol=r["protocol"],
                src_network=r.get("src_network", "any"),
                dst_network=r.get("dst_network", "any"),
                dst_port=r.get("dst_port"),
                dst_port_range=r.get("dst_port_range"),
                established=r.get("established", False),
            )
            for r in acl_data["rules"]
        ]
        acls.append(Acl(
            id=_id(f"acl.{device.name}.{acl_data['name']}"),
            device_id=device.id,
            device_name=device.name,
            name=acl_data["name"],
            acl_type=acl_data.get("acl_type", "extended"),
            rules=rules,
        ))
    return acls


# ──────────────────────────────────────────────────────────────────────────────
# Cross-linking: build Connection records from BGP peer table
# ──────────────────────────────────────────────────────────────────────────────

def build_connections(
    bgp_map: dict[str, list[dict]],   # device_name → [{peer_ip, local_as, remote_as}]
    ip_to_device: dict[str, str],     # ip_address → device_name
    interface_map: dict[str, dict],   # (device_name, ip) → Interface id/name
) -> list[Connection]:
    """
    For each BGP peer, try to resolve the peer IP to a known device and
    create a Connection record. Deduplicates A↔B pairs.
    """
    connections: list[Connection] = []
    seen: set[frozenset] = set()

    for src_device, peers in bgp_map.items():
        for peer in peers:
            peer_ip = peer["peer_ip"]
            dst_device = ip_to_device.get(peer_ip)
            if dst_device is None:
                log.debug("Skipping BGP peer %s from %s — not a known device", peer_ip, src_device)
                continue  # external peer not in dataset; skip to avoid dangling edges

            pair = frozenset([src_device, dst_device])
            if pair in seen:
                continue
            seen.add(pair)

            local_as = peer["local_as"]
            remote_as = peer["remote_as"]

            # Find the interface on src that owns the BGP session (optional — best effort)
            src_iface = interface_map.get(src_device, {}).get("name") or "bgp"
            dst_iface = interface_map.get(dst_device, {}).get("name") or "bgp"

            # Determine if this is iBGP or eBGP
            ibgp = local_as == remote_as

            # Check whether either side has ACLs on the interfaces involved
            has_acl = bool(
                interface_map.get(src_device, {}).get("acl_out") or
                interface_map.get(dst_device, {}).get("acl_in")
            )

            connections.append(Connection(
                id=_id(f"conn.bgp.{src_device}.{dst_device}"),
                src_device_id=_id(f"device.{src_device}"),
                src_device_name=src_device,
                src_interface=f"BGP AS{local_as}",
                dst_device_id=_id(f"device.{dst_device}"),
                dst_device_name=dst_device,
                dst_interface=f"BGP AS{remote_as}",
                link_type="bgp",
                status="up",
                has_acl=has_acl,
                has_firewall=False,
                description=f"{'iBGP' if ibgp else 'eBGP'} AS{local_as}↔AS{remote_as}",
            ))

    return connections


# ──────────────────────────────────────────────────────────────────────────────
# Cross-linking: build Connection records from shared /30 subnets (P2P links)
# ──────────────────────────────────────────────────────────────────────────────

def build_subnet_connections(
    all_ifaces: list[dict],   # [{device_name, iface_name, ip_address, prefix_length, acl_in, acl_out, admin_status}]
    seen: set[frozenset],
) -> list[Connection]:
    """
    Detect point-to-point links: when exactly two interfaces on *different*
    devices share the same /30 (or /31) subnet, they are directly connected.
    Also catches /29 subnets with only two populated addresses.
    """
    from collections import defaultdict

    # Group by network address (computed from ip + prefix_length)
    net_to_ifaces: dict[str, list[dict]] = defaultdict(list)
    for iface in all_ifaces:
        ip   = iface.get("ip_address")
        pfx  = iface.get("prefix_length")
        if not ip or pfx is None:
            continue
        try:
            net = str(ipaddress.ip_interface(f"{ip}/{pfx}").network)
            net_to_ifaces[net].append(iface)
        except ValueError:
            continue

    connections: list[Connection] = []
    for net, ifaces in net_to_ifaces.items():
        # Collapse to unique devices (keep first iface per device for this net)
        by_device: dict[str, dict] = {}
        for iface in ifaces:
            dev = iface["device_name"]
            if dev not in by_device:
                by_device[dev] = iface

        if len(by_device) != 2:
            continue  # not a P2P link (subnet shared by more/fewer devices)

        net_obj = ipaddress.ip_network(net)
        if net_obj.prefixlen < 29:
            continue  # too broad to be a P2P link

        (src_dev, src_iface), (dst_dev, dst_iface) = list(by_device.items())

        pair = frozenset([src_dev, dst_dev])
        if pair in seen:
            continue
        seen.add(pair)

        has_acl = bool(src_iface.get("acl_out") or dst_iface.get("acl_in") or
                       src_iface.get("acl_in")  or dst_iface.get("acl_out"))
        status  = "up" if (src_iface.get("admin_status", "up") == "up" and
                            dst_iface.get("admin_status", "up") == "up") else "down"

        connections.append(Connection(
            id=_id(f"conn.subnet.{src_dev}.{dst_dev}"),
            src_device_id=_id(f"device.{src_dev}"),
            src_device_name=src_dev,
            src_interface=src_iface["iface_name"],
            dst_device_id=_id(f"device.{dst_dev}"),
            dst_device_name=dst_dev,
            dst_interface=dst_iface["iface_name"],
            link_type="routed",
            status=status,
            has_acl=has_acl,
            has_firewall=False,
            description=f"P2P link {net}",
        ))

    return connections


# ──────────────────────────────────────────────────────────────────────────────
# Cross-linking: build Connection records from interface descriptions
# ──────────────────────────────────────────────────────────────────────────────

def build_description_connections(
    all_ifaces: list[dict],   # [{device_name, iface_name, description, vlan_mode, admin_status, ...}]
    known_devices: set[str],  # set of all hostname strings in the dataset
    seen: set[frozenset],
) -> list[Connection]:
    """
    Detect L2 trunk/uplink connections by scanning interface descriptions for
    peer device hostnames.  Pattern: any word in the description that exactly
    matches a known device hostname triggers a link.
    """
    connections: list[Connection] = []

    for iface in all_ifaces:
        desc = (iface.get("description") or "").lower()
        if not desc:
            continue
        src_dev = iface["device_name"]

        for candidate in known_devices:
            if candidate == src_dev:
                continue
            if candidate.lower() in desc:
                pair = frozenset([src_dev, candidate])
                if pair in seen:
                    continue
                seen.add(pair)

                is_trunk = iface.get("vlan_mode") == "trunk"
                status   = "up" if iface.get("admin_status", "up") == "up" else "down"

                connections.append(Connection(
                    id=_id(f"conn.desc.{src_dev}.{candidate}"),
                    src_device_id=_id(f"device.{src_dev}"),
                    src_device_name=src_dev,
                    src_interface=iface["iface_name"],
                    dst_device_id=_id(f"device.{candidate}"),
                    dst_device_name=candidate,
                    dst_interface="uplink",
                    link_type="trunk" if is_trunk else "access",
                    status=status,
                    has_acl=False,
                    has_firewall=False,
                    description=f"{'Trunk' if is_trunk else 'Link'} via description match",
                ))

    return connections


# ──────────────────────────────────────────────────────────────────────────────
# SSE helpers
# ──────────────────────────────────────────────────────────────────────────────

def _sse(event_type: str, data: dict) -> str:
    payload = json.dumps({"type": event_type, **data})
    return f"data: {payload}\n\n"


# ──────────────────────────────────────────────────────────────────────────────
# Endpoint
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/stream")
async def ingest_stream(folder_path: str, wipe: bool = False):
    """
    SSE stream: scan *folder_path* for network config files, parse them,
    index results into Elasticsearch, emit per-file progress events.
    """
    async def generate() -> AsyncIterator[str]:
        yield _sse("start", {"folder": folder_path, "wipe": wipe})

        folder = Path(folder_path)
        if not folder.exists() or not folder.is_dir():
            yield _sse("error", {"message": f"Folder not found: {folder_path}"})
            return

        # ── 1. Scan ──────────────────────────────────────────────────────────
        try:
            config_files = scan_folder(folder)
        except Exception as exc:
            yield _sse("error", {"message": f"Scan failed: {exc}"})
            return

        yield _sse("scan", {"found": len(config_files), "folder": str(folder)})

        if not config_files:
            yield _sse("done", {
                "summary": {"devices": 0, "interfaces": 0, "connections": 0, "acls": 0, "errors": 0}
            })
            return

        # ── 2. Optionally wipe indices ────────────────────────────────────────
        es = get_es()
        if wipe:
            try:
                wipe_indices()
                yield _sse("wipe", {"message": "Indices wiped and recreated"})
            except Exception as exc:
                yield _sse("error", {"message": f"Wipe failed: {exc}"})
                return
        else:
            bootstrap_indices()

        # ── 3. Parse each file ───────────────────────────────────────────────
        all_devices: list[Device] = []
        all_interfaces: list[Interface] = []
        all_acls: list[Acl] = []

        # For connection cross-linking
        bgp_map: dict[str, list[dict]] = {}       # device_name → [{peer_ip,local_as,remote_as}]
        ip_to_device: dict[str, str] = {}         # ip → device_name
        iface_by_device: dict[str, dict] = {}     # device_name → first non-loopback iface dict
        all_parsed_ifaces: list[dict] = []        # flat list for subnet/desc cross-linking

        error_count = 0

        for path in config_files:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
                parsed = _dispatch_parser(text, path)
                hostname = parsed["hostname"]

                device = _build_device(parsed)
                interfaces = _build_interfaces(parsed, device)
                acls = _build_acls(parsed, device)

                # Index immediately
                _bulk_index(es, IDX_DEVICES, [device])
                _bulk_index(es, IDX_INTERFACES, interfaces)
                _bulk_index(es, IDX_ACLS, acls)

                all_devices.append(device)
                all_interfaces.extend(interfaces)
                all_acls.extend(acls)

                # Collect data for cross-linking
                if parsed.get("bgp_peers"):
                    bgp_map[hostname] = parsed["bgp_peers"]

                for iface in parsed["interfaces"]:
                    ip = iface.get("ip_address")
                    if ip:
                        ip_to_device[ip] = hostname
                        # Store first routed interface per device for connection metadata
                        if hostname not in iface_by_device and "loopback" not in iface["name"].lower():
                            iface_by_device[hostname] = iface

                    # Collect for subnet + description cross-linking
                    all_parsed_ifaces.append({
                        "device_name":   hostname,
                        "iface_name":    iface["name"],
                        "ip_address":    iface.get("ip_address"),
                        "prefix_length": iface.get("prefix_length"),
                        "description":   iface.get("description"),
                        "vlan_mode":     iface.get("vlan_mode", "none"),
                        "admin_status":  iface.get("admin_status", "up"),
                        "acl_in":        iface.get("acl_in"),
                        "acl_out":       iface.get("acl_out"),
                    })

                yield _sse("file", {
                    "name": path.name,
                    "path": str(path.relative_to(folder)),
                    "status": "ok",
                    "hostname": hostname,
                    "vendor": parsed["vendor"],
                    "os": parsed["os"],
                    "interfaces": len(interfaces),
                    "acls": len(acls),
                    "bgp_peers": len(parsed.get("bgp_peers", [])),
                })

            except Exception as exc:
                error_count += 1
                log.exception("Failed to parse %s", path)
                yield _sse("file", {
                    "name": path.name,
                    "path": str(path),
                    "status": "error",
                    "error": str(exc),
                    "hostname": "",
                    "interfaces": 0,
                    "acls": 0,
                    "bgp_peers": 0,
                })

        # ── 4. Build and index connections ───────────────────────────────────
        known_devices = {d.name for d in all_devices}
        seen_pairs: set[frozenset] = set()

        # Pass 1: BGP peer connections (routers, firewalls)
        connections  = build_connections(bgp_map, ip_to_device, iface_by_device)
        for c in connections:
            seen_pairs.add(frozenset([c.src_device_name, c.dst_device_name]))

        # Pass 2: Shared /30–/29 subnet → direct P2P links (routed uplinks)
        connections += build_subnet_connections(all_parsed_ifaces, seen_pairs)

        # Pass 3: Interface description hostname matching → trunk / L2 links
        connections += build_description_connections(all_parsed_ifaces, known_devices, seen_pairs)

        if connections:
            _bulk_index(es, IDX_CONNECTIONS, connections)
        yield _sse("link", {"connections": len(connections)})

        # ── 5. Done ──────────────────────────────────────────────────────────
        yield _sse("done", {
            "summary": {
                "devices": len(all_devices),
                "interfaces": len(all_interfaces),
                "connections": len(connections),
                "acls": len(all_acls),
                "errors": error_count,
            }
        })

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ──────────────────────────────────────────────────────────────────────────────
# Single-file upload endpoint
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/upload")
async def ingest_upload(
    file: UploadFile = File(...),
    vendor: Optional[str] = Form(None),
):
    """
    Upload a single network config file and index it into Elasticsearch.

    Form fields:
      file   — the config file
      vendor — optional hint: "cisco" | "juniper" | "huawei" (auto-detected if omitted)

    Returns a JSON summary including detected hostname, vendor, POP, role,
    and counts of indexed interfaces and ACLs.
    """
    content = await file.read()
    try:
        text = content.decode("utf-8", errors="replace")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Cannot decode file: {exc}")

    source_path = Path(file.filename or "upload.txt")

    try:
        parsed = _dispatch_parser(text, source_path, vendor_hint=vendor or "")
    except Exception as exc:
        log.exception("Failed to parse uploaded file %s", file.filename)
        raise HTTPException(status_code=422, detail=f"Parse error: {exc}")

    hostname = parsed["hostname"]

    # Build model objects
    device = _build_device(parsed)
    interfaces = _build_interfaces(parsed, device)
    acls = _build_acls(parsed, device)

    # Index into Elasticsearch
    es = get_es()
    bootstrap_indices()
    _bulk_index(es, IDX_DEVICES, [device])
    _bulk_index(es, IDX_INTERFACES, interfaces)
    _bulk_index(es, IDX_ACLS, acls)

    return {
        "status": "ok",
        "hostname": hostname,
        "vendor": parsed["vendor"],
        "os": parsed["os"],
        "device_type": parsed.get("device_type", "switch"),
        "pop": parsed.get("pop"),
        "role": parsed.get("role"),
        "interfaces": len(interfaces),
        "acls": len(acls),
        "bgp_peers": len(parsed.get("bgp_peers", [])),
    }


# ──────────────────────────────────────────────────────────────────────────────
# POP management endpoints
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/pops")
def list_pops():
    """Return the sorted list of unique POP codes currently in the device index."""
    es = get_es()
    try:
        resp = es.search(
            index=IDX_DEVICES,
            body={
                "size": 0,
                "aggs": {
                    "pops": {
                        "terms": {"field": "pop", "size": 200, "missing": "__none__"}
                    }
                },
            },
        )
        buckets = resp["aggregations"]["pops"]["buckets"]
        pops = sorted(
            b["key"] for b in buckets if b["key"] != "__none__"
        )
        return pops
    except Exception as exc:
        log.warning("Failed to list POPs: %s", exc)
        return []


@router.post("/pops/assign")
def assign_pop(device_name: str, pop: str):
    """
    Assign or reassign the POP for a single device.
    Updates the device document in-place (no re-ingest needed).
    """
    es = get_es()
    device_id = _id(f"device.{device_name}")
    try:
        es.update(
            index=IDX_DEVICES,
            id=device_id,
            body={"doc": {"pop": pop.upper()}},
            refresh=True,
        )
        return {"status": "ok", "device": device_name, "pop": pop.upper()}
    except Exception as exc:
        log.error("Failed to assign POP %s to %s: %s", pop, device_name, exc)
        raise HTTPException(status_code=500, detail=str(exc))

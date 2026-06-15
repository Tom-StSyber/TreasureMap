"""
parsers/huawei.py — Huawei VRP (Versatile Routing Platform) configuration parser.

Supports VRP V2/V5/V8 running configurations.

Detection heuristic
-------------------
  File contains "sysname " directive AND at least one "interface " block.

Supported constructs
--------------------
  sysname <hostname>
  interface <name>
    description <text>
    ip address <ip> <mask>       (dotted-decimal mask)
    undo shutdown               (interface is admin-up)
    shutdown                    (interface is admin-down)
    port link-type access|trunk
    port default vlan <N>       (access VLAN)
    port trunk allow-pass vlan <N> [to <M>] [<N> ...]
    ip access-group <name> inbound|outbound
    traffic-filter inbound|outbound acl <name|number>
"""
from __future__ import annotations

import ipaddress
import re
from pathlib import Path
from typing import Optional


# ──────────────────────────────────────────────────────────────────────────────
# Format detection
# ──────────────────────────────────────────────────────────────────────────────

def is_huawei_config(text: str) -> bool:
    has_sysname = bool(re.search(r"^\s*sysname\s+\S+", text, re.MULTILINE))
    has_iface = bool(re.search(r"^\s*interface\s+\S+", text, re.MULTILINE))
    return has_sysname and has_iface


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _mask_to_prefix(mask: str) -> Optional[int]:
    try:
        return ipaddress.IPv4Network(f"0.0.0.0/{mask}", strict=False).prefixlen
    except ValueError:
        return None


def _empty_iface(name: str) -> dict:
    return {
        "name": name,
        "description": None,
        "ip_address": None,
        "prefix_length": None,
        "admin_status": "up",   # Huawei interfaces are up by default
        "vlan_mode": "none",
        "vlan_id": None,
        "trunk_vlans": [],
        "native_vlan": None,
        "acl_in": None,
        "acl_out": None,
    }


def _parse_trunk_vlan_list(raw: str) -> list[int]:
    """
    Parse Huawei trunk vlan list: "10 to 20 30 40 to 50"
    Returns list of VLAN IDs.
    """
    vlans: list[int] = []
    tokens = raw.split()
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.lower() == "to" and i > 0 and i + 1 < len(tokens):
            # range: prev_token to next_token
            try:
                lo = int(tokens[i - 1])
                hi = int(tokens[i + 1])
                # Remove the last-added lo if already added individually
                if vlans and vlans[-1] == lo:
                    vlans.pop()
                vlans.extend(range(lo, hi + 1))
                i += 2
            except (ValueError, IndexError):
                i += 1
        elif tok.isdigit():
            vlans.append(int(tok))
            i += 1
        elif "-" in tok:
            parts = tok.split("-")
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                vlans.extend(range(int(parts[0]), int(parts[1]) + 1))
            i += 1
        else:
            i += 1
    return vlans


# ──────────────────────────────────────────────────────────────────────────────
# Main parser
# ──────────────────────────────────────────────────────────────────────────────

def parse_huawei_config(text: str, source_path: Path) -> dict:
    """
    Parse a Huawei VRP running configuration.

    Returns the same schema as parsers.ios_config.parse_ios_running_config:
    {hostname, vendor, os, device_type, version, model, interfaces, acls, bgp_peers, source_file}
    """
    result = {
        "hostname": source_path.stem,
        "vendor": "Huawei",
        "os": "VRP",
        "device_type": "switch",
        "version": "",
        "model": "",
        "interfaces": [],
        "acls": [],
        "bgp_peers": [],
        "source_file": source_path.name,
    }

    lines = text.splitlines()
    n = len(lines)
    i = 0

    bgp_peers: list[dict] = []
    local_as: Optional[int] = None

    while i < n:
        raw = lines[i]
        line = raw.strip()

        # ── sysname ───────────────────────────────────────────────────────────
        m = re.match(r"^sysname\s+(\S+)", line)
        if m:
            result["hostname"] = m.group(1)
            i += 1
            continue

        # ── version ───────────────────────────────────────────────────────────
        m = re.match(r"^(?:Huawei Versatile Routing Platform )?Software.*Version\s+([\w.()]+)", line, re.IGNORECASE)
        if m:
            result["version"] = m.group(1)
            i += 1
            continue

        m = re.match(r"^version\s+([\w.()]+)", line, re.IGNORECASE)
        if m:
            result["version"] = m.group(1)
            i += 1
            continue

        # ── interface block ───────────────────────────────────────────────────
        iface_m = re.match(r"^interface\s+(\S+)", line)
        if iface_m:
            iface_name = iface_m.group(1)
            iface = _empty_iface(iface_name)
            i += 1
            while i < n:
                sub_raw = lines[i]
                # Interface block ends when next top-level statement begins
                # (non-indented line that's not blank)
                if sub_raw and not sub_raw[0].isspace():
                    break
                sub = sub_raw.strip()

                if not sub or sub.startswith("#"):
                    i += 1
                    continue

                # description
                desc_m = re.match(r"^description\s+(.*)", sub)
                if desc_m:
                    iface["description"] = desc_m.group(1).strip()
                    i += 1
                    continue

                # ip address <ip> <mask>
                ip_m = re.match(r"^ip address\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)", sub)
                if ip_m:
                    iface["ip_address"] = ip_m.group(1)
                    pfx = _mask_to_prefix(ip_m.group(2))
                    iface["prefix_length"] = pfx
                    iface["vlan_mode"] = "routed"
                    i += 1
                    continue

                # shutdown / undo shutdown
                if sub == "shutdown":
                    iface["admin_status"] = "disabled"
                    i += 1
                    continue
                if sub == "undo shutdown":
                    iface["admin_status"] = "up"
                    i += 1
                    continue

                # port link-type access|trunk
                link_m = re.match(r"^port link-type\s+(access|trunk|hybrid)", sub)
                if link_m:
                    mode = link_m.group(1)
                    if mode in ("access", "trunk"):
                        iface["vlan_mode"] = mode
                    i += 1
                    continue

                # port default vlan N  (access)
                pvlan_m = re.match(r"^port default vlan\s+(\d+)", sub)
                if pvlan_m:
                    iface["vlan_id"] = int(pvlan_m.group(1))
                    if iface["vlan_mode"] == "none":
                        iface["vlan_mode"] = "access"
                    i += 1
                    continue

                # port trunk allow-pass vlan <list>
                trunk_m = re.match(r"^port trunk allow-pass vlan\s+(.+)", sub)
                if trunk_m:
                    vlans = _parse_trunk_vlan_list(trunk_m.group(1))
                    iface["trunk_vlans"].extend(vlans)
                    if iface["vlan_mode"] == "none":
                        iface["vlan_mode"] = "trunk"
                    i += 1
                    continue

                # port trunk pvid vlan N  (native VLAN on trunk)
                native_m = re.match(r"^port trunk pvid vlan\s+(\d+)", sub)
                if native_m:
                    iface["native_vlan"] = int(native_m.group(1))
                    i += 1
                    continue

                # ACL / traffic filter
                # traffic-filter inbound acl <name|num>
                tf_m = re.match(r"^traffic-filter\s+(inbound|outbound)\s+acl\s+(\S+)", sub)
                if tf_m:
                    direction = tf_m.group(1)
                    acl_name = tf_m.group(2)
                    if direction == "inbound":
                        iface["acl_in"] = acl_name
                    else:
                        iface["acl_out"] = acl_name
                    i += 1
                    continue

                # ip access-group <name> inbound|outbound
                ag_m = re.match(r"^ip access-group\s+(\S+)\s+(inbound|outbound)", sub)
                if ag_m:
                    acl_name = ag_m.group(1)
                    direction = ag_m.group(2)
                    if direction == "inbound":
                        iface["acl_in"] = acl_name
                    else:
                        iface["acl_out"] = acl_name
                    i += 1
                    continue

                i += 1

            result["interfaces"].append(iface)
            continue

        # ── BGP ───────────────────────────────────────────────────────────────
        bgp_m = re.match(r"^bgp\s+(\d+)", line)
        if bgp_m:
            local_as = int(bgp_m.group(1))
            i += 1
            while i < n:
                sub_raw = lines[i]
                if sub_raw and not sub_raw[0].isspace():
                    break
                sub = sub_raw.strip()
                # peer <ip> as-number <N>
                peer_m = re.match(r"^peer\s+(\d+\.\d+\.\d+\.\d+)\s+as-number\s+(\d+)", sub)
                if peer_m:
                    bgp_peers.append({
                        "peer_ip": peer_m.group(1),
                        "local_as": local_as,
                        "remote_as": int(peer_m.group(2)),
                    })
                i += 1
            continue

        i += 1

    # Determine device type
    has_routed = any(i.get("ip_address") for i in result["interfaces"]
                     if not re.match(r"^(LoopBack|NULL)", i["name"], re.IGNORECASE))
    has_switch = any(i.get("vlan_mode") in ("access", "trunk") for i in result["interfaces"])
    has_bgp = bool(bgp_peers)

    if (has_routed or has_bgp) and not has_switch:
        result["device_type"] = "router"
    elif has_switch:
        result["device_type"] = "switch"

    result["bgp_peers"] = bgp_peers
    return result

"""
parsers/juniper.py — Juniper JunOS configuration parser.

Supports two input formats:
  1. Hierarchical (stanza-based):
       system { host-name eqx-nyc-pe-01; }
       interfaces { ge-0/0/0 { description "uplink"; unit 0 { family inet { address 10.0.0.1/30; } } } }
  2. Set-format (one directive per line):
       set system host-name eqx-nyc-sw-01
       set interfaces ge-0/0/0 unit 0 family inet address 10.0.0.1/30

Detection heuristic
-------------------
  Hierarchical: contains "system {" or "interfaces {" with stanza-style braces
  Set-format:   majority of non-blank lines start with "set "
"""
from __future__ import annotations

import ipaddress
import re
from pathlib import Path
from typing import Optional


# ──────────────────────────────────────────────────────────────────────────────
# Format detection
# ──────────────────────────────────────────────────────────────────────────────

def is_junos_config(text: str) -> bool:
    """Return True if text looks like a JunOS config (either format)."""
    return is_junos_hierarchical(text) or is_junos_set(text)


def is_junos_hierarchical(text: str) -> bool:
    has_system = bool(re.search(r"^\s*system\s*\{", text, re.MULTILINE))
    has_ifaces = bool(re.search(r"^\s*interfaces\s*\{", text, re.MULTILINE))
    has_version = bool(re.search(r"^\s*version\s+\d+\.\d+[A-Z]\d+", text, re.MULTILINE))
    return (has_system or has_version) and has_ifaces


def is_junos_set(text: str) -> bool:
    non_blank = [l for l in text.splitlines() if l.strip() and not l.strip().startswith("#")]
    if not non_blank:
        return False
    set_lines = sum(1 for l in non_blank if l.strip().startswith("set "))
    return set_lines >= max(3, len(non_blank) * 0.6)


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
        "admin_status": "up",
        "vlan_mode": "none",
        "vlan_id": None,
        "trunk_vlans": [],
        "native_vlan": None,
        "acl_in": None,
        "acl_out": None,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Hierarchical parser
# ──────────────────────────────────────────────────────────────────────────────

def _strip_semicolon(s: str) -> str:
    return s.rstrip(";").strip()


def _parse_hierarchical(text: str, source_path: Path) -> dict:
    """Parse a JunOS hierarchical (stanza-based) configuration."""
    result = {
        "hostname": source_path.stem,
        "vendor": "Juniper",
        "os": "JunOS",
        "device_type": "router",
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

    # We need to parse the top-level stanzas.
    # Simple single-pass approach: track brace depth.
    # Top-level stanzas: system {}, interfaces {}, routing-options {}, protocols {}

    def skip_to_close(start_i: int) -> int:
        """Return the index after the matching closing brace for block starting at start_i."""
        depth = 0
        j = start_i
        while j < n:
            for ch in lines[j]:
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        return j + 1
            j += 1
        return n

    def collect_block(start_i: int) -> list[str]:
        """Collect lines of a block (including nested), returns lines between outer braces."""
        depth = 0
        collected = []
        j = start_i
        while j < n:
            line = lines[j]
            for ch in line:
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
            if depth > 0 or (depth == 0 and j == start_i):
                collected.append(line)
            elif depth == 0:
                collected.append(line)
                break
            j += 1
        return collected

    while i < n:
        line = lines[i].strip()

        # version
        m = re.match(r"^version\s+([\d.A-Z\-]+)", line)
        if m:
            result["version"] = m.group(1)
            i += 1
            continue

        # system { ... }
        if re.match(r"^system\s*\{", line):
            # parse system block for hostname and model
            j = i + 1
            while j < n:
                sub = lines[j].strip()
                if sub == "}":
                    break
                if re.match(r"^host-name\s+", sub):
                    result["hostname"] = _strip_semicolon(sub.split(None, 1)[1])
                j += 1
            i = skip_to_close(i)
            continue

        # interfaces { ... }
        if re.match(r"^interfaces\s*\{", line):
            i = _parse_hierarchical_interfaces(lines, i + 1, n, result)
            continue

        # routing-options { ... } for static routes / BGP info
        if re.match(r"^routing-options\s*\{", line):
            i = skip_to_close(i)
            continue

        # protocols { bgp { ... } }
        if re.match(r"^protocols\s*\{", line):
            i = _parse_protocols_block(lines, i + 1, n, result)
            continue

        i += 1

    return result


def _parse_hierarchical_interfaces(lines: list[str], start: int, n: int, result: dict) -> int:
    """Parse the interfaces { ... } block. Returns next line index after closing }."""
    i = start
    depth = 1  # we entered after the opening {

    while i < n and depth > 0:
        line = lines[i]
        stripped = line.strip()

        if "{" in stripped:
            depth += stripped.count("{")
        if "}" in stripped:
            depth -= stripped.count("}")
            if depth <= 0:
                return i + 1

        # Interface definition: one level inside interfaces {} (depth == 2 BEFORE the { is counted)
        # We check depth == 2 (was 1, now 2 after counting the opening {)
        m = re.match(r"^\s{0,4}(\S+)\s*\{", line)  # e.g. "    ge-0/0/0 {"
        if m and depth == 2:
            iface_name = m.group(1)
            # Skip management interfaces that aren't topology-relevant
            if not re.match(r"^(fxp\d+|em\d+)$", iface_name):
                iface = _empty_iface(iface_name)
                i = _parse_one_iface(lines, i + 1, n, iface)
                result["interfaces"].append(iface)
                # _parse_one_iface consumed everything including the closing },
                # so reset depth to 1 (back inside interfaces {})
                depth = 1
                continue

        i += 1

    return i


def _parse_one_iface(lines: list[str], start: int, n: int, iface: dict) -> int:
    """Parse one interface block. Returns next line index after closing }."""
    i = start
    depth = 1

    while i < n and depth > 0:
        line = lines[i]
        stripped = line.strip()

        open_count = stripped.count("{")
        close_count = stripped.count("}")
        depth += open_count - close_count

        if depth <= 0:
            return i + 1

        # Description
        m = re.match(r"^\s*description\s+\"?(.+?)\"?\s*;", line)
        if m:
            iface["description"] = m.group(1).strip()

        # Disable (JunOS uses 'disable;' to admin-down an interface)
        if stripped == "disable;":
            iface["admin_status"] = "disabled"

        # Unit 0 — look for family inet address
        addr_m = re.match(r"^\s*address\s+(\d+\.\d+\.\d+\.\d+)/(\d+)\s*;", line)
        if addr_m and iface["ip_address"] is None:
            iface["ip_address"] = addr_m.group(1)
            iface["prefix_length"] = int(addr_m.group(2))

        # Ethernet-switching: interface-mode
        mode_m = re.match(r"^\s*interface-mode\s+(trunk|access)\s*;", line)
        if mode_m:
            iface["vlan_mode"] = mode_m.group(1)

        # Ethernet-switching: vlan members
        vlan_m = re.match(r"^\s*members\s+(.+?)\s*;", line)
        if vlan_m:
            raw = vlan_m.group(1).strip()
            # Could be VLAN name, range like "10-20", or list
            vlans = _parse_junos_vlan_members(raw)
            if vlans:
                if iface["vlan_mode"] == "access" and len(vlans) == 1:
                    iface["vlan_id"] = vlans[0]
                else:
                    # Retain trunk mode; don't downgrade to access
                    if iface["vlan_mode"] != "trunk":
                        iface["vlan_mode"] = "trunk"
                    iface["trunk_vlans"].extend(vlans)

        i += 1

    return i


def _parse_protocols_block(lines: list[str], start: int, n: int, result: dict) -> int:
    """Parse protocols { bgp { ... } } for BGP peer data."""
    i = start
    depth = 1
    local_as = None

    while i < n and depth > 0:
        line = lines[i]
        stripped = line.strip()

        open_count = stripped.count("{")
        close_count = stripped.count("}")
        depth += open_count - close_count

        if depth <= 0:
            return i + 1

        # local-as
        m = re.match(r"^\s*local-as\s+(\d+)\s*;", line)
        if m:
            local_as = int(m.group(1))

        # neighbor <ip> { remote-as N; }
        nb_m = re.match(r"^\s*neighbor\s+(\d+\.\d+\.\d+\.\d+)\s*\{", line)
        if nb_m:
            peer_ip = nb_m.group(1)
            # Look ahead for remote-as in the neighbor block
            j = i + 1
            peer_depth = 1
            remote_as = None
            while j < n and peer_depth > 0:
                sub = lines[j].strip()
                peer_depth += sub.count("{") - sub.count("}")
                ra_m = re.match(r"^peer-as\s+(\d+)\s*;", sub)
                if not ra_m:
                    ra_m = re.match(r"^remote-as\s+(\d+)\s*;", sub)
                if ra_m:
                    remote_as = int(ra_m.group(1))
                j += 1
            if peer_ip and remote_as and local_as:
                result["bgp_peers"].append({
                    "peer_ip": peer_ip,
                    "local_as": local_as,
                    "remote_as": remote_as,
                })

        i += 1

    return i


def _parse_junos_vlan_members(raw: str) -> list[int]:
    """Parse JunOS vlan members: numeric IDs, ranges '10-20', or skip named VLANs."""
    vlans = []
    for tok in re.split(r"[\s,]+", raw):
        tok = tok.strip()
        if not tok:
            continue
        range_m = re.match(r"^(\d+)-(\d+)$", tok)
        if range_m:
            lo, hi = int(range_m.group(1)), int(range_m.group(2))
            vlans.extend(range(lo, hi + 1))
        elif tok.isdigit():
            vlans.append(int(tok))
        # else: named VLAN — skip numeric conversion
    return vlans


# ──────────────────────────────────────────────────────────────────────────────
# Set-format parser
# ──────────────────────────────────────────────────────────────────────────────

def _parse_set(text: str, source_path: Path) -> dict:
    """Parse a JunOS set-format configuration."""
    result = {
        "hostname": source_path.stem,
        "vendor": "Juniper",
        "os": "JunOS",
        "device_type": "switch",
        "version": "",
        "model": "",
        "interfaces": [],
        "acls": [],
        "bgp_peers": [],
        "source_file": source_path.name,
    }

    # Accumulate interface data keyed by physical interface name
    iface_map: dict[str, dict] = {}  # e.g. "ge-0/0/0" → {...}
    local_as: Optional[int] = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("set "):
            continue
        # Remove the leading "set "
        stmt = line[4:]

        # hostname
        m = re.match(r"^system host-name\s+(\S+)", stmt)
        if m:
            result["hostname"] = m.group(1)
            continue

        # interfaces
        m = re.match(r"^interfaces\s+(\S+)\s+(.*)", stmt)
        if m:
            iface_name = m.group(1)
            rest = m.group(2).strip()

            # Skip unit-based subinterface naming — we track by physical name
            # but strip "unit N" prefix from the rest
            rest = re.sub(r"^unit\s+\d+\s+", "", rest)

            if iface_name not in iface_map:
                iface_map[iface_name] = _empty_iface(iface_name)

            iface = iface_map[iface_name]

            # description
            desc_m = re.match(r"^description\s+\"?(.+?)\"?\s*$", rest)
            if desc_m:
                iface["description"] = desc_m.group(1)
                continue

            # disable
            if rest.strip() == "disable":
                iface["admin_status"] = "disabled"
                continue

            # IP address: family inet address x.x.x.x/y
            addr_m = re.match(r"^family inet address\s+(\d+\.\d+\.\d+\.\d+)/(\d+)", rest)
            if addr_m:
                if iface["ip_address"] is None:
                    iface["ip_address"] = addr_m.group(1)
                    iface["prefix_length"] = int(addr_m.group(2))
                continue

            # Ethernet-switching mode
            mode_m = re.match(r"^family ethernet-switching interface-mode\s+(trunk|access)", rest)
            if mode_m:
                iface["vlan_mode"] = mode_m.group(1)
                continue

            # VLAN members
            vlan_m = re.match(r"^family ethernet-switching vlan members\s+(.+)", rest)
            if vlan_m:
                raw_vlan = vlan_m.group(1).strip()
                vlans = _parse_junos_vlan_members(raw_vlan)
                if vlans:
                    if iface["vlan_mode"] == "access" and len(vlans) == 1 and not iface["trunk_vlans"]:
                        iface["vlan_id"] = vlans[0]
                    else:
                        # Don't downgrade trunk mode to access when vlan members are parsed
                        if iface["vlan_mode"] != "trunk":
                            iface["vlan_mode"] = "trunk"
                        iface["trunk_vlans"].extend(vlans)
                continue

        # BGP
        m = re.match(r"^routing-options autonomous-system\s+(\d+)", stmt)
        if m:
            local_as = int(m.group(1))
            continue

        m = re.match(r"^protocols bgp group\s+\S+\s+neighbor\s+(\d+\.\d+\.\d+\.\d+)\s+peer-as\s+(\d+)", stmt)
        if m and local_as:
            result["bgp_peers"].append({
                "peer_ip": m.group(1),
                "local_as": local_as,
                "remote_as": int(m.group(2)),
            })
            continue

    # Determine device type
    has_routing = bool(result["bgp_peers"]) or any(
        i.get("ip_address") for i in iface_map.values()
        if not re.match(r"^(lo|irb)", i["name"], re.IGNORECASE)
    )
    has_switching = any(i.get("vlan_mode") in ("trunk", "access") for i in iface_map.values())
    if has_routing and not has_switching:
        result["device_type"] = "router"
    elif has_switching:
        result["device_type"] = "switch"

    result["interfaces"] = list(iface_map.values())
    return result


# ──────────────────────────────────────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────────────────────────────────────

def parse_junos_config(text: str, source_path: Path) -> dict:
    """
    Auto-detect JunOS format and parse.

    Returns the same schema as parsers.ios_config.parse_ios_running_config:
    {hostname, vendor, os, device_type, version, model, interfaces, acls, bgp_peers, source_file}
    """
    if is_junos_set(text):
        return _parse_set(text, source_path)
    return _parse_hierarchical(text, source_path)

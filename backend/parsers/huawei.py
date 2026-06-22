"""
TreasureMap — Huawei VRP configuration parser.

Supports Huawei VRP (Versatile Routing Platform) format used on:
  CE series (data-center switches), NE series (routers), S series (campus switches)

VRP syntax is similar to IOS but uses different keywords:
  • "interface GigabitEthernet0/0/0"
  • "ip address 10.0.0.1 255.255.255.0"
  • "acl number 3000" / "rule 5 permit ip source ..."
  • "vlan batch 10 20 30"
  • "port trunk allow-pass vlan 10 20"
  • "traffic-filter inbound acl 3000"

Returns a dict:
  {
    "device":     { name, hostname, vendor, model, os, management_ip, device_type, tags },
    "interfaces": [ {name, description, ip_address, prefix_length, admin_status,
                     vlan_mode, vlan_id, trunk_vlans, acl_in, acl_out} ],
    "acls":       [ {name, acl_type, rules:[...]} ],
  }
"""
from __future__ import annotations
import re
import logging
from typing import Optional

log = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _mask_to_prefix(mask: str) -> Optional[int]:
    try:
        return sum(bin(int(o)).count("1") for o in mask.split("."))
    except Exception:
        return None


def _pick_mgmt_ip(interfaces: dict) -> Optional[str]:
    # Loopback first
    for name, iface in interfaces.items():
        if re.match(r"loopback", name, re.I) and iface.get("ip_address"):
            return iface["ip_address"]
    # MEth / management
    for name, iface in interfaces.items():
        if re.match(r"(meth|management|m-ethernet|eth-trunk\s*0$)", name, re.I) and iface.get("ip_address"):
            return iface["ip_address"]
    # First IP
    for iface in interfaces.values():
        if iface.get("ip_address"):
            return iface["ip_address"]
    return None


def _iface_ensure(interfaces: dict, name: str):
    if name not in interfaces:
        interfaces[name] = {
            "name": name, "description": None, "ip_address": None,
            "prefix_length": None, "mac_address": None,
            "admin_status": "up", "oper_status": "up",
            "vlan_mode": "none", "vlan_id": None, "trunk_vlans": [],
            "native_vlan": None, "acl_in": None, "acl_out": None,
            "firewall_policy": None, "speed_mbps": None, "duplex": None,
        }


def _guess_device_type(hostname: str, model: str, interfaces: dict) -> str:
    h = (hostname + " " + model).lower()
    if any(k in h for k in ("firewall", "usg", "secpath")):
        return "firewall"
    if any(k in h for k in ("ce6", "ce7", "ce8", "s5", "s6", "s7", "quidway", "switch", "sw")):
        return "switch"
    if any(k in h for k in ("ne40", "ne80", "cr", "asr", "router", "pe", "gw", "edge", "core")):
        return "router"
    # count routed interfaces
    routed = sum(1 for i in interfaces.values() if i.get("ip_address"))
    return "router" if routed >= 2 else "switch"


# ──────────────────────────────────────────────────────────────────────────────
# Main parser
# ──────────────────────────────────────────────────────────────────────────────

def parse_huawei(raw: str, hostname: str = "unknown") -> dict:
    """
    Parse a Huawei VRP config string.

    Args:
        raw:      Full text of the config file.
        hostname: Override hostname if not detectable from config.

    Returns dict with keys: device, interfaces, acls.
    """
    interfaces: dict[str, dict] = {}
    acls: dict[str, dict] = {}

    current_iface: Optional[str] = None
    current_acl:   Optional[str] = None
    current_acl_seq_base: int = 0
    model = "Huawei VRP"

    lines = raw.splitlines()
    i = 0
    while i < len(lines):
        raw_line = lines[i]
        line = raw_line.strip()
        i += 1

        if not line or line.startswith("!") or line.startswith("#"):
            # Section separator — exit interface/acl context
            if line == "#":
                current_iface = None
                current_acl   = None
            continue

        # ── System hostname ──────────────────────────────────────
        m = re.match(r"sysname\s+(\S+)", line, re.I)
        if m:
            if hostname == "unknown":
                hostname = m.group(1)
            continue

        # ── Model from header comment ────────────────────────────
        m = re.match(r"#\s*(?:board|device)?\s*model[:\s]+(\S+)", line, re.I)
        if m:
            model = m.group(1)
            continue

        # ── VLAN batch ───────────────────────────────────────────
        # "vlan batch 10 20 30 to 40" — we just note VLANs exist; no device model impact
        # (skip — VLANs are tracked per-interface)

        # ── Interface block ──────────────────────────────────────
        m = re.match(r"interface\s+(.+)", line, re.I)
        if m:
            current_iface = m.group(1).strip()
            current_acl   = None
            _iface_ensure(interfaces, current_iface)
            continue

        # Inside interface block
        if current_iface:
            _parse_iface_line(line, current_iface, interfaces, acls)
            continue

        # ── ACL number block ─────────────────────────────────────
        m = re.match(r"acl\s+(number\s+)?(\d+)", line, re.I)
        if m:
            acl_num = m.group(2)
            acl_name = f"acl-{acl_num}"
            current_acl = acl_name
            current_iface = None
            acl_type = "standard" if int(acl_num) < 2000 else "extended"
            if acl_name not in acls:
                acls[acl_name] = {"name": acl_name, "acl_type": acl_type, "rules": []}
            continue

        # ── ACL name block ───────────────────────────────────────
        m = re.match(r"acl\s+name\s+(\S+)", line, re.I)
        if m:
            acl_name = m.group(1)
            current_acl = acl_name
            current_iface = None
            if acl_name not in acls:
                acls[acl_name] = {"name": acl_name, "acl_type": "named", "rules": []}
            continue

        # Inside ACL block
        if current_acl:
            _parse_acl_line(line, current_acl, acls)
            continue

    # Post-process
    mgmt_ip = _pick_mgmt_ip(interfaces)
    device_type = _guess_device_type(hostname, model, interfaces)

    log.info(
        "Parsed Huawei VRP config for %s: %d interfaces, %d ACLs",
        hostname, len(interfaces), len(acls)
    )

    return {
        "device": {
            "name": hostname,
            "hostname": hostname,
            "vendor": "Huawei",
            "model": model,
            "os": "VRP",
            "management_ip": mgmt_ip or "0.0.0.0",
            "device_type": device_type,
            "tags": ["huawei", "vrp", "parsed"],
        },
        "interfaces": list(interfaces.values()),
        "acls": list(acls.values()),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Interface line parser
# ──────────────────────────────────────────────────────────────────────────────

def _parse_iface_line(line: str, iface: str, interfaces: dict, acls: dict):
    idata = interfaces[iface]

    # description
    m = re.match(r"description\s+(.+)", line, re.I)
    if m:
        idata["description"] = m.group(1)
        return

    # shutdown (admin down)
    if re.match(r"shutdown", line, re.I):
        idata["admin_status"] = "disabled"
        return

    # undo shutdown (bring up)
    if re.match(r"undo shutdown", line, re.I):
        idata["admin_status"] = "up"
        return

    # ip address A.B.C.D M.M.M.M [secondary]
    m = re.match(r"ip address\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)", line, re.I)
    if m:
        ip, mask = m.group(1), m.group(2)
        idata["ip_address"] = ip
        idata["prefix_length"] = _mask_to_prefix(mask)
        idata["vlan_mode"] = "routed"
        return

    # ipv6 address — record if no v4
    m = re.match(r"ipv6 address\s+(\S+)", line, re.I)
    if m and not idata.get("ip_address"):
        addr = m.group(1).split("/")[0]
        idata["ip_address"] = addr
        pl = m.group(1).split("/")[1] if "/" in m.group(1) else None
        if pl:
            idata["prefix_length"] = int(pl)
        return

    # port link-type (access/trunk/hybrid)
    m = re.match(r"port link-type\s+(access|trunk|hybrid)", line, re.I)
    if m:
        mode = m.group(1).lower()
        idata["vlan_mode"] = "trunk" if mode == "trunk" else "access"
        return

    # port default vlan (access)
    m = re.match(r"port default vlan\s+(\d+)", line, re.I)
    if m:
        idata["vlan_id"] = int(m.group(1))
        idata["vlan_mode"] = "access"
        return

    # port trunk allow-pass vlan
    m = re.match(r"port trunk allow-pass vlan\s+(.+)", line, re.I)
    if m:
        vlan_str = m.group(1)
        idata["vlan_mode"] = "trunk"
        idata["trunk_vlans"] = _parse_vlan_list(vlan_str)
        return

    # port trunk pvid vlan (native vlan)
    m = re.match(r"port trunk pvid vlan\s+(\d+)", line, re.I)
    if m:
        idata["native_vlan"] = int(m.group(1))
        return

    # traffic-filter inbound/outbound acl [number] NAME
    m = re.match(r"traffic-filter\s+(inbound|outbound)\s+acl\s+(?:number\s+)?(\S+)", line, re.I)
    if m:
        direction, acl_ref = m.group(1).lower(), m.group(2)
        acl_name = f"acl-{acl_ref}" if acl_ref.isdigit() else acl_ref
        if direction == "inbound":
            idata["acl_in"] = acl_name
        else:
            idata["acl_out"] = acl_name
        idata["firewall_policy"] = acl_name
        # Ensure ACL entry exists
        if acl_name not in (acls or {}):
            acls[acl_name] = {
                "name": acl_name, "acl_type": "extended", "rules": []
            }
        return

    # speed
    m = re.match(r"speed\s+(\d+)", line, re.I)
    if m:
        spd = int(m.group(1))
        # VRP uses Mb/s in speed command
        idata["speed_mbps"] = spd
        return

    # duplex
    m = re.match(r"duplex\s+(auto|full|half)", line, re.I)
    if m:
        idata["duplex"] = m.group(1).lower()
        return


# ──────────────────────────────────────────────────────────────────────────────
# ACL line parser
# ──────────────────────────────────────────────────────────────────────────────

_PROTO_MAP = {
    "ip": "ip", "tcp": "tcp", "udp": "udp",
    "icmp": "icmp", "ospf": "ospf", "igmp": "igmp",
    "gre": "gre", "esp": "esp", "ah": "ah",
}

def _parse_acl_line(line: str, acl_name: str, acls: dict):
    acl = acls[acl_name]

    # rule [sequence] {permit|deny} {protocol} [source S M] [destination D M] [dst-port eq P]
    m = re.match(
        r"rule\s+(\d+)\s+(permit|deny)\s+(\S+)"
        r"(?:\s+source\s+(\S+)\s+(\S+))?"
        r"(?:\s+destination\s+(\S+)\s+(\S+))?"
        r"(?:\s+destination-port\s+eq\s+(\d+))?",
        line, re.I
    )
    if m:
        seq       = int(m.group(1))
        action    = m.group(2).lower()
        proto     = _PROTO_MAP.get(m.group(3).lower(), m.group(3).lower())
        src_host  = m.group(4)
        src_wc    = m.group(5)
        dst_host  = m.group(6)
        dst_wc    = m.group(7)
        dst_port  = m.group(8)

        src_net = "any"
        if src_host and src_host.lower() != "any":
            if src_wc == "0.0.0.0":
                src_net = f"{src_host}/32"
            elif src_wc:
                src_net = _wildcard_to_cidr(src_host, src_wc)
            else:
                src_net = src_host

        dst_net = "any"
        if dst_host and dst_host.lower() != "any":
            if dst_wc == "0.0.0.0":
                dst_net = f"{dst_host}/32"
            elif dst_wc:
                dst_net = _wildcard_to_cidr(dst_host, dst_wc)
            else:
                dst_net = dst_host

        rule = {
            "sequence": seq, "action": action, "protocol": proto,
            "src_network": src_net, "dst_network": dst_net,
        }
        if dst_port:
            rule["dst_port"] = int(dst_port)

        acl["rules"].append(rule)
        return

    # Simple "rule N permit/deny" (standard ACL style)
    m = re.match(r"rule\s+(\d+)\s+(permit|deny)\s+source\s+(\S+)\s+(\S+)", line, re.I)
    if m:
        seq, action, src_host, src_wc = int(m.group(1)), m.group(2).lower(), m.group(3), m.group(4)
        src_net = _wildcard_to_cidr(src_host, src_wc) if src_host.lower() != "any" else "any"
        acl["rules"].append({
            "sequence": seq, "action": action, "protocol": "ip",
            "src_network": src_net, "dst_network": "any",
        })


# ──────────────────────────────────────────────────────────────────────────────
# VLAN list expander
# ──────────────────────────────────────────────────────────────────────────────

def _parse_vlan_list(vlan_str: str) -> list[int]:
    """Parse '10 20 30 to 40 50' → [10, 20, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 50]."""
    vlans = []
    tokens = vlan_str.strip().split()
    idx = 0
    while idx < len(tokens):
        t = tokens[idx]
        if t.lower() == "to":
            idx += 1
            continue
        if t.isdigit():
            val = int(t)
            # Check if next token is "to"
            if idx + 1 < len(tokens) and tokens[idx + 1].lower() == "to":
                end_val = int(tokens[idx + 2]) if idx + 2 < len(tokens) else val
                vlans.extend(range(val, end_val + 1))
                idx += 3
                continue
            vlans.append(val)
        idx += 1
    return vlans


def _wildcard_to_cidr(ip: str, wildcard: str) -> str:
    """Convert wildcard mask to CIDR. 10.0.0.0 / 0.0.0.255 → 10.0.0.0/24."""
    try:
        wc_octets = [int(o) for o in wildcard.split(".")]
        prefix_len = sum(bin(255 - o).count("1") for o in wc_octets)
        return f"{ip}/{prefix_len}"
    except Exception:
        return ip

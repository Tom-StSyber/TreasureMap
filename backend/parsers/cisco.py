"""
TreasureMap — Cisco IOS/IOS-XE/NX-OS configuration parser.

Handles:
  • IOS / IOS-XE  (classic indented blocks)
  • NX-OS         (feature-based, "feature" lines, vrf context)

Returns the same dict shape as the Juniper and Huawei parsers:
  {
    "device":     { name, hostname, vendor, model, os, management_ip, device_type, tags },
    "interfaces": [ {name, description, ip_address, prefix_length, admin_status,
                     vlan_mode, vlan_id, trunk_vlans, native_vlan, acl_in, acl_out} ],
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


def _wildcard_to_prefix(wildcard: str) -> Optional[int]:
    """Convert a wildcard mask to prefix length: 0.0.0.255 → 24."""
    try:
        wc_octets = [int(o) for o in wildcard.split(".")]
        return sum(bin(255 - o).count("1") for o in wc_octets)
    except Exception:
        return None


def _pick_mgmt_ip(interfaces: dict) -> Optional[str]:
    for name, iface in interfaces.items():
        if re.match(r"loopback\s*0", name, re.I) and iface.get("ip_address"):
            return iface["ip_address"]
    for name, iface in interfaces.items():
        if re.match(r"(mgmt|management)", name, re.I) and iface.get("ip_address"):
            return iface["ip_address"]
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
    if any(k in h for k in ("asa", "firepower", "ftd", "pix", "fwsm", "fw")):
        return "firewall"
    if any(k in h for k in ("ws-c", "c9", "nexus", "n5k", "n7k", "sw", "switch", "cat")):
        return "switch"
    if any(k in h for k in ("asr", "isr", "csr", "7200", "7600", "router", "pe", "gw", "edge", "core")):
        return "router"
    routed = sum(1 for iface in interfaces.values() if iface.get("ip_address"))
    return "router" if routed >= 2 else "switch"


_PROTO_MAP = {
    "ip": "ip", "tcp": "tcp", "udp": "udp", "icmp": "icmp",
    "ospf": "ospf", "eigrp": "eigrp", "bgp": "bgp",
    "gre": "gre", "esp": "esp", "ah": "ah",
}

_NAMED_PORT = {
    "ssh": 22, "telnet": 23, "smtp": 25, "dns": 53,
    "http": 80, "https": 443, "bgp": 179, "snmp": 161,
    "ntp": 123, "ftp": 21, "ftp-data": 20, "tftp": 69,
    "rdp": 3389, "syslog": 514,
}

def _resolve_port(token: str) -> Optional[int]:
    if token.isdigit():
        return int(token)
    return _NAMED_PORT.get(token.lower())


# ──────────────────────────────────────────────────────────────────────────────
# ACL parsers
# ──────────────────────────────────────────────────────────────────────────────

def _parse_std_acl_line(line: str, acl: dict, seq: int):
    """Parse IOS standard ACL entry: 'permit host 10.0.0.1' or 'deny 10.0.0.0 0.0.0.255'"""
    m = re.match(r"(\d+\s+)?(permit|deny)\s+(.+)", line, re.I)
    if not m:
        return
    seq_override = m.group(1)
    action = m.group(2).lower()
    rest = m.group(3).strip()

    actual_seq = int(seq_override.strip()) if seq_override else seq
    src_net = "any"

    if rest.lower() == "any":
        src_net = "any"
    elif rest.lower().startswith("host "):
        src_net = rest.split()[1] + "/32"
    else:
        parts = rest.split()
        if len(parts) >= 2:
            pl = _wildcard_to_prefix(parts[1])
            src_net = f"{parts[0]}/{pl}" if pl is not None else parts[0]
        else:
            src_net = parts[0]

    acl["rules"].append({
        "sequence": actual_seq, "action": action, "protocol": "ip",
        "src_network": src_net, "dst_network": "any",
    })


def _parse_ext_acl_line(line: str, acl: dict, seq: int):
    """
    Parse IOS extended ACL entry:
    [seq] permit|deny proto src src-wc [lt|gt|eq port] dst dst-wc [lt|gt|eq port] [established]
    """
    m = re.match(r"(\d+\s+)?(permit|deny)\s+(\S+)\s+(.+)", line, re.I)
    if not m:
        return
    seq_override = m.group(1)
    action       = m.group(2).lower()
    proto        = _PROTO_MAP.get(m.group(3).lower(), m.group(3).lower())
    rest         = m.group(4).strip()
    actual_seq   = int(seq_override.strip()) if seq_override else seq

    tokens = rest.split()
    src_net = "any"
    dst_net = "any"
    src_port = dst_port = None
    established = False
    ti = 0

    def _read_net_wc(tokens, idx):
        """Read host/any/network+wildcard from tokens starting at idx. Returns (net, next_idx)."""
        if idx >= len(tokens):
            return "any", idx
        if tokens[idx].lower() == "any":
            return "any", idx + 1
        if tokens[idx].lower() == "host":
            if idx + 1 < len(tokens):
                return tokens[idx + 1] + "/32", idx + 2
            return "any", idx + 1
        # network wildcard
        net = tokens[idx]
        if idx + 1 < len(tokens) and re.match(r"\d+\.\d+\.\d+\.\d+", tokens[idx + 1]):
            pl = _wildcard_to_prefix(tokens[idx + 1])
            return (f"{net}/{pl}" if pl is not None else net), idx + 2
        return net, idx + 1

    def _read_port(tokens, idx):
        """Read 'eq PORT' or 'lt PORT' or 'gt PORT' if present."""
        if idx >= len(tokens):
            return None, idx
        if tokens[idx].lower() in ("eq", "lt", "gt", "neq"):
            op = tokens[idx]
            if idx + 1 < len(tokens):
                return _resolve_port(tokens[idx + 1]), idx + 2
        return None, idx

    # Source
    if proto in ("ip", "icmp", "ospf", "eigrp", "gre", "esp", "ah"):
        src_net, ti = _read_net_wc(tokens, ti)
        dst_net, ti = _read_net_wc(tokens, ti)
    else:
        src_net, ti = _read_net_wc(tokens, ti)
        src_port, ti = _read_port(tokens, ti)
        dst_net, ti = _read_net_wc(tokens, ti)
        dst_port, ti = _read_port(tokens, ti)

    if ti < len(tokens) and tokens[ti].lower() == "established":
        established = True

    rule = {
        "sequence": actual_seq, "action": action, "protocol": proto,
        "src_network": src_net, "dst_network": dst_net,
        "established": established,
    }
    if src_port is not None:
        rule["src_port"] = src_port
    if dst_port is not None:
        rule["dst_port"] = dst_port

    acl["rules"].append(rule)


# ──────────────────────────────────────────────────────────────────────────────
# Main parser
# ──────────────────────────────────────────────────────────────────────────────

def parse_cisco_ios(raw: str, hostname: str = "unknown") -> dict:
    """
    Parse a Cisco IOS/IOS-XE/NX-OS configuration string.

    Returns dict with keys: device, interfaces, acls.
    """
    interfaces: dict[str, dict] = {}
    acls: dict[str, dict] = {}
    model = "Cisco IOS"

    current_iface: Optional[str] = None
    current_acl:   Optional[str] = None
    current_acl_type: str = "extended"
    acl_seq: int = 10

    for raw_line in raw.splitlines():
        line = raw_line.strip()

        if not line or line.startswith("!"):
            if not line or line == "!":
                current_iface = None
                current_acl   = None
            continue

        # ── Hostname ──────────────────────────────────────────────
        m = re.match(r"hostname\s+(\S+)", line, re.I)
        if m:
            if hostname == "unknown":
                hostname = m.group(1)
            continue

        # ── Model ─────────────────────────────────────────────────
        m = re.match(r"!.*[Mm]odel[:\s]+(\S+)", line)
        if not m:
            m = re.match(r"^\s*#.*[Mm]odel[:\s]+(\S+)", line)
        if m:
            model = m.group(1)
            continue

        # ── Interface block ───────────────────────────────────────
        m = re.match(r"interface\s+(.+)", line, re.I)
        if m:
            current_iface = m.group(1).strip()
            current_acl = None
            _iface_ensure(interfaces, current_iface)
            continue

        # Inside interface
        if current_iface:
            _parse_iface_line(line, current_iface, interfaces)
            continue

        # ── Named ACL ─────────────────────────────────────────────
        m = re.match(r"ip access-list\s+(standard|extended)\s+(\S+)", line, re.I)
        if m:
            current_acl_type = m.group(1).lower()
            acl_name = m.group(2)
            current_acl = acl_name
            current_iface = None
            acl_seq = 10
            if acl_name not in acls:
                acls[acl_name] = {"name": acl_name, "acl_type": current_acl_type, "rules": []}
            continue

        # Inside named ACL
        if current_acl and current_acl_type == "extended":
            m = re.match(r"(?:\d+\s+)?(permit|deny)\s+", line, re.I)
            if m:
                _parse_ext_acl_line(line, acls[current_acl], acl_seq)
                acl_seq += 10
                continue

        if current_acl and current_acl_type == "standard":
            m = re.match(r"(?:\d+\s+)?(permit|deny)\s+", line, re.I)
            if m:
                _parse_std_acl_line(line, acls[current_acl], acl_seq)
                acl_seq += 10
                continue

        # ── Numbered ACL (inline, IOS classic) ───────────────────
        # "access-list 100 permit tcp ..."
        m = re.match(r"access-list\s+(\d+)\s+(permit|deny)\s+(.+)", line, re.I)
        if m:
            acl_num, action, rest = m.group(1), m.group(2).lower(), m.group(3)
            acl_name = f"acl-{acl_num}"
            if acl_name not in acls:
                a_type = "standard" if int(acl_num) <= 99 or (199 < int(acl_num) <= 299) else "extended"
                acls[acl_name] = {"name": acl_name, "acl_type": a_type, "rules": []}
            synthetic = f"{action} {rest}"
            if acls[acl_name]["acl_type"] == "standard":
                _parse_std_acl_line(synthetic, acls[acl_name], len(acls[acl_name]["rules"]) * 10 + 10)
            else:
                _parse_ext_acl_line(synthetic, acls[acl_name], len(acls[acl_name]["rules"]) * 10 + 10)
            continue

    mgmt_ip = _pick_mgmt_ip(interfaces)
    device_type = _guess_device_type(hostname, model, interfaces)

    log.info(
        "Parsed Cisco IOS config for %s: %d interfaces, %d ACLs",
        hostname, len(interfaces), len(acls)
    )

    return {
        "device": {
            "name": hostname,
            "hostname": hostname,
            "vendor": "Cisco",
            "model": model,
            "os": "IOS-XE",
            "management_ip": mgmt_ip or "0.0.0.0",
            "device_type": device_type,
            "tags": ["cisco", "ios", "parsed"],
        },
        "interfaces": list(interfaces.values()),
        "acls": list(acls.values()),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Interface line parser
# ──────────────────────────────────────────────────────────────────────────────

def _parse_iface_line(line: str, iface: str, interfaces: dict):
    idata = interfaces[iface]

    m = re.match(r"description\s+(.+)", line, re.I)
    if m:
        idata["description"] = m.group(1)
        return

    if re.match(r"shutdown", line, re.I):
        idata["admin_status"] = "disabled"
        return

    if re.match(r"no shutdown", line, re.I):
        idata["admin_status"] = "up"
        return

    # ip address A.B.C.D M.M.M.M [secondary]
    m = re.match(r"ip address\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)", line, re.I)
    if m:
        idata["ip_address"] = m.group(1)
        idata["prefix_length"] = _mask_to_prefix(m.group(2))
        idata["vlan_mode"] = "routed"
        return

    # switchport mode
    m = re.match(r"switchport mode\s+(access|trunk|dynamic)", line, re.I)
    if m:
        mode = m.group(1).lower()
        idata["vlan_mode"] = "trunk" if mode == "trunk" else "access"
        return

    # switchport access vlan
    m = re.match(r"switchport access vlan\s+(\d+)", line, re.I)
    if m:
        idata["vlan_id"] = int(m.group(1))
        idata["vlan_mode"] = "access"
        return

    # switchport trunk allowed vlan
    m = re.match(r"switchport trunk allowed vlan\s+(.+)", line, re.I)
    if m:
        idata["vlan_mode"] = "trunk"
        idata["trunk_vlans"] = _parse_vlan_list(m.group(1))
        return

    # switchport trunk native vlan
    m = re.match(r"switchport trunk native vlan\s+(\d+)", line, re.I)
    if m:
        idata["native_vlan"] = int(m.group(1))
        return

    # ip access-group ACL-NAME in|out
    m = re.match(r"ip access-group\s+(\S+)\s+(in|out)", line, re.I)
    if m:
        acl_name, direction = m.group(1), m.group(2).lower()
        if direction == "in":
            idata["acl_in"] = acl_name
        else:
            idata["acl_out"] = acl_name
        idata["firewall_policy"] = acl_name
        return

    # speed
    m = re.match(r"speed\s+(\d+)", line, re.I)
    if m:
        idata["speed_mbps"] = int(m.group(1))
        return

    # duplex
    m = re.match(r"duplex\s+(auto|full|half)", line, re.I)
    if m:
        idata["duplex"] = m.group(1).lower()
        return


def _parse_vlan_list(vlan_str: str) -> list[int]:
    """Parse IOS vlan list: '10,20,30-40,50' → [10, 20, 30..40, 50]."""
    vlans = []
    for part in re.split(r"[,\s]+", vlan_str.strip()):
        if "-" in part:
            lo, hi = part.split("-", 1)
            try:
                vlans.extend(range(int(lo), int(hi) + 1))
            except ValueError:
                pass
        elif part.isdigit():
            vlans.append(int(part))
    return vlans

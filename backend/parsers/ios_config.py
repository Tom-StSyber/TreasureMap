"""
parsers/ios_config.py — Cisco IOS / IOS-XE / NX-OS running-config parser.

Outputs TreasureMap model instances (Device, Interface, Acl, AclRule).
Connection building happens in the ingest router after all files are parsed,
so that BGP peer IPs can be cross-referenced against the full IP→device map.

Supported input formats
-----------------------
  .cfg / .conf / .txt  containing a Cisco IOS running configuration
  (hostname, interface blocks, ip access-list, router bgp, router ospf)

Detection heuristic
-------------------
  File is treated as a Cisco running config if it contains a "hostname X"
  line and at least one "interface " block.
"""
from __future__ import annotations

import ipaddress
import re
import uuid
from pathlib import Path
from typing import Optional

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _id(seed: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"tm.{seed}"))


def _mask_to_prefix(mask: str) -> Optional[int]:
    try:
        return ipaddress.IPv4Network(f"0.0.0.0/{mask}", strict=False).prefixlen
    except ValueError:
        return None


def _wildcard_to_prefix(wildcard: str) -> Optional[int]:
    """Convert ACL wildcard mask (0.0.0.255) to prefix length (24)."""
    try:
        # Invert each octet
        parts = [255 - int(o) for o in wildcard.split(".")]
        if len(parts) != 4:
            return None
        mask = ".".join(str(p) for p in parts)
        return ipaddress.IPv4Network(f"0.0.0.0/{mask}", strict=False).prefixlen
    except (ValueError, IndexError):
        return None


_IS_IP = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")


def _is_ip(s: str) -> bool:
    return bool(_IS_IP.match(s))


# ──────────────────────────────────────────────────────────────────────────────
# Vendor / OS detection
# ──────────────────────────────────────────────────────────────────────────────

def detect_vendor_os(text: str) -> tuple[str, str, str]:
    """
    Returns (vendor, os, device_type) based on content fingerprints.
    device_type: router | switch | firewall | server | host | unknown
    """
    low = text[:4000].lower()  # only check preamble

    # ── Host/server stub metadata (checked FIRST) ─────────────────────────────
    # Stub configs carry:  ! device-type: server|host|workstation
    #                      ! vendor: Microsoft|Linux|...
    #                      ! os: Windows Server 2022|Ubuntu 22.04|...
    dtype_m = re.search(r"^!\s*device-type:\s*(\w+)", text, re.MULTILINE | re.IGNORECASE)
    if dtype_m:
        dtype = dtype_m.group(1).lower()
        if dtype == "workstation":
            dtype = "host"
        if dtype in ("server", "host"):
            os_m  = re.search(r"^!\s*os:\s*(.+)",     text, re.MULTILINE | re.IGNORECASE)
            ven_m = re.search(r"^!\s*vendor:\s*(.+)",  text, re.MULTILINE | re.IGNORECASE)
            os_str  = os_m.group(1).strip()  if os_m  else "Unknown"
            ven_str = ven_m.group(1).strip() if ven_m else "Generic"
            return ven_str, os_str, dtype

    # Juniper JunOS
    if re.search(r"^\s*version\s+\d+\.\d+[A-Z]\d+", text, re.MULTILINE):
        return "Juniper", "JunOS", "router"
    if "interfaces {" in text and "routing-options {" in text:
        return "Juniper", "JunOS", "router"

    # Cisco ASA / PIX (firewall)
    if "asa version" in low or "pix version" in low or ": hardware:" in low:
        return "Cisco", "ASA-OS", "firewall"

    # NX-OS (Nexus)
    if re.search(r"^feature\s+\w+", text, re.MULTILINE) and "nxos" in low:
        return "Cisco", "NX-OS", "switch"

    # IOS-XE (16.x / 17.x usually IOS-XE)
    m = re.search(r"^version\s+(\d+\.\d+)", text, re.MULTILINE)
    if m:
        major = int(m.group(1).split(".")[0])
        if major >= 16:
            vendor, os_ = "Cisco", "IOS-XE"
        elif major >= 12:
            vendor, os_ = "Cisco", "IOS"
        else:
            vendor, os_ = "Cisco", "IOS"
    else:
        vendor, os_ = "Cisco", "IOS"

    # Infer device type
    if re.search(r"^interface\s+(vlan|loopback|port-channel)", text, re.MULTILINE | re.IGNORECASE):
        if re.search(r"^(spanning-tree|vlan\s+\d)", text, re.MULTILINE | re.IGNORECASE):
            device_type = "switch"
        else:
            device_type = "router"
    elif re.search(r"^router\s+(bgp|ospf|eigrp|rip)", text, re.MULTILINE | re.IGNORECASE):
        device_type = "router"
    else:
        device_type = "router"

    return vendor, os_, device_type


def is_ios_running_config(text: str) -> bool:
    """Quick check: does this look like a Cisco running config?"""
    has_hostname = bool(re.search(r"^hostname\s+\S+", text, re.MULTILINE))
    has_interface = bool(re.search(r"^interface\s+\S+", text, re.MULTILINE))
    return has_hostname and has_interface


# ──────────────────────────────────────────────────────────────────────────────
# Extended ACL parser helpers
# ──────────────────────────────────────────────────────────────────────────────

# Matches: [seq] permit|deny proto src [src_port] dst [dst_port] [established] [log]
# We parse: action, protocol, src_network, dst_network, dst_port, dst_port_range
_ACL_LINE_RE = re.compile(
    r"^(?:(\d+)\s+)?"                         # optional sequence number
    r"(permit|deny)\s+"                        # action
    r"(ip|tcp|udp|icmp|ospf|eigrp|gre|\d+)"   # protocol
    r"\s+(any|host\s+\S+|\d+\.\d+\.\d+\.\d+(?:\s+\d+\.\d+\.\d+\.\d+)?)"   # src
    r"(?:\s+eq\s+(\d+))?"                     # src port (rarely used)
    r"\s+(any|host\s+\S+|\d+\.\d+\.\d+\.\d+(?:\s+\d+\.\d+\.\d+\.\d+)?)"   # dst
    r"(?:\s+(?:eq|range)\s+(\d+)(?:\s+(\d+))?)?"   # dst port / range
    r"(?:\s+(established))?"                   # established flag
    , re.IGNORECASE
)

_SERVICE_PORTS: dict[str, int] = {
    "ftp": 21, "ssh": 22, "telnet": 23, "smtp": 25, "dns": 53, "tftp": 69,
    "http": 80, "www": 80, "pop3": 110, "nntp": 119, "ntp": 123,
    "netbios-ssn": 139, "imap": 143, "snmp": 161, "snmptrap": 162,
    "bgp": 179, "ldap": 389, "https": 443, "smb": 445, "rdp": 3389,
    "netconf": 830, "tacacs": 49, "syslog": 514,
}


def _resolve_port(tok: Optional[str]) -> Optional[int]:
    if tok is None:
        return None
    if tok.isdigit():
        return int(tok)
    return _SERVICE_PORTS.get(tok.lower())


def _parse_network(tok: str) -> str:
    """Convert ACL network token to CIDR or 'any'."""
    tok = tok.strip()
    if tok.lower() == "any":
        return "any"
    if tok.lower().startswith("host "):
        ip = tok.split(None, 1)[1].strip()
        return f"{ip}/32"
    parts = tok.split()
    if len(parts) == 2 and _is_ip(parts[0]) and _is_ip(parts[1]):
        pfx = _wildcard_to_prefix(parts[1])
        if pfx is not None:
            return f"{parts[0]}/{pfx}"
        return parts[0]
    if len(parts) == 1 and _is_ip(parts[0]):
        return f"{parts[0]}/32"
    return tok


def _parse_acl_rule(line: str, seq_counter: list[int]) -> Optional[dict]:
    """
    Parse one ACE line. Returns a dict ready for AclRule(**d), or None.
    seq_counter is a mutable [int] used for auto-numbering unnamed ACEs.
    """
    line = line.strip()
    if not line or line.startswith("!") or line.startswith("remark"):
        return None

    m = _ACL_LINE_RE.match(line)
    if not m:
        return None

    seq_str, action, proto, src_tok, _src_port_tok, dst_tok, dst_port_tok, dst_port_end_tok, established_tok = m.groups()

    if seq_str:
        seq = int(seq_str)
    else:
        seq_counter[0] += 10
        seq = seq_counter[0]

    dst_port: Optional[int] = None
    dst_port_range: Optional[list[int]] = None

    if dst_port_tok:
        if dst_port_end_tok:  # range
            lo = _resolve_port(dst_port_tok)
            hi = _resolve_port(dst_port_end_tok)
            if lo is not None and hi is not None:
                dst_port_range = [lo, hi]
        else:
            dst_port = _resolve_port(dst_port_tok)

    return {
        "sequence": seq,
        "action": action.lower(),
        "protocol": proto.lower(),
        "src_network": _parse_network(src_tok),
        "dst_network": _parse_network(dst_tok),
        "dst_port": dst_port,
        "dst_port_range": dst_port_range,
        "established": bool(established_tok),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Main parser
# ──────────────────────────────────────────────────────────────────────────────

def parse_ios_running_config(text: str, source_path: Path) -> dict:
    """
    Parse a Cisco IOS / IOS-XE running config.

    Returns:
    {
      "hostname":   str,
      "vendor":     str,
      "os":         str,
      "device_type": str,
      "version":    str,
      "interfaces": [{ name, ip_address, prefix_length, description,
                       admin_status, vlan_mode, vlan_id, trunk_vlans,
                       native_vlan, acl_in, acl_out }],
      "acls":       [{ name, acl_type, rules: [{sequence,action,protocol,
                                                src_network,dst_network,
                                                dst_port,dst_port_range,
                                                established}] }],
      "bgp_peers":  [{ peer_ip, local_as, remote_as }],
      "model":      str,
      "source_file": str,
    }
    """
    vendor, os_, device_type = detect_vendor_os(text)

    result: dict = {
        "hostname": source_path.stem,  # fallback
        "vendor": vendor,
        "os": os_,
        "device_type": device_type,
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

    # ── ACL collection (named and numbered) ──────────────────────────────────
    named_acls: dict[str, dict] = {}   # name → {acl_type, rules}
    numbered_acls: dict[str, dict] = {}  # "100", "10" → {acl_type, rules}

    # ── BGP data ─────────────────────────────────────────────────────────────
    bgp_peers: list[dict] = []

    while i < n:
        raw = lines[i]
        line = raw.strip()

        # ── Top-level: hostname ───────────────────────────────────────────────
        if line.startswith("hostname "):
            result["hostname"] = line.split(None, 1)[1].strip()

        # ── Top-level: version ───────────────────────────────────────────────
        elif line.startswith("version "):
            result["version"] = line.split(None, 1)[1].strip()

        # ── Interface block ───────────────────────────────────────────────────
        elif line.startswith("interface "):
            iface_name = line.split(None, 1)[1].strip()
            iface: dict = {
                "name": iface_name,
                "ip_address": None,
                "prefix_length": None,
                "description": None,
                "admin_status": "up",
                "vlan_mode": "none",
                "vlan_id": None,
                "trunk_vlans": [],
                "native_vlan": None,
                "acl_in": None,
                "acl_out": None,
            }
            i += 1
            while i < n:
                sub_raw = lines[i]
                if sub_raw and not sub_raw[0].isspace():
                    break
                sub = sub_raw.strip()

                if sub.startswith("ip address ") and "dhcp" not in sub and "secondary" not in sub:
                    parts = sub.split()
                    if len(parts) >= 4:
                        iface["ip_address"] = parts[2]
                        pfx = _mask_to_prefix(parts[3])
                        iface["prefix_length"] = pfx

                elif sub == "shutdown":
                    iface["admin_status"] = "disabled"

                elif sub.startswith("description "):
                    iface["description"] = sub.split(None, 1)[1].strip()

                elif sub.startswith("ip access-group "):
                    parts = sub.split()
                    if len(parts) >= 4:
                        acl_name = parts[2]
                        direction = parts[3].lower()
                        if direction == "in":
                            iface["acl_in"] = acl_name
                        elif direction == "out":
                            iface["acl_out"] = acl_name

                elif sub == "switchport mode trunk":
                    iface["vlan_mode"] = "trunk"

                elif sub == "switchport mode access":
                    iface["vlan_mode"] = "access"

                elif sub.startswith("switchport access vlan "):
                    try:
                        iface["vlan_id"] = int(sub.split()[-1])
                    except ValueError:
                        pass

                elif sub.startswith("switchport trunk native vlan "):
                    try:
                        iface["native_vlan"] = int(sub.split()[-1])
                    except ValueError:
                        pass

                elif sub.startswith("switchport trunk allowed vlan "):
                    vlan_str = sub.split("vlan", 1)[1].strip()
                    vlans: list[int] = []
                    for tok in re.split(r"[,\s]+", vlan_str):
                        tok = tok.strip()
                        if "-" in tok:
                            try:
                                lo, hi = tok.split("-")
                                vlans.extend(range(int(lo), int(hi) + 1))
                            except ValueError:
                                pass
                        elif tok.isdigit():
                            vlans.append(int(tok))
                    iface["trunk_vlans"] = vlans

                i += 1
            result["interfaces"].append(iface)
            continue  # i already advanced

        # ── Named extended ACL ───────────────────────────────────────────────
        elif re.match(r"^ip access-list (extended|standard)\s+(\S+)", line, re.IGNORECASE):
            m = re.match(r"^ip access-list (extended|standard)\s+(\S+)", line, re.IGNORECASE)
            acl_type = m.group(1).lower()
            acl_name = m.group(2)
            rules: list[dict] = []
            seq_counter = [0]
            i += 1
            while i < n:
                sub_raw = lines[i]
                if sub_raw and not sub_raw[0].isspace():
                    break
                sub = sub_raw.strip()
                rule = _parse_acl_rule(sub, seq_counter)
                if rule:
                    rules.append(rule)
                i += 1
            named_acls[acl_name] = {"acl_type": acl_type, "rules": rules}
            continue

        # ── Numbered ACL (access-list N ...) ─────────────────────────────────
        elif re.match(r"^access-list\s+(\d+)\s+(permit|deny)", line, re.IGNORECASE):
            m = re.match(r"^access-list\s+(\d+)\s+(.+)$", line, re.IGNORECASE)
            if m:
                acl_num = m.group(1)
                acl_type = "extended" if int(acl_num) >= 100 else "standard"
                remainder = f"{m.group(2)}"
                seq_counter_n = numbered_acls.get(acl_num, {}).get("_seq", [0])
                rule = _parse_acl_rule(remainder, seq_counter_n)
                if rule:
                    if acl_num not in numbered_acls:
                        numbered_acls[acl_num] = {"acl_type": acl_type, "rules": [], "_seq": seq_counter_n}
                    numbered_acls[acl_num]["rules"].append(rule)

        # ── BGP block ────────────────────────────────────────────────────────
        elif re.match(r"^router bgp\s+(\d+)", line, re.IGNORECASE):
            m = re.match(r"^router bgp\s+(\d+)", line, re.IGNORECASE)
            local_as = int(m.group(1))
            peer_groups: dict[str, int] = {}  # group_name → remote_as
            peer_group_members: list[tuple[str, str]] = []  # (ip, group_name)

            i += 1
            while i < n:
                sub_raw = lines[i]
                if sub_raw and not sub_raw[0].isspace():
                    break
                sub = sub_raw.strip()

                nb = re.match(r"^neighbor\s+(\S+)\s+(.+)$", sub, re.IGNORECASE)
                if nb:
                    nbr_id = nb.group(1)
                    rest = nb.group(2).strip()

                    rm = re.match(r"^remote-as\s+(\d+)", rest, re.IGNORECASE)
                    if rm:
                        remote_as = int(rm.group(1))
                        if _is_ip(nbr_id):
                            bgp_peers.append({
                                "peer_ip": nbr_id,
                                "local_as": local_as,
                                "remote_as": remote_as,
                            })
                        else:
                            peer_groups[nbr_id] = remote_as

                    pg = re.match(r"^peer-group\s+(\S+)", rest, re.IGNORECASE)
                    if pg and _is_ip(nbr_id):
                        peer_group_members.append((nbr_id, pg.group(1)))

                i += 1

            # Resolve peer-group members
            for ip, grp in peer_group_members:
                ras = peer_groups.get(grp)
                if ras and not any(p["peer_ip"] == ip for p in bgp_peers):
                    bgp_peers.append({"peer_ip": ip, "local_as": local_as, "remote_as": ras})
            continue

        i += 1

    # ── Merge numbered ACLs into named_acls ──────────────────────────────────
    for num, data in numbered_acls.items():
        rules = data.get("rules", [])
        if rules:
            named_acls[f"ACL-{num}"] = {"acl_type": data["acl_type"], "rules": rules}

    # ── Build final ACL list ──────────────────────────────────────────────────
    result["acls"] = [
        {"name": name, "acl_type": data["acl_type"], "rules": data["rules"]}
        for name, data in named_acls.items()
        if data["rules"]
    ]

    result["bgp_peers"] = bgp_peers
    return result


# ──────────────────────────────────────────────────────────────────────────────
# File scanner
# ──────────────────────────────────────────────────────────────────────────────

CONFIG_EXTENSIONS = {".cfg", ".conf", ".txt", ".log", ".ios", ".config"}


def scan_folder(folder: Path) -> list[Path]:
    """
    Recursively find files that look like network device running configs.
    Returns only files that pass the is_ios_running_config() heuristic.
    """
    candidates: list[Path] = []
    for ext in CONFIG_EXTENSIONS:
        candidates.extend(folder.rglob(f"*{ext}"))

    results: list[Path] = []
    for path in sorted(candidates):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            if is_ios_running_config(text):
                results.append(path)
        except OSError:
            pass
    return results

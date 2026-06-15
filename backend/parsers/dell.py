"""
TreasureMap — Dell OS10 (PowerSwitch) running-config parser.

Supported platforms:
  Dell EMC PowerSwitch S-series, Z-series (OS10 / Enterprise SONiC)

Detection:
  Requires 'hostname <name>' AND at least one 'interface ethernet' line.
  The 'ethernet' prefix is exclusive to Dell OS10; no other major vendor uses it.

Interface naming examples:
  ethernet1/1/1         — physical ToR port (slot/port/subport)
  ethernet1/1/1:1       — breakout sub-port
  mgmt1/1/1             — management port
  loopback<N>           — loopback
  port-channel<N>       — LAG / port-channel

VLAN modes:
  switchport mode trunk/access
  switchport trunk allowed vlan <list|add <list>>
  switchport access vlan <id>

Returns the same schema as the other TreasureMap parsers:
  {
    "hostname": str,
    "vendor":   "dell",
    "os":       "os10",
    "interfaces": [...],
    "bgp_peers":  [...],
    "source_path": str,
  }
"""
import re

# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def is_dell_os10(text: str) -> bool:
    """Return True if the text looks like a Dell OS10 running config."""
    has_hostname = False
    has_eth_iface = False
    for line in text.splitlines():
        s = line.strip()
        if re.match(r'^hostname\s+\S', s):
            has_hostname = True
        if re.match(r'^interface\s+ethernet', s, re.I):
            has_eth_iface = True
        if has_hostname and has_eth_iface:
            return True
    return False


# ---------------------------------------------------------------------------
# VLAN list helper  (handles "10,20,30"  and  "10-20,30,40-50")
# ---------------------------------------------------------------------------

def _parse_vlan_list(raw: str) -> list[int]:
    vlans: list[int] = []
    for token in re.split(r'[\s,]+', raw.strip()):
        token = token.strip()
        if not token:
            continue
        m = re.match(r'^(\d+)-(\d+)$', token)
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
            vlans.extend(range(lo, hi + 1))
        elif re.match(r'^\d+$', token):
            vlans.append(int(token))
    return sorted(set(vlans))


# ---------------------------------------------------------------------------
# Interface factory
# ---------------------------------------------------------------------------

def _empty_iface(name: str) -> dict:
    return {
        "name":          name,
        "description":   "",
        "ip_address":    None,
        "prefix_length": None,
        "admin_status":  "up",   # OS10 default is admin-up
        "vlan_mode":     "none",
        "vlan_id":       None,
        "trunk_vlans":   [],
        "native_vlan":   None,
        "acl_in":        None,
        "acl_out":       None,
    }


# ---------------------------------------------------------------------------
# Interface block parser
# ---------------------------------------------------------------------------

def _parse_interface_block(lines: list[str], start: int, n: int, iface: dict) -> int:
    """
    Parse one interface block starting just after the 'interface <name>' line.
    Returns the index of the first line AFTER the block.
    """
    i = start
    while i < n:
        raw = lines[i]
        # OS10 interface blocks end at the next non-indented non-comment line
        if raw and not raw[0].isspace() and raw.strip() and not raw.strip().startswith('!'):
            break
        s = raw.strip()
        if not s or s.startswith('!'):
            i += 1
            continue

        # description
        m = re.match(r'^description\s+"?(.+?)"?\s*$', s)
        if m:
            iface["description"] = m.group(1).strip('"')

        # ip address <addr>/<prefix>
        m = re.match(r'^ip address\s+(\d[\d.]+)/(\d+)', s)
        if m:
            iface["ip_address"]    = m.group(1)
            iface["prefix_length"] = int(m.group(2))

        # admin state
        if s == 'no shutdown':
            iface["admin_status"] = "up"
        elif s == 'shutdown':
            iface["admin_status"] = "disabled"

        # switchport mode
        m = re.match(r'^switchport mode (trunk|access)', s)
        if m:
            iface["vlan_mode"] = m.group(1)

        # switchport access vlan
        m = re.match(r'^switchport access vlan (\d+)', s)
        if m:
            iface["vlan_id"]   = int(m.group(1))
            iface["vlan_mode"] = "access"

        # switchport trunk allowed vlan [add] <list>
        m = re.match(r'^switchport trunk allowed vlan(?:\s+add)?\s+(.+)', s)
        if m:
            iface["trunk_vlans"] = _parse_vlan_list(m.group(1))
            if iface["vlan_mode"] == "none":
                iface["vlan_mode"] = "trunk"

        # switchport trunk native vlan
        m = re.match(r'^switchport trunk native vlan (\d+)', s)
        if m:
            iface["native_vlan"] = int(m.group(1))

        # ip access-group <name> in|out
        m = re.match(r'^ip access-group\s+(\S+)\s+(in|out)', s)
        if m:
            if m.group(2) == 'in':
                iface["acl_in"] = m.group(1)
            else:
                iface["acl_out"] = m.group(1)

        i += 1
    return i


# ---------------------------------------------------------------------------
# BGP block parser
# ---------------------------------------------------------------------------

def _parse_bgp_block(lines: list[str], start: int, n: int, local_as: int) -> tuple[int, list[dict]]:
    """Parse a 'router bgp <asn>' block. Returns (next_i, peers_list)."""
    peers = []
    i = start
    while i < n:
        raw = lines[i]
        if raw and not raw[0].isspace() and raw.strip() and not raw.strip().startswith('!'):
            break
        s = raw.strip()
        m = re.match(r'^neighbor\s+(\S+)\s+remote-as\s+(\d+)', s)
        if m:
            peers.append({
                "peer_ip":  m.group(1),
                "remote_as": int(m.group(2)),
                "local_as":  local_as,
            })
        i += 1
    return i, peers


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def parse_dell_os10_config(text: str, source_path: str = '') -> dict:
    """
    Parse a Dell OS10 running config and return a normalised device dict.
    """
    result: dict = {
        "hostname":    "",
        "vendor":      "dell",
        "os":          "os10",
        "interfaces":  [],
        "bgp_peers":   [],
        "source_path": source_path,
    }

    lines = text.splitlines()
    n = len(lines)
    i = 0

    while i < n:
        raw = lines[i]
        s = raw.strip()

        if not s or s.startswith('!'):
            i += 1
            continue

        # hostname
        m = re.match(r'^hostname\s+(\S+)', s)
        if m:
            result["hostname"] = m.group(1)
            i += 1
            continue

        # interface block
        m = re.match(r'^interface\s+(\S+)', s, re.I)
        if m:
            iface_name = m.group(1)
            iface = _empty_iface(iface_name)
            i = _parse_interface_block(lines, i + 1, n, iface)
            result["interfaces"].append(iface)
            continue

        # router bgp
        m = re.match(r'^router bgp (\d+)', s)
        if m:
            local_as = int(m.group(1))
            i, peers = _parse_bgp_block(lines, i + 1, n, local_as)
            result["bgp_peers"].extend(peers)
            continue

        i += 1

    return result

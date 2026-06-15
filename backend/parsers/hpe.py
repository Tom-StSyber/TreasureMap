"""
TreasureMap — HPE Aruba OS-CX running-config parser.

Supported platforms:
  HPE Aruba CX 6000, 6100, 6200, 6300, 6400, 8100, 8320, 8325, 8360 series.

Detection heuristics (require hostname + at least two of):
  • Interface names matching digit/digit/digit  (e.g. 1/1/1)
  • 'vlan trunk allowed' or 'vlan access <id>'  (OS-CX VLAN syntax, NOT 'switchport')
  • 'vrf mgmt'  (OS-CX management VRF construct)

Interface naming:
  1/1/1          — physical port (member/slot/port)
  lag<N>         — LAG / port-channel
  loopback<N>    — loopback
  mgmt           — out-of-band management port (may have 'vrf attach mgmt')
  vlan<N>        — SVI / routed VLAN interface

VLAN modes (OS-CX syntax, no 'switchport' prefix):
  vlan trunk native <id>
  vlan trunk allowed <list>        # comma or space separated, ranges ok
  vlan access <id>

BGP:
  router bgp <asn>
      bgp router-id <ip>
      neighbor <ip> remote-as <asn>

Returns the same schema as all other TreasureMap parsers.
"""
import re

# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def is_hpe_aruba_cx(text: str) -> bool:
    """Return True if text looks like an HPE Aruba OS-CX running config."""
    has_hostname   = False
    has_num_iface  = False   # interface 1/1/1 style
    has_vlan_cmd   = False   # 'vlan trunk' or 'vlan access' (OS-CX style)
    has_vrf_mgmt   = False   # vrf mgmt

    for line in text.splitlines():
        s = line.strip()
        if re.match(r'^hostname\s+\S', s):
            has_hostname = True
        if re.match(r'^interface\s+\d+/\d+/\d+', s):
            has_num_iface = True
        if re.match(r'^\s*(vlan\s+trunk|vlan\s+access\s+\d)', line):
            has_vlan_cmd = True
        if re.match(r'^vrf\s+mgmt', s):
            has_vrf_mgmt = True

    if not has_hostname or not has_num_iface:
        return False
    return has_vlan_cmd or has_vrf_mgmt


# ---------------------------------------------------------------------------
# VLAN list helper  (handles "10,20,30"  "10-20,30"  "10 20 30")
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
        "admin_status":  "up",   # OS-CX default: ports are admin-up
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
    Consume one OS-CX interface block (4-space indent).
    Returns index of first line after the block.
    """
    i = start
    while i < n:
        raw = lines[i]
        # End of block = non-indented, non-blank, non-comment line
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

        # ip address <addr>/<prefix>  (CIDR — OS-CX always uses prefix length)
        m = re.match(r'^ip address\s+(\d[\d.]+)/(\d+)', s)
        if m:
            iface["ip_address"]    = m.group(1)
            iface["prefix_length"] = int(m.group(2))

        # admin state
        if s == 'no shutdown':
            iface["admin_status"] = "up"
        elif s == 'shutdown':
            iface["admin_status"] = "disabled"

        # vrf attach mgmt — mark mgmt interface, no topology significance
        # (just skip)

        # OS-CX VLAN commands (no 'switchport' prefix)
        # vlan access <id>
        m = re.match(r'^vlan access (\d+)', s)
        if m:
            iface["vlan_id"]   = int(m.group(1))
            iface["vlan_mode"] = "access"

        # vlan trunk native <id>
        m = re.match(r'^vlan trunk native (\d+)', s)
        if m:
            iface["native_vlan"] = int(m.group(1))
            if iface["vlan_mode"] == "none":
                iface["vlan_mode"] = "trunk"

        # vlan trunk allowed <list>
        m = re.match(r'^vlan trunk allowed\s+(.+)', s)
        if m:
            raw_list = m.group(1)
            iface["trunk_vlans"] = _parse_vlan_list(raw_list)
            iface["vlan_mode"]   = "trunk"

        # apply access-list ip <name> in|out
        m = re.match(r'^apply access-list ip\s+(\S+)\s+(in|out)', s)
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
                "peer_ip":   m.group(1),
                "remote_as": int(m.group(2)),
                "local_as":  local_as,
            })
        i += 1
    return i, peers


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def parse_hpe_aruba_cx_config(text: str, source_path: str = '') -> dict:
    """
    Parse an HPE Aruba OS-CX running config and return a normalised device dict.
    """
    result: dict = {
        "hostname":    "",
        "vendor":      "hpe",
        "os":          "aruba-cx",
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

        if not s or s.startswith('!') or s == '':
            i += 1
            continue

        # hostname
        m = re.match(r'^hostname\s+(\S+)', s)
        if m:
            result["hostname"] = m.group(1)
            i += 1
            continue

        # interface block — matches: 1/1/1, lag1, loopback0, mgmt, vlan10
        m = re.match(r'^interface\s+(\S+)', s, re.I)
        if m:
            iface_name = m.group(1)
            # Skip management interface (adds no topology value)
            iface = _empty_iface(iface_name)
            i = _parse_interface_block(lines, i + 1, n, iface)
            # Only keep interfaces with some useful data
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

"""
pop_detector.py — Derive POP (Point of Presence) and network role from device hostnames.

Hostname convention: {site}-{location}-{role}-{seq}
Examples:
  eqx-nyc-pe-01  →  POP=EQX-NYC,  role=gateway   (Provider Edge router)
  eqx-nyc-sw-01  →  POP=EQX-NYC,  role=switch
  drt-va-sw-01   →  POP=DRT-VA,   role=switch
  chi-il-fw-01   →  POP=CHI-IL,   role=firewall
  nyc-dc-oob-01  →  POP=NYC-DC,   role=oob

Role keywords and their canonical names:
  pe, ce, br, gw, rtr, router  →  gateway
  sw, switch, agg              →  switch
  fw, asa, pix, firewall       →  firewall
  oob, mgmt, console           →  oob
  lb, f5, netscaler            →  loadbalancer
  ap, wlc, wifi                →  wireless
"""
from __future__ import annotations

import re

# ──────────────────────────────────────────────────────────────────────────────
# Role keyword lookup (lower-case)
# ──────────────────────────────────────────────────────────────────────────────

_ROLE_MAP: dict[str, str] = {
    # Provider/customer edge, gateway, border, WAN router
    "pe": "gateway", "ce": "gateway", "br": "gateway", "gw": "gateway",
    "rtr": "gateway", "router": "gateway", "wan": "gateway",
    "edge": "gateway", "core": "gateway", "cr": "gateway",
    # Access/distribution/aggregation switches
    "sw": "switch", "switch": "switch", "agg": "switch",
    "acc": "switch", "dist": "switch", "tor": "switch",
    # Firewalls
    "fw": "firewall", "asa": "firewall", "pix": "firewall",
    "firewall": "firewall", "pa": "firewall", "ftd": "firewall",
    # Out-of-band / management
    "oob": "oob", "mgmt": "oob", "console": "oob", "kvm": "oob",
    # Load balancers
    "lb": "loadbalancer", "f5": "loadbalancer", "netscaler": "loadbalancer",
    "adc": "loadbalancer",
    # Wireless
    "ap": "wireless", "wlc": "wireless", "wifi": "wireless",
}

# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def detect_pop_and_role(hostname: str) -> tuple[str | None, str | None]:
    """
    Parse *hostname* to extract POP code and network role.

    Returns (pop, role) where either may be None if detection fails.

    Detection strategy:
      1. Split hostname on '-' (most common separator)
      2. Walk token by token; the first token matching a role keyword
         defines the role boundary.
      3. Everything before that boundary is the POP code (joined with '-',
         uppercased).  Everything at/after is the role segment + sequence.
      4. Require at least 3 tokens total; POP portion must be ≥ 2 tokens.
    """
    if not hostname:
        return None, None

    # Normalise: lowercase, strip domain suffix (e.g. .corp.example.com)
    name = hostname.lower().split(".")[0]
    tokens = name.split("-")

    if len(tokens) < 3:
        return None, None

    # Find the first token that matches a role keyword
    role_idx: int | None = None
    for idx, tok in enumerate(tokens):
        if tok in _ROLE_MAP:
            role_idx = idx
            break

    if role_idx is None or role_idx < 2:
        # No role keyword found, or not enough POP tokens
        return None, None

    pop_tokens = tokens[:role_idx]
    role_token = tokens[role_idx]

    pop = "-".join(pop_tokens).upper()
    role = _ROLE_MAP[role_token]

    return pop, role


def enrich_parsed(parsed: dict) -> dict:
    """
    Add 'pop' and 'role' keys to a parsed device dict in-place.
    Returns the same dict.
    """
    pop, role = detect_pop_and_role(parsed.get("hostname", ""))
    parsed["pop"] = pop
    parsed["role"] = role
    return parsed

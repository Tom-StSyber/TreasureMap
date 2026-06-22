"""
TreasureMap — POP (Point of Presence) location detector and device role classifier.

Infers the datacenter POP from device naming conventions used in the lab:
  • Geographic codes: DC, VA, NY, CA, FL, TX, IL, WA, MA, GA, NJ, OH, CO, AZ, OR
  • City codes:       NYC, LAX, DFW, SJC, CHI, ATL, MIA, SEA, BOS, PHX, DEN, IAD
  • Provider codes:   EQX / EQ (Equinix), DRT / DR (Digital Realty / DuPont Fabros)
  • Numeric suffix:   device names are often iterative within a POP (sw-nyc-01, sw-nyc-02)

Device role classification:
  • gateway  — border/edge/PE routers and inter-POP links; prominently displayed in UI
  • oob      — out-of-band management devices (console servers, IPMI, jump hosts)
  • core     — core/distribution switches/routers within a POP
  • access   — access layer / end-device facing
  • unknown  — could not determine

Usage:
    from pop_detector import detect_pop, detect_role, POP_COLORS

    pop  = detect_pop("eqx-nyc-gw-01")   # → "EQX-NYC"
    role = detect_role("eqx-nyc-gw-01", device_type="router")  # → "gateway"
"""
from __future__ import annotations
import re
from typing import Optional

# ──────────────────────────────────────────────────────────────────────────────
# Location token → canonical POP label
# ──────────────────────────────────────────────────────────────────────────────

# Provider prefix tokens (higher priority — match first)
_PROVIDER_TOKENS: dict[str, str] = {
    "eqx":  "EQX",
    "eq":   "EQX",
    "drt":  "DRT",
    "dr":   "DRT",
    "dfr":  "DRT",   # DuPont Fabros variant
    "cyxtera": "CYXTERA",
    "coresite": "CORESITE",
    "iron":  "IRONMTN",   # Iron Mountain
    "qts":   "QTS",
    "nlyte": "NLYTE",
}

# Geographic tokens (city / state / metro) → human-readable city label
_GEO_TOKENS: dict[str, str] = {
    # US States
    "dc":  "Washington DC",
    "va":  "Virginia",
    "ny":  "New York",
    "nyc": "New York",
    "ca":  "California",
    "fl":  "Florida",
    "mia": "Miami",
    "tx":  "Texas",
    "dal": "Dallas",
    "dfw": "Dallas",
    "il":  "Chicago",
    "chi": "Chicago",
    "wa":  "Seattle",
    "sea": "Seattle",
    "ma":  "Boston",
    "bos": "Boston",
    "ga":  "Atlanta",
    "atl": "Atlanta",
    "nj":  "New Jersey",
    "oh":  "Ohio",
    "co":  "Colorado",
    "den": "Denver",
    "az":  "Arizona",
    "phx": "Phoenix",
    "or":  "Oregon",
    "pdx": "Portland",
    # Silicon Valley / SF Bay
    "sjc": "San Jose",
    "sfo": "San Francisco",
    "sv":  "Silicon Valley",
    # Other
    "lax": "Los Angeles",
    "iad": "Ashburn VA",
    "ash": "Ashburn VA",
    "ams": "Amsterdam",
    "lon": "London",
    "lhr": "London",
    "fra": "Frankfurt",
    "sin": "Singapore",
    "syd": "Sydney",
    "tok": "Tokyo",
    "nrt": "Tokyo",
}

# Tokens that indicate a device role within a POP rather than a location
_ROLE_TOKENS = {
    "gw", "gateway", "pe", "p0", "border", "edge", "core",
    "oob", "console", "consvr", "conserver", "mgmt", "iom",
    "jump", "jumpbox", "bastion", "bmc",
    "sw", "switch", "rtr", "router", "fw", "firewall",
    "access", "dist", "distribution", "agg", "aggregation",
}


def _tokenise(hostname: str) -> list[str]:
    """Split hostname on delimiters and return lower-case tokens."""
    # Remove trailing domain
    name = hostname.split(".")[0].lower()
    # Split on -, _, ., digits-alpha or alpha-digits boundaries
    tokens = re.split(r"[-_.]", name)
    # Also split on numeric/alpha transition within tokens
    expanded = []
    for t in tokens:
        parts = re.split(r"(?<=\d)(?=[a-z])|(?<=[a-z])(?=\d)", t)
        expanded.extend(parts)
    return [t for t in expanded if t]


def detect_pop(hostname: str) -> Optional[str]:
    """
    Infer the POP label from a device hostname.

    Returns a canonical POP string like "EQX-NYC", "DRT-VA", "NY", or None if
    no location can be determined.
    """
    tokens = _tokenise(hostname)
    if not tokens:
        return None

    provider: Optional[str] = None
    geo: Optional[str] = None

    for tok in tokens:
        # Skip purely numeric tokens (device index)
        if tok.isdigit():
            continue
        # Skip role tokens
        if tok in _ROLE_TOKENS:
            continue

        if tok in _PROVIDER_TOKENS and provider is None:
            provider = _PROVIDER_TOKENS[tok]
            continue

        if tok in _GEO_TOKENS and geo is None:
            geo = tok.upper()
            continue

    if provider and geo:
        return f"{provider}-{geo}"
    if provider:
        return provider
    if geo:
        return geo
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Device role detection
# ──────────────────────────────────────────────────────────────────────────────

# Token → role mapping (highest priority first)
_GATEWAY_TOKENS = {
    "gw", "gateway", "pe", "border", "edge", "egress", "ingress",
    "core", "cr", "br", "asbr", "abr", "p0", "wan",
}
_OOB_TOKENS = {
    "oob", "console", "consvr", "conserver", "mgmt", "mgmt0", "iom",
    "jump", "jumpbox", "bastion", "bmc", "ipmi", "kvm", "lights",
}


def detect_role(hostname: str, device_type: str = "") -> str:
    """
    Classify a device's functional role within the topology.

    Returns one of: 'gateway', 'oob', 'core', 'access', 'unknown'
    """
    tokens = set(_tokenise(hostname))
    dt = (device_type or "").lower()

    if tokens & _OOB_TOKENS:
        return "oob"

    if tokens & _GATEWAY_TOKENS:
        return "gateway"

    if dt == "firewall":
        return "gateway"   # firewalls are always logically at the border

    if any(t in tokens for t in ("core", "dist", "distribution", "agg", "aggregation", "spine", "leaf")):
        return "core"

    if any(t in tokens for t in ("access", "acc", "tor", "top")):
        return "access"

    return "unknown"


# ──────────────────────────────────────────────────────────────────────────────
# POP box colour palette (used by the frontend to colour-code POP compound nodes)
# ──────────────────────────────────────────────────────────────────────────────

# Stable colour assignment: hash the POP name to one of these background colours.
_POP_PALETTE = [
    "#0f172a",   # slate-900
    "#1e1b4b",   # indigo-950
    "#0c4a6e",   # sky-950
    "#052e16",   # green-950
    "#2d1810",   # custom dark-amber
    "#1a0533",   # custom dark-purple
    "#0a2540",   # custom dark-blue
    "#1f1707",   # custom dark-yellow
]

_POP_BORDER_PALETTE = [
    "#334155",   # slate-600
    "#4338ca",   # indigo-600
    "#0284c7",   # sky-600
    "#16a34a",   # green-600
    "#d97706",   # amber-600
    "#9333ea",   # purple-600
    "#2563eb",   # blue-600
    "#ca8a04",   # yellow-600
]


def pop_colour(pop_name: str) -> dict:
    """Return {background, border} CSS colours for a POP compound node."""
    h = abs(hash(pop_name)) % len(_POP_PALETTE)
    return {
        "background": _POP_PALETTE[h],
        "border":     _POP_BORDER_PALETTE[h],
    }


# ──────────────────────────────────────────────────────────────────────────────
# Batch processing
# ──────────────────────────────────────────────────────────────────────────────

def enrich_devices(devices: list[dict]) -> list[dict]:
    """
    Given a list of device dicts (from Elasticsearch), add/update:
      • pop   — detected POP label (or existing value if already set)
      • role  — gateway | oob | core | access | unknown

    Returns the same list (mutated in place).
    """
    for dev in devices:
        hostname = dev.get("hostname") or dev.get("name") or ""
        device_type = dev.get("device_type", "")

        # Respect manually assigned POPs
        if not dev.get("pop"):
            dev["pop"] = detect_pop(hostname)

        dev["role"] = detect_role(hostname, device_type)

    return devices

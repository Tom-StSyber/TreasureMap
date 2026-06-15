"""
TreasureMap — /pathfind endpoint.

Algorithm:
  1. Build an in-memory graph from ES (devices = nodes, connections = edges).
  2. Resolve source/destination strings to device names (by name, IP, or "internet").
  3. BFS to find the shortest path.
  4. Walk the path edges and evaluate ACL rules at each hop to determine
     whether the requested traffic (protocol/port) is authorised.
  5. Return per-hop results and an overall authorisation verdict.

ACL evaluation follows Cisco/Juniper conventions:
  - Rules evaluated in ascending sequence order.
  - First match wins (permit or deny).
  - Implicit deny-all if no rule matches.
"""
from __future__ import annotations
import ipaddress
from collections import deque
from typing import Optional
from fastapi import APIRouter, HTTPException
from es_client import get_es
from config import IDX_DEVICES, IDX_INTERFACES, IDX_CONNECTIONS, IDX_ACLS
from models import PathRequest, PathResult, HopResult

router = APIRouter(prefix="/pathfind", tags=["pathfind"])

# Well-known service aliases → port numbers
SERVICE_PORTS: dict[str, int] = {
    "ssh": 22, "telnet": 23, "smtp": 25, "dns": 53,
    "http": 80, "https": 443, "snmp": 161, "snmptrap": 162,
    "rdp": 3389, "netconf": 830, "restconf": 443, "bgp": 179,
    "ospf": 89,   # protocol number, not port — handled separately
    "ping": 0,    # maps to icmp
}
SERVICE_PROTOCOLS: dict[str, str] = {
    "ssh": "tcp", "telnet": "tcp", "http": "tcp", "https": "tcp",
    "rdp": "tcp", "smtp": "tcp", "netconf": "tcp", "restconf": "tcp",
    "bgp": "tcp", "dns": "udp", "snmp": "udp", "snmptrap": "udp",
    "ping": "icmp", "ospf": "ospf",
}


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

def _ip_matches(ip: str, network: str) -> bool:
    """Return True if ip falls within network (CIDR) or network == 'any'."""
    if network == "any" or network == "0.0.0.0/0":
        return True
    try:
        return ipaddress.ip_address(ip) in ipaddress.ip_network(network, strict=False)
    except ValueError:
        return False


def _port_matches(rule_port: Optional[int], rule_range: Optional[list],
                  pkt_port: Optional[int]) -> bool:
    """Return True if pkt_port satisfies the rule's port constraint."""
    if rule_port is None and rule_range is None:
        return True  # rule doesn't restrict port
    if pkt_port is None:
        return True  # packet port not specified → assume match (conservative)
    if rule_port is not None and rule_port == pkt_port:
        return True
    if rule_range and rule_range[0] <= pkt_port <= rule_range[1]:
        return True
    return False


def _eval_acl(rules: list[dict], src_ip: str, dst_ip: str,
              protocol: str, dst_port: Optional[int]) -> tuple[str, int | None, str | None]:
    """
    Evaluate ACL rules against packet attributes.
    Returns (action, matched_seq, matched_description).
    """
    for rule in sorted(rules, key=lambda r: r["sequence"]):
        # Protocol check
        rule_proto = rule.get("protocol", "ip").lower()
        if rule_proto not in ("ip", "any") and rule_proto != protocol.lower():
            continue
        # Source IP
        if not _ip_matches(src_ip or "0.0.0.0", rule.get("src_network", "any")):
            continue
        # Destination IP
        if not _ip_matches(dst_ip or "0.0.0.0", rule.get("dst_network", "any")):
            continue
        # Destination port
        if not _port_matches(rule.get("dst_port"), rule.get("dst_port_range"), dst_port):
            continue
        # Source port (rarely used in ACLs but honour it)
        # ... omitted for brevity, uncomment if needed
        return rule["action"], rule["sequence"], rule.get("description")

    # Implicit deny
    return "deny", None, "implicit deny all"


# ─────────────────────────────────────────────────────────────────
# Graph builder
# ─────────────────────────────────────────────────────────────────

def _build_graph(es) -> tuple[dict[str, list[dict]], dict[str, dict]]:
    """
    Build adjacency list and edge-lookup from ES.
    adj[device_name] = [{"neighbor": ..., "conn": {...}}, ...]
    edge_by_id[conn_id] = conn_doc
    """
    conn_hits = es.search(index=IDX_CONNECTIONS,
                          body={"query": {"match_all": {}}, "size": 2000})
    conns = [h["_source"] for h in conn_hits["hits"]["hits"]]

    adj: dict[str, list[dict]] = {}
    edge_by_id: dict[str, dict] = {}

    for c in conns:
        edge_by_id[c["id"]] = c
        # Both directions (undirected graph for path finding)
        for src, dst in [(c["src_device_name"], c["dst_device_name"]),
                         (c["dst_device_name"], c["src_device_name"])]:
            adj.setdefault(src, []).append({"neighbor": dst, "conn": c})

    return adj, edge_by_id


def _bfs(adj: dict, start: str, end: str) -> list[str] | None:
    """BFS — returns list of device names [start, …, end] or None."""
    if start == end:
        return [start]
    visited = {start}
    queue: deque[list[str]] = deque([[start]])
    while queue:
        path = queue.popleft()
        node = path[-1]
        for entry in adj.get(node, []):
            nbr = entry["neighbor"]
            if nbr in visited:
                continue
            new_path = path + [nbr]
            if nbr == end:
                return new_path
            visited.add(nbr)
            queue.append(new_path)
    return None


def _get_conn_between(adj: dict, a: str, b: str) -> dict | None:
    for entry in adj.get(a, []):
        if entry["neighbor"] == b:
            return entry["conn"]
    return None


# ─────────────────────────────────────────────────────────────────
# Device / IP resolver
# ─────────────────────────────────────────────────────────────────

def _resolve_name(es, query: str) -> str:
    """
    Resolve a query string to a device name.
    Accepts: device name, management IP, interface IP, 'internet'.
    """
    q = query.strip().lower()
    if q == "internet":
        return "internet"

    # Try exact device name
    hits = es.search(index=IDX_DEVICES,
                     body={"query": {"term": {"name": q}}, "size": 1})
    if hits["hits"]["hits"]:
        return hits["hits"]["hits"][0]["_source"]["name"]

    # Try management IP
    hits = es.search(index=IDX_DEVICES,
                     body={"query": {"term": {"management_ip": q}}, "size": 1})
    if hits["hits"]["hits"]:
        return hits["hits"]["hits"][0]["_source"]["name"]

    # Try interface IP
    hits = es.search(index=IDX_INTERFACES,
                     body={"query": {"term": {"ip_address": q}}, "size": 1})
    if hits["hits"]["hits"]:
        return hits["hits"]["hits"][0]["_source"]["device_name"]

    raise HTTPException(status_code=404, detail=f"Cannot resolve '{query}' to a known device")


# ─────────────────────────────────────────────────────────────────
# ACL fetch helper
# ─────────────────────────────────────────────────────────────────

def _fetch_acl(es, device_name: str, acl_name: str) -> list[dict]:
    hits = es.search(index=IDX_ACLS,
                     body={"query": {"bool": {"must": [
                         {"term": {"device_name": device_name}},
                         {"term": {"name": acl_name}},
                     ]}}, "size": 1})
    if hits["hits"]["hits"]:
        return hits["hits"]["hits"][0]["_source"].get("rules", [])
    return []


def _fetch_interface(es, device_name: str, iface_name: str) -> dict | None:
    hits = es.search(index=IDX_INTERFACES,
                     body={"query": {"bool": {"must": [
                         {"term": {"device_name": device_name}},
                         {"term": {"name": iface_name}},
                     ]}}, "size": 1})
    if hits["hits"]["hits"]:
        return hits["hits"]["hits"][0]["_source"]
    return None


# ─────────────────────────────────────────────────────────────────
# Main endpoint
# ─────────────────────────────────────────────────────────────────

@router.post("", response_model=PathResult)
def find_path(req: PathRequest):
    es = get_es()

    # Normalise service aliases (e.g. "ssh" → protocol=tcp, port=22)
    protocol = req.protocol
    dst_port = req.dst_port
    if protocol and protocol.lower() in SERVICE_PORTS:
        svc = protocol.lower()
        if dst_port is None:
            dst_port = SERVICE_PORTS[svc] or None
        protocol = SERVICE_PROTOCOLS.get(svc, "tcp")

    # Resolve names
    src_name = _resolve_name(es, req.source)
    dst_name = _resolve_name(es, req.destination)

    # Build graph
    adj, _ = _build_graph(es)

    # BFS
    path = _bfs(adj, src_name, dst_name)
    if not path:
        return PathResult(
            found=False, source=req.source, destination=req.destination,
            protocol=protocol, dst_port=dst_port,
            summary=f"No path found from '{req.source}' to '{req.destination}'.",
        )

    # Walk path and evaluate ACLs at each hop
    hops: list[HopResult] = []
    edge_ids: list[str] = []
    overall_authorized: bool | None = None  # None = no ACLs encountered yet
    deny_at_hop: int | None = None

    src_ip = req.src_ip or ""
    dst_ip = req.destination if _is_ip(req.destination) else ""

    for hop_idx, (node_a, node_b) in enumerate(zip(path[:-1], path[1:]), start=1):
        conn = _get_conn_between(adj, node_a, node_b)
        if not conn:
            continue

        edge_ids.append(conn["id"])

        # Determine which interfaces are on this hop
        # Traffic flows: node_a → node_b
        # src_interface is on node_a, dst_interface is on node_b
        if conn["src_device_name"] == node_a:
            iface_out_name = conn["src_interface"]
            iface_in_name  = conn["dst_interface"]
        else:
            iface_out_name = conn["dst_interface"]
            iface_in_name  = conn["src_interface"]

        hop_status = conn.get("status", "up")
        acl_result = None
        acl_name_used = None
        acl_rule_seq = None
        notes = None

        # Only evaluate ACLs when we have protocol context
        if protocol and (conn.get("has_acl") or conn.get("has_firewall")):
            # Check egress ACL on node_a's outgoing interface
            iface_out = _fetch_interface(es, node_a, iface_out_name)
            if iface_out and iface_out.get("acl_out"):
                aclname = iface_out["acl_out"]
                rules = _fetch_acl(es, node_a, aclname)
                action, seq, desc = _eval_acl(rules, src_ip, dst_ip, protocol, dst_port)
                acl_result = action
                acl_name_used = aclname
                acl_rule_seq = seq
                notes = desc

            # Check ingress ACL on node_b's incoming interface
            iface_in = _fetch_interface(es, node_b, iface_in_name)
            if iface_in and iface_in.get("acl_in") and acl_result != "deny":
                aclname = iface_in["acl_in"]
                rules = _fetch_acl(es, node_b, aclname)
                action, seq, desc = _eval_acl(rules, src_ip, dst_ip, protocol, dst_port)
                acl_result = action
                acl_name_used = aclname
                acl_rule_seq = seq
                notes = desc

            # Check firewall policy (treated as deny-unless-explicit-permit)
            if conn.get("has_firewall") and acl_result != "deny":
                iface_fw = _fetch_interface(es, node_a, iface_out_name) or \
                           _fetch_interface(es, node_b, iface_in_name)
                fw_policy = (iface_fw or {}).get("firewall_policy")
                if fw_policy:
                    rules = _fetch_acl(es, node_a, fw_policy) or \
                            _fetch_acl(es, node_b, fw_policy)
                    if rules:
                        action, seq, desc = _eval_acl(rules, src_ip, dst_ip, protocol, dst_port)
                        acl_result = action
                        acl_name_used = fw_policy
                        acl_rule_seq = seq
                        notes = desc

        # If no ACL was found on an acl-flagged link, note it
        if (conn.get("has_acl") or conn.get("has_firewall")) and acl_result is None and protocol:
            acl_result = "no-acl-data"
            notes = "Link marked as ACL/FW but policy data not in database"

        if not (conn.get("has_acl") or conn.get("has_firewall")):
            acl_result = "no-acl"

        # Update overall authorisation
        if acl_result == "deny":
            if overall_authorized is None or overall_authorized:
                overall_authorized = False
            deny_at_hop = hop_idx
        elif acl_result in ("permit", "no-acl") and overall_authorized is None:
            overall_authorized = True

        hops.append(HopResult(
            hop=hop_idx,
            device_name=node_a,
            interface_in=None if hop_idx == 1 else iface_in_name,
            interface_out=iface_out_name,
            link_status=hop_status,
            acl_result=acl_result,
            acl_name=acl_name_used,
            acl_rule_seq=acl_rule_seq,
            notes=notes,
        ))

    # Add destination hop
    hops.append(HopResult(
        hop=len(path),
        device_name=dst_name,
        interface_in=None,
        interface_out=None,
        link_status="n/a",
        acl_result=None,
        notes="Destination",
    ))

    # Summary
    if not protocol:
        summary = f"Path found: {' → '.join(path)} ({len(path)-1} hops). No protocol specified — ACLs not evaluated."
    elif overall_authorized is False:
        hop = deny_at_hop or "?"
        summary = (f"DENIED at hop {hop}. "
                   f"Traffic {protocol.upper()}"
                   f"{f':{dst_port}' if dst_port else ''} from '{req.source}' to '{req.destination}' "
                   f"is blocked by policy along the path.")
    elif overall_authorized is True:
        summary = (f"PERMITTED. "
                   f"Traffic {protocol.upper()}"
                   f"{f':{dst_port}' if dst_port else ''} from '{req.source}' to '{req.destination}' "
                   f"is authorised on all {len(path)-1} hops.")
    else:
        summary = (f"Path found ({len(path)-1} hops). "
                   f"No ACL data available to evaluate {protocol.upper()} authorisation.")

    return PathResult(
        found=True,
        source=req.source,
        destination=req.destination,
        protocol=protocol,
        dst_port=dst_port,
        authorized=overall_authorized,
        path=path,
        edges=edge_ids,
        hops=hops,
        summary=summary,
    )


def _is_ip(s: str) -> bool:
    try:
        ipaddress.ip_address(s)
        return True
    except ValueError:
        return False


# ─────────────────────────────────────────────────────────────────
# Search endpoint (auto-complete style)
# ─────────────────────────────────────────────────────────────────

@router.get("/search")
def search_nodes(q: str):
    """
    Fuzzy search across device names, IPs, hostnames.
    Used by the frontend auto-complete in the path search panel.
    """
    es = get_es()
    body = {
        "query": {
            "bool": {
                "should": [
                    {"wildcard": {"name": {"value": f"*{q.lower()}*"}}},
                    {"wildcard": {"hostname": {"value": f"*{q.lower()}*"}}},
                    {"term": {"management_ip": q}},
                    {"match": {"tags": q}},
                ]
            }
        },
        "size": 20,
        "_source": ["name", "management_ip", "device_type", "vendor", "location"],
    }
    hits = es.search(index=IDX_DEVICES, body=body)
    return [h["_source"] for h in hits["hits"]["hits"]]

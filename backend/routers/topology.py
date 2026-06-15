"""
TreasureMap — /topology endpoint.
Returns all devices + connections formatted for Cytoscape.js.
"""
from fastapi import APIRouter
from es_client import get_es
from config import IDX_DEVICES, IDX_CONNECTIONS

router = APIRouter(prefix="/topology", tags=["topology"])

# Edge-type → CSS class name (consumed by Cytoscape stylesheet in the frontend)
def _edge_class(conn: dict) -> str:
    """Derive the visual class for a connection record."""
    if conn.get("status") == "disabled":
        return "edge-disabled"
    has_restriction = conn.get("has_acl") or conn.get("has_firewall")
    if has_restriction:
        return "edge-acl"
    if conn.get("link_type") == "trunk":
        return "edge-trunk"
    if conn.get("link_type") == "bgp":
        return "edge-bgp"
    return "edge-up"


@router.get("")
def get_topology():
    """
    Returns Cytoscape.js-ready elements:
      nodes  → one per device
      edges  → one per connection
    """
    es = get_es()

    # Devices
    dev_hits = es.search(index=IDX_DEVICES, body={"query": {"match_all": {}}, "size": 500})
    devices = [h["_source"] for h in dev_hits["hits"]["hits"]]

    # Connections
    conn_hits = es.search(index=IDX_CONNECTIONS, body={"query": {"match_all": {}}, "size": 2000})
    connections = [h["_source"] for h in conn_hits["hits"]["hits"]]

    # Map device_name → device_type for node icons
    dev_type_map = {d["name"]: d["device_type"] for d in devices}

    nodes = [
        {
            "data": {
                "id": d["name"],
                "label": d["name"],
                "device_type": d["device_type"],
                "vendor": d["vendor"],
                "model": d["model"],
                "management_ip": d["management_ip"],
                "os": d["os"],
                "location": d.get("location", ""),
                "tags": d.get("tags", []),
            },
            "classes": f"node-{d['device_type']}",
        }
        for d in devices
    ]

    edges = [
        {
            "data": {
                "id": c["id"],
                "source": c["src_device_name"],
                "target": c["dst_device_name"],
                "src_interface": c["src_interface"],
                "dst_interface": c["dst_interface"],
                "link_type": c["link_type"],
                "status": c["status"],
                "has_acl": c.get("has_acl", False),
                "has_firewall": c.get("has_firewall", False),
                "bandwidth_mbps": c.get("bandwidth_mbps"),
                "description": c.get("description", ""),
            },
            "classes": _edge_class(c),
        }
        for c in connections
    ]

    return {"nodes": nodes, "edges": edges}


@router.get("/summary")
def get_topology_summary():
    """High-level counts for the textual overview panel."""
    es = get_es()
    from config import IDX_INTERFACES, IDX_ACLS

    def _count(index, query=None):
        body = {"query": query or {"match_all": {}}}
        return es.count(index=index, body=body)["count"]

    return {
        "devices":     _count(IDX_DEVICES),
        "interfaces":  _count(IDX_INTERFACES),
        "connections": _count(IDX_CONNECTIONS),
        "acls":        _count(IDX_ACLS),
        "links_up":      _count(IDX_CONNECTIONS, {"term": {"status": "up"}}),
        "links_disabled": _count(IDX_CONNECTIONS, {"term": {"status": "disabled"}}),
        "links_with_acl": _count(IDX_CONNECTIONS, {"term": {"has_acl": True}}),
        "trunk_links":    _count(IDX_CONNECTIONS, {"term": {"link_type": "trunk"}}),
    }

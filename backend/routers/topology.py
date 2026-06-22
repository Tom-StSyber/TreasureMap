"""
TreasureMap — /topology endpoint.
Returns all devices + connections formatted for Cytoscape.js.

POP compound nodes:
  Devices that share a POP label are grouped under a parent compound node.
  The parent node carries the POP label and a colour hint the frontend uses
  to draw the labelled box.  Devices with no detected POP go in a synthetic
  "__unassigned__" parent so they still render correctly (the frontend hides
  that parent's border/background).
"""
from fastapi import APIRouter
from es_client import get_es
from config import IDX_DEVICES, IDX_CONNECTIONS
from pop_detector import pop_colour, detect_pop, detect_role

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
    return "edge-up"


def _node_classes(d: dict) -> str:
    """Compose CSS class string for a device node."""
    classes = [f"node-{d['device_type']}"]
    role = d.get("role") or detect_role(d.get("hostname", d["name"]), d["device_type"])
    if role == "gateway":
        classes.append("node-role-gateway")
    elif role == "oob":
        classes.append("node-role-oob")
    elif role == "core":
        classes.append("node-role-core")
    return " ".join(classes)


@router.get("")
def get_topology():
    """
    Returns Cytoscape.js-ready elements:
      pop_nodes → one compound (parent) node per POP
      nodes     → one per device (with parent set to its POP)
      edges     → one per connection
    """
    es = get_es()

    # Devices
    dev_hits = es.search(index=IDX_DEVICES, body={"query": {"match_all": {}}, "size": 500})
    devices = [h["_source"] for h in dev_hits["hits"]["hits"]]

    # Connections
    conn_hits = es.search(index=IDX_CONNECTIONS, body={"query": {"match_all": {}}, "size": 2000})
    connections = [h["_source"] for h in conn_hits["hits"]["hits"]]

    # Collect distinct POP labels; enrich devices missing pop/role on the fly
    pops_seen: dict[str, dict] = {}   # pop_id → colour info
    for d in devices:
        if not d.get("pop"):
            d["pop"] = detect_pop(d.get("hostname", d["name"]))
        if not d.get("role"):
            d["role"] = detect_role(d.get("hostname", d["name"]), d["device_type"])

        pop_id = d["pop"] or "__unassigned__"
        if pop_id not in pops_seen:
            pops_seen[pop_id] = pop_colour(pop_id)

    # Build POP compound nodes (parents)
    pop_nodes = []
    for pop_id, colours in pops_seen.items():
        if pop_id == "__unassigned__":
            # Hidden parent — unassigned devices still belong to it so compound
            # layout works, but the UI renders it invisibly.
            pop_nodes.append({
                "data": {
                    "id":    "__unassigned__",
                    "label": "",
                    "pop":   "",
                    "bg":    "transparent",
                    "border":"transparent",
                },
                "classes": "pop-unassigned",
            })
        else:
            pop_nodes.append({
                "data": {
                    "id":    f"pop-{pop_id}",
                    "label": pop_id,
                    "pop":   pop_id,
                    "bg":    colours["background"],
                    "border":colours["border"],
                },
                "classes": "pop-box",
            })

    # Build device nodes
    nodes = []
    for d in devices:
        pop_id = d.get("pop")
        parent_id = f"pop-{pop_id}" if pop_id else "__unassigned__"
        nodes.append({
            "data": {
                "id":            d["name"],
                "label":         d["name"],
                "parent":        parent_id,
                "device_type":   d["device_type"],
                "vendor":        d["vendor"],
                "model":         d["model"],
                "management_ip": d["management_ip"],
                "os":            d["os"],
                "location":      d.get("location", ""),
                "pop":           d.get("pop", ""),
                "role":          d.get("role", "unknown"),
                "tags":          d.get("tags", []),
            },
            "classes": _node_classes(d),
        })

    edges = [
        {
            "data": {
                "id":            c["id"],
                "source":        c["src_device_name"],
                "target":        c["dst_device_name"],
                "src_interface": c["src_interface"],
                "dst_interface": c["dst_interface"],
                "link_type":     c["link_type"],
                "status":        c["status"],
                "has_acl":       c.get("has_acl", False),
                "has_firewall":  c.get("has_firewall", False),
                "bandwidth_mbps":c.get("bandwidth_mbps"),
                "description":   c.get("description", ""),
            },
            "classes": _edge_class(c),
        }
        for c in connections
    ]

    return {"nodes": pop_nodes + nodes, "edges": edges}


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

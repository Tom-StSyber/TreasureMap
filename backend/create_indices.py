from elasticsearch import Elasticsearch

es = Elasticsearch("http://localhost:9200")

indices = {
    "devices": {
        "mappings": {
            "properties": {
                "hostname":   {"type": "keyword"},
                "ip":         {"type": "ip"},
                "vendor":     {"type": "keyword"},
                "model":      {"type": "keyword"},
                "os_version": {"type": "keyword"},
                "location":   {"type": "keyword"},
                "updated_at": {"type": "date"}
            }
        }
    },
    "interfaces": {
        "mappings": {
            "properties": {
                "device":      {"type": "keyword"},
                "name":        {"type": "keyword"},
                "ip":          {"type": "ip"},
                "prefix_len":  {"type": "integer"},
                "vlan_id":     {"type": "integer"},
                "admin_up":    {"type": "boolean"},
                "oper_up":     {"type": "boolean"},
                "speed_mbps":  {"type": "integer"},
                "description": {"type": "text"}
            }
        }
    },
    "links": {
        "mappings": {
            "properties": {
                "src_device": {"type": "keyword"},
                "src_port":   {"type": "keyword"},
                "dst_device": {"type": "keyword"},
                "dst_port":   {"type": "keyword"},
                "link_type":  {"type": "keyword"},  # trunk, access, routed
                "vlans":      {"type": "integer"}   # array of vlan IDs on trunk
            }
        }
    },
    "acls": {
        "mappings": {
            "properties": {
                "device":          {"type": "keyword"},
                "acl_name":        {"type": "keyword"},
                "direction":       {"type": "keyword"},  # in/out
                "interface":       {"type": "keyword"},
                "rules":           {"type": "object", "enabled": False}  # store raw, don't index
            }
        }
    },
    "vlans": {
        "mappings": {
            "properties": {
                "vlan_id":    {"type": "integer"},
                "name":       {"type": "keyword"},
                "device":     {"type": "keyword"},
                "interfaces": {"type": "keyword"}
            }
        }
    }
}

for name, body in indices.items():
    if not es.indices.exists(index=name):
        es.indices.create(index=name, body=body)
        print(f"Created index: {name}")
    else:
        print(f"Index already exists: {name}")
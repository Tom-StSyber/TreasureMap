"""
TreasureMap — Elasticsearch client + index bootstrap.
"""
from elasticsearch import Elasticsearch, NotFoundError
from config import (
    ELASTICSEARCH_URL,
    IDX_DEVICES, IDX_INTERFACES, IDX_CONNECTIONS, IDX_ACLS,
)
import logging

log = logging.getLogger(__name__)

_client: Elasticsearch | None = None


def get_es() -> Elasticsearch:
    global _client
    if _client is None:
        _client = Elasticsearch(ELASTICSEARCH_URL, request_timeout=30)
    return _client


# ---------------------------------------------------------------------------
# Index mappings
# ---------------------------------------------------------------------------

MAPPINGS = {
    IDX_DEVICES: {
        "mappings": {
            "properties": {
                "id":            {"type": "keyword"},
                "name":          {"type": "keyword"},
                "hostname":      {"type": "keyword"},
                "management_ip": {"type": "ip"},
                "vendor":        {"type": "keyword"},
                "model":         {"type": "keyword"},
                "os":            {"type": "keyword"},
                "device_type":   {"type": "keyword"},
                "location":      {"type": "keyword"},
                "tags":          {"type": "keyword"},
                "pop":           {"type": "keyword"},
                "role":          {"type": "keyword"},
            }
        }
    },
    IDX_INTERFACES: {
        "mappings": {
            "properties": {
                "id":             {"type": "keyword"},
                "device_id":      {"type": "keyword"},
                "device_name":    {"type": "keyword"},
                "name":           {"type": "keyword"},
                "description":    {"type": "text"},
                "ip_address":     {"type": "ip"},
                "prefix_length":  {"type": "integer"},
                "mac_address":    {"type": "keyword"},
                "admin_status":   {"type": "keyword"},
                "oper_status":    {"type": "keyword"},
                "speed_mbps":     {"type": "integer"},
                "duplex":         {"type": "keyword"},
                "vlan_mode":      {"type": "keyword"},
                "vlan_id":        {"type": "integer"},
                "trunk_vlans":    {"type": "integer"},
                "native_vlan":    {"type": "integer"},
                "acl_in":         {"type": "keyword"},
                "acl_out":        {"type": "keyword"},
                "firewall_policy":{"type": "keyword"},
            }
        }
    },
    IDX_CONNECTIONS: {
        "mappings": {
            "properties": {
                "id":               {"type": "keyword"},
                "src_device_id":    {"type": "keyword"},
                "src_device_name":  {"type": "keyword"},
                "src_interface":    {"type": "keyword"},
                "dst_device_id":    {"type": "keyword"},
                "dst_device_name":  {"type": "keyword"},
                "dst_interface":    {"type": "keyword"},
                "link_type":        {"type": "keyword"},
                "status":           {"type": "keyword"},
                "has_acl":          {"type": "boolean"},
                "has_firewall":     {"type": "boolean"},
                "bandwidth_mbps":   {"type": "integer"},
                "description":      {"type": "text"},
            }
        }
    },
    IDX_ACLS: {
        "mappings": {
            "properties": {
                "id":          {"type": "keyword"},
                "device_id":   {"type": "keyword"},
                "device_name": {"type": "keyword"},
                "name":        {"type": "keyword"},
                "acl_type":    {"type": "keyword"},
                "rules":       {"type": "object", "enabled": False},  # stored as nested JSON
            }
        }
    },
}


def bootstrap_indices():
    """Create indices with mappings if they don't exist."""
    es = get_es()
    for index, body in MAPPINGS.items():
        if not es.indices.exists(index=index):
            es.indices.create(index=index, body=body)
            log.info("Created index: %s", index)
        else:
            log.info("Index already exists: %s", index)


def wipe_indices():
    """Drop and recreate all TreasureMap indices (used by the ingest script)."""
    es = get_es()
    for index in MAPPINGS:
        try:
            es.indices.delete(index=index)
            log.info("Deleted index: %s", index)
        except NotFoundError:
            pass
    bootstrap_indices()

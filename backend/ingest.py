"""
TreasureMap — Data ingest script.

Modes:
  python ingest.py                    # load built-in sample network data
  python ingest.py --samples          # also parse sample Juniper/Huawei configs
  python ingest.py --config-dir PATH  # parse all .txt/.conf/.cfg files in PATH
  python ingest.py --no-wipe          # append without dropping existing indices

Run from the backend/ directory.
"""
import sys
import os
import argparse
import logging
import uuid

sys.path.insert(0, ".")

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger(__name__)


# ── Vendor detection ────────────────────────────────────────────────

def _detect_vendor(raw: str) -> str:
    head = "\n".join(raw.splitlines()[:200]).lower()
    if "juniper" in head or "junos" in head or "set system host-name" in head:
        return "juniper"
    if "huawei" in head or "vrp" in head or "sysname " in head:
        return "huawei"
    return "cisco"


def _parse_config(raw: str, vendor: str, hostname: str) -> dict:
    if vendor == "juniper":
        from parsers.juniper import parse_junos
        return parse_junos(raw, hostname)
    if vendor == "huawei":
        from parsers.huawei import parse_huawei
        return parse_huawei(raw, hostname)
    from parsers.cisco import parse_cisco_ios
    return parse_cisco_ios(raw, hostname)


# ── ES helpers ──────────────────────────────────────────────────────

def _bulk_index(es, index: str, docs: list, id_field: str = "id"):
    if not docs:
        return
    ops = []
    for doc in docs:
        doc_dict = doc.model_dump() if hasattr(doc, "model_dump") else dict(doc)
        ops.append({"index": {"_index": index, "_id": doc_dict[id_field]}})
        ops.append(doc_dict)
    result = es.bulk(body=ops, refresh=True)
    errors = [item for item in result["items"] if "error" in item.get("index", {})]
    if errors:
        log.error("Bulk index errors: %s", errors)
    log.info("  Indexed %d docs into %s", len(docs), index)


def _upsert_parsed(es, parsed: dict, IDX_DEVICES, IDX_INTERFACES, IDX_ACLS):
    """Write a parsed config result into Elasticsearch."""
    from pop_detector import detect_pop, detect_role

    dev = parsed["device"]
    dev_name = dev["name"]

    if not dev.get("pop"):
        dev["pop"] = detect_pop(dev_name)
    dev["role"] = detect_role(dev_name, dev.get("device_type", ""))

    dev_id = str(uuid.uuid4())
    dev["id"] = dev_id
    es.index(index=IDX_DEVICES, id=dev_id, document=dev, refresh=True)
    log.info("  Device: %s  vendor=%s  pop=%s  role=%s",
             dev_name, dev["vendor"], dev.get("pop"), dev.get("role"))

    for iface in parsed.get("interfaces", []):
        iface["device_id"]   = dev_id
        iface["device_name"] = dev_name
        iface_id = str(uuid.uuid5(uuid.UUID(dev_id), iface["name"]))
        iface["id"] = iface_id
        es.index(index=IDX_INTERFACES, id=iface_id, document=iface, refresh=True)

    for acl in parsed.get("acls", []):
        acl["device_id"]   = dev_id
        acl["device_name"] = dev_name
        acl_id = str(uuid.uuid5(uuid.UUID(dev_id), acl["name"]))
        acl["id"] = acl_id
        es.index(index=IDX_ACLS, id=acl_id, document=acl, refresh=True)

    log.info("  Interfaces: %d, ACLs: %d",
             len(parsed.get("interfaces", [])), len(parsed.get("acls", [])))


# ── Sample network data loader ──────────────────────────────────────

def _load_sample_network(es, IDX_DEVICES, IDX_INTERFACES, IDX_CONNECTIONS, IDX_ACLS):
    from data.sample_network import all_data
    data = all_data()

    # Enrich sample devices with POP/role
    from pop_detector import detect_pop, detect_role
    for dev in data["devices"]:
        dev_dict = dev.model_dump() if hasattr(dev, "model_dump") else dict(dev)
        if not dev_dict.get("pop"):
            dev_dict["pop"] = detect_pop(dev_dict.get("hostname", dev_dict["name"]))
        dev_dict["role"] = detect_role(dev_dict.get("hostname", dev_dict["name"]),
                                       dev_dict.get("device_type", ""))

    log.info("Indexing sample devices …")
    _bulk_index(es, IDX_DEVICES, data["devices"])
    log.info("Indexing sample interfaces …")
    _bulk_index(es, IDX_INTERFACES, data["interfaces"])
    log.info("Indexing sample connections …")
    _bulk_index(es, IDX_CONNECTIONS, data["connections"])
    log.info("Indexing sample ACLs …")
    _bulk_index(es, IDX_ACLS, data["acls"])


# ── Sample config files (Juniper / Huawei) ─────────────────────────

_SAMPLE_CONFIGS = [
    ("data/sample_junos.txt",     "juniper"),
    ("data/sample_junos_set.txt", "juniper"),
    ("data/sample_huawei.txt",    "huawei"),
]


def _load_sample_configs(es, IDX_DEVICES, IDX_INTERFACES, IDX_ACLS):
    for path, vendor in _SAMPLE_CONFIGS:
        if not os.path.exists(path):
            log.warning("Sample config not found: %s", path)
            continue
        log.info("Parsing sample config: %s (%s)", path, vendor)
        with open(path, encoding="utf-8", errors="replace") as fh:
            raw = fh.read()
        parsed = _parse_config(raw, vendor, "unknown")
        _upsert_parsed(es, parsed, IDX_DEVICES, IDX_INTERFACES, IDX_ACLS)


def _load_config_dir(es, config_dir: str, IDX_DEVICES, IDX_INTERFACES, IDX_ACLS):
    exts = {".txt", ".conf", ".cfg", ".log"}
    count = 0
    for fname in sorted(os.listdir(config_dir)):
        if not any(fname.endswith(e) for e in exts):
            continue
        fpath = os.path.join(config_dir, fname)
        log.info("Processing: %s", fpath)
        with open(fpath, encoding="utf-8", errors="replace") as fh:
            raw = fh.read()
        vendor = _detect_vendor(raw)
        # Use stem as hostname hint
        hostname = os.path.splitext(fname)[0]
        try:
            parsed = _parse_config(raw, vendor, hostname)
            _upsert_parsed(es, parsed, IDX_DEVICES, IDX_INTERFACES, IDX_ACLS)
            count += 1
        except Exception as exc:
            log.error("Failed to parse %s: %s", fpath, exc)
    log.info("Config dir ingest done: %d files processed", count)


# ── Main ────────────────────────────────────────────────────────────

def run(wipe: bool = True, load_samples: bool = False, config_dir: str = None):
    from es_client import get_es, bootstrap_indices, wipe_indices
    from config import IDX_DEVICES, IDX_INTERFACES, IDX_CONNECTIONS, IDX_ACLS

    es = get_es()
    try:
        es.info()
    except Exception as exc:
        log.error("Cannot reach Elasticsearch: %s", exc)
        sys.exit(1)

    if wipe:
        log.info("Wiping and recreating indices …")
        wipe_indices()
    else:
        log.info("Bootstrapping indices (no wipe) …")
        bootstrap_indices()

    # Always load the built-in synthetic sample network
    log.info("Loading built-in sample network …")
    _load_sample_network(es, IDX_DEVICES, IDX_INTERFACES, IDX_CONNECTIONS, IDX_ACLS)

    if load_samples:
        log.info("Loading sample Juniper/Huawei config files …")
        _load_sample_configs(es, IDX_DEVICES, IDX_INTERFACES, IDX_ACLS)

    if config_dir:
        log.info("Loading configs from directory: %s", config_dir)
        _load_config_dir(es, config_dir, IDX_DEVICES, IDX_INTERFACES, IDX_ACLS)

    log.info("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load data into TreasureMap Elasticsearch")
    parser.add_argument("--no-wipe",    dest="wipe",    action="store_false",
                        help="Don't wipe existing indices before loading")
    parser.add_argument("--samples",    dest="samples", action="store_true",
                        help="Also parse sample Juniper/Huawei config files")
    parser.add_argument("--config-dir", dest="config_dir", default=None,
                        metavar="PATH",
                        help="Directory of device config files to parse and ingest")
    parser.set_defaults(wipe=True, samples=False)
    args = parser.parse_args()

    run(wipe=args.wipe, load_samples=args.samples, config_dir=args.config_dir)

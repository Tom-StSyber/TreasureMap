"""
TreasureMap — /ingest endpoints.

POST /ingest/config
    Upload a device config file for parsing. Auto-detects vendor from
    the file content. Returns parsed device/interface/acl data and
    writes it to Elasticsearch.

PATCH /ingest/devices/{name}/pop
    Manually assign a device to a POP (for devices whose name does not
    match any auto-detection pattern).

GET /ingest/pops
    List all known POP labels (from devices that have a pop field set).
"""
from __future__ import annotations
import logging
import uuid
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional

from es_client import get_es
from config import IDX_DEVICES, IDX_INTERFACES, IDX_ACLS
from models import Device, Interface, Acl, AclRule
from pop_detector import detect_pop, detect_role

router = APIRouter(prefix="/ingest", tags=["ingest"])
log = logging.getLogger(__name__)

# Maximum accepted config upload. Generous headroom over real-world configs
# (a large stacked/chassis running-config with show-tech appended is well under
# this); the cap exists to stop unbounded/oversized uploads from exhausting
# memory. See SECURITY_REVIEW.md M-4. Bump if a legitimate file ever exceeds it.
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB


async def _read_capped(upload: UploadFile, cap: int) -> bytes:
    """
    Read an UploadFile in chunks, aborting with HTTP 413 as soon as the
    cumulative size exceeds `cap`. Never buffers more than `cap` bytes, so a
    hostile or accidental huge upload cannot blow up API memory.
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(1024 * 1024)  # 1 MB at a time
        if not chunk:
            break
        total += len(chunk)
        if total > cap:
            raise HTTPException(
                status_code=413,
                detail=f"Config file exceeds the {cap // (1024 * 1024)} MB upload limit.",
            )
        chunks.append(chunk)
    return b"".join(chunks)


# ──────────────────────────────────────────────────────────────────────────────
# Vendor auto-detection
# ──────────────────────────────────────────────────────────────────────────────

def _detect_vendor(raw: str) -> str:
    """Heuristic: scan first 200 lines for vendor signatures."""
    head = "\n".join(raw.splitlines()[:200]).lower()

    if "juniper" in head or "junos" in head or "set system host-name" in head:
        return "juniper"
    if "huawei" in head or "vrp" in head or "sysname " in head:
        return "huawei"
    if "cisco" in head or "ios" in head or "nx-os" in head or "hostname " in head:
        return "cisco"
    if "extreme" in head or "extremexos" in head or "exos" in head:
        return "extreme"
    if "nokia" in head or "timos" in head or "sr-os" in head:
        return "nokia"

    # Fall back to Cisco — most common
    return "cisco"


def _parse_config(raw: str, vendor: str, hostname: str) -> dict:
    """Dispatch to the correct parser."""
    if vendor == "juniper":
        from parsers.juniper import parse_junos
        return parse_junos(raw, hostname)
    if vendor == "huawei":
        from parsers.huawei import parse_huawei
        return parse_huawei(raw, hostname)
    # Default: Cisco IOS
    from parsers.cisco import parse_cisco_ios
    return parse_cisco_ios(raw, hostname)


# ──────────────────────────────────────────────────────────────────────────────
# Config upload endpoint
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/config")
async def ingest_config(
    file:     UploadFile = File(...),
    hostname: str        = Form("unknown"),
    vendor:   str        = Form("auto"),
):
    """
    Parse a device configuration file and load it into Elasticsearch.

    Form fields:
      file      — the config file
      hostname  — device hostname (used as the document ID; auto-detected if "unknown")
      vendor    — cisco | juniper | huawei | auto (default: auto)
    """
    raw = (await _read_capped(file, MAX_UPLOAD_BYTES)).decode("utf-8", errors="replace")

    # Auto-detect vendor
    resolved_vendor = vendor if vendor != "auto" else _detect_vendor(raw)
    log.info("Ingesting config from %s, vendor=%s, hostname_hint=%s",
             file.filename, resolved_vendor, hostname)

    try:
        parsed = _parse_config(raw, resolved_vendor, hostname)
    except Exception as exc:
        log.exception("Parse error")
        raise HTTPException(status_code=422, detail=f"Parse error: {exc}")

    dev_data   = parsed["device"]
    ifaces     = parsed.get("interfaces", [])
    acls_data  = parsed.get("acls", [])

    # Resolve POP and role
    dev_name = dev_data["name"]
    if not dev_data.get("pop"):
        dev_data["pop"] = detect_pop(dev_name)
    dev_data["role"] = detect_role(dev_name, dev_data.get("device_type", ""))

    es = get_es()

    # ── Upsert device ──────────────────────────────────────────
    existing = es.search(
        index=IDX_DEVICES,
        body={"query": {"term": {"name": dev_name}}, "size": 1},
    )
    if existing["hits"]["hits"]:
        doc_id = existing["hits"]["hits"][0]["_id"]
        existing_doc = existing["hits"]["hits"][0]["_source"]
        # Preserve manually assigned POP if already set
        if existing_doc.get("pop") and not dev_data.get("pop"):
            dev_data["pop"] = existing_doc["pop"]
    else:
        doc_id = dev_data.get("id") or str(uuid.uuid4())

    dev_data["id"] = doc_id
    es.index(index=IDX_DEVICES, id=doc_id, document=dev_data, refresh=True)

    # ── Upsert interfaces ──────────────────────────────────────
    iface_count = 0
    for iface in ifaces:
        iface["device_id"]   = doc_id
        iface["device_name"] = dev_name
        iface_id = str(uuid.uuid5(uuid.UUID(doc_id) if _is_uuid(doc_id) else uuid.uuid4(),
                                  iface["name"]))
        iface["id"] = iface_id
        es.index(index=IDX_INTERFACES, id=iface_id, document=iface, refresh=True)
        iface_count += 1

    # ── Upsert ACLs ────────────────────────────────────────────
    acl_count = 0
    for acl in acls_data:
        acl["device_id"]   = doc_id
        acl["device_name"] = dev_name
        acl_id = str(uuid.uuid5(uuid.UUID(doc_id) if _is_uuid(doc_id) else uuid.uuid4(),
                                 acl["name"]))
        acl["id"] = acl_id
        es.index(index=IDX_ACLS, id=acl_id, document=acl, refresh=True)
        acl_count += 1

    return {
        "status":     "ok",
        "device":     dev_name,
        "vendor":     resolved_vendor,
        "pop":        dev_data.get("pop"),
        "role":       dev_data.get("role"),
        "interfaces": iface_count,
        "acls":       acl_count,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Manual POP assignment
# ──────────────────────────────────────────────────────────────────────────────

class PopAssign(BaseModel):
    pop: str


@router.patch("/devices/{name}/pop")
def assign_pop(name: str, body: PopAssign):
    """
    Manually assign a device to a POP.
    Used when auto-detection fails and the user right-clicks → Assign to POP.
    """
    es = get_es()
    hits = es.search(
        index=IDX_DEVICES,
        body={"query": {"term": {"name": name}}, "size": 1},
    )
    if not hits["hits"]["hits"]:
        raise HTTPException(status_code=404, detail=f"Device '{name}' not found")

    doc_id = hits["hits"]["hits"][0]["_id"]
    es.update(
        index=IDX_DEVICES,
        id=doc_id,
        body={"doc": {"pop": body.pop}},
        refresh=True,
    )
    return {"status": "ok", "device": name, "pop": body.pop}


# ──────────────────────────────────────────────────────────────────────────────
# List POPs
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/pops")
def list_pops():
    """Return all distinct POP labels present in the device index."""
    es = get_es()
    resp = es.search(
        index=IDX_DEVICES,
        body={
            "size": 0,
            "aggs": {
                "pops": {
                    "terms": {"field": "pop", "size": 200, "missing": "__unassigned__"}
                }
            }
        }
    )
    buckets = resp.get("aggregations", {}).get("pops", {}).get("buckets", [])
    return [
        {"pop": b["key"], "count": b["doc_count"]}
        for b in buckets
        if b["key"] != "__unassigned__"
    ]


# ──────────────────────────────────────────────────────────────────────────────
# Connection discovery
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/discover-connections")
def discover_connections():
    """
    Run the automatic connection discovery engine against all devices and
    interfaces currently in Elasticsearch.

    Three strategies are applied in order:
      1. subnet    — interface pairs sharing a /29-/31 subnet
      2. description — interface descriptions that name a known device
      3. cdp_lldp  — CDP/LLDP neighbor blocks embedded in config exports

    Returns counts of connections found, written, and skipped (duplicates).
    """
    from connection_discovery import discover_connections as _discover
    try:
        result = _discover()
        return result
    except Exception as exc:
        log.exception("Connection discovery failed")
        raise HTTPException(status_code=500, detail=str(exc))


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _is_uuid(s: str) -> bool:
    try:
        uuid.UUID(s)
        return True
    except (ValueError, AttributeError):
        return False

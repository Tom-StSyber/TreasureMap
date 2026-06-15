"""
ingest_batfish.py — Cisco IOS running-config → Elasticsearch ingestion.

Reads .cfg files from data/samples/batfish/tests/roles/networks/example/configs/,
parses hostname / interfaces / BGP / OSPF from each running config, and bulk-indexes
the structured results into ES as command="running-config" documents.

Usage:
    python backend/ingest_batfish.py [--configs-dir PATH] [--es-url URL] [--index NAME] [--dry-run]
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk, BulkIndexError

CONFIGS_DIR = (
    Path(__file__).parent.parent
    / "data" / "samples" / "batfish"
    / "tests" / "roles" / "networks" / "example" / "configs"
)
ES_URL = "http://localhost:9200"
INDEX_NAME = "network-configs"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ingest_batfish")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_IP_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")


def _is_ip(s: str) -> bool:
    return bool(_IP_RE.match(s))


def _mask_to_prefix(mask: str) -> str:
    """Convert dotted-quad mask to prefix length string, e.g. '255.255.255.0' → '24'."""
    try:
        return str(ipaddress.IPv4Network(f"0.0.0.0/{mask}", strict=False).prefixlen)
    except ValueError:
        return ""


# ---------------------------------------------------------------------------
# Running-config parser
# ---------------------------------------------------------------------------

def parse_ios_config(text: str) -> dict:
    """
    Parse a Cisco IOS running config into structured data.

    Returns:
        {
          hostname: str,
          version:  str,
          interfaces: [
            {name, ip, mask, prefix_length, cidr, description, shutdown}
          ],
          bgp: {local_as, router_id, peers: [{ip, remote_as}]} | None,
          ospf: [{process_id, router_id, networks: [{network, wildcard, area}]}],
        }
    """
    result: dict = {
        "hostname": "",
        "version": "",
        "interfaces": [],
        "bgp": None,
        "ospf": [],
    }

    lines = text.splitlines()
    total = len(lines)
    i = 0

    while i < total:
        raw = lines[i]
        line = raw.strip()

        # ---- Top-level directives ----------------------------------------
        if line.startswith("hostname "):
            result["hostname"] = line.split(None, 1)[1].strip()
            i += 1
            continue

        if line.startswith("version "):
            result["version"] = line.split(None, 1)[1].strip()
            i += 1
            continue

        # ---- Interface block ---------------------------------------------
        if line.startswith("interface "):
            iface_name = line.split(None, 1)[1].strip()
            iface: dict = {
                "name": iface_name,
                "ip": "",
                "mask": "",
                "prefix_length": "",
                "cidr": "",
                "description": "",
                "shutdown": False,
            }
            i += 1
            while i < total:
                sub_raw = lines[i]
                # Interface sub-commands are indented with exactly one space
                if sub_raw and not sub_raw[0].isspace():
                    break
                sub = sub_raw.strip()
                if sub.startswith("ip address ") and "dhcp" not in sub and "secondary" not in sub:
                    parts = sub.split()
                    if len(parts) >= 4:
                        iface["ip"] = parts[2]
                        iface["mask"] = parts[3]
                        iface["prefix_length"] = _mask_to_prefix(parts[3])
                        if iface["ip"] and iface["prefix_length"]:
                            iface["cidr"] = f"{iface['ip']}/{iface['prefix_length']}"
                elif sub == "shutdown":
                    iface["shutdown"] = True
                elif sub.startswith("description "):
                    iface["description"] = sub.split(None, 1)[1].strip()
                i += 1
            result["interfaces"].append(iface)
            continue  # i already advanced

        # ---- BGP block ---------------------------------------------------
        if line.startswith("router bgp "):
            local_as = int(line.split()[2])
            bgp: dict = {
                "local_as": local_as,
                "router_id": "",
                "peer_groups": {},   # name → remote_as (internal, not returned)
                "peers": [],         # [{ip, remote_as}]
            }
            # Collect raw neighbor stmts for two-pass peer-group resolution
            peer_group_members: list[tuple[str, str]] = []  # (ip, group_name)

            i += 1
            while i < total:
                sub_raw = lines[i]
                if sub_raw and not sub_raw[0].isspace():
                    break
                sub = sub_raw.strip()

                if sub.startswith("bgp router-id "):
                    bgp["router_id"] = sub.split()[2]

                elif sub.startswith("neighbor "):
                    parts = sub.split()
                    if len(parts) >= 4:
                        nbr_id = parts[1]
                        keyword = parts[2]

                        if keyword == "remote-as":
                            remote_as = int(parts[3])
                            if _is_ip(nbr_id):
                                # Direct neighbour statement
                                bgp["peers"].append({
                                    "ip": nbr_id,
                                    "remote_as": remote_as,
                                })
                            else:
                                # Peer-group definition
                                bgp["peer_groups"][nbr_id] = remote_as

                        elif keyword == "peer-group" and _is_ip(nbr_id):
                            peer_group_members.append((nbr_id, parts[3]))

                i += 1

            # Resolve peer-group members
            for ip, group in peer_group_members:
                remote_as = bgp["peer_groups"].get(group)
                if remote_as is not None:
                    # Avoid duplicates (direct remote-as may already exist)
                    if not any(p["ip"] == ip for p in bgp["peers"]):
                        bgp["peers"].append({"ip": ip, "remote_as": remote_as})

            # Drop internal helper before storing
            del bgp["peer_groups"]
            result["bgp"] = bgp
            continue

        # ---- OSPF block --------------------------------------------------
        if line.startswith("router ospf "):
            process_id = int(line.split()[2])
            ospf_proc: dict = {
                "process_id": process_id,
                "router_id": "",
                "networks": [],
            }
            i += 1
            while i < total:
                sub_raw = lines[i]
                if sub_raw and not sub_raw[0].isspace():
                    break
                sub = sub_raw.strip()
                if sub.startswith("router-id "):
                    ospf_proc["router_id"] = sub.split()[1]
                elif sub.startswith("network "):
                    parts = sub.split()
                    if len(parts) >= 5 and parts[3] == "area":
                        ospf_proc["networks"].append({
                            "network": parts[1],
                            "wildcard": parts[2],
                            "area": parts[4],
                        })
                i += 1
            result["ospf"].append(ospf_proc)
            continue

        i += 1

    return result


# ---------------------------------------------------------------------------
# ES document helpers
# ---------------------------------------------------------------------------

def _doc_id(source_file: str) -> str:
    return hashlib.sha1(f"batfish|{source_file}".encode()).hexdigest()


def build_action(parsed: dict, source_file: str, index: str) -> dict:
    hostname = parsed.get("hostname") or source_file.removesuffix(".cfg")
    return {
        "_index": index,
        "_id": _doc_id(source_file),
        "_source": {
            "platform": "cisco_ios",
            "command": "running-config",
            "source_type": "batfish",
            "source_file": source_file,
            "hostname": hostname,
            "ingested_at": datetime.now(timezone.utc).isoformat(),
            "records": parsed,
        },
    }


def generate_actions(configs_dir: Path, index: str) -> Iterator[dict]:
    cfg_files = sorted(configs_dir.glob("*.cfg"))
    if not cfg_files:
        log.warning("No .cfg files found in %s", configs_dir)
        return

    for cfg_path in cfg_files:
        text = cfg_path.read_text(encoding="utf-8", errors="replace")
        parsed = parse_ios_config(text)
        hostname = parsed.get("hostname") or cfg_path.stem
        bgp_peers = len(parsed["bgp"]["peers"]) if parsed.get("bgp") else 0
        log.info(
            "  %-20s  ifaces=%-3d  bgp_peers=%-3d  version=%s",
            hostname,
            len(parsed["interfaces"]),
            bgp_peers,
            parsed.get("version", ""),
        )
        yield build_action(parsed, cfg_path.name, index)


# ---------------------------------------------------------------------------
# Index management
# ---------------------------------------------------------------------------

def ensure_index(es: Elasticsearch, index: str) -> None:
    if not es.indices.exists(index=index):
        es.indices.create(index=index)
        log.info("Created index '%s'", index)
    else:
        log.info("Index '%s' already exists", index)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--configs-dir", default=str(CONFIGS_DIR))
    p.add_argument("--es-url", default=ES_URL)
    p.add_argument("--index", default=INDEX_NAME)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--chunk-size", type=int, default=100)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    configs_dir = Path(args.configs_dir)

    if not configs_dir.is_dir():
        log.error("configs-dir not found: %s", configs_dir)
        sys.exit(1)

    log.info("Scanning: %s", configs_dir)

    if args.dry_run:
        log.info("DRY RUN — no data will be written to Elasticsearch")
        count = 0
        for action in generate_actions(configs_dir, args.index):
            count += 1
            src = action["_source"]
            print(json.dumps({
                "hostname": src["hostname"],
                "interfaces": len(src["records"]["interfaces"]),
                "bgp_peers": len(src["records"]["bgp"]["peers"]) if src["records"]["bgp"] else 0,
                "ospf_procs": len(src["records"]["ospf"]),
            }, indent=2))
        log.info("Dry-run complete — %d documents would be indexed", count)
        return

    es = Elasticsearch(args.es_url)
    if not es.ping():
        log.error("Cannot reach Elasticsearch at %s", args.es_url)
        sys.exit(1)
    log.info("Connected to Elasticsearch at %s", args.es_url)

    ensure_index(es, args.index)

    try:
        success, errors = bulk(
            es,
            generate_actions(configs_dir, args.index),
            chunk_size=args.chunk_size,
            raise_on_error=False,
            stats_only=False,
        )
    except BulkIndexError as exc:
        log.error("Bulk index error: %s", exc)
        sys.exit(1)

    log.info("Done — %d documents indexed", success)
    if errors:
        log.warning("%d errors:", len(errors))
        for err in errors[:5]:
            log.warning("  %s", err)


if __name__ == "__main__":
    main()

"""
TreasureMap — Data ingest script.
Wipes and reloads all TreasureMap indices with the sample network data.
Run from the backend/ directory:
  python ingest.py
  python ingest.py --wipe     # drop + recreate indices first (default)
  python ingest.py --no-wipe  # append without dropping
"""
import sys
import argparse
import logging
from es_client import get_es, bootstrap_indices, wipe_indices
from config import IDX_DEVICES, IDX_INTERFACES, IDX_CONNECTIONS, IDX_ACLS

# Must be importable — run from backend/ dir
sys.path.insert(0, ".")
from data.sample_network import all_data

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger(__name__)


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


def run(wipe: bool = True):
    es = get_es()

    # Verify ES is reachable
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

    data = all_data()

    log.info("Indexing devices …")
    _bulk_index(es, IDX_DEVICES, data["devices"])

    log.info("Indexing interfaces …")
    _bulk_index(es, IDX_INTERFACES, data["interfaces"])

    log.info("Indexing connections …")
    _bulk_index(es, IDX_CONNECTIONS, data["connections"])

    log.info("Indexing ACLs …")
    _bulk_index(es, IDX_ACLS, data["acls"])

    log.info("Done. Sample network loaded successfully.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load sample data into TreasureMap ES")
    parser.add_argument("--no-wipe", dest="wipe", action="store_false",
                        help="Don't wipe existing indices")
    parser.set_defaults(wipe=True)
    args = parser.parse_args()
    run(wipe=args.wipe)

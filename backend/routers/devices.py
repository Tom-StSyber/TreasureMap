"""
TreasureMap — /devices endpoints.
"""
from fastapi import APIRouter, Query, HTTPException
from es_client import get_es
from config import IDX_DEVICES, IDX_INTERFACES, IDX_CONNECTIONS, IDX_ACLS

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("")
def list_devices(
    vendor: str | None = Query(None),
    device_type: str | None = Query(None),
    tag: str | None = Query(None),
):
    es = get_es()
    must = []
    if vendor:
        must.append({"term": {"vendor": vendor}})
    if device_type:
        must.append({"term": {"device_type": device_type}})
    if tag:
        must.append({"term": {"tags": tag}})

    body = {"query": {"bool": {"must": must}} if must else {"match_all": {}}, "size": 500}
    hits = es.search(index=IDX_DEVICES, body=body)
    return [h["_source"] for h in hits["hits"]["hits"]]


@router.get("/{name}")
def get_device(name: str):
    es = get_es()
    hits = es.search(
        index=IDX_DEVICES,
        body={"query": {"term": {"name": name}}, "size": 1},
    )
    results = hits["hits"]["hits"]
    if not results:
        raise HTTPException(status_code=404, detail=f"Device '{name}' not found")
    return results[0]["_source"]


@router.get("/{name}/interfaces")
def get_device_interfaces(name: str):
    es = get_es()
    hits = es.search(
        index=IDX_INTERFACES,
        body={"query": {"term": {"device_name": name}}, "size": 100},
    )
    return [h["_source"] for h in hits["hits"]["hits"]]


@router.get("/{name}/acls")
def get_device_acls(name: str):
    es = get_es()
    hits = es.search(
        index=IDX_ACLS,
        body={"query": {"term": {"device_name": name}}, "size": 50},
    )
    return [h["_source"] for h in hits["hits"]["hits"]]


@router.get("/{name}/connections")
def get_device_connections(name: str):
    es = get_es()
    hits = es.search(
        index=IDX_CONNECTIONS,
        body={
            "query": {
                "bool": {
                    "should": [
                        {"term": {"src_device_name": name}},
                        {"term": {"dst_device_name": name}},
                    ],
                    "minimum_should_match": 1,
                }
            },
            "size": 100,
        },
    )
    return [h["_source"] for h in hits["hits"]["hits"]]

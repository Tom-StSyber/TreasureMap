"""
TreasureMap — FastAPI application entry point.
"""
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from config import CORS_ORIGINS
from es_client import bootstrap_indices, get_es
from routers import devices, topology, pathfind, ingest

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("TreasureMap API starting — bootstrapping Elasticsearch indices …")
    try:
        bootstrap_indices()
        log.info("Elasticsearch ready.")
    except Exception as exc:
        log.warning("Could not reach Elasticsearch at startup: %s", exc)
    yield
    log.info("TreasureMap API shutting down.")


app = FastAPI(
    title="TreasureMap API",
    description="Network topology mapper — devices, connections, path-finding.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(devices.router)
app.include_router(topology.router)
app.include_router(pathfind.router)
app.include_router(ingest.router)


@app.get("/health")
def health():
    try:
        info = get_es().info()
        return {"status": "ok", "elasticsearch": info["version"]["number"]}
    except Exception as exc:
        return {"status": "degraded", "error": str(exc)}

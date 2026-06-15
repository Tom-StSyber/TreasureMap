"""
TreasureMap — Configuration (env-driven with sane defaults).
"""
import os

ELASTICSEARCH_URL = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
ELASTICSEARCH_INDEX_PREFIX = os.getenv("ES_INDEX_PREFIX", "treasuremap")

# Index names
IDX_DEVICES     = f"{ELASTICSEARCH_INDEX_PREFIX}_devices"
IDX_INTERFACES  = f"{ELASTICSEARCH_INDEX_PREFIX}_interfaces"
IDX_CONNECTIONS = f"{ELASTICSEARCH_INDEX_PREFIX}_connections"
IDX_ACLS        = f"{ELASTICSEARCH_INDEX_PREFIX}_acls"

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")

API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))

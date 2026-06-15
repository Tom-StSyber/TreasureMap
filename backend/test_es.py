# save as D:\Home-Lab\TreasureMap\backend\test_es.py
from elasticsearch import Elasticsearch

es = Elasticsearch("http://localhost:9200")
print(es.info())
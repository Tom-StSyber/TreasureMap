import json, urllib.request

data = json.loads(urllib.request.urlopen("http://localhost:8000/topology").read())
devices = data["devices"]
links = data["links"]

print(f"Devices: {len(devices)}")
print(f"Links:   {len(links)}")

print("\nNamed devices (batfish):")
skip_prefixes = ("arista_", "cisco_", "hp_", "juniper_", "brocade_", "dell_", "eltex_", "broadcom_")
for d in sorted(devices, key=lambda x: x["id"]):
    if not any(d["id"].startswith(p) for p in skip_prefixes):
        print(f"  {d['id']:<22}  ifaces={len(d['interfaces']):<3}  version={d.get('version','')}")

print("\nBGP links:")
for l in links:
    if l.get("link_type") == "bgp":
        print(f"  {l['source']:<20} -> {l['target']:<20}  ({l['source_interface']} / {l['target_interface']})")

print("\nAll link types:")
from collections import Counter
print(Counter(l.get("link_type", "cdp") for l in links))

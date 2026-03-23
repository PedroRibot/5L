import json
import requests

with open("config/config.json") as f:
    cfg = json.load(f)

params = {
    "limit": cfg["limit"],
    "sort": cfg["sort"],
    "period": cfg["period"],
    "nsfw": cfg["nsfw"],
    "type": cfg["type"],
}

print(f"Request params: {json.dumps(params, indent=2)}\n")

resp = requests.get("https://civitai.com/api/v1/images", params=params, timeout=30)
print(f"Status: {resp.status_code}")

data = resp.json()
items = data.get("items", [])
metadata = data.get("metadata", {})

print(f"Items returned: {len(items)}")
print(f"Metadata: {json.dumps(metadata, indent=2)}\n")

for i, item in enumerate(items[:5], 1):
    print(f"--- Item {i} ---")
    print(f"  id:    {item.get('id')}")
    print(f"  type:  {item.get('type')}")
    print(f"  url:   {item.get('url', '')[:80]}")
    print(f"  stats: {item.get('stats')}")
    print()

if len(items) > 5:
    print(f"... and {len(items) - 5} more items")

"""
Collect the item lists for the study: every Sentinel-2 L2A item of 2025 over 20 cities, from
Element84 Earth Search (sentinel-2-c1-l2a) and Microsoft Planetary Computer (sentinel-2-l2a).

    python -m study.collect            -> study/data/items_<catalog>.jsonl (cached; re-run is a no-op)

For each item we keep what lineage needs: id, datetime, scene key (product URI), created/updated
timestamps, processing baseline, bbox and a content hash of the item as served today.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pystac_client import Client  # noqa: E402

from lineage.identity import item_content_hash, scene_key  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
YEAR = "2025-01-01T00:00:00Z/2025-12-31T23:59:59Z"
HALF = 0.05  # bbox half-width in degrees (~10 km box): a city centre

CATALOGS = {
    "earthsearch": ("https://earth-search.aws.element84.com/v1", "sentinel-2-c1-l2a"),
    "planetary": ("https://planetarycomputer.microsoft.com/api/stac/v1", "sentinel-2-l2a"),
}

# 20 cities on six continents (lon, lat of the centre)
CITIES = {
    "Zurich": (8.54, 47.37), "Lodz": (19.46, 51.76), "London": (-0.12, 51.51), "Warsaw": (21.01, 52.23),
    "Paris": (2.35, 48.86), "Madrid": (-3.70, 40.42), "Rome": (12.50, 41.90), "Stockholm": (18.07, 59.33),
    "Athens": (23.73, 37.98), "Cairo": (31.24, 30.04), "Nairobi": (36.82, -1.29), "Lagos": (3.38, 6.52),
    "Cape Town": (18.42, -33.92), "Mumbai": (72.88, 19.08), "Tokyo": (139.69, 35.69), "Sydney": (151.21, -33.87),
    "Sao Paulo": (-46.63, -23.55), "Mexico City": (-99.13, 19.43), "Toronto": (-79.38, 43.65), "Los Angeles": (-118.24, 34.05),
}


def bbox_of(city: str) -> list[float]:
    lon, lat = CITIES[city]
    return [round(lon - HALF, 4), round(lat - HALF, 4), round(lon + HALF, 4), round(lat + HALF, 4)]


def record(city: str, item: dict) -> dict:
    p = item.get("properties") or {}
    return {
        "city": city,
        "id": item["id"],
        "datetime": p.get("datetime"),
        "scene_key": scene_key(item),
        "created": p.get("created"),
        "updated": p.get("updated"),
        "baseline": p.get("s2:processing_baseline"),
        "tile": p.get("s2:mgrs_tile") or (p.get("grid:code") or "").replace("MGRS-", "") or None,
        "bbox": item.get("bbox"),
        "content_hash": item_content_hash(item),
    }


def collect(name: str) -> Path:
    url, coll = CATALOGS[name]
    out = DATA / f"items_{name}.jsonl"
    if out.exists():
        return out
    DATA.mkdir(parents=True, exist_ok=True)
    client = Client.open(url, headers={"User-Agent": "stac-lineage-study/1.0"})
    tmp = out.with_suffix(".part")
    with open(tmp, "w", encoding="utf-8") as f:
        for city in CITIES:
            for attempt in range(4):
                try:
                    s = client.search(collections=[coll], bbox=bbox_of(city), datetime=YEAR, limit=100)
                    rows = [record(city, it) for it in s.items_as_dicts()]
                    break
                except Exception as e:  # noqa: BLE001 - transient network errors
                    print(f"  {name} {city}: retry after {e.__class__.__name__}")
                    time.sleep(5 * (attempt + 1))
            else:
                raise RuntimeError(f"{name} {city}: failed")
            for r in rows:
                f.write(json.dumps(r) + "\n")
            print(f"  {name:12s} {city:12s} {len(rows):4d} items")
    tmp.replace(out)
    return out


if __name__ == "__main__":
    for n in CATALOGS:
        collect(n)

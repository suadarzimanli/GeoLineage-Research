"""STAC search: connect to catalog, search by bbox/collection, return items for lineage."""

from dataclasses import dataclass
from typing import Any

from pystac_client import Client


@dataclass
class StacIngestResult:
    """Result of STAC search: catalog URL, search params, and items with id/href for lineage."""
    catalog_url: str
    search_params: dict[str, Any]
    items: list[dict[str, Any]]  # each: id, href, geometry (optional), datetime (optional)


# Default catalog for prototyping (no auth)
DEFAULT_CATALOG_URL = "https://earth-search.aws.element84.com/v1"
DEFAULT_COLLECTION = "sentinel-2-c1-l2a"


def search_stac(
    bbox: tuple[float, float, float, float],
    catalog_url: str = DEFAULT_CATALOG_URL,
    collection: str = DEFAULT_COLLECTION,
    datetime_range: str | None = None,
    max_items: int = 10,
) -> StacIngestResult:
    """
    Search a STAC API by bbox and collection. Returns item ids and hrefs for lineage.
    bbox: (minx, miny, maxx, maxy) in WGS84.
    """
    client = Client.open(catalog_url)
    search = client.search(
        bbox=bbox,
        collections=[collection],
        datetime=datetime_range,
        max_items=max_items,
    )
    items_list = list(search.items())

    # Build minimal item records for lineage (id, href; checksum from asset if available)
    input_assets = []
    for item in items_list:
        item_id = item.id
        # Prefer self link or first asset href for "canonical" reference
        href = item.get_self_href() or (item.assets.get("thumbnail", item.assets.get("visual")) and item.assets.get("thumbnail", item.assets.get("visual")).href) or ""
        if not href and item.assets:
            first_asset = next(iter(item.assets.values()))
            href = first_asset.href
        checksum = None
        if item.assets:
            first_asset = next(iter(item.assets.values()))
            if hasattr(first_asset, "extra_fields") and first_asset.extra_fields:
                checksum = first_asset.extra_fields.get("checksum:sha256") or first_asset.extra_fields.get("sha256")
        input_assets.append({"id": item_id, "href": href, "checksum": checksum})

    search_params = {
        "bbox": list(bbox),
        "collection": collection,
        "datetime": datetime_range,
        "max_items": max_items,
    }

    return StacIngestResult(
        catalog_url=catalog_url,
        search_params=search_params,
        items=input_assets,
    )


def search_stac_pystac_items(
    bbox: tuple[float, float, float, float],
    catalog_url: str = DEFAULT_CATALOG_URL,
    collection: str = DEFAULT_COLLECTION,
    datetime_range: str | None = None,
    max_items: int = 10,
):
    """
    Same search but returns pystac.Item objects for use in transform (e.g. geometry).
    """
    client = Client.open(catalog_url)
    search = client.search(
        bbox=bbox,
        collections=[collection],
        datetime=datetime_range,
        max_items=max_items,
    )
    return list(search.items())

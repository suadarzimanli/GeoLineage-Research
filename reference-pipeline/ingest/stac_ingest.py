"""STAC search: query a catalog by bbox/collection/datetime in a deterministic order."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests
from pystac_client import Client

from lineage.identity import DEFAULT_SORTBY, item_content_hash, normalize_datetime, scene_key
from lineage.schema import InputAsset

# Default catalog (public, no auth)
DEFAULT_CATALOG_URL = "https://earth-search.aws.element84.com/v1"
DEFAULT_COLLECTION = "sentinel-2-c1-l2a"
USER_AGENT = "geolineage-reference/2.0"


@dataclass
class StacIngestResult:
    """Result of a STAC search: catalog, normalised search parameters, items and total matches."""
    catalog_url: str
    search_params: dict[str, Any]
    items: list[Any]  # pystac.Item
    matched: int | None  # numberMatched reported by the catalog, if any


def _search(client: Client, bbox, collection, datetime_range, max_items, sortby):
    kwargs = dict(bbox=list(bbox), collections=[collection], datetime=datetime_range,
                  max_items=max_items, limit=min(max_items, 100))
    if sortby:
        kwargs["sortby"] = sortby
    return client.search(**kwargs)


def search(
    bbox: tuple[float, float, float, float],
    catalog_url: str = DEFAULT_CATALOG_URL,
    collection: str = DEFAULT_COLLECTION,
    datetime_range: str | None = None,
    max_items: int = 10,
    sortby: list[dict[str, str]] | None = None,
) -> StacIngestResult:
    """
    Search a STAC API. Results are ordered newest first (ties by id) so the same query returns the
    same first `max_items` items while the catalog is unchanged. Dates are normalised to RFC 3339.
    """
    dt = normalize_datetime(datetime_range)
    order = DEFAULT_SORTBY if sortby is None else sortby
    client = Client.open(catalog_url, headers={"User-Agent": USER_AGENT})
    s = _search(client, bbox, collection, dt, max_items, order)
    items = list(s.items())
    try:
        matched = s.matched()
    except Exception:  # noqa: BLE001 - optional in STAC
        matched = None
    search_params = {"bbox": list(bbox), "collection": collection, "datetime": dt,
                     "max_items": max_items, "sortby": order}
    return StacIngestResult(catalog_url=catalog_url, search_params=search_params, items=items, matched=matched)


def to_input_asset(item) -> InputAsset:
    """Lineage record for one item: id, canonical href, catalog checksum, content hash, scene key."""
    d = item.to_dict(include_self_link=True, transform_hrefs=False)
    href = item.get_self_href() or ""
    if not href and item.assets:
        href = next(iter(item.assets.values())).href
    checksum = None
    if item.assets:
        first = next(iter(item.assets.values()))
        extra = getattr(first, "extra_fields", None) or {}
        checksum = extra.get("checksum:sha256") or extra.get("sha256") or extra.get("file:checksum")
    props = d.get("properties") or {}
    return InputAsset(id=item.id, href=href, checksum=checksum, content_hash=item_content_hash(d),
                      scene_key=scene_key(d), updated=props.get("updated"))


def item_exists(catalog_url: str, collection: str, item_id: str, timeout: float = 20.0) -> bool | None:
    """True/False if the catalog does/does not have the item now; None if the check failed."""
    url = f"{catalog_url.rstrip('/')}/collections/{collection}/items/{requests.utils.quote(item_id, safe='')}"
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    except requests.RequestException:
        return None
    if r.status_code == 200:
        return True
    if r.status_code == 404:
        return False
    return None


# ------------------------------------------------------------------ backwards-compatible helpers

def search_stac_pystac_items(bbox, catalog_url=DEFAULT_CATALOG_URL, collection=DEFAULT_COLLECTION,
                             datetime_range=None, max_items=10):
    """Same search, returning only the pystac.Item objects."""
    return search(bbox, catalog_url, collection, datetime_range, max_items).items


def search_stac(bbox, catalog_url=DEFAULT_CATALOG_URL, collection=DEFAULT_COLLECTION,
                datetime_range=None, max_items=10) -> StacIngestResult:
    """Search and return lineage-ready input records in `items` (dicts)."""
    r = search(bbox, catalog_url, collection, datetime_range, max_items)
    r.items = [to_input_asset(i).to_dict() for i in r.items]
    return r

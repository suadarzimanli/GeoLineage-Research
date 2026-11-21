"""
Identity rules for lineage: which runs are comparable, and when two inputs are "the same".

Three keys, all SHA-256 over canonical JSON (sorted keys, no whitespace), so the Python reference
pipeline and the hosted Worker compute identical values:

  query_key      catalog + collection + bbox + datetime interval + max_items + sort order.
                 Only runs with the same query key are compared ("previous run" = previous run of
                 the same query), and only they may reuse each other's output.
  content_hash   an item's geometry, bbox, properties and asset hrefs (links are excluded: they
                 carry server-specific URLs). Same id + different content hash = the item changed
                 in place (e.g. metadata fix or reprocessing published under the same id).
  scene_key      a catalog-independent name for the scene: s2:product_uri for Sentinel-2,
                 otherwise the item id. Lets runs against different catalogs be compared.

Pure standard library: no network, no geospatial dependencies.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

# Deterministic STAC order: newest first, ties broken by id.
DEFAULT_SORTBY: list[dict[str, str]] = [
    {"field": "properties.datetime", "direction": "desc"},
    {"field": "id", "direction": "asc"},
]

ROUND_BBOX = 6  # decimal degrees ≈ 0.1 m; avoids float noise in keys


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def normalize_datetime(value: str | None) -> str | None:
    """
    Normalise a STAC datetime or interval to RFC 3339 so catalogs accept it and equal intervals
    produce equal query keys: '2025-06-01/2025-06-30' -> '2025-06-01T00:00:00Z/2025-06-30T23:59:59Z'.
    Open ends ('..') are kept. Returns None for empty input; raises ValueError for malformed input.
    """
    if value is None or not str(value).strip():
        return None
    parts = str(value).strip().split("/")
    if len(parts) > 2:
        raise ValueError("datetime must be a single instant or 'start/end'")
    out = []
    for i, p in enumerate(parts):
        p = p.strip()
        if p in ("", ".."):
            out.append("..")
        elif _DATE_ONLY.match(p):
            out.append(p + ("T00:00:00Z" if i == 0 else "T23:59:59Z"))
        elif re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})$", p):
            out.append(p)
        else:
            raise ValueError(f"not an RFC 3339 date or time: {p!r}")
    if len(out) == 2 and out[0] == ".." and out[1] == "..":
        raise ValueError("an interval needs at least one end")
    return "/".join(out)


def query_key(
    catalog_url: str,
    collection: str,
    bbox: Iterable[float],
    datetime: str | None,
    max_items: int,
    sortby: list[dict[str, str]] | None = None,
) -> str:
    """Hash identifying a query. Equal keys = same question asked of the same catalog."""
    return sha256_hex(canonical_json({
        "catalog_url": catalog_url.rstrip("/"),
        "collection": collection,
        "bbox": [f"{float(v):.{ROUND_BBOX}f}" for v in bbox],  # text, so Python and JavaScript agree
        "datetime": normalize_datetime(datetime),
        "max_items": int(max_items),
        "sortby": sortby if sortby is not None else DEFAULT_SORTBY,
    }))


def item_content_hash(item: dict[str, Any]) -> str:
    """Hash of what a downstream step could depend on; links are excluded (server-specific)."""
    assets = item.get("assets") or {}
    return sha256_hex(canonical_json({
        "id": item.get("id"),
        "geometry": item.get("geometry"),
        "bbox": item.get("bbox"),
        "properties": item.get("properties") or {},
        "assets": {k: (v or {}).get("href") for k, v in sorted(assets.items())},
    }))


def scene_key(item: dict[str, Any]) -> str:
    """Catalog-independent scene name: the Sentinel-2 product URI without '.SAFE', else the id."""
    props = item.get("properties") or {}
    uri = props.get("s2:product_uri")
    if isinstance(uri, str) and uri:
        return uri[:-5] if uri.endswith(".SAFE") else uri
    return str(item.get("id"))


# --------------------------------------------------------------------------- diff

@dataclass
class InputDiff:
    """Comparison of two input sets of the same query."""
    added: list[str] = field(default_factory=list)  # ids new in the current run
    removed: list[str] = field(default_factory=list)  # ids no longer returned
    changed: list[str] = field(default_factory=list)  # same id, different content hash
    unchanged: list[str] = field(default_factory=list)
    removed_reason: dict[str, str] = field(default_factory=dict)  # id -> outside_window | gone | unknown

    def to_dict(self) -> dict[str, Any]:
        return {"added": self.added, "removed": self.removed, "changed": self.changed,
                "unchanged": self.unchanged, "removed_reason": self.removed_reason}

    @property
    def identical(self) -> bool:
        return not (self.added or self.removed or self.changed)


def diff_inputs(previous: dict[str, str | None], current: dict[str, str | None]) -> InputDiff:
    """
    previous/current map item id -> content hash (None if unknown). An item counts as changed only
    when both hashes are known and differ; unknown hashes compare by id (older receipts).
    """
    d = InputDiff()
    for i in sorted(current):
        if i not in previous:
            d.added.append(i)
        elif previous[i] and current[i] and previous[i] != current[i]:
            d.changed.append(i)
        else:
            d.unchanged.append(i)
    d.removed = sorted(i for i in previous if i not in current)
    return d


def classify_removed(diff: InputDiff, still_in_catalog) -> InputDiff:
    """
    Label each removed id: 'outside_window' if the catalog still has it (it only fell out of the
    first max_items results), 'gone' if the catalog no longer has it, 'unknown' if the check failed.
    `still_in_catalog(id) -> True | False | None`.
    """
    for i in diff.removed:
        ok = still_in_catalog(i)
        diff.removed_reason[i] = "outside_window" if ok is True else "gone" if ok is False else "unknown"
    return diff

"""
Run the GeoLineage pipeline: STAC search → GeoParquet footprints → lineage receipt → diff.

  python -m scripts.run_pipeline --bbox -122.5 37.5 -122.2 37.8 [--datetime 2025-06-01/2025-08-31]
                                 [--catalog URL] [--collection NAME] [--max-items N]

Identity rules (lineage/identity.py): a run is compared with, and may reuse the output of, only the
previous run of the same query (catalog, collection, bbox, datetime, max_items, sort order). Inputs
are the same when ids *and* content hashes match. Reuse is decided before the transform runs.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ingest.stac_ingest import DEFAULT_CATALOG_URL, DEFAULT_COLLECTION, item_exists, search, to_input_asset  # noqa: E402
from lineage.diff import diff_since_last_run, input_assets_equal  # noqa: E402
from lineage.identity import query_key  # noqa: E402
from lineage.schema import LineageRun, OutputAsset, TransformStep, build_dag_from_run, new_run_id, timestamp_iso  # noqa: E402
from lineage.store import get_previous_run_for_query, load_run, record_run  # noqa: E402

MAX_REMOVED_CHECKS = 50  # catalog look-ups to label removed items


def run_pipeline(
    bbox: tuple[float, float, float, float],
    catalog_url: str = DEFAULT_CATALOG_URL,
    collection: str = DEFAULT_COLLECTION,
    max_items: int = 10,
    output_dir: Path | None = None,
    lineage_dir: Path | None = None,
    datetime_range: str | None = None,
) -> tuple[LineageRun, str, str | None]:
    """Execute one run. Returns (LineageRun, run_id, reused_from_run_id)."""
    output_dir = Path(output_dir or (ROOT / "outputs"))
    lineage_dir = Path(lineage_dir or (ROOT / "lineage_runs"))

    # 1) ingest (deterministic order) and lineage records for the inputs
    result = search(bbox, catalog_url, collection, datetime_range, max_items)
    input_assets = [to_input_asset(i) for i in result.items]
    sp = dict(result.search_params)
    sp["query_key"] = query_key(catalog_url, collection, bbox, sp["datetime"], max_items, sp["sortby"])
    sp["matched"] = result.matched

    # 2) minimum recompute, decided before any transform: same query, same inputs (ids + content)
    prev_id = get_previous_run_for_query(None, sp["query_key"], lineage_dir)
    prev = load_run(prev_id, lineage_dir) if prev_id else None
    run_id = new_run_id()
    reused_from = None
    if prev and prev.output_assets and input_assets_equal(input_assets, prev.input_assets):
        reused_from = prev.transform_steps[0].parameters.get("reused_from_run_id") or prev.run_id
        output_assets = list(prev.output_assets)
        steps = [TransformStep("footprints_to_geoparquet", {"crs": prev.output_assets[0].crs, "reused_from_run_id": reused_from})]
    else:
        from transform.footprints_to_geoparquet import items_to_geoparquet  # geospatial deps only when needed

        out = items_to_geoparquet(result.items, output_dir=output_dir / run_id, filename="footprints.parquet")
        output_assets = [OutputAsset(path=out.output_path, checksum=out.checksum, crs=out.crs)]
        steps = [TransformStep("footprints_to_geoparquet", {"crs": out.crs})]

    run = LineageRun(run_id=run_id, timestamp=timestamp_iso(), catalog_url=catalog_url, search_params=sp,
                     input_assets=input_assets, transform_steps=steps, output_assets=output_assets)
    run.lineage_dag = build_dag_from_run(run)
    record_run(run, lineage_dir)
    return run, run_id, reused_from


def main():
    import argparse

    p = argparse.ArgumentParser(description="GeoLineage pipeline: STAC → GeoParquet → lineage")
    p.add_argument("--bbox", type=float, nargs=4, required=True, metavar=("minx", "miny", "maxx", "maxy"))
    p.add_argument("--datetime", default=None, help="date or interval, e.g. 2025-06-01/2025-08-31")
    p.add_argument("--catalog", default=DEFAULT_CATALOG_URL)
    p.add_argument("--collection", default=DEFAULT_COLLECTION)
    p.add_argument("--max-items", type=int, default=10)
    p.add_argument("--out-dir", type=Path, default=ROOT / "outputs")
    p.add_argument("--lineage-dir", type=Path, default=ROOT / "lineage_runs")
    args = p.parse_args()

    run, run_id, reused_from = run_pipeline(tuple(args.bbox), args.catalog, args.collection, args.max_items,
                                            args.out_dir, args.lineage_dir, args.datetime)
    print("Run ID:", run_id, "| query:", run.search_params["query_key"][:12], "| matched:", run.search_params.get("matched"))
    print("Output reused from run " + reused_from if reused_from else "Output: " + run.output_assets[0].path)
    print("Lineage saved to:", args.lineage_dir / "runs" / f"{run_id}.json")

    remaining = [MAX_REMOVED_CHECKS]

    def check(item_id: str):
        if remaining[0] <= 0:
            return None
        remaining[0] -= 1
        return item_exists(args.catalog, args.collection, item_id)

    diff = diff_since_last_run(run, args.lineage_dir, still_in_catalog=check)
    if diff.previous_run_id:
        reasons = {}
        for r in diff.removed_reason.values():
            reasons[r] = reasons.get(r, 0) + 1
        print(f"\nCompared with the previous run of this query ({diff.previous_run_id}):")
        print(f"  added {len(diff.added)}, removed {len(diff.removed)} {reasons or ''}, changed {len(diff.changed)}, unchanged {len(diff.unchanged)}")
    else:
        print("\nFirst run of this query: nothing to compare with.")


if __name__ == "__main__":
    main()

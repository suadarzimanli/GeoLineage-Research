"""
Run the GeoLineage pipeline: STAC search → transform to GeoParquet → record lineage → diff.
Usage:
  python -m scripts.run_pipeline --bbox -122.5 37.5 -122.2 37.8 [--catalog URL] [--collection NAME] [--max-items N]
  python -m scripts.run_pipeline --bbox -122.5 37.5 -122.2 37.8 --out-dir ./outputs
"""

from __future__ import annotations

import sys
from pathlib import Path

# Project root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ingest.stac_ingest import search_stac_pystac_items, DEFAULT_CATALOG_URL, DEFAULT_COLLECTION
from transform.footprints_to_geoparquet import items_to_geoparquet
from lineage.schema import (
    LineageRun,
    InputAsset,
    OutputAsset,
    TransformStep,
    build_dag_from_run,
    new_run_id,
    timestamp_iso,
)
from lineage.store import record_run, load_run, get_latest_run_id_for_region, DEFAULT_LINEAGE_DIR
from lineage.diff import diff_since_last_run, input_assets_equal


def run_pipeline(
    bbox: tuple[float, float, float, float],
    catalog_url: str = DEFAULT_CATALOG_URL,
    collection: str = DEFAULT_COLLECTION,
    max_items: int = 10,
    output_dir: Path | None = None,
    lineage_dir: Path | None = None,
) -> tuple[LineageRun, str, str | None]:
    """
    Execute one pipeline run. Returns (LineageRun, run_id, reused_from_run_id).
    reused_from_run_id is set when inputs matched the latest run and we skipped the transform.
    """
    output_dir = output_dir or (ROOT / "outputs")
    lineage_dir = lineage_dir or (ROOT / "lineage_runs")

    # 1) Ingest: get pystac items
    items = search_stac_pystac_items(
        bbox=bbox,
        catalog_url=catalog_url,
        collection=collection,
        max_items=max_items,
    )

    # Build input_assets for lineage (id, href, checksum)
    input_assets = []
    for item in items:
        href = item.get_self_href()
        if not href and item.assets:
            first_asset = next(iter(item.assets.values()))
            href = first_asset.href
        checksum = None
        if item.assets:
            first_asset = next(iter(item.assets.values()))
            if hasattr(first_asset, "extra_fields") and first_asset.extra_fields:
                checksum = first_asset.extra_fields.get("checksum:sha256") or first_asset.extra_fields.get("sha256")
        input_assets.append(InputAsset(id=item.id, href=href or "", checksum=checksum))

    search_params = {
        "bbox": list(bbox),
        "collection": collection,
        "datetime": None,
        "max_items": max_items,
    }

    run_id = new_run_id()
    run_output_dir = Path(output_dir) / run_id
    run_output_dir.mkdir(parents=True, exist_ok=True)

    # 2) Minimum recompute: if inputs match the latest run *for this region* (same bbox, catalog, collection), reuse
    latest_run_id = get_latest_run_id_for_region(
        lineage_dir, catalog_url=catalog_url, collection=collection, bbox=bbox
    )
    latest_run = load_run(latest_run_id, lineage_dir) if latest_run_id else None
    reused_from_run_id = None
    if latest_run and input_assets_equal(input_assets, latest_run.input_assets):
        output_assets = list(latest_run.output_assets)
        transform_steps = [
            TransformStep(
                name="footprints_to_geoparquet",
                parameters={"crs": latest_run.output_assets[0].crs, "reused_from_run_id": latest_run.run_id},
            ),
        ]
        reused_from_run_id = latest_run.run_id
    else:
        # Transform: footprints → GeoParquet
        transform_result = items_to_geoparquet(
            items,
            output_dir=run_output_dir,
            filename="footprints.parquet",
        )
        output_assets = [
            OutputAsset(
                path=transform_result.output_path,
                checksum=transform_result.checksum,
                crs=transform_result.crs,
            )
        ]
        transform_steps = [
            TransformStep(name="footprints_to_geoparquet", parameters={"crs": transform_result.crs}),
        ]

    run = LineageRun(
        run_id=run_id,
        timestamp=timestamp_iso(),
        catalog_url=catalog_url,
        search_params=search_params,
        input_assets=input_assets,
        transform_steps=transform_steps,
        output_assets=output_assets,
        lineage_dag=None,
    )
    run.lineage_dag = build_dag_from_run(run)

    # 3) Save lineage (so "previous" for diff is the run before this one when we run again)
    record_run(run, lineage_dir)

    return run, run_id, reused_from_run_id


def main():
    import argparse
    p = argparse.ArgumentParser(description="GeoLineage pipeline: STAC → GeoParquet → lineage")
    p.add_argument("--bbox", type=float, nargs=4, required=True, metavar=("minx", "miny", "maxx", "maxy"), help="Bounding box WGS84")
    p.add_argument("--catalog", default=DEFAULT_CATALOG_URL, help="STAC catalog URL")
    p.add_argument("--collection", default=DEFAULT_COLLECTION, help="STAC collection")
    p.add_argument("--max-items", type=int, default=10, help="Max STAC items")
    p.add_argument("--out-dir", type=Path, default=ROOT / "outputs", help="Output directory")
    p.add_argument("--lineage-dir", type=Path, default=ROOT / "lineage_runs", help="Lineage directory")
    args = p.parse_args()

    bbox = tuple(args.bbox)
    run, run_id, reused_from = run_pipeline(
        bbox=bbox,
        catalog_url=args.catalog,
        collection=args.collection,
        max_items=args.max_items,
        output_dir=args.out_dir,
        lineage_dir=args.lineage_dir,
    )

    print("Run ID:", run_id)
    if reused_from:
        print("Output unchanged (reused from run", reused_from + ")")
    else:
        print("Output:", run.output_assets[0].path)
    print("Lineage saved to:", args.lineage_dir / "runs" / f"{run_id}.json")

    # Diff since last run (previous run, if any)
    diff = diff_since_last_run(run, args.lineage_dir)
    if diff.previous_run_id:
        print("\nDiff since previous run:", diff.previous_run_id)
        print("  Added inputs:", len(diff.added))
        print("  Removed inputs:", len(diff.removed))
        print("  Unchanged inputs:", len(diff.unchanged))
    else:
        print("\nNo previous run to diff against.")


if __name__ == "__main__":
    main()

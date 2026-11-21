r"""
Run the pipeline for multiple bboxes (multi-region). Enables incremental recompute:
when re-running the same list of bboxes, only regions whose input set changed are recomputed;
others reuse the previous run for that region (per-region reuse).

Usage (from the reference-pipeline folder):
  python -m scripts.run_pipeline_multi_bbox --bbox -122.5 37.5 -122.2 37.8 --bbox -122.4 37.6 -122.1 37.9 --max-items 5
  python -m scripts.run_pipeline_multi_bbox --bbox-file bboxes.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.run_pipeline import run_pipeline


def parse_bbox(s: str) -> tuple[float, float, float, float]:
    """Parse 'minx,miny,maxx,maxy' or '-122.5,37.5,-122.2,37.8'."""
    parts = [float(x.strip()) for x in s.split(",")]
    if len(parts) != 4:
        raise ValueError(f"bbox must have 4 values, got {len(parts)}")
    return (parts[0], parts[1], parts[2], parts[3])


def main():
    p = argparse.ArgumentParser(
        description="Run GeoLineage pipeline for multiple bboxes (multi-region); supports incremental recompute."
    )
    p.add_argument(
        "--bbox",
        action="append",
        dest="bboxes",
        type=parse_bbox,
        metavar="minx,miny,maxx,maxy",
        help="Bounding box (repeat for multiple regions)",
    )
    p.add_argument(
        "--bbox-file",
        type=Path,
        help="JSON file with array of bboxes [[minx,miny,maxx,maxy], ...]",
    )
    p.add_argument("--catalog", default="https://earth-search.aws.element84.com/v1", help="STAC catalog URL")
    p.add_argument("--collection", default="sentinel-2-c1-l2a", help="STAC collection")
    p.add_argument("--max-items", type=int, default=5, help="Max STAC items per region")
    p.add_argument("--out-dir", type=Path, default=ROOT / "outputs", help="Output directory")
    args = p.parse_args()

    bboxes = list(args.bboxes or [])
    if args.bbox_file and args.bbox_file.exists():
        data = json.loads(args.bbox_file.read_text(encoding="utf-8"))
        if isinstance(data, list):
            bboxes.extend(tuple(b) for b in data)
        else:
            bboxes.extend(tuple(data["bboxes"]))

    if not bboxes:
        p.error("Provide at least one --bbox or --bbox-file")

    start = time.perf_counter()
    reused = 0
    recomputed = 0
    for i, bbox in enumerate(bboxes):
        run, run_id, reused_from = run_pipeline(
            bbox=bbox,
            catalog_url=args.catalog,
            collection=args.collection,
            max_items=args.max_items,
            output_dir=args.out_dir,
        )
        if reused_from:
            reused += 1
            print(f"  Region {i + 1}/{len(bboxes)}: reused from {reused_from[:8]}...")
        else:
            recomputed += 1
            print(f"  Region {i + 1}/{len(bboxes)}: new output {run_id[:8]}...")
    elapsed = time.perf_counter() - start
    print(f"\nMulti-region run: {len(bboxes)} regions, {reused} reused, {recomputed} recomputed, {elapsed:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())

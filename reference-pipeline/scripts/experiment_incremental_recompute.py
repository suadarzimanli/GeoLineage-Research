r"""
Experiment: measure incremental recompute time saved vs full rebuild.

Runs the pipeline for N bboxes in two passes:
  - Pass 1 (full): all N regions computed from scratch.
  - Pass 2 (incremental): same N regions; only regions whose input set changed are recomputed; others reuse.

Reports: full_time, incremental_time, time_saved_ratio, reuse_count, recompute_count.

Usage (from geo-lineage folder):
  python -m scripts.experiment_incremental_recompute
  python -m scripts.experiment_incremental_recompute --n 5
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.run_pipeline import run_pipeline

# Dedicated dirs so we don't pollute main outputs/lineage
INC_OUTPUTS = ROOT / "incremental_experiment_outputs"
INC_LINEAGE = ROOT / "incremental_experiment_lineage_runs"

# Default: 5 small bboxes (same area, slightly shifted) so STAC may return same or different items
DEFAULT_BBOXES = [
    (-122.5, 37.5, -122.2, 37.8),
    (-122.4, 37.5, -122.1, 37.8),
    (-122.5, 37.6, -122.2, 37.9),
    (-122.45, 37.52, -122.15, 37.82),
    (-122.48, 37.55, -122.18, 37.85),
]

CATALOG = "https://earth-search.aws.element84.com/v1"
COLLECTION = "sentinel-2-c1-l2a"
MAX_ITEMS = 5


def main():
    p = argparse.ArgumentParser(
        description="Measure incremental recompute: time saved when re-running same regions (only changed regions recomputed)."
    )
    p.add_argument("--n", type=int, default=5, help="Number of regions (bboxes) to use (default 5)")
    args = p.parse_args()
    n = max(1, min(args.n, len(DEFAULT_BBOXES)))
    bboxes = DEFAULT_BBOXES[:n]

    INC_OUTPUTS.mkdir(parents=True, exist_ok=True)
    INC_LINEAGE.mkdir(parents=True, exist_ok=True)
    (INC_LINEAGE / "runs").mkdir(parents=True, exist_ok=True)

    print("=== Incremental recompute experiment ===\n")
    print(f"Regions: {n} bboxes, catalog={CATALOG}, collection={COLLECTION}, max_items={MAX_ITEMS}")
    print(f"Output dir: {INC_OUTPUTS}")
    print(f"Lineage dir: {INC_LINEAGE}\n")

    # Pass 1: full rebuild (all regions computed)
    print("Pass 1 (full rebuild):")
    start1 = time.perf_counter()
    pass1_recomputed = 0
    for i, bbox in enumerate(bboxes):
        _, run_id, reused_from = run_pipeline(
            bbox=bbox,
            catalog_url=CATALOG,
            collection=COLLECTION,
            max_items=MAX_ITEMS,
            output_dir=INC_OUTPUTS,
            lineage_dir=INC_LINEAGE,
        )
        if reused_from:
            pass1_recomputed -= 1  # shouldn't happen on first pass
        pass1_recomputed += 1
        print(f"  Region {i + 1}: {run_id[:8]}...")
    full_time = time.perf_counter() - start1
    print(f"  Full rebuild time: {full_time:.2f}s\n")

    # Pass 2: incremental (same regions; expect reuse when input set unchanged)
    print("Pass 2 (incremental):")
    start2 = time.perf_counter()
    pass2_reused = 0
    pass2_recomputed = 0
    for i, bbox in enumerate(bboxes):
        _, run_id, reused_from = run_pipeline(
            bbox=bbox,
            catalog_url=CATALOG,
            collection=COLLECTION,
            max_items=MAX_ITEMS,
            output_dir=INC_OUTPUTS,
            lineage_dir=INC_LINEAGE,
        )
        if reused_from:
            pass2_reused += 1
            print(f"  Region {i + 1}: reused from {reused_from[:8]}...")
        else:
            pass2_recomputed += 1
            print(f"  Region {i + 1}: recomputed {run_id[:8]}...")
    incremental_time = time.perf_counter() - start2
    print(f"  Incremental pass time: {incremental_time:.2f}s\n")

    # Metric
    if full_time > 0:
        time_saved_ratio = (full_time - incremental_time) / full_time
        time_saved_pct = time_saved_ratio * 100
    else:
        time_saved_ratio = 0.0
        time_saved_pct = 0.0

    print("--- Results ---")
    print(f"  Full rebuild (pass 1):     {full_time:.2f}s")
    print(f"  Incremental (pass 2):     {incremental_time:.2f}s")
    print(f"  Reused in pass 2:         {pass2_reused}/{n}")
    print(f"  Recomputed in pass 2:     {pass2_recomputed}/{n}")
    print(f"  Time saved (vs full):     {time_saved_pct:.1f}%")
    print(f"  Recompute time saved:     {full_time - incremental_time:.2f}s")
    print("\n=== Done ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())

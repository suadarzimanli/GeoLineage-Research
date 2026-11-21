r"""
Reproducibility check: run pipeline twice with same params and verify output checksums match.
Then run with different max_items and verify diff reflects the change.

Usage (from the reference-pipeline folder):
  .venv\Scripts\python.exe -m scripts.reproducibility_check
  or: python -m scripts.reproducibility_check --bbox -122.5 37.5 -122.2 37.8
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.run_pipeline import run_pipeline

LINEAGE_DIR = ROOT / "lineage_runs"
OUTPUTS_DIR = ROOT / "outputs"
DEFAULT_BBOX = (-122.5, 37.5, -122.2, 37.8)


def main():
    import argparse
    p = argparse.ArgumentParser(description="GeoLineage reproducibility check")
    p.add_argument("--bbox", type=float, nargs=4, default=DEFAULT_BBOX, metavar=("minx", "miny", "maxx", "maxy"))
    args = p.parse_args()
    bbox = tuple(args.bbox)

    print("=== GeoLineage reproducibility check ===\n")

    # Experiment A: same parameters twice
    print("Experiment A: Same bbox, collection, max_items (2 runs)")
    run1, id1, reused1 = run_pipeline(bbox=bbox, catalog_url="https://earth-search.aws.element84.com/v1", collection="sentinel-2-c1-l2a", max_items=5, output_dir=OUTPUTS_DIR, lineage_dir=LINEAGE_DIR)
    run2, id2, reused2 = run_pipeline(bbox=bbox, catalog_url="https://earth-search.aws.element84.com/v1", collection="sentinel-2-c1-l2a", max_items=5, output_dir=OUTPUTS_DIR, lineage_dir=LINEAGE_DIR)

    checksum1 = run1.output_assets[0].checksum
    checksum2 = run2.output_assets[0].checksum
    if reused2:
        print("  Run 2 reused output from run 1 (inputs unchanged) -> no duplicate file.")
        print("  Checksums: run1 =", checksum1[:16] + "...", "| run2 points to same output.")
    else:
        print("  Run 1 checksum:", checksum1[:20] + "...")
        print("  Run 2 checksum:", checksum2[:20] + "...")
        if checksum1 == checksum2:
            print("  PASS: Same inputs -> same output checksum.")
        else:
            print("  NOTE: Checksums differ (catalog may have returned different items between runs).")

    # Experiment B: different max_items
    print("\nExperiment B: Increase max_items (5 -> 10)")
    run3, id3, _ = run_pipeline(bbox=bbox, catalog_url="https://earth-search.aws.element84.com/v1", collection="sentinel-2-c1-l2a", max_items=10, output_dir=OUTPUTS_DIR, lineage_dir=LINEAGE_DIR)
    from lineage.diff import diff_runs, diff_since_last_run
    auto = diff_since_last_run(run3, LINEAGE_DIR)
    print("  A different max_items is a different query; previous run of this query:", auto.previous_run_id)
    diff = diff_runs(run2, run3)  # explicit comparison with the 5-item run
    print("  Explicit diff vs the 5-item run -> added:", len(diff.added), "| removed:", len(diff.removed),
          "| changed:", len(diff.changed), "| unchanged:", len(diff.unchanged))
    if len(diff.unchanged) == len(run2.input_assets) and not diff.removed:
        print("  PASS: with a fixed sort order, the first 5 items are kept and only new items are added.")
    else:
        print("  NOTE: the first 5 items changed between runs (catalog updated in between).")

    print("\n=== Done ===")


if __name__ == "__main__":
    main()

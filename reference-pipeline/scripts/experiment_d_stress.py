r"""
Experiment D: Non-determinism stress test.
Run the pipeline N times with identical parameters and report:
  - Reuse rate (runs 2..N that reused prior output) / (N-1)
  - Input-set stability (runs where input_assets matched previous) / (N-1)
  - Spurious diff rate (runs where diff reported added/removed despite same params) / (N-1)

Usage (from the reference-pipeline folder):
  .venv\Scripts\python.exe -m scripts.experiment_d_stress --bbox -122.5 37.5 -122.2 37.8
  .venv\Scripts\python.exe -m scripts.experiment_d_stress --bbox -122.5 37.5 -122.2 37.8 --n 20
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Use dedicated dirs so we don't pollute main or validation outputs
STRESS_OUTPUTS = ROOT / "experiment_d_outputs"
STRESS_LINEAGE = ROOT / "experiment_d_lineage_runs"

DEFAULT_BBOX = (-122.5, 37.5, -122.2, 37.8)
DEFAULT_N = 10


def main():
    import argparse
    p = argparse.ArgumentParser(description="Experiment D: non-determinism stress test (M5 reproducibility rate)")
    p.add_argument("--bbox", type=float, nargs=4, default=DEFAULT_BBOX, metavar=("minx", "miny", "maxx", "maxy"))
    p.add_argument("--n", type=int, default=DEFAULT_N, help="Number of consecutive runs with same params (default 10)")
    args = p.parse_args()
    bbox = tuple(args.bbox)
    n = max(2, args.n)

    STRESS_OUTPUTS.mkdir(parents=True, exist_ok=True)
    STRESS_LINEAGE.mkdir(parents=True, exist_ok=True)
    (STRESS_LINEAGE / "runs").mkdir(parents=True, exist_ok=True)

    from scripts.run_pipeline import run_pipeline
    from lineage.diff import diff_since_last_run, input_assets_equal
    from lineage.store import get_previous_run_id, load_run

    catalog_url = "https://earth-search.aws.element84.com/v1"
    collection = "sentinel-2-c1-l2a"
    max_items = 5

    reuse_count = 0  # only for runs 2..N (reruns)
    input_stable_count = 0
    spurious_diff_count = 0
    prev_run_id = None
    prev_input_assets = None

    print("Experiment D: Non-determinism stress test")
    print("=" * 60)
    print(f"Bbox: {bbox}, catalog: Earth Search, collection: {collection}, max_items: {max_items}")
    print(f"N = {n} runs (same parameters)")
    print(f"Outputs: {STRESS_OUTPUTS}, Lineage: {STRESS_LINEAGE}")
    print()

    for i in range(n):
        run, run_id, reused = run_pipeline(
            bbox=bbox,
            catalog_url=catalog_url,
            collection=collection,
            max_items=max_items,
            output_dir=STRESS_OUTPUTS,
            lineage_dir=STRESS_LINEAGE,
        )
        if i > 0 and reused:
            reuse_count += 1
        if prev_run_id and prev_input_assets is not None:
            if input_assets_equal(run.input_assets, prev_input_assets):
                input_stable_count += 1
            diff = diff_since_last_run(run, STRESS_LINEAGE)
            if diff.previous_run_id and (len(diff.added) > 0 or len(diff.removed) > 0):
                spurious_diff_count += 1
        prev_run_id = run_id
        prev_input_assets = run.input_assets
        print(f"  Run {i+1}/{n}: run_id={run_id[:8]}... reused={bool(reused)}")

    denom = n - 1
    reuse_rate = reuse_count / denom if denom else 0
    input_stability = input_stable_count / denom if denom else 0
    spurious_rate = spurious_diff_count / denom if denom else 0

    print()
    print("Metrics (M5 / Experiment D):")
    print(f"  Reuse rate:           {reuse_count}/{denom} = {reuse_rate:.2%}")
    print(f"  Input-set stability:  {input_stable_count}/{denom} = {input_stability:.2%}")
    print(f"  Spurious diff rate:   {spurious_diff_count}/{denom} = {spurious_rate:.2%}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())

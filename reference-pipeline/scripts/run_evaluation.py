r"""
Run evaluation: lineage completeness (can we answer "what produced this?" for every output?)
and optional summary of where to get other metrics.

Usage (from geo-lineage folder):
  python -m scripts.run_evaluation
  python -m scripts.run_evaluation --lineage-dir lineage_runs
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lineage.store import list_runs, load_run, DEFAULT_LINEAGE_DIR
from lineage.query import get_lineage


def main():
    p = argparse.ArgumentParser(
        description="Evaluate GeoLineage: lineage completeness (what produced this? for every output)."
    )
    p.add_argument(
        "--lineage-dir",
        type=Path,
        default=ROOT / "lineage_runs",
        help="Lineage directory (default: lineage_runs)",
    )
    args = p.parse_args()
    lineage_dir = args.lineage_dir

    if not lineage_dir.exists() or not (lineage_dir / "runs").exists():
        print("No lineage runs found at", lineage_dir)
        print("Run the pipeline at least once, then run this script again.")
        return 1

    runs = list_runs(lineage_dir)
    if not runs:
        print("No runs in", lineage_dir)
        return 1

    complete = 0
    total_outputs = 0
    for run_id in runs:
        run = load_run(run_id, lineage_dir)
        if not run or not run.output_assets:
            continue
        for i in range(len(run.output_assets)):
            total_outputs += 1
            result = get_lineage(run_id=run_id, output_index=i, lineage_dir=lineage_dir)
            if result and result.produced_by.inputs and result.produced_by.transform_name:
                complete += 1

    print("=== GeoLineage evaluation ===\n")
    print("Lineage completeness (can we answer 'what produced this output?' for every output?)")
    if total_outputs == 0:
        print("  No outputs found.")
    else:
        pct = 100.0 * complete / total_outputs if total_outputs else 0
        print(f"  Complete: {complete}/{total_outputs} ({pct:.1f}%)")
        if complete == total_outputs:
            print("  Target 100%: PASS")
        else:
            print("  Target 100%: not met (check runs with missing or invalid lineage_dag)")

    print("\n--- Other metrics (run these scripts for full evaluation) ---")
    print("  Reproducibility / reuse:  python -m scripts.validation_suite")
    print("  Reproducibility (A+B):     python -m scripts.reproducibility_check")
    print("  Stress (M5):              python -m scripts.experiment_d_stress --n 20")
    print("  Incremental recompute:    python -m scripts.experiment_incremental_recompute --n 5")
    print("\n=== Done ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())

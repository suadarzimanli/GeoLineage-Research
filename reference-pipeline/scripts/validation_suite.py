r"""
Automated validation suite for GeoLineage.
Runs the main logic checks and prints a PASS/FAIL report.

Usage (from the reference-pipeline folder):
  .venv\Scripts\python.exe -m scripts.validation_suite
  .venv\Scripts\python.exe -m scripts.validation_suite --bbox -122.5 37.5 -122.2 37.8
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Use a dedicated subdir for validation runs so we don't pollute main outputs
VAL_OUTPUTS = ROOT / "validation_outputs"
VAL_LINEAGE = ROOT / "validation_lineage_runs"

DEFAULT_BBOX = (-122.5, 37.5, -122.2, 37.8)


def run_test(name: str, fn, *args, **kwargs):
    """Run a test function; return (passed: bool, message: str)."""
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        return False, str(e)


def test_1_first_run(bbox):
    """Test 1: First run produces output and lineage."""
    from scripts.run_pipeline import run_pipeline

    VAL_OUTPUTS.mkdir(parents=True, exist_ok=True)
    VAL_LINEAGE.mkdir(parents=True, exist_ok=True)
    (VAL_LINEAGE / "runs").mkdir(parents=True, exist_ok=True)

    run, run_id, reused = run_pipeline(
        bbox=bbox,
        catalog_url="https://earth-search.aws.element84.com/v1",
        collection="sentinel-2-c1-l2a",
        max_items=5,
        output_dir=VAL_OUTPUTS,
        lineage_dir=VAL_LINEAGE,
    )
    if not run.output_assets:
        return False, "No output_assets in run"
    out_path = Path(run.output_assets[0].path)
    lineage_path = VAL_LINEAGE / "runs" / f"{run_id}.json"
    if not out_path.exists():
        return False, f"Output file missing: {out_path}"
    if not lineage_path.exists():
        return False, f"Lineage file missing: {lineage_path}"
    return True, f"Run {run_id[:8]}... -> output + lineage OK"


def test_2_reuse(bbox):
    """Test 2: Second run with same params reuses output (minimum recompute)."""
    from scripts.run_pipeline import run_pipeline
    from lineage.store import get_latest_run_id, load_run

    latest_before = get_latest_run_id(VAL_LINEAGE)
    run, run_id, reused = run_pipeline(
        bbox=bbox,
        catalog_url="https://earth-search.aws.element84.com/v1",
        collection="sentinel-2-c1-l2a",
        max_items=5,
        output_dir=VAL_OUTPUTS,
        lineage_dir=VAL_LINEAGE,
    )
    if not reused:
        return False, f"Expected reuse; got reused_from={reused}"
    if run.output_assets[0].path != load_run(latest_before, VAL_LINEAGE).output_assets[0].path:
        return False, "Reused run should point to previous output path"
    return True, f"Output unchanged (reused from {reused[:8]}...)"


def test_3_diff(bbox):
    """Test 3: A different query (more items) is a new query: no automatic diff, new output;
    an explicit comparison with the 5-item run shows the 5 shared items and the added ones."""
    from scripts.run_pipeline import run_pipeline
    from lineage.diff import diff_runs, diff_since_last_run
    from lineage.store import get_latest_run_id, load_run

    five = load_run(get_latest_run_id(VAL_LINEAGE), VAL_LINEAGE)

    run, run_id, reused = run_pipeline(
        bbox=bbox,
        catalog_url="https://earth-search.aws.element84.com/v1",
        collection="sentinel-2-c1-l2a",
        max_items=10,
        output_dir=VAL_OUTPUTS,
        lineage_dir=VAL_LINEAGE,
    )
    if reused:
        return False, "Expected new output when max_items increased"
    if diff_since_last_run(run, VAL_LINEAGE).previous_run_id is not None:
        return False, "A different query must not be diffed automatically"
    diff = diff_runs(five, run)
    if len(diff.unchanged) != len(five.input_assets) or diff.removed:
        return False, f"Expected the 5 items to be kept; got unchanged={len(diff.unchanged)}, removed={len(diff.removed)}"
    return True, f"Explicit diff vs 5-item run: added={len(diff.added)}, unchanged={len(diff.unchanged)}, removed=0"


def test_4_lineage_structure():
    """Test 4: Lineage JSON has required fields."""
    from lineage.store import get_latest_run_id, load_run

    run_id = get_latest_run_id(VAL_LINEAGE)
    if not run_id:
        return False, "No run to load"
    run = load_run(run_id, VAL_LINEAGE)
    if not run:
        return False, f"Could not load run {run_id}"
    required = ["run_id", "timestamp", "catalog_url", "search_params", "input_assets", "transform_steps", "output_assets"]
    d = run.to_dict()
    missing = [k for k in required if k not in d]
    if missing:
        return False, f"Lineage missing keys: {missing}"
    if not run.output_assets:
        return False, "output_assets empty"
    if not run.output_assets[0].checksum:
        return False, "output_assets[0].checksum empty"
    return True, "Lineage has run_id, timestamp, catalog_url, search_params, input_assets, transform_steps, output_assets, checksum"


def main():
    import argparse
    p = argparse.ArgumentParser(description="GeoLineage validation suite")
    p.add_argument("--bbox", type=float, nargs=4, default=DEFAULT_BBOX, metavar=("minx", "miny", "maxx", "maxy"))
    args = p.parse_args()
    bbox = tuple(args.bbox)

    import shutil
    for d in (VAL_OUTPUTS, VAL_LINEAGE):  # start clean so earlier sessions cannot change the outcome
        shutil.rmtree(d, ignore_errors=True)

    print("=" * 60)
    print("GeoLineage Validation Suite")
    print("=" * 60)
    print(f"Bbox: {bbox}")
    print(f"Validation outputs: {VAL_OUTPUTS}")
    print(f"Validation lineage: {VAL_LINEAGE}")
    print()

    tests = [
        ("1. First run (output + lineage)", test_1_first_run, (bbox,)),
        ("2. Second run same params (reuse)", test_2_reuse, (bbox,)),
        ("3. Run more items (diff)", test_3_diff, (bbox,)),
        ("4. Lineage structure", test_4_lineage_structure, ()),
    ]
    results = []
    for name, fn, fn_args in tests:
        passed, msg = run_test(name, fn, *fn_args)
        results.append((name, passed, msg))
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")
        print(f"        {msg}")
        print()

    print("=" * 60)
    passed_count = sum(1 for _, p, _ in results if p)
    total = len(results)
    if passed_count == total:
        print(f"All {total} tests PASSED. Logic validated.")
    else:
        print(f"Result: {passed_count}/{total} passed.")
    print("=" * 60)
    return 0 if passed_count == total else 1


if __name__ == "__main__":
    sys.exit(main())

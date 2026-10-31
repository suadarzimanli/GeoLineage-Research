r"""
Query lineage: answer "what produced this output?" (by output path or run_id).

Usage (from geo-lineage folder):
  python -m scripts.query_lineage --run-id <run_id>
  python -m scripts.query_lineage --output <path_to_footprints.parquet>
  .venv\Scripts\python.exe -m scripts.query_lineage --run-id <run_id>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lineage.query import get_lineage
from lineage.store import DEFAULT_LINEAGE_DIR


def _format_result(r) -> str:
    lines = [
        "--- What produced this output? ---",
        f"Run ID: {r.run_id}",
        f"Output: {r.output.get('path', '')}",
        f"  checksum: {r.output.get('checksum', '')[:24]}...",
        f"  crs: {r.output.get('crs', '')}",
        "",
        "Produced by:",
        f"  transform: {r.produced_by.transform_name}",
        f"  parameters: {json.dumps(r.produced_by.parameters, indent=4)}",
        "  inputs:",
    ]
    for i, inp in enumerate(r.produced_by.inputs):
        lines.append(f"    [{i}] catalog: {inp.get('catalog_url', '')}")
        lines.append(f"        search_params: {json.dumps(inp.get('search_params', {}))}")
        lines.append(f"        input_asset_count: {inp.get('input_asset_count', 0)}")
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(
        description='Query lineage: which inputs + parameters produced this output?'
    )
    p.add_argument("--output", type=Path, default=None, help="Path to output file (e.g. footprints.parquet)")
    p.add_argument("--run-id", type=str, default=None, help="Run ID (use instead of --output)")
    p.add_argument("--output-index", type=int, default=0, help="Output index when using --run-id (default 0)")
    p.add_argument("--lineage-dir", type=Path, default=ROOT / "lineage_runs", help="Lineage directory")
    p.add_argument("--json", action="store_true", help="Print raw JSON instead of human-readable summary")
    args = p.parse_args()

    if args.output is None and args.run_id is None:
        p.error("Provide either --output <path> or --run-id <run_id>")

    result = get_lineage(
        output_path=args.output,
        run_id=args.run_id,
        output_index=args.output_index,
        lineage_dir=args.lineage_dir,
    )

    if result is None:
        print("No lineage found for the given output or run_id.", file=sys.stderr)
        sys.exit(1)

    if args.json:
        out = {
            "run_id": result.run_id,
            "output": result.output,
            "produced_by": {
                "transform_name": result.produced_by.transform_name,
                "parameters": result.produced_by.parameters,
                "inputs": result.produced_by.inputs,
            },
        }
        print(json.dumps(out, indent=2))
    else:
        print(_format_result(result))


if __name__ == "__main__":
    main()

"""
Query lineage: answer "what produced this output?" by walking the lineage DAG backward.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .schema import LineageRun, LineageDAG, DAGNode, DAGEdge, build_dag_from_run
from .store import load_run, list_runs, DEFAULT_LINEAGE_DIR


@dataclass
class ProducedBy:
    """Summary of how an output was produced (transform + inputs)."""
    transform_name: str
    parameters: dict[str, Any]
    inputs: list[dict[str, Any]]  # list of input_set summaries: catalog_url, search_params, input_asset_count


@dataclass
class LineageQueryResult:
    """Result of 'what produced this output?' query."""
    run_id: str
    output: dict[str, Any]  # path, checksum, crs
    produced_by: ProducedBy


def _find_run_id_by_output_path(
    output_path: str | Path,
    lineage_dir: Path | None = None,
) -> str | None:
    """Find run_id of the run that produced this output path (or contains it)."""
    lineage_dir = lineage_dir or DEFAULT_LINEAGE_DIR
    try:
        query_resolved = Path(output_path).resolve()
    except Exception:
        query_resolved = Path(output_path)
    query_str = str(query_resolved)
    for run_id in list_runs(lineage_dir):
        run = load_run(run_id, lineage_dir)
        if run is None:
            continue
        for out in run.output_assets:
            try:
                stored = Path(out.path).resolve()
            except Exception:
                stored = Path(out.path)
            if str(stored) == query_str or query_str in str(stored) or str(stored) in query_str:
                return run_id
    return None


def get_lineage(
    output_path: str | Path | None = None,
    run_id: str | None = None,
    output_index: int = 0,
    lineage_dir: Path | None = None,
) -> LineageQueryResult | None:
    """
    Answer "what produced this output?" by walking the lineage DAG backward.

    Call with either:
      - output_path: path to the output file (searches all runs for matching output_assets.path)
      - run_id (and optionally output_index): direct run and output index (default 0).

    Returns a LineageQueryResult with output, transform name/parameters, and input set summary;
    or None if not found.
    """
    lineage_dir = lineage_dir or DEFAULT_LINEAGE_DIR
    rid = run_id
    if rid is None and output_path is not None:
        rid = _find_run_id_by_output_path(output_path, lineage_dir)
    if rid is None:
        return None

    run = load_run(rid, lineage_dir)
    if run is None or not run.output_assets:
        return None
    if output_index >= len(run.output_assets):
        return None

    dag = run.lineage_dag if run.lineage_dag is not None else build_dag_from_run(run)
    out_asset = run.output_assets[output_index]
    out_id = f"{run.run_id}:output_{output_index}"

    # Find edge into this output node
    in_edge: DAGEdge | None = None
    for e in dag.edges:
        if e.to_node_id == out_id:
            in_edge = e
            break
    if in_edge is None:
        return None

    # Find predecessor node(s) (input_set)
    inputs_summary: list[dict[str, Any]] = []
    for n in dag.nodes:
        if n.node_id == in_edge.from_node_id and n.type == "input_set":
            data = n.data
            inputs_summary.append({
                "catalog_url": data.get("catalog_url"),
                "search_params": data.get("search_params"),
                "input_asset_count": len(data.get("input_assets", [])),
            })
            break

    return LineageQueryResult(
        run_id=run.run_id,
        output={"path": out_asset.path, "checksum": out_asset.checksum, "crs": out_asset.crs},
        produced_by=ProducedBy(
            transform_name=in_edge.transform_name,
            parameters=in_edge.parameters,
            inputs=inputs_summary,
        ),
    )


def get_lineage_by_run_id(
    run_id: str,
    output_index: int = 0,
    lineage_dir: Path | None = None,
) -> LineageQueryResult | None:
    """Convenience: get lineage for the given run and output index (default first output)."""
    return get_lineage(run_id=run_id, output_index=output_index, lineage_dir=lineage_dir)

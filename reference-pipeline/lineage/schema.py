"""Lineage schema: run metadata, input/output assets, transform steps, and lineage DAG."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
import json
import uuid


# ---------------------------------------------------------------------------
# DAG types (STACD-style: nodes = input_set / output_asset, edges = transform)
# ---------------------------------------------------------------------------

@dataclass
class DAGNode:
    """One node in the lineage DAG. type is 'input_set' or 'output_asset'."""
    node_id: str
    type: str  # "input_set" | "output_asset"
    data: dict[str, Any]  # type-specific: catalog_url, search_params, input_assets | path, checksum, crs

    def to_dict(self) -> dict[str, Any]:
        return {"node_id": self.node_id, "type": self.type, "data": self.data}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DAGNode":
        return cls(node_id=d["node_id"], type=d["type"], data=d["data"])


@dataclass
class DAGEdge:
    """Edge: from_node_id -> transform -> to_node_id."""
    from_node_id: str
    to_node_id: str
    transform_name: str
    parameters: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_node_id": self.from_node_id,
            "to_node_id": self.to_node_id,
            "transform_name": self.transform_name,
            "parameters": self.parameters,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DAGEdge":
        return cls(
            from_node_id=d["from_node_id"],
            to_node_id=d["to_node_id"],
            transform_name=d["transform_name"],
            parameters=d.get("parameters", {}),
        )


@dataclass
class LineageDAG:
    """Lineage as a directed acyclic graph: nodes (input_set, output_asset) and edges (transform)."""
    nodes: list[DAGNode]
    edges: list[DAGEdge]

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "LineageDAG":
        nodes = [DAGNode.from_dict(n) for n in d.get("nodes", [])]
        edges = [DAGEdge.from_dict(e) for e in d.get("edges", [])]
        return cls(nodes=nodes, edges=edges)


def build_dag_from_run(run: "LineageRun") -> LineageDAG:
    """Build a LineageDAG from a LineageRun (for current single-step pipeline or backward compat)."""
    nodes: list[DAGNode] = []
    edges: list[DAGEdge] = []

    # One input_set node
    input_set_id = f"{run.run_id}:input_set"
    nodes.append(DAGNode(
        node_id=input_set_id,
        type="input_set",
        data={
            "catalog_url": run.catalog_url,
            "search_params": run.search_params,
            "input_assets": [a.to_dict() for a in run.input_assets],
        },
    ))

    # One output_asset node per output
    for i, out in enumerate(run.output_assets):
        out_id = f"{run.run_id}:output_{i}"
        nodes.append(DAGNode(
            node_id=out_id,
            type="output_asset",
            data={"path": out.path, "checksum": out.checksum, "crs": out.crs},
        ))
        # Edge: input_set -> transform -> this output
        step = run.transform_steps[i] if i < len(run.transform_steps) else run.transform_steps[0]
        edges.append(DAGEdge(
            from_node_id=input_set_id,
            to_node_id=out_id,
            transform_name=step.name,
            parameters=step.parameters,
        ))

    return LineageDAG(nodes=nodes, edges=edges)


# ---------------------------------------------------------------------------
# Run-level schema (existing)
# ---------------------------------------------------------------------------

@dataclass
class InputAsset:
    """One input (STAC item or asset) used in the pipeline."""
    id: str
    href: str
    checksum: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "href": self.href, "checksum": self.checksum}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "InputAsset":
        return cls(id=d["id"], href=d["href"], checksum=d.get("checksum"))


@dataclass
class OutputAsset:
    """One output file produced by the pipeline."""
    path: str
    checksum: str
    crs: str

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "checksum": self.checksum, "crs": self.crs}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "OutputAsset":
        return cls(path=d["path"], checksum=d["checksum"], crs=d["crs"])


@dataclass
class TransformStep:
    """One transform step (name + parameters)."""
    name: str
    parameters: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "parameters": self.parameters}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TransformStep":
        return cls(name=d["name"], parameters=d.get("parameters", {}))


@dataclass
class LineageRun:
    """Full lineage record for one pipeline run. Optionally includes lineage_dag (STACD-style DAG)."""
    run_id: str
    timestamp: str
    catalog_url: str
    search_params: dict[str, Any]
    input_assets: list[InputAsset]
    transform_steps: list[TransformStep]
    output_assets: list[OutputAsset]
    lineage_dag: LineageDAG | None = None  # optional; built from run if missing when loading old JSON

    def to_dict(self) -> dict[str, Any]:
        out = {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "catalog_url": self.catalog_url,
            "search_params": self.search_params,
            "input_assets": [a.to_dict() for a in self.input_assets],
            "transform_steps": [t.to_dict() for t in self.transform_steps],
            "output_assets": [a.to_dict() for a in self.output_assets],
        }
        if self.lineage_dag is not None:
            out["lineage_dag"] = self.lineage_dag.to_dict()
        return out

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "LineageRun":
        dag = None
        if "lineage_dag" in d and d["lineage_dag"]:
            dag = LineageDAG.from_dict(d["lineage_dag"])
        run = cls(
            run_id=d["run_id"],
            timestamp=d["timestamp"],
            catalog_url=d["catalog_url"],
            search_params=d["search_params"],
            input_assets=[InputAsset.from_dict(a) for a in d["input_assets"]],
            transform_steps=[TransformStep.from_dict(t) for t in d["transform_steps"]],
            output_assets=[OutputAsset.from_dict(a) for a in d["output_assets"]],
            lineage_dag=dag,
        )
        # Backward compatibility: if no DAG was stored, build it from the run
        if run.lineage_dag is None:
            run.lineage_dag = build_dag_from_run(run)
        return run

    @classmethod
    def from_json(cls, s: str) -> "LineageRun":
        return cls.from_dict(json.loads(s))


def new_run_id() -> str:
    return str(uuid.uuid4())


def timestamp_iso() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

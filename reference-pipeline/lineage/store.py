"""Persist and query lineage runs (JSON files under lineage/runs/)."""

from pathlib import Path
from .schema import LineageRun

# Default directory for lineage runs (relative to project root or cwd)
DEFAULT_LINEAGE_DIR = Path(__file__).resolve().parent.parent / "lineage_runs"


def _ensure_lineage_dir(lineage_dir: Path) -> Path:
    lineage_dir = Path(lineage_dir)
    (lineage_dir / "runs").mkdir(parents=True, exist_ok=True)
    return lineage_dir


def record_run(run: LineageRun, lineage_dir: Path | None = None) -> Path:
    """Save a lineage run to lineage_dir/runs/{run_id}.json. Returns path to file."""
    lineage_dir = lineage_dir or DEFAULT_LINEAGE_DIR
    _ensure_lineage_dir(lineage_dir)
    path = lineage_dir / "runs" / f"{run.run_id}.json"
    path.write_text(run.to_json(), encoding="utf-8")
    return path


def load_run(run_id: str, lineage_dir: Path | None = None) -> LineageRun | None:
    """Load a lineage run by run_id. Returns None if not found."""
    lineage_dir = lineage_dir or DEFAULT_LINEAGE_DIR
    path = lineage_dir / "runs" / f"{run_id}.json"
    if not path.exists():
        return None
    return LineageRun.from_json(path.read_text(encoding="utf-8"))


def list_runs(lineage_dir: Path | None = None) -> list[str]:
    """List all run_ids (ordered by filename; no timestamp sort)."""
    lineage_dir = lineage_dir or DEFAULT_LINEAGE_DIR
    runs_dir = lineage_dir / "runs"
    if not runs_dir.exists():
        return []
    return [p.stem for p in runs_dir.glob("*.json")]


def get_latest_run_id(lineage_dir: Path | None = None) -> str | None:
    """Return run_id of the most recent run (by timestamp in JSON)."""
    lineage_dir = lineage_dir or DEFAULT_LINEAGE_DIR
    runs_dir = lineage_dir / "runs"
    if not runs_dir.exists():
        return None
    latest_run = None
    latest_ts = None
    for p in runs_dir.glob("*.json"):
        run = LineageRun.from_json(p.read_text(encoding="utf-8"))
        if latest_ts is None or run.timestamp > latest_ts:
            latest_ts = run.timestamp
            latest_run = run.run_id
    return latest_run


def _bbox_match(stored_bbox: list | None, bbox: tuple[float, float, float, float]) -> bool:
    """True if stored_bbox (from JSON list) matches bbox tuple (order: minx, miny, maxx, maxy)."""
    if not stored_bbox or len(stored_bbox) != 4:
        return False
    return (
        abs(float(stored_bbox[0]) - bbox[0]) < 1e-9
        and abs(float(stored_bbox[1]) - bbox[1]) < 1e-9
        and abs(float(stored_bbox[2]) - bbox[2]) < 1e-9
        and abs(float(stored_bbox[3]) - bbox[3]) < 1e-9
    )


def get_latest_run_id_for_region(
    lineage_dir: Path | None = None,
    catalog_url: str | None = None,
    collection: str | None = None,
    bbox: tuple[float, float, float, float] | None = None,
) -> str | None:
    """
    Return run_id of the most recent run (by timestamp) that matches the given region:
    same catalog_url, same search_params.collection, and same search_params.bbox.
    Used for incremental recompute: reuse only from runs that targeted the same region.
    """
    lineage_dir = lineage_dir or DEFAULT_LINEAGE_DIR
    runs_dir = lineage_dir / "runs"
    if not runs_dir.exists():
        return None
    latest_run = None
    latest_ts = None
    for p in runs_dir.glob("*.json"):
        run = LineageRun.from_json(p.read_text(encoding="utf-8"))
        if catalog_url is not None and run.catalog_url != catalog_url:
            continue
        if collection is not None and run.search_params.get("collection") != collection:
            continue
        if bbox is not None and not _bbox_match(run.search_params.get("bbox"), bbox):
            continue
        if latest_ts is None or run.timestamp > latest_ts:
            latest_ts = run.timestamp
            latest_run = run.run_id
    return latest_run


def get_previous_run_id(run_id: str, lineage_dir: Path | None = None) -> str | None:
    """Return run_id of the run with the next-oldest timestamp before the given run_id."""
    lineage_dir = lineage_dir or DEFAULT_LINEAGE_DIR
    runs_dir = lineage_dir / "runs"
    if not runs_dir.exists():
        return None
    runs_with_ts = []
    for p in runs_dir.glob("*.json"):
        run = LineageRun.from_json(p.read_text(encoding="utf-8"))
        runs_with_ts.append((run.run_id, run.timestamp))
    runs_with_ts.sort(key=lambda x: x[1])
    ids = [r[0] for r in runs_with_ts]
    if run_id not in ids:
        return None
    i = ids.index(run_id)
    return ids[i - 1] if i > 0 else None

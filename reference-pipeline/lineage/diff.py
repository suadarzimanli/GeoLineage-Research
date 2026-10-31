"""Diff current run's inputs vs previous run (what changed)."""

from pathlib import Path
from dataclasses import dataclass
from .schema import LineageRun, InputAsset
from .store import load_run, DEFAULT_LINEAGE_DIR


@dataclass
class DiffResult:
    """What changed between previous and current run (by input assets)."""
    previous_run_id: str | None
    added: list[InputAsset]
    removed: list[InputAsset]
    unchanged: list[InputAsset]


def _asset_key(a: InputAsset) -> tuple[str, str]:
    return (a.id, a.checksum or "")


def input_assets_equal(a_list: list[InputAsset], b_list: list[InputAsset]) -> bool:
    """True if the two lists contain the same set of inputs (by id and checksum)."""
    return {_asset_key(x) for x in a_list} == {_asset_key(x) for x in b_list}


def diff_since_last_run(
    current_run: LineageRun,
    lineage_dir: Path | None = None,
) -> DiffResult:
    """
    Compare current_run's input_assets to the previous run's (run with next-oldest
    timestamp). Returns added, removed, and unchanged assets.
    """
    from .store import get_previous_run_id
    lineage_dir = lineage_dir or DEFAULT_LINEAGE_DIR
    prev_run_id = get_previous_run_id(current_run.run_id, lineage_dir)
    prev_run = load_run(prev_run_id, lineage_dir) if prev_run_id else None

    current_set = {_asset_key(a): a for a in current_run.input_assets}
    previous_set = {_asset_key(a): a for a in (prev_run.input_assets if prev_run else [])}

    added = [current_set[k] for k in current_set if k not in previous_set]
    removed = [previous_set[k] for k in previous_set if k not in current_set]
    unchanged = [current_set[k] for k in current_set if k in previous_set]

    return DiffResult(
        previous_run_id=prev_run_id,
        added=added,
        removed=removed,
        unchanged=unchanged,
    )

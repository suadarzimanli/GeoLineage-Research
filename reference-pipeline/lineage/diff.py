"""Diff a run's inputs against the previous run of the *same query* (what changed, and why)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .identity import InputDiff, classify_removed, diff_inputs
from .schema import InputAsset, LineageRun
from .store import DEFAULT_LINEAGE_DIR, get_previous_run_for_query, load_run, run_query_key


@dataclass
class DiffResult:
    """What changed between the previous run of the same query and the current run."""
    previous_run_id: str | None
    added: list[InputAsset]
    removed: list[InputAsset]
    unchanged: list[InputAsset]
    changed: list[InputAsset] = field(default_factory=list)
    removed_reason: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "previous_run_id": self.previous_run_id,
            "added": [a.id for a in self.added],
            "removed": [a.id for a in self.removed],
            "changed": [a.id for a in self.changed],
            "unchanged": [a.id for a in self.unchanged],
            "removed_reason": self.removed_reason,
        }


def _identity_map(assets: list[InputAsset]) -> dict[str, str | None]:
    return {a.id: a.identity for a in assets}


def input_assets_equal(a_list: list[InputAsset], b_list: list[InputAsset]) -> bool:
    """True if both lists hold the same items with the same content (id + content hash or checksum)."""
    return diff_inputs(_identity_map(a_list), _identity_map(b_list)).identical


def diff_since_last_run(
    current_run: LineageRun,
    lineage_dir: Path | None = None,
    still_in_catalog: Callable[[str], bool | None] | None = None,
) -> DiffResult:
    """
    Compare the current run with the previous run of the same query. With `still_in_catalog`,
    removed items are labelled 'outside_window' (still in the catalog) or 'gone'.
    """
    lineage_dir = lineage_dir or DEFAULT_LINEAGE_DIR
    prev_id = get_previous_run_for_query(current_run.run_id, run_query_key(current_run), lineage_dir)
    prev = load_run(prev_id, lineage_dir) if prev_id else None
    if prev is None:
        return DiffResult(previous_run_id=None, added=list(current_run.input_assets), removed=[], unchanged=[])

    d: InputDiff = diff_inputs(_identity_map(prev.input_assets), _identity_map(current_run.input_assets))
    if still_in_catalog is not None and d.removed:
        classify_removed(d, still_in_catalog)
    cur = {a.id: a for a in current_run.input_assets}
    old = {a.id: a for a in prev.input_assets}
    return DiffResult(
        previous_run_id=prev_id,
        added=[cur[i] for i in d.added],
        removed=[old[i] for i in d.removed],
        unchanged=[cur[i] for i in d.unchanged],
        changed=[cur[i] for i in d.changed],
        removed_reason=d.removed_reason,
    )


def diff_runs(previous: LineageRun, current: LineageRun) -> DiffResult:
    """Explicit comparison of any two runs (e.g. the same area with a different max_items)."""
    d = diff_inputs(_identity_map(previous.input_assets), _identity_map(current.input_assets))
    cur = {a.id: a for a in current.input_assets}
    old = {a.id: a for a in previous.input_assets}
    return DiffResult(previous_run_id=previous.run_id, added=[cur[i] for i in d.added], removed=[old[i] for i in d.removed],
                      unchanged=[cur[i] for i in d.unchanged], changed=[cur[i] for i in d.changed])

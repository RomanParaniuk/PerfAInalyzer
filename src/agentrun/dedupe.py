"""Location-keyed duplicate-finding merge for the agent path (FR-011, research.md §7).

Parallel same-stage subagents can repeat a finding at partition boundaries or via
shared-context leakage; this merge collapses exactly those repeats. Applied per stage
to the union of its units' findings (so cross-stage findings at one location are never
merged — stage attribution is part of the report contract). Deterministic and
token-free: survivor by highest severity rank, then longest `suggested_action`, then
first in input (sorted-filename union) order; the survivor is kept verbatim."""

from __future__ import annotations

from collections.abc import Sequence

from src.models.finding import SEVERITY_RANK, StageFinding

# Rank used when severity is absent (valuable findings): always after real severities.
_NO_SEVERITY_RANK = len(SEVERITY_RANK) + 1


def _normalized_symbol(symbol: str | None) -> str:
    return (symbol or "").strip().lower()


def _merge_key(finding: StageFinding) -> tuple:
    return (
        finding.kind,
        finding.location.file_path,
        finding.location.line_start,
        _normalized_symbol(finding.location.symbol),
    )


def _survivor_rank(indexed: tuple[int, StageFinding]) -> tuple:
    index, finding = indexed
    severity_rank = (
        SEVERITY_RANK[finding.severity] if finding.severity is not None else _NO_SEVERITY_RANK
    )
    return (severity_rank, -len(finding.suggested_action or ""), index)


def dedupe_findings(findings: Sequence[StageFinding]) -> list[StageFinding]:
    """Collapse duplicate findings (same kind + location) to a single survivor.

    Output keeps the first-seen order of each duplicate group, so the merged union
    stays deterministic for downstream stamping and aggregation."""
    groups: dict[tuple, list[tuple[int, StageFinding]]] = {}
    for index, finding in enumerate(findings):
        groups.setdefault(_merge_key(finding), []).append((index, finding))
    return [min(group, key=_survivor_rank)[1] for group in groups.values()]

"""Deterministic report aggregation: merge stage findings into one `Report` with
severity/priority ordering, explicit empty sections, and incomplete-stage notes.
No AI involvement in this step (Principle II, IV)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from src.models.action_item import PRIORITY_RANK, ActionItem, Priority
from src.models.finding import SEVERITY_RANK, Finding, FindingKind
from src.models.report import AnalysisRun, IncompleteStage, Report
from src.models.stage import STAGE_ORDER_INDEX, StageStatus
from src.providers.anthropic_client import is_near_identical

logger = logging.getLogger("perf_ai.aggregator")


def _issue_sort_key(finding: Finding) -> tuple:
    assert finding.severity is not None  # guaranteed by model validation for issues
    return (
        SEVERITY_RANK[finding.severity],
        STAGE_ORDER_INDEX[finding.originating_stage],
        finding.location.file_path,
        finding.location.line_start or 0,
    )


def _valuable_sort_key(finding: Finding) -> tuple:
    return (
        STAGE_ORDER_INDEX[finding.originating_stage],
        finding.location.file_path,
        finding.location.line_start or 0,
    )


def derive_action_items(issues: list[Finding]) -> list[ActionItem]:
    """Build the Action Items section from Issue findings' `suggested_action` (FR-006).

    Priority derives from the related issue's severity; the list is priority-sorted so
    the highest-impact item is first (FR-008). A suggested action that merely restates
    its issue's description is rejected as a logged data-quality note — the issue stays
    in the report, but no action item is derived from it (not a hard failure)."""
    items: list[ActionItem] = []
    counter = 1
    for issue in issues:  # issues arrive severity-sorted; stable sort preserves that order
        action = issue.suggested_action or ""
        if is_near_identical(issue.description, action):
            logger.warning(
                "data-quality: dropping action item for %s — suggested_action is a "
                "near-identical restatement of the issue description",
                issue.finding_id,
            )
            continue
        assert issue.severity is not None
        items.append(
            ActionItem(
                action_item_id=f"action-{counter:03d}",
                related_finding_ids=[issue.finding_id],
                recommendation=action,
                priority=Priority(issue.severity.value),
            )
        )
        counter += 1
    items.sort(key=lambda item: PRIORITY_RANK[item.priority])
    return items


def aggregate(
    run: AnalysisRun,
    *,
    coverage_notes: list[str] | None = None,
    limitations: list[str] | None = None,
    generated_at: datetime | None = None,
) -> Report:
    """Merge all completed stages' findings into one `Report` (FR-004..FR-010, FR-012)."""
    all_findings = [f for stage in run.stages for f in stage.findings]

    issues = sorted(
        (f for f in all_findings if f.kind is FindingKind.ISSUE), key=_issue_sort_key
    )
    valuable = sorted(
        (f for f in all_findings if f.kind is FindingKind.VALUABLE_FINDING),
        key=_valuable_sort_key,
    )

    incomplete = [
        IncompleteStage(stage=s.name, reason=s.failure_reason or "did not complete")
        for s in run.stages
        if s.status in (StageStatus.FAILED, StageStatus.TIMED_OUT)
    ]

    notes = [n for n in (coverage_notes or []) if n and n.strip()]
    coverage_note = "\n".join(notes) if notes else None

    return Report(
        issues=issues,
        action_items=derive_action_items(issues),
        valuable_findings=valuable,
        incomplete_stages=incomplete,
        coverage_note=coverage_note,
        limitations=list(limitations or []),
        generated_at=generated_at or datetime.now(UTC),
    )

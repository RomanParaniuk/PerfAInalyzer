"""Unit tests (T055): aggregator severity/priority sorting edge cases (ties, mixed
stages) and the near-identical data-quality drop path."""

import logging
from datetime import UTC, datetime

from src.models.finding import Finding
from src.models.report import AnalysisRun, RunStatus
from src.models.stage import AnalysisStage, StageName, StageStatus
from src.report.aggregator import aggregate, derive_action_items


def issue(
    stage: StageName,
    n: int,
    severity: str,
    *,
    file_path: str = "orders.py",
    line: int | None = 10,
    description: str = "Nested loop performs an O(n^2) scan over the orders list.",
    action: str = "Build a set of seen ids before the loop and test membership against it.",
) -> Finding:
    return Finding.model_validate(
        {
            "finding_id": f"{stage.value}-{n:03d}",
            "originating_stage": stage,
            "kind": "issue",
            "description": description,
            "location": {"file_path": file_path, "line_start": line, "line_end": line},
            "severity": severity,
            "suggested_action": action,
        }
    )


def run_with(stages: dict[StageName, list[Finding]], *, failed: dict[StageName, str] | None = None) -> AnalysisRun:
    failed = failed or {}
    stage_models = []
    for name in StageName:
        if name in failed:
            stage_models.append(
                AnalysisStage(name=name, status=StageStatus.FAILED, failure_reason=failed[name])
            )
        else:
            stage_models.append(
                AnalysisStage(name=name, status=StageStatus.COMPLETED, findings=stages.get(name, []))
            )
    return AnalysisRun(
        code_scope_path="/scope",
        started_at=datetime.now(UTC),
        status=RunStatus.COMPLETED_WITH_PARTIAL_RESULTS if failed else RunStatus.COMPLETED,
        stages=stage_models,
    )


class TestIssueSorting:
    def test_severity_descending_across_stages(self):
        run = run_with(
            {
                StageName.CONCURRENCY_SCALABILITY: [issue(StageName.CONCURRENCY_SCALABILITY, 1, "critical")],
                StageName.ALGORITHMIC_COMPLEXITY: [issue(StageName.ALGORITHMIC_COMPLEXITY, 1, "low")],
                StageName.RESOURCE_IO_EFFICIENCY: [issue(StageName.RESOURCE_IO_EFFICIENCY, 1, "high")],
            }
        )
        report = aggregate(run)
        severities = [i.severity.value for i in report.issues]
        assert severities == ["critical", "high", "low"]

    def test_severity_tie_broken_by_stage_order(self):
        run = run_with(
            {
                StageName.CONCURRENCY_SCALABILITY: [issue(StageName.CONCURRENCY_SCALABILITY, 1, "high")],
                StageName.ALGORITHMIC_COMPLEXITY: [issue(StageName.ALGORITHMIC_COMPLEXITY, 1, "high")],
            }
        )
        report = aggregate(run)
        assert [i.originating_stage for i in report.issues] == [
            StageName.ALGORITHMIC_COMPLEXITY,
            StageName.CONCURRENCY_SCALABILITY,
        ]

    def test_full_tie_broken_by_file_then_line(self):
        run = run_with(
            {
                StageName.ALGORITHMIC_COMPLEXITY: [
                    issue(StageName.ALGORITHMIC_COMPLEXITY, 1, "medium", file_path="b.py", line=5),
                    issue(StageName.ALGORITHMIC_COMPLEXITY, 2, "medium", file_path="a.py", line=9),
                    issue(StageName.ALGORITHMIC_COMPLEXITY, 3, "medium", file_path="a.py", line=2),
                ]
            }
        )
        report = aggregate(run)
        keys = [(i.location.file_path, i.location.line_start) for i in report.issues]
        assert keys == [("a.py", 2), ("a.py", 9), ("b.py", 5)]


class TestActionItemDerivation:
    def test_priority_matches_related_issue_severity(self):
        issues = [issue(StageName.ALGORITHMIC_COMPLEXITY, 1, "critical")]
        items = derive_action_items(issues)
        assert len(items) == 1
        assert items[0].priority.value == "critical"
        assert items[0].related_finding_ids == ["algorithmic_complexity-001"]

    def test_near_identical_recommendation_dropped_and_logged(self, caplog):
        restatement = issue(
            StageName.ALGORITHMIC_COMPLEXITY,
            1,
            "high",
            description="The loop scans the orders list quadratically.",
            action="The loop scans the orders list quadratically!",
        )
        concrete = issue(StageName.RESOURCE_IO_EFFICIENCY, 1, "low")
        with caplog.at_level(logging.WARNING, logger="perf_ai.aggregator"):
            items = derive_action_items([restatement, concrete])
        assert len(items) == 1
        assert items[0].related_finding_ids == ["resource_io_efficiency-001"]
        assert any("data-quality" in r.message for r in caplog.records)

    def test_priority_sorted_highest_first(self):
        issues = [
            issue(StageName.ALGORITHMIC_COMPLEXITY, 1, "low"),
            issue(StageName.ALGORITHMIC_COMPLEXITY, 2, "critical"),
            issue(StageName.ALGORITHMIC_COMPLEXITY, 3, "medium"),
        ]
        priorities = [i.priority.value for i in derive_action_items(issues)]
        assert priorities == ["critical", "medium", "low"]


class TestAggregateReport:
    def test_incomplete_stages_recorded_with_reason(self):
        run = run_with({}, failed={StageName.RESOURCE_IO_EFFICIENCY: "timed out after 600s"})
        report = aggregate(run)
        assert len(report.incomplete_stages) == 1
        entry = report.incomplete_stages[0]
        assert entry.stage is StageName.RESOURCE_IO_EFFICIENCY
        assert entry.reason == "timed out after 600s"

    def test_coverage_notes_joined(self):
        run = run_with({})
        report = aggregate(run, coverage_notes=["note one", "", "note two"])
        assert report.coverage_note == "note one\nnote two"

    def test_empty_run_produces_empty_but_valid_report(self):
        report = aggregate(run_with({}))
        assert report.issues == []
        assert report.action_items == []
        assert report.valuable_findings == []
        assert report.coverage_note is None

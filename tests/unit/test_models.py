"""Unit tests for model validation rules (T009): severity iff issue, suggested_action iff
issue, non-empty file_path, report section kinds, and run-status masking rules."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from src.models.action_item import ActionItem, Priority
from src.models.finding import Finding, FindingKind, LocationRef, Severity, StageFinding
from src.models.report import AnalysisRun, IncompleteStage, Report, RunStatus
from src.models.stage import AnalysisStage, StageName, StageResult, StageStatus


def make_location(**overrides) -> dict:
    return {"file_path": "src/orders.py", "symbol": "find_duplicates", "line_start": 10, "line_end": 25} | overrides


def make_issue_payload(**overrides) -> dict:
    payload = {
        "kind": "issue",
        "description": "Nested loop performs an O(n^2) scan over the orders list.",
        "location": make_location(),
        "severity": "high",
        "suggested_action": "Build a set of seen order ids before the loop and test membership against it.",
    }
    return payload | overrides


class TestStageFindingCrossFieldRules:
    def test_valid_issue_accepted(self):
        finding = StageFinding.model_validate(make_issue_payload())
        assert finding.kind is FindingKind.ISSUE
        assert finding.severity is Severity.HIGH

    def test_issue_without_severity_rejected(self):
        with pytest.raises(ValidationError, match="severity is required"):
            StageFinding.model_validate(make_issue_payload(severity=None))

    def test_issue_without_suggested_action_rejected(self):
        with pytest.raises(ValidationError, match="suggested_action is required"):
            StageFinding.model_validate(make_issue_payload(suggested_action=None))

    def test_issue_with_blank_suggested_action_rejected(self):
        with pytest.raises(ValidationError, match="suggested_action is required"):
            StageFinding.model_validate(make_issue_payload(suggested_action="   "))

    def test_valuable_finding_with_severity_rejected(self):
        payload = make_issue_payload(kind="valuable_finding", suggested_action=None)
        with pytest.raises(ValidationError, match="severity must be null"):
            StageFinding.model_validate(payload)

    def test_valuable_finding_without_severity_accepted(self):
        payload = make_issue_payload(kind="valuable_finding", severity=None, suggested_action=None)
        finding = StageFinding.model_validate(payload)
        assert finding.kind is FindingKind.VALUABLE_FINDING
        assert finding.severity is None

    def test_empty_description_rejected(self):
        with pytest.raises(ValidationError):
            StageFinding.model_validate(make_issue_payload(description=""))


class TestLocationRef:
    def test_empty_file_path_rejected(self):
        with pytest.raises(ValidationError):
            LocationRef.model_validate(make_location(file_path=""))

    def test_line_end_before_line_start_rejected(self):
        with pytest.raises(ValidationError, match="line_end"):
            LocationRef.model_validate(make_location(line_start=20, line_end=10))

    def test_file_scoped_location_allows_null_lines(self):
        loc = LocationRef.model_validate({"file_path": "src/orders.py"})
        assert loc.line_start is None and loc.line_end is None


class TestFindingAttribution:
    def test_finding_requires_originating_stage_and_id(self):
        with pytest.raises(ValidationError):
            Finding.model_validate(make_issue_payload())

    def test_finding_with_attribution_accepted(self):
        finding = Finding.model_validate(
            make_issue_payload()
            | {"finding_id": "algorithmic_complexity-001", "originating_stage": "algorithmic_complexity"}
        )
        assert finding.originating_stage is StageName.ALGORITHMIC_COMPLEXITY


class TestActionItem:
    def test_requires_at_least_one_related_finding(self):
        with pytest.raises(ValidationError):
            ActionItem.model_validate(
                {
                    "action_item_id": "AI-001",
                    "related_finding_ids": [],
                    "recommendation": "Use a set for membership checks.",
                    "priority": "high",
                }
            )

    def test_valid_action_item(self):
        item = ActionItem.model_validate(
            {
                "action_item_id": "AI-001",
                "related_finding_ids": ["algorithmic_complexity-001"],
                "recommendation": "Use a set for membership checks.",
                "priority": "critical",
            }
        )
        assert item.priority is Priority.CRITICAL


class TestStageResult:
    def test_unknown_stage_name_rejected(self):
        with pytest.raises(ValidationError):
            StageResult.model_validate({"stage_name": "quantum_analysis", "findings": []})

    def test_empty_findings_is_valid_and_distinct_from_failure(self):
        result = StageResult.model_validate({"stage_name": "concurrency_scalability", "findings": []})
        assert result.findings == []
        assert result.coverage_note is None


def _stamped_issue() -> Finding:
    return Finding.model_validate(
        make_issue_payload()
        | {"finding_id": "algorithmic_complexity-001", "originating_stage": "algorithmic_complexity"}
    )


class TestReportSections:
    def test_issue_in_valuable_findings_rejected(self):
        with pytest.raises(ValidationError, match="valuable_findings"):
            Report.model_validate(
                {"valuable_findings": [_stamped_issue().model_dump()], "generated_at": datetime.now(UTC)}
            )

    def test_valuable_finding_in_issues_rejected(self):
        valuable = _stamped_issue().model_dump() | {
            "kind": "valuable_finding",
            "severity": None,
            "suggested_action": None,
        }
        with pytest.raises(ValidationError, match="issues"):
            Report.model_validate({"issues": [valuable], "generated_at": datetime.now(UTC)})

    def test_empty_sections_are_valid(self):
        report = Report.model_validate({"generated_at": datetime.now(UTC)})
        assert report.issues == [] and report.action_items == [] and report.valuable_findings == []


class TestAnalysisRunStatus:
    def _stage(self, name: StageName, status: StageStatus) -> AnalysisStage:
        return AnalysisStage(name=name, status=status)

    def test_completed_run_with_failed_stage_rejected(self):
        with pytest.raises(ValidationError, match="mask"):
            AnalysisRun(
                code_scope_path="/tmp/scope",
                started_at=datetime.now(UTC),
                status=RunStatus.COMPLETED,
                stages=[
                    self._stage(StageName.STRUCTURAL_CONTEXT, StageStatus.COMPLETED),
                    self._stage(StageName.ALGORITHMIC_COMPLEXITY, StageStatus.FAILED),
                ],
            )

    def test_partial_results_status_requires_a_failed_stage(self):
        with pytest.raises(ValidationError, match="partial"):
            AnalysisRun(
                code_scope_path="/tmp/scope",
                started_at=datetime.now(UTC),
                status=RunStatus.COMPLETED_WITH_PARTIAL_RESULTS,
                stages=[self._stage(StageName.STRUCTURAL_CONTEXT, StageStatus.COMPLETED)],
            )

    def test_partial_results_status_accepted_with_timed_out_stage(self):
        run = AnalysisRun(
            code_scope_path="/tmp/scope",
            started_at=datetime.now(UTC),
            status=RunStatus.COMPLETED_WITH_PARTIAL_RESULTS,
            stages=[
                self._stage(StageName.STRUCTURAL_CONTEXT, StageStatus.COMPLETED),
                self._stage(StageName.RESOURCE_IO_EFFICIENCY, StageStatus.TIMED_OUT),
            ],
        )
        assert run.status is RunStatus.COMPLETED_WITH_PARTIAL_RESULTS

    def test_incomplete_stage_model(self):
        entry = IncompleteStage(stage=StageName.RESOURCE_IO_EFFICIENCY, reason="timed out after 120s")
        assert entry.stage is StageName.RESOURCE_IO_EFFICIENCY

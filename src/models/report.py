"""Report and AnalysisRun models — the aggregate artifacts of one pipeline run."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from src.models.action_item import ActionItem
from src.models.finding import Finding, FindingKind
from src.models.stage import (
    TERMINAL_STAGE_STATUSES,
    AnalysisStage,
    StageName,
    StageStatus,
)


class IncompleteStage(BaseModel):
    stage: StageName
    reason: str = Field(min_length=1)


class Report(BaseModel):
    """The final human-readable artifact for one Analysis Run. Rendered twice from this
    one instance (Markdown + HTML) with identical content; empty sections are rendered
    with an explicit "none found" marker at the template layer (FR-010)."""

    issues: list[Finding] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)
    valuable_findings: list[Finding] = Field(default_factory=list)
    incomplete_stages: list[IncompleteStage] = Field(default_factory=list)
    coverage_note: str | None = None
    limitations: list[str] = Field(default_factory=list)
    generated_at: datetime

    @model_validator(mode="after")
    def _section_kinds(self) -> Report:
        for finding in self.issues:
            if finding.kind is not FindingKind.ISSUE:
                raise ValueError("Report.issues may only contain findings with kind == 'issue'")
        for finding in self.valuable_findings:
            if finding.kind is not FindingKind.VALUABLE_FINDING:
                raise ValueError(
                    "Report.valuable_findings may only contain findings with "
                    "kind == 'valuable_finding'"
                )
        return self


class RunStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    COMPLETED_WITH_PARTIAL_RESULTS = "completed_with_partial_results"


class AnalysisRun(BaseModel):
    """A single execution of the pipeline against one defined code scope. Never persisted
    beyond producing its two output files (stateless across runs)."""

    code_scope_path: str = Field(min_length=1)
    started_at: datetime
    status: RunStatus = RunStatus.IN_PROGRESS
    detected_languages: list[str] = Field(default_factory=list)
    stages: list[AnalysisStage] = Field(default_factory=list)
    report: Report | None = None

    @model_validator(mode="after")
    def _status_must_not_mask_failures(self) -> AnalysisRun:
        if self.status is RunStatus.IN_PROGRESS:
            return self
        non_terminal = [s.name for s in self.stages if s.status not in TERMINAL_STAGE_STATUSES]
        if non_terminal:
            raise ValueError(
                f"run status '{self.status}' requires all stages terminal; "
                f"still pending/running: {[str(n) for n in non_terminal]}"
            )
        incomplete = [
            s.name
            for s in self.stages
            if s.status in (StageStatus.FAILED, StageStatus.TIMED_OUT)
        ]
        if self.status is RunStatus.COMPLETED and incomplete:
            raise ValueError(
                "run status 'completed' may not mask failed/timed-out stages: "
                f"{[str(n) for n in incomplete]}"
            )
        if self.status is RunStatus.COMPLETED_WITH_PARTIAL_RESULTS and not incomplete:
            raise ValueError(
                "run status 'completed_with_partial_results' requires at least one "
                "failed/timed-out stage"
            )
        return self

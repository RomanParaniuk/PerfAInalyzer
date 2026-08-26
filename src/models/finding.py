"""Finding and LocationRef models — the base shapes shared by Issues and Valuable Findings.

`StageFinding` is the payload shape a stage returns through the `report_stage_findings`
tool (no identity, no attribution). `Finding` is the domain shape after the orchestrator
stamps `finding_id` and `originating_stage` — attribution is structurally guaranteed by
the orchestrator, never trusted to model output (FR-009).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class FindingKind(StrEnum):
    ISSUE = "issue"
    VALUABLE_FINDING = "valuable_finding"


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# Lower rank sorts first (most severe first).
SEVERITY_RANK: dict[Severity, int] = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
}


class LocationRef(BaseModel):
    """Where a finding points, relative to the submitted code scope."""

    file_path: str = Field(min_length=1)
    symbol: str | None = None
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _line_order(self) -> LocationRef:
        if self.line_start is not None and self.line_end is not None and self.line_end < self.line_start:
            raise ValueError("line_end must be >= line_start")
        return self


class StageFinding(BaseModel):
    """A finding exactly as reported by a stage via `report_stage_findings`."""

    kind: FindingKind
    description: str = Field(min_length=1)
    location: LocationRef
    severity: Severity | None = None
    suggested_action: str | None = None

    @model_validator(mode="after")
    def _cross_field_rules(self) -> StageFinding:
        if self.kind is FindingKind.ISSUE:
            if self.severity is None:
                raise ValueError("severity is required (non-null) when kind == 'issue'")
            if self.suggested_action is None or not self.suggested_action.strip():
                raise ValueError("suggested_action is required (non-null) when kind == 'issue'")
        else:
            if self.severity is not None:
                raise ValueError("severity must be null when kind == 'valuable_finding'")
        return self


class Finding(StageFinding):
    """A stage finding after the orchestrator stamped run-scoped identity and attribution."""

    finding_id: str = Field(min_length=1)
    originating_stage: StageName


from src.models.stage import StageName  # noqa: E402  (bottom import breaks the model cycle)

Finding.model_rebuild()

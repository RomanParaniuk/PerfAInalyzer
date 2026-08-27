"""Analysis stage models: the fixed stage-name/status enums, the `StageResult` payload
shape returned by the `report_stage_findings` tool, and the `AnalysisStage` run record."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class StageName(StrEnum):
    STRUCTURAL_CONTEXT = "structural_context"
    ALGORITHMIC_COMPLEXITY = "algorithmic_complexity"
    RESOURCE_IO_EFFICIENCY = "resource_io_efficiency"
    CONCURRENCY_SCALABILITY = "concurrency_scalability"
    MEMORY_ALLOCATION = "memory_allocation"
    DATA_ACCESS_EFFICIENCY = "data_access_efficiency"
    STARTUP_INITIALIZATION = "startup_initialization"
    DEPENDENCY_FOOTPRINT = "dependency_footprint"


# Fixed pipeline order (FR-002); also the tie-break order for report sorting.
STAGE_ORDER: tuple[StageName, ...] = (
    StageName.STRUCTURAL_CONTEXT,
    StageName.ALGORITHMIC_COMPLEXITY,
    StageName.RESOURCE_IO_EFFICIENCY,
    StageName.CONCURRENCY_SCALABILITY,
    StageName.MEMORY_ALLOCATION,
    StageName.DATA_ACCESS_EFFICIENCY,
    StageName.STARTUP_INITIALIZATION,
    StageName.DEPENDENCY_FOOTPRINT,
)

STAGE_ORDER_INDEX: dict[StageName, int] = {name: i for i, name in enumerate(STAGE_ORDER)}

STAGE_LABELS: dict[StageName, str] = {
    StageName.STRUCTURAL_CONTEXT: "Structural & Context Analysis",
    StageName.ALGORITHMIC_COMPLEXITY: "Algorithmic Complexity Analysis",
    StageName.RESOURCE_IO_EFFICIENCY: "Resource & I/O Efficiency Analysis",
    StageName.CONCURRENCY_SCALABILITY: "Concurrency & Scalability Analysis",
    StageName.MEMORY_ALLOCATION: "Memory & Allocation Analysis",
    StageName.DATA_ACCESS_EFFICIENCY: "Data Access & Query Efficiency Analysis",
    StageName.STARTUP_INITIALIZATION: "Startup & Initialization Analysis",
    StageName.DEPENDENCY_FOOTPRINT: "Dependency Footprint Analysis",
}


class StageStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


TERMINAL_STAGE_STATUSES = frozenset(
    {StageStatus.COMPLETED, StageStatus.FAILED, StageStatus.TIMED_OUT}
)


class StageResult(BaseModel):
    """Validated payload of one `report_stage_findings` tool call (contract:
    stage-output-schema.md). Findings here are pre-attribution `StageFinding`s."""

    stage_name: StageName
    findings: list[StageFinding] = Field(default_factory=list)
    coverage_note: str | None = None


class AnalysisStage(BaseModel):
    """One discrete pipeline step and its outcome within a single run."""

    name: StageName
    status: StageStatus = StageStatus.PENDING
    failure_reason: str | None = None
    findings: list[Finding] = Field(default_factory=list)
    model_used: str | None = None


from src.models.finding import (  # noqa: E402  (bottom import breaks the model cycle)
    Finding,
    StageFinding,
)

StageResult.model_rebuild()
AnalysisStage.model_rebuild()

"""Stage-result file loading, validation, and unit -> stage mapping for `agent render`
(data-model.md "Stage Result File" / "Consolidated Run", contracts/agent-support-cli.md).

Every expected unit with a missing, unparsable, schema-invalid, or wrong-stage result
file becomes a *failed unit* with a human-readable reason — the run continues (FR-010).
Findings from valid files are stamped with `originating_stage` structurally (from the
unit's stage, via the existing orchestrator stamping), never trusted from the payload
(FR-004)."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from src.agentrun.workplan import WorkPlan, WorkUnit
from src.models.finding import StageFinding
from src.models.stage import (
    STAGE_ORDER,
    AnalysisStage,
    StageResult,
    StageStatus,
)
from src.pipeline.orchestrator import stamp_findings

DedupeFn = Callable[[list[StageFinding]], list[StageFinding]]


@dataclass
class UnitOutcome:
    """One work unit's load/validation outcome at render time."""

    unit: WorkUnit
    result: StageResult | None = None
    failure_reason: str | None = None

    @property
    def ok(self) -> bool:
        return self.result is not None


def _validation_summary(exc: ValidationError) -> str:
    """First validation error as one human-readable line (never a traceback)."""
    first = exc.errors()[0]
    location = ".".join(str(part) for part in first["loc"]) or "payload"
    return f"{first['msg']} (at {location})"


def _load_one(results_dir: Path, unit: WorkUnit) -> UnitOutcome:
    path = results_dir / unit.result_file
    if not path.is_file():
        return UnitOutcome(
            unit, failure_reason=f"no result file was written (expected {unit.result_file})"
        )
    try:
        envelope = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return UnitOutcome(
            unit, failure_reason=f"result file is not parsable JSON: {exc}"
        )
    if not isinstance(envelope, dict) or "unit_id" not in envelope or "result" not in envelope:
        return UnitOutcome(
            unit,
            failure_reason="result file must be a JSON object with 'unit_id' and 'result' keys",
        )
    if envelope["unit_id"] != unit.unit_id:
        return UnitOutcome(
            unit,
            failure_reason=(
                f"unit_id {envelope['unit_id']!r} does not match the filename stem "
                f"{unit.unit_id!r}"
            ),
        )
    try:
        result = StageResult.model_validate(envelope["result"])
    except ValidationError as exc:
        return UnitOutcome(
            unit,
            failure_reason=f"result payload failed schema validation: {_validation_summary(exc)}",
        )
    if result.stage_name is not unit.stage:
        return UnitOutcome(
            unit,
            failure_reason=(
                f"result declares stage '{result.stage_name.value}' but the unit "
                f"belongs to stage '{unit.stage.value}'"
            ),
        )
    return UnitOutcome(unit, result=result)


def load_unit_results(results_dir: Path, plan: WorkPlan) -> list[UnitOutcome]:
    """Load every expected unit's result file, in the plan's deterministic unit order."""
    return [_load_one(results_dir, unit) for unit in plan.units]


def build_stages(
    outcomes: Sequence[UnitOutcome], *, dedupe: DedupeFn | None = None
) -> tuple[list[AnalysisStage], list[str]]:
    """Map unit outcomes onto 001's stage vocabulary (data-model.md "Consolidated Run").

    All units valid -> stage completed; some failed -> completed plus a coverage note
    naming the failed partitions; all failed -> stage failed. Returns the four stages in
    pipeline order plus the coverage notes for the aggregator."""
    stages: list[AnalysisStage] = []
    notes: list[str] = []
    for stage_name in STAGE_ORDER:
        stage_outcomes = [o for o in outcomes if o.unit.stage is stage_name]
        if not stage_outcomes:
            continue
        valid_results = [o.result for o in stage_outcomes if o.result is not None]
        failed = [o for o in stage_outcomes if not o.ok]
        stage = AnalysisStage(name=stage_name)
        if valid_results:
            union: list[StageFinding] = [f for r in valid_results for f in r.findings]
            if dedupe is not None:
                union = dedupe(union)
            stage.findings = stamp_findings(
                StageResult(stage_name=stage_name, findings=union), stage_name
            )
            stage.status = StageStatus.COMPLETED
            for result in valid_results:
                if result.coverage_note:
                    notes.append(f"{stage_name.value} stage: {result.coverage_note}")
            if failed:
                described = "; ".join(
                    f"partition {o.unit.partition_id} ({', '.join(o.unit.files)}): "
                    f"{o.failure_reason}"
                    for o in failed
                )
                notes.append(
                    f"{stage_name.value} stage: no usable results for {described} — "
                    "findings cover only the remaining partition(s)"
                )
        else:
            stage.status = StageStatus.FAILED
            reasons = "; ".join(
                f"{o.unit.unit_id}: {o.failure_reason}" for o in failed
            )
            stage.failure_reason = f"all of the stage's work units failed — {reasons}"
        stages.append(stage)
    return stages, notes


def all_units_failed(outcomes: Sequence[UnitOutcome]) -> bool:
    """True when every unit of every stage failed (render exit code 3, FR-010)."""
    return bool(outcomes) and not any(o.ok for o in outcomes)

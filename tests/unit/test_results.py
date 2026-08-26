"""Unit tests (T008): validation -> failed-unit mapping in src/agentrun/results.py.

Missing/unparsable/invalid/wrong-stage result files each become a failed unit with the
reason recorded while valid files load; `originating_stage` is stamped structurally by
code (from the unit's stage), never trusted from the payload; unit outcomes map to
stage status per data-model.md "Consolidated Run"."""

from __future__ import annotations

import json
from pathlib import Path

from src.agentrun.results import build_stages, load_unit_results
from src.agentrun.workplan import build_work_plan
from src.lib.discovery import discover_files
from src.models.stage import StageName, StageStatus

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
ANTI_PATTERN_FIXTURE = FIXTURES_DIR / "anti_pattern_sample"
PARTIAL_RESULTS = FIXTURES_DIR / "agent_results_partial"
ALL_FAILED_RESULTS = FIXTURES_DIR / "agent_results_all_failed"


def _plan(max_parallel: int = 1):
    files = discover_files(ANTI_PATTERN_FIXTURE)
    return build_work_plan(ANTI_PATTERN_FIXTURE, files, max_parallel=max_parallel)


def _valid_result(stage: StageName, file_path: str = "orders.py") -> dict:
    return {
        "stage_name": stage.value,
        "findings": [
            {
                "kind": "issue",
                "description": f"A planted {stage.value} problem for mapping tests.",
                "location": {"file_path": file_path, "line_start": 3},
                "severity": "medium",
                "suggested_action": "Restructure the loop to reuse the cached value.",
            }
        ],
        "coverage_note": None,
    }


def _write_result(results_dir: Path, unit_id: str, payload: dict) -> None:
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / f"{unit_id}.json").write_text(
        json.dumps({"unit_id": unit_id, "result": payload}), encoding="utf-8"
    )


class TestFailedUnitMapping:
    def test_each_invalid_kind_becomes_failed_unit_with_reason(self, tmp_path: Path):
        plan = _plan()
        # structural: valid; algorithmic: unparsable; resource_io: schema-invalid;
        # concurrency: missing (no file).
        _write_result(
            tmp_path, "structural_context--all", _valid_result(StageName.STRUCTURAL_CONTEXT)
        )
        (tmp_path / "algorithmic_complexity--p1.json").write_text("{{{", encoding="utf-8")
        _write_result(
            tmp_path,
            "resource_io_efficiency--p1",
            {"stage_name": "resource_io_efficiency", "findings": [{"kind": "issue"}]},
        )
        outcomes = {o.unit.unit_id: o for o in load_unit_results(tmp_path, plan)}

        assert outcomes["structural_context--all"].ok
        for failed_id in (
            "algorithmic_complexity--p1",
            "resource_io_efficiency--p1",
            "concurrency_scalability--p1",
        ):
            outcome = outcomes[failed_id]
            assert not outcome.ok
            assert outcome.failure_reason and outcome.failure_reason.strip()

    def test_fixture_partial_set_maps_expected_units(self):
        plan_data = json.loads((PARTIAL_RESULTS / "workplan.json").read_text())
        from src.agentrun.workplan import WorkPlan

        plan = WorkPlan.model_validate(plan_data)
        outcomes = {o.unit.unit_id: o for o in load_unit_results(PARTIAL_RESULTS, plan)}
        assert outcomes["structural_context--all"].ok
        assert outcomes["algorithmic_complexity--p1"].ok
        assert outcomes["algorithmic_complexity--p2"].ok
        assert not outcomes["resource_io_efficiency--p1"].ok  # schema-invalid
        assert outcomes["resource_io_efficiency--p2"].ok
        assert not outcomes["concurrency_scalability--p1"].ok  # wrong stage
        assert not outcomes["concurrency_scalability--p2"].ok  # missing file


class TestStructuralStamping:
    def test_originating_stage_comes_from_unit_not_payload(self, tmp_path: Path):
        plan = _plan()
        for unit in plan.units:
            _write_result(tmp_path, unit.unit_id, _valid_result(unit.stage))
        outcomes = load_unit_results(tmp_path, plan)
        stages, _notes = build_stages(outcomes)
        for stage in stages:
            for finding in stage.findings:
                assert finding.originating_stage is stage.name
                assert finding.finding_id


class TestStageStatusMapping:
    def test_all_units_valid_stage_completed(self, tmp_path: Path):
        plan = _plan(max_parallel=4)  # 2 partitions per analysis stage
        for unit in plan.units:
            _write_result(tmp_path, unit.unit_id, _valid_result(unit.stage))
        stages, notes = build_stages(load_unit_results(tmp_path, plan))
        assert all(s.status is StageStatus.COMPLETED for s in stages)
        assert notes == []

    def test_some_units_failed_stage_completed_with_coverage_note(self, tmp_path: Path):
        plan = _plan(max_parallel=4)
        for unit in plan.units:
            if unit.unit_id == "algorithmic_complexity--p1":
                continue  # missing -> failed unit
            _write_result(tmp_path, unit.unit_id, _valid_result(unit.stage))
        stages, notes = build_stages(load_unit_results(tmp_path, plan))
        by_name = {s.name: s for s in stages}
        assert by_name[StageName.ALGORITHMIC_COMPLEXITY].status is StageStatus.COMPLETED
        assert any("p1" in note for note in notes), "coverage note must name the failed partition"

    def test_all_units_failed_stage_failed(self, tmp_path: Path):
        plan = _plan(max_parallel=1)
        for unit in plan.units:
            if unit.stage is StageName.CONCURRENCY_SCALABILITY:
                continue  # every concurrency unit missing -> stage failed
            _write_result(tmp_path, unit.unit_id, _valid_result(unit.stage))
        stages, _notes = build_stages(load_unit_results(tmp_path, plan))
        by_name = {s.name: s for s in stages}
        concurrency = by_name[StageName.CONCURRENCY_SCALABILITY]
        assert concurrency.status is StageStatus.FAILED
        assert concurrency.failure_reason

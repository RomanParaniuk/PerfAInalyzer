"""Contract tests (T006): the work-plan JSON shape per data-model.md "Work Plan".

All fields present; partitions pairwise disjoint and jointly covering every discovered
file; units ordered structural-first then stage-major x partition-index;
P = clamp(ceil(max_parallel / 3), 1, file_count); identical inputs -> identical plan."""

from __future__ import annotations

import json
import math
from pathlib import Path

from src.agentrun.workplan import build_work_plan, compute_partition_count, plan_to_json
from src.lib.discovery import discover_files
from src.models.stage import STAGE_ORDER, StageName

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
ANTI_PATTERN_FIXTURE = FIXTURES_DIR / "anti_pattern_sample"

ANALYSIS_STAGES = [s for s in STAGE_ORDER if s is not StageName.STRUCTURAL_CONTEXT]


def _plan(max_parallel: int = 4):
    files = discover_files(ANTI_PATTERN_FIXTURE)
    return build_work_plan(ANTI_PATTERN_FIXTURE, files, max_parallel=max_parallel)


class TestWorkPlanFields:
    def test_all_documented_fields_present(self):
        data = json.loads(plan_to_json(_plan()))
        assert set(data) >= {
            "scope_path",
            "detected_languages",
            "file_count",
            "max_parallel",
            "partitions",
            "units",
        }
        assert data["detected_languages"] == ["javascript", "python"]
        assert data["file_count"] == 3  # orders.py, pricing.py, search.js
        assert data["max_parallel"] == 4
        for partition in data["partitions"]:
            assert set(partition) >= {"partition_id", "files", "total_bytes"}
        for unit in data["units"]:
            assert set(unit) >= {"unit_id", "stage", "partition_id", "files", "result_file"}
            assert unit["result_file"] == f"{unit['unit_id']}.json"


class TestPartitionsDisjointAndCovering:
    def test_disjoint_and_jointly_covering(self):
        plan = _plan(max_parallel=4)
        all_files = {f.rel_path for f in discover_files(ANTI_PATTERN_FIXTURE)}
        seen: list[str] = []
        for partition in plan.partitions:
            seen.extend(partition.files)
        assert len(seen) == len(set(seen)), "partitions overlap"
        assert set(seen) == all_files, "partitions do not cover the discovered files"


class TestUnitOrdering:
    def test_structural_first_then_stage_major_partition_order(self):
        plan = _plan(max_parallel=4)
        assert plan.units[0].unit_id == "structural_context--all"
        assert plan.units[0].stage is StageName.STRUCTURAL_CONTEXT
        assert plan.units[0].partition_id == "all"

        expected_rest = [
            f"{stage.value}--{partition.partition_id}"
            for stage in ANALYSIS_STAGES
            for partition in plan.partitions
        ]
        assert [u.unit_id for u in plan.units[1:]] == expected_rest


class TestPartitionCountFormula:
    def test_clamped_ceil_formula(self):
        # P = clamp(ceil(N / 3), 1, file_count)
        for n in range(1, 11):
            for file_count in (1, 2, 5, 50):
                expected = max(1, min(math.ceil(n / 3), file_count))
                assert compute_partition_count(n, file_count) == expected

    def test_three_file_scope_partitions(self):
        assert len(_plan(max_parallel=1).partitions) == 1
        assert len(_plan(max_parallel=4).partitions) == 2
        assert len(_plan(max_parallel=10).partitions) == 3  # ceil(10/3)=4, clamped at 3 files

    def test_unit_counts(self):
        assert len(_plan(max_parallel=1).units) == 4  # 1 structural + 3 stages x 1
        assert len(_plan(max_parallel=4).units) == 7  # 1 structural + 3 stages x 2


class TestDeterminism:
    def test_identical_inputs_produce_identical_plan(self):
        files_a = discover_files(ANTI_PATTERN_FIXTURE)
        files_b = discover_files(ANTI_PATTERN_FIXTURE)
        plan_a = build_work_plan(ANTI_PATTERN_FIXTURE, files_a, max_parallel=4)
        plan_b = build_work_plan(ANTI_PATTERN_FIXTURE, files_b, max_parallel=4)
        assert plan_to_json(plan_a) == plan_to_json(plan_b)

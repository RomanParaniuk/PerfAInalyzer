"""Unit tests (T021): partitioning in src/agentrun/workplan.py.

Determinism, size balance of the greedy bin-pack, P clamping when N exceeds the
available work, and the documented unit counts for N=1 and N=4."""

from __future__ import annotations

from pathlib import Path

from src.agentrun.workplan import build_work_plan, plan_to_json
from src.lib.discovery import SourceFile, discover_files

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
ANTI_PATTERN_FIXTURE = FIXTURES_DIR / "anti_pattern_sample"
CLEAN_FIXTURE = FIXTURES_DIR / "clean_sample"


def _synthetic_files(sizes: dict[str, int]) -> list[SourceFile]:
    return [
        SourceFile(
            path=Path("/scope") / name,
            rel_path=name,
            language="python",
            size_bytes=size,
        )
        for name, size in sizes.items()
    ]


class TestDeterminism:
    def test_same_inputs_identical_plan(self):
        files = discover_files(ANTI_PATTERN_FIXTURE)
        first = build_work_plan(ANTI_PATTERN_FIXTURE, files, max_parallel=6)
        second = build_work_plan(ANTI_PATTERN_FIXTURE, list(files), max_parallel=6)
        assert plan_to_json(first) == plan_to_json(second)

    def test_input_order_does_not_change_plan(self):
        files = discover_files(ANTI_PATTERN_FIXTURE)
        reordered = list(reversed(files))
        first = build_work_plan(ANTI_PATTERN_FIXTURE, files, max_parallel=6)
        second = build_work_plan(ANTI_PATTERN_FIXTURE, reordered, max_parallel=6)
        assert plan_to_json(first) == plan_to_json(second)


class TestSizeBalance:
    def test_greedy_bin_pack_bounds_byte_spread(self):
        # 12 files with mixed sizes into 4 partitions: greedy largest-first keeps the
        # spread between the heaviest and lightest partition below one max-size file.
        sizes = {f"f{i:02d}.py": size for i, size in enumerate(
            [900, 850, 800, 400, 390, 380, 200, 150, 120, 80, 40, 10]
        )}
        files = _synthetic_files(sizes)
        plan = build_work_plan(Path("/scope"), files, max_parallel=10)
        assert len(plan.partitions) == 4  # ceil(10/3) = 4, file_count = 12
        totals = [p.total_bytes for p in plan.partitions]
        assert max(totals) - min(totals) <= max(sizes.values())
        assert sum(totals) == sum(sizes.values())

    def test_partitions_disjoint_and_covering_synthetic(self):
        files = _synthetic_files({f"m{i}.py": 100 + i for i in range(7)})
        plan = build_work_plan(Path("/scope"), files, max_parallel=9)
        covered = [f for p in plan.partitions for f in p.files]
        assert len(covered) == len(set(covered)) == 7


class TestClamping:
    def test_more_parallelism_than_work_clamps_to_file_count(self):
        # clean_sample has a single analyzable file: P collapses to 1 even at N=10.
        files = discover_files(CLEAN_FIXTURE)
        assert len(files) == 1
        plan = build_work_plan(CLEAN_FIXTURE, files, max_parallel=10)
        assert len(plan.partitions) == 1
        assert len(plan.units) == 4  # structural + 3 stages x 1 partition
        assert all(len(p.files) >= 1 for p in plan.partitions)


class TestUnitCounts:
    def test_n1_yields_exactly_four_units(self):
        files = discover_files(ANTI_PATTERN_FIXTURE)
        plan = build_work_plan(ANTI_PATTERN_FIXTURE, files, max_parallel=1)
        assert len(plan.units) == 4

    def test_n4_yields_two_partitions_and_seven_units(self):
        files = discover_files(ANTI_PATTERN_FIXTURE)
        plan = build_work_plan(ANTI_PATTERN_FIXTURE, files, max_parallel=4)
        assert len(plan.partitions) == 2
        assert len(plan.units) == 7

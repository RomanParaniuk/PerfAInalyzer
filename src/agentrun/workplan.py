"""Work-plan computation for the agent path (data-model.md "Work Plan", research.md §5).

Deterministic and zero-token: partition count is `P = clamp(ceil(N / 3), 1, file_count)`,
files are assigned by greedy size-balanced bin-packing (largest file first into the
currently smallest bin), and units are ordered structural-first then stage-major x
partition-index — identical inputs always produce an identical plan."""

from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel

from src.lib.discovery import SourceFile, detect_languages
from src.models.stage import STAGE_ORDER, StageName

MAX_PARALLEL_MIN = 1
MAX_PARALLEL_MAX = 10

STRUCTURAL_UNIT_ID = "structural_context--all"

# The three per-partition analysis stages; structural context is always one whole-scope
# unit whose summary the later units share (research.md §4).
ANALYSIS_STAGES: tuple[StageName, ...] = tuple(
    stage for stage in STAGE_ORDER if stage is not StageName.STRUCTURAL_CONTEXT
)


class Partition(BaseModel):
    """A disjoint, size-balanced group of scope files (data-model.md "Partition")."""

    partition_id: str
    files: list[str]  # paths relative to scope_path
    total_bytes: int


class WorkUnit(BaseModel):
    """One independently executable piece of analysis work (data-model.md "Work Unit")."""

    unit_id: str  # "<stage>--<partition_id>"; doubles as the result filename stem
    stage: StageName
    partition_id: str
    files: list[str]  # a file *list*, never file contents (token rule, research §9)
    result_file: str  # "<unit_id>.json"


class WorkPlan(BaseModel):
    """The deterministic output of `perf-ai agent scope` (data-model.md "Work Plan")."""

    scope_path: str
    detected_languages: list[str]
    file_count: int
    max_parallel: int
    partitions: list[Partition]
    units: list[WorkUnit]


def compute_partition_count(max_parallel: int, file_count: int) -> int:
    """P = clamp(ceil(max_parallel / 3), 1, file_count)."""
    return max(1, min(math.ceil(max_parallel / 3), file_count))


def _partition_files(files: Sequence[SourceFile], count: int) -> list[Partition]:
    """Greedy size-balanced bin-pack: largest file first into the currently smallest bin."""
    members: list[list[SourceFile]] = [[] for _ in range(count)]
    sizes = [0] * count
    for source in sorted(files, key=lambda f: (-f.size_bytes, f.rel_path)):
        smallest = min(range(count), key=lambda i: (sizes[i], i))
        members[smallest].append(source)
        sizes[smallest] += source.size_bytes
    return [
        Partition(
            partition_id=f"p{index}",
            files=sorted(f.rel_path for f in group),
            total_bytes=sum(f.size_bytes for f in group),
        )
        for index, group in enumerate(members, start=1)
    ]


def build_work_plan(
    root: Path, files: Sequence[SourceFile], max_parallel: int
) -> WorkPlan:
    """Build the full work plan: 1 structural unit + one unit per (stage x partition)."""
    partitions = _partition_files(
        files, compute_partition_count(max_parallel, len(files))
    )
    units = [
        WorkUnit(
            unit_id=STRUCTURAL_UNIT_ID,
            stage=StageName.STRUCTURAL_CONTEXT,
            partition_id="all",
            files=sorted(f.rel_path for f in files),
            result_file=f"{STRUCTURAL_UNIT_ID}.json",
        )
    ]
    for stage in ANALYSIS_STAGES:
        for partition in partitions:
            unit_id = f"{stage.value}--{partition.partition_id}"
            units.append(
                WorkUnit(
                    unit_id=unit_id,
                    stage=stage,
                    partition_id=partition.partition_id,
                    files=list(partition.files),
                    result_file=f"{unit_id}.json",
                )
            )
    return WorkPlan(
        scope_path=str(root.resolve()),
        detected_languages=detect_languages(files),
        file_count=len(files),
        max_parallel=max_parallel,
        partitions=partitions,
        units=units,
    )


def plan_to_json(plan: WorkPlan) -> str:
    """Deterministic serialization of the plan (research.md §5)."""
    return plan.model_dump_json(indent=2)

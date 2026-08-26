"""Mock Anthropic provider test double (T019): returns fixture `StageResult` payloads
with no network calls, for use by integration tests. Mirrors the `run_stage` signature
of `AnthropicProvider` exactly."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from src.models.stage import StageName, StageResult
from src.providers.anthropic_client import STAGE_MODELS


@dataclass
class RecordedCall:
    stage_name: StageName
    system_prompt: str
    shared_context: str
    stage_input: str


@dataclass
class MockProvider:
    """Drop-in replacement for `AnthropicProvider` returning canned stage results.

    `failures` maps a stage to the exception its call should raise; `delays` maps a
    stage to seconds to sleep before responding (for timeout tests).
    """

    results: dict[StageName, StageResult]
    failures: dict[StageName, Exception] = field(default_factory=dict)
    delays: dict[StageName, float] = field(default_factory=dict)
    calls: list[RecordedCall] = field(default_factory=list)

    def run_stage(
        self,
        *,
        stage_name: StageName,
        system_prompt: str,
        shared_context: str,
        stage_input: str,
        max_output_tokens: int = 8192,
        on_first_token: Callable[[], None] | None = None,
    ) -> StageResult:
        self.calls.append(
            RecordedCall(
                stage_name=stage_name,
                system_prompt=system_prompt,
                shared_context=shared_context,
                stage_input=stage_input,
            )
        )
        if on_first_token is not None:
            on_first_token()
        delay = self.delays.get(stage_name, 0.0)
        if delay:
            time.sleep(delay)
        failure = self.failures.get(stage_name)
        if failure is not None:
            raise failure
        result = self.results.get(stage_name)
        if result is None:
            result = StageResult(stage_name=stage_name, findings=[])
        return result.model_copy(deep=True)

    def model_used_for(self, stage_name: StageName) -> str:
        return STAGE_MODELS[stage_name]


def make_stage_result(
    stage: StageName, findings: list[dict], coverage_note: str | None = None
) -> StageResult:
    return StageResult.model_validate(
        {"stage_name": stage, "findings": findings, "coverage_note": coverage_note}
    )


def anti_pattern_results() -> dict[StageName, StageResult]:
    """Canned results matching tests/fixtures/anti_pattern_sample/ content."""
    return {
        StageName.STRUCTURAL_CONTEXT: make_stage_result(
            StageName.STRUCTURAL_CONTEXT,
            [
                {
                    "kind": "valuable_finding",
                    "description": (
                        "The codebase cleanly separates order processing (orders.py) from "
                        "pricing computation (pricing.py), which keeps the hot pricing path "
                        "independently optimizable."
                    ),
                    "location": {"file_path": "orders.py", "symbol": None, "line_start": None, "line_end": None},
                    "severity": None,
                    "suggested_action": None,
                }
            ],
        ),
        StageName.ALGORITHMIC_COMPLEXITY: make_stage_result(
            StageName.ALGORITHMIC_COMPLEXITY,
            [
                {
                    "kind": "issue",
                    "description": (
                        "find_duplicate_orders performs a nested O(n^2) scan: for every order "
                        "it linearly searches the full orders list again for a matching id."
                    ),
                    "location": {
                        "file_path": "orders.py",
                        "symbol": "find_duplicate_orders",
                        "line_start": 9,
                        "line_end": 17,
                    },
                    "severity": "critical",
                    "suggested_action": (
                        "Build a set of seen order ids once before the loop and test membership "
                        "against that set, reducing the duplicate scan from O(n^2) to O(n)."
                    ),
                },
                {
                    "kind": "issue",
                    "description": (
                        "process_orders accumulates every processed order into the module-level "
                        "PROCESSED_HISTORY list, which grows without bound for long-running use."
                    ),
                    "location": {
                        "file_path": "orders.py",
                        "symbol": "process_orders",
                        "line_start": 20,
                        "line_end": 28,
                    },
                    "severity": "medium",
                    "suggested_action": (
                        "Replace the unbounded list with collections.deque(maxlen=N) sized to the "
                        "retention actually needed, or stream processed orders to the consumer "
                        "instead of retaining them in memory."
                    ),
                },
                {
                    "kind": "issue",
                    "description": (
                        "findMatches in search.js calls items.indexOf inside a for loop over "
                        "queries, an O(n*m) linear rescan of the items array per query."
                    ),
                    "location": {
                        "file_path": "search.js",
                        "symbol": "findMatches",
                        "line_start": 3,
                        "line_end": 12,
                    },
                    "severity": "low",
                    "suggested_action": (
                        "Construct a Set from items once before the loop and use set.has() for "
                        "each query lookup instead of items.indexOf."
                    ),
                },
                {
                    "kind": "valuable_finding",
                    "description": (
                        "compute_discount in pricing.py is memoized with functools.lru_cache, so "
                        "repeated discount lookups for the same tier avoid recomputation — an "
                        "appropriate, well-applied caching choice."
                    ),
                    "location": {
                        "file_path": "pricing.py",
                        "symbol": "compute_discount",
                        "line_start": 8,
                        "line_end": 16,
                    },
                    "severity": None,
                    "suggested_action": None,
                },
            ],
        ),
        StageName.RESOURCE_IO_EFFICIENCY: make_stage_result(
            StageName.RESOURCE_IO_EFFICIENCY,
            [
                {
                    "kind": "issue",
                    "description": (
                        "write_audit_log re-opens audit.log inside the per-order loop, paying "
                        "file-open/close overhead for every single order written."
                    ),
                    "location": {
                        "file_path": "orders.py",
                        "symbol": "write_audit_log",
                        "line_start": 31,
                        "line_end": 37,
                    },
                    "severity": "high",
                    "suggested_action": (
                        "Open audit.log once before the loop (with a context manager wrapping the "
                        "whole loop) and reuse the file handle for every write."
                    ),
                },
            ],
        ),
        StageName.CONCURRENCY_SCALABILITY: make_stage_result(
            StageName.CONCURRENCY_SCALABILITY, []
        ),
    }


def clean_results() -> dict[StageName, StageResult]:
    """Canned results for tests/fixtures/clean_sample/: no findings anywhere."""
    return {stage: StageResult(stage_name=stage, findings=[]) for stage in StageName}

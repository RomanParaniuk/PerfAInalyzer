"""Pipeline orchestrator: stage sequencing, Stage 2-4 concurrency, timeout/failure
handling, and structural stamping of finding attribution (FR-009, FR-012).

Prompt-cache mechanics (Principle II): caches are model-scoped, so the shared context is
built exactly once (byte-identical string) and the Sonnet fan-out is staggered — the
first Sonnet stage streams until its first token (writing the cache entry), then the
other two fire and hit that cache instead of paying for the shared prefix again.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Protocol

from src.lib.discovery import SourceFile, detect_languages
from src.models.finding import Finding
from src.models.report import AnalysisRun, RunStatus
from src.models.stage import (
    STAGE_ORDER,
    AnalysisStage,
    StageName,
    StageResult,
    StageStatus,
)
from src.pipeline.context import (
    DEFAULT_STAGE_INPUT_BUDGETS,
    ContextBundle,
    StructuralIndex,
    assemble_context,
    build_shared_context,
    build_structural_index,
)
from src.providers.anthropic_client import (
    STAGE_MODELS,
    ProviderAuthError,
    ProviderError,
)


class StageProvider(Protocol):
    """What the orchestrator needs from a provider (real or test double)."""

    def run_stage(
        self,
        *,
        stage_name: StageName,
        system_prompt: str,
        shared_context: str,
        stage_input: str,
        max_output_tokens: int = 8192,
        on_first_token: Callable[[], None] | None = None,
    ) -> StageResult: ...


@dataclass(frozen=True)
class StageSpec:
    """One analysis stage's prompt contract (defined per stage in pipeline/stages/)."""

    name: StageName
    system_prompt: str
    instructions: str


@dataclass
class PipelineConfig:
    timeout_minutes: float = 10.0
    stage_budgets: dict[StageName, int] = field(
        default_factory=lambda: dict(DEFAULT_STAGE_INPUT_BUDGETS)
    )
    max_output_tokens: int = 8192
    stagger_wait_seconds: float = 60.0  # max wait for the cache-priming first token


@dataclass
class PipelineOutcome:
    run: AnalysisRun
    coverage_notes: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


ProgressCallback = Callable[[StageName, StageStatus, str | None], None]

SONNET_STAGES: tuple[StageName, ...] = (
    StageName.ALGORITHMIC_COMPLEXITY,
    StageName.RESOURCE_IO_EFFICIENCY,
    StageName.CONCURRENCY_SCALABILITY,
)


def stamp_findings(result: StageResult, stage_name: StageName) -> list[Finding]:
    """Stamp `originating_stage` and a run-stable `finding_id` on every finding.

    Done by the orchestrator — never the model — so attribution is structurally
    guaranteed (contracts/stage-output-schema.md, FR-009).
    """
    return [
        Finding(
            **finding.model_dump(),
            finding_id=f"{stage_name.value}-{i:03d}",
            originating_stage=stage_name,
        )
        for i, finding in enumerate(result.findings, start=1)
    ]


def _summarize_structural(result: StageResult) -> str | None:
    """Serialize Stage 1's findings into the architectural summary shared with Stages 2-4."""
    if not result.findings:
        return None
    lines = []
    for finding in result.findings:
        location = finding.location.file_path
        if finding.location.symbol:
            location += f" ({finding.location.symbol})"
        lines.append(f"- [{location}] {finding.description}")
    return "\n".join(lines)


def _index_limitations(index: StructuralIndex) -> list[str]:
    limitations: list[str] = []
    syntax_error_files = index.files_with_syntax_errors()
    if syntax_error_files:
        limitations.append(
            "Some files contain syntax errors and were analyzed best-effort from a "
            f"partial parse: {', '.join(sorted(syntax_error_files))}."
        )
    best_effort = [f for f in index.best_effort_files() if f not in set(syntax_error_files)]
    if best_effort:
        limitations.append(
            "No parser grammar was available for some files; they were analyzed "
            f"best-effort using line-based chunking: {', '.join(sorted(best_effort))}."
        )
    return limitations


class _StageRunner:
    """Executes one stage call and records its outcome on the AnalysisStage."""

    def __init__(
        self,
        provider: StageProvider,
        spec: StageSpec,
        stage: AnalysisStage,
        bundle: ContextBundle,
        config: PipelineConfig,
        on_progress: ProgressCallback | None,
    ) -> None:
        self.provider = provider
        self.spec = spec
        self.stage = stage
        self.bundle = bundle
        self.config = config
        self.on_progress = on_progress

    def _progress(self, status: StageStatus, detail: str | None = None) -> None:
        if self.on_progress is not None:
            self.on_progress(self.stage.name, status, detail)

    def __call__(self, on_first_token: Callable[[], None] | None = None) -> StageResult:
        self.stage.status = StageStatus.RUNNING
        self._progress(StageStatus.RUNNING)
        stage_input = (
            f"{self.spec.instructions}\n\n# Stage-specific code excerpts\n\n"
            f"{self.bundle.stage_excerpts}"
        )
        result = self.provider.run_stage(
            stage_name=self.stage.name,
            system_prompt=self.spec.system_prompt,
            shared_context=self.bundle.shared_context,
            stage_input=stage_input,
            max_output_tokens=self.config.max_output_tokens,
            on_first_token=on_first_token,
        )
        return result

    def record_success(self, result: StageResult) -> None:
        self.stage.findings = stamp_findings(result, self.stage.name)
        self.stage.status = StageStatus.COMPLETED
        self._progress(StageStatus.COMPLETED, f"{len(self.stage.findings)} finding(s)")

    def record_failure(self, status: StageStatus, reason: str) -> None:
        self.stage.status = status
        self.stage.failure_reason = reason
        self._progress(status, reason)


def run_pipeline(
    *,
    root: Path,
    files: Sequence[SourceFile],
    provider: StageProvider,
    stage_specs: dict[StageName, StageSpec] | None = None,
    config: PipelineConfig | None = None,
    on_progress: ProgressCallback | None = None,
) -> PipelineOutcome:
    """Run the four-stage pipeline. A failing/timed-out stage never blocks the rest of
    the run (FR-012); a `ProviderAuthError` on the first stage propagates so the CLI can
    exit with the configuration-error code before burning further calls."""
    if stage_specs is None:
        from src.pipeline.stages import get_stage_specs

        stage_specs = get_stage_specs()
    config = config or PipelineConfig()

    started_at = datetime.now(UTC)
    deadline = monotonic() + config.timeout_minutes * 60.0

    def remaining() -> float:
        return max(1.0, deadline - monotonic())

    index = build_structural_index(root, files)
    limitations = _index_limitations(index)
    coverage_notes: list[str] = []

    stages: dict[StageName, AnalysisStage] = {
        name: AnalysisStage(name=name, model_used=STAGE_MODELS[name]) for name in STAGE_ORDER
    }

    executor = ThreadPoolExecutor(max_workers=len(SONNET_STAGES) + 1)
    try:
        # --- Stage 1: structural/context understanding (claude-haiku-4-5) ---------
        structural_shared = build_shared_context(index)
        structural_bundle = assemble_context(
            index,
            StageName.STRUCTURAL_CONTEXT,
            shared_context=structural_shared,
            token_budget=config.stage_budgets.get(StageName.STRUCTURAL_CONTEXT),
        )
        if structural_bundle.coverage_note:
            coverage_notes.append(f"Structural stage: {structural_bundle.coverage_note}")

        structural_runner = _StageRunner(
            provider,
            stage_specs[StageName.STRUCTURAL_CONTEXT],
            stages[StageName.STRUCTURAL_CONTEXT],
            structural_bundle,
            config,
            on_progress,
        )
        stage1_summary: str | None = None
        structural_future = executor.submit(structural_runner)
        try:
            structural_result = structural_future.result(timeout=remaining())
            structural_runner.record_success(structural_result)
            stage1_summary = _summarize_structural(structural_result)
            if structural_result.coverage_note:
                coverage_notes.append(f"Structural stage: {structural_result.coverage_note}")
        except FutureTimeoutError:
            structural_runner.record_failure(
                StageStatus.TIMED_OUT,
                f"did not complete within the {config.timeout_minutes:g}-minute run budget",
            )
        except ProviderAuthError:
            raise  # configuration error: surface before any further stage spends calls
        except ProviderError as exc:
            structural_runner.record_failure(StageStatus.FAILED, str(exc))

        # --- Stages 2-4: concurrent, against the cached shared context ------------
        # Built once so the string is byte-identical across all three calls.
        shared_context = build_shared_context(index, stage1_summary)

        runners: dict[StageName, _StageRunner] = {}
        for name in SONNET_STAGES:
            bundle = assemble_context(
                index,
                name,
                shared_context=shared_context,
                token_budget=config.stage_budgets.get(name),
            )
            if bundle.coverage_note:
                coverage_notes.append(f"{name.value} stage: {bundle.coverage_note}")
            runners[name] = _StageRunner(
                provider, stage_specs[name], stages[name], bundle, config, on_progress
            )

        # Stagger: fire one Sonnet stage, wait until the provider starts answering
        # (the cache entry for the shared prefix is written at that point), then
        # fan out the remaining two as cache hits.
        cache_primed = threading.Event()
        first_stage, *rest_stages = SONNET_STAGES
        futures = {
            first_stage: executor.submit(runners[first_stage], cache_primed.set)
        }
        futures[first_stage].add_done_callback(lambda _f: cache_primed.set())
        cache_primed.wait(timeout=min(config.stagger_wait_seconds, remaining()))
        for name in rest_stages:
            futures[name] = executor.submit(runners[name])

        for name in SONNET_STAGES:
            runner = runners[name]
            try:
                result = futures[name].result(timeout=remaining())
                runner.record_success(result)
                if result.coverage_note:
                    coverage_notes.append(f"{name.value} stage: {result.coverage_note}")
            except FutureTimeoutError:
                runner.record_failure(
                    StageStatus.TIMED_OUT,
                    f"did not complete within the {config.timeout_minutes:g}-minute run budget",
                )
            except ProviderError as exc:
                runner.record_failure(StageStatus.FAILED, str(exc))
            except Exception as exc:  # defensive: never let one stage sink the run
                runner.record_failure(StageStatus.FAILED, f"unexpected error: {exc}")
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    incomplete = [
        s for s in stages.values() if s.status in (StageStatus.FAILED, StageStatus.TIMED_OUT)
    ]
    status = (
        RunStatus.COMPLETED_WITH_PARTIAL_RESULTS if incomplete else RunStatus.COMPLETED
    )
    run = AnalysisRun(
        code_scope_path=str(root),
        started_at=started_at,
        status=status,
        detected_languages=detect_languages(files),
        stages=[stages[name] for name in STAGE_ORDER],
    )
    return PipelineOutcome(run=run, coverage_notes=coverage_notes, limitations=limitations)

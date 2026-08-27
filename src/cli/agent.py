"""`perf-ai agent` sub-app (contracts/agent-support-cli.md, feature 002).

Deterministic helper surface for the agent-path skill: `scope` (preflight + work-plan
JSON) and `render` (result validation + consolidation through the existing aggregator
and renderer). Both subcommands are offline — they never call a model and never read
ANTHROPIC_API_KEY (FR-002). Additive only: `perf-ai analyze` is untouched (FR-003).

Exit codes — scope: 0 = plan on stdout; 1 = invalid target; 2 = invalid invocation
(--max-parallel missing/non-integer/outside 1-10). render: 0 = report written (incl.
partial); 1 = invalid invocation; 3 = every unit of every stage failed (failure-noting
report still written). Code 2 is reserved (001 configuration error) and never used by
render, because the agent path has no credential configuration by design."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from pydantic import ValidationError

from src.agentrun.dedupe import dedupe_findings
from src.agentrun.results import all_units_failed, build_stages, load_unit_results
from src.agentrun.verification import (
    VERIFICATION_FILENAME,
    apply_verification,
    load_verification,
)
from src.agentrun.workplan import (
    MAX_PARALLEL_MAX,
    MAX_PARALLEL_MIN,
    WorkPlan,
    build_work_plan,
    plan_to_json,
)
from src.lib.discovery import discover_files, discover_manifests
from src.models.report import AnalysisRun, RunStatus
from src.models.stage import StageStatus
from src.report.aggregator import aggregate
from src.report.renderer import write_reports

agent_app = typer.Typer(
    help="Deterministic agent-path helpers: preflight/work-plan generation and "
    "subagent-result consolidation. Offline; no API key is read.",
    add_completion=False,
)

WORKPLAN_FILENAME = "workplan.json"


def _fail(message: str, exit_code: int) -> NoReturn:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(exit_code)


def _validated_max_parallel(raw: str | None) -> int:
    """The coded FR-009 gate: --max-parallel is required, integer, and within 1-10."""
    range_text = f"{MAX_PARALLEL_MIN}-{MAX_PARALLEL_MAX}"
    if raw is None:
        _fail(
            f"--max-parallel is required (accepted range {range_text}). Pass "
            "--max-parallel N, or invoke the /perf-analyze skill without a "
            "max-parallel=N argument to be asked interactively.",
            2,
        )
    try:
        value = int(raw)
    except ValueError:
        _fail(
            f"--max-parallel must be an integer in the accepted range {range_text}; "
            f"got {raw!r}.",
            2,
        )
    if not MAX_PARALLEL_MIN <= value <= MAX_PARALLEL_MAX:
        _fail(
            f"--max-parallel {value} is outside the accepted range {range_text}.",
            2,
        )
    return value


@agent_app.command()
def scope(
    path: Annotated[
        Path,
        typer.Argument(help="Local directory or repository root to analyze."),
    ] = Path("."),
    max_parallel: Annotated[
        str | None,
        typer.Option(
            "--max-parallel",
            help="Confirmed parallelism limit (required, 1-10; deliberately no default).",
        ),
    ] = None,
    include: Annotated[
        list[str] | None,
        typer.Option("--include", help="Glob restricting the code scope (repeatable)."),
    ] = None,
    exclude: Annotated[
        list[str] | None,
        typer.Option("--exclude", help="Glob excluded from the code scope (repeatable)."),
    ] = None,
) -> None:
    """Validate the analysis target and emit the work-plan JSON on stdout."""
    limit = _validated_max_parallel(max_parallel)

    if not path.exists() or not os.access(path, os.R_OK):
        _fail(
            f"path does not exist or is not readable: {path}. Check the path and "
            "invoke the command again.",
            1,
        )
    files = discover_files(path, include=include or (), exclude=exclude or ())
    if not files:
        _fail(
            "no source code in a recognized language was found under: "
            f"{path}. Point the command at a directory containing source files, or "
            "loosen the --include/--exclude globs.",
            1,
        )

    manifests = discover_manifests(path, exclude=exclude or ())
    plan = build_work_plan(path, files, max_parallel=limit, manifests=manifests)
    typer.echo(plan_to_json(plan))


@agent_app.command()
def render(
    results_dir: Annotated[
        Path,
        typer.Option(
            "--results-dir",
            help="Directory containing the stage-result files plus the run's workplan.json.",
        ),
    ],
    scope: Annotated[
        Path,
        typer.Option("--scope", help="The analyzed scope path (recorded in the report header)."),
    ],
    output_dir: Annotated[
        Path,
        typer.Option(
            "--output-dir",
            help="Directory to write perf-report.md and perf-report.html into.",
        ),
    ] = Path("."),
) -> None:
    """Validate subagent results and render perf-report.md / perf-report.html."""
    if not results_dir.is_dir():
        _fail(
            f"results directory does not exist or is not a directory: {results_dir}.",
            1,
        )
    workplan_path = results_dir / WORKPLAN_FILENAME
    if not workplan_path.is_file():
        _fail(
            f"no {WORKPLAN_FILENAME} found in {results_dir}; copy the plan emitted by "
            "`agent scope` into the results directory first.",
            1,
        )
    try:
        plan = WorkPlan.model_validate(
            json.loads(workplan_path.read_text(encoding="utf-8"))
        )
    except (ValueError, ValidationError) as exc:
        _fail(f"{WORKPLAN_FILENAME} is not a parsable work plan: {exc}", 1)
    if not scope.exists():
        _fail(f"scope path does not exist: {scope}.", 1)

    outcomes = load_unit_results(results_dir, plan)
    # Dedup between per-stage union and aggregation (FR-011): duplicates from
    # parallel same-stage subagents collapse to one location-keyed survivor.
    stages, coverage_notes = build_stages(outcomes, dedupe=dedupe_findings)
    if not plan.manifests:
        # No manifest, no dependency unit — say so rather than omitting the stage silently.
        coverage_notes.append(
            "dependency_footprint stage: no dependency manifest (package.json, "
            "pyproject.toml, go.mod, …) was found in the scope, so declared "
            "dependencies were not analyzed."
        )

    # Optional stage-4h overlay: refuted issues are dropped, the outcome is a
    # limitations note; a missing or unusable file never blocks the render.
    limitations: list[str] = []
    verification, verification_warning = load_verification(
        results_dir / VERIFICATION_FILENAME
    )
    if verification_warning:
        typer.echo(f"Warning: {verification_warning}", err=True)
    if verification is not None:
        limitations.append(apply_verification(stages, verification).note)

    incomplete = any(
        s.status in (StageStatus.FAILED, StageStatus.TIMED_OUT) for s in stages
    )
    run = AnalysisRun(
        code_scope_path=str(scope.resolve()),
        started_at=datetime.now(UTC),
        status=RunStatus.COMPLETED_WITH_PARTIAL_RESULTS
        if incomplete
        else RunStatus.COMPLETED,
        detected_languages=plan.detected_languages,
        stages=stages,
    )
    report = aggregate(run, coverage_notes=coverage_notes, limitations=limitations)
    run.report = report
    md_path, html_path = write_reports(report, run, output_dir)
    typer.echo(f"Report written to {md_path} and {html_path}")

    if all_units_failed(outcomes):
        typer.echo(
            "Error: every work unit of every stage failed; the report records the "
            "failure details.",
            err=True,
        )
        raise typer.Exit(3)

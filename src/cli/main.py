"""`perf-ai` CLI (contracts/cli-interface.md).

Exit codes: 0 = report written (including partial-results runs); 1 = invalid PATH or no
recognized-language code; 2 = missing/rejected ANTHROPIC_API_KEY before analysis could
proceed; 3 = every stage failed/timed out (a report noting the total failure is still
written).

The API key is read exclusively from the ANTHROPIC_API_KEY environment variable — never
from a CLI flag (it would leak into shell history) — and is never logged or echoed."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from src.lib.discovery import detect_languages, discover_files, discover_manifests
from src.models.stage import STAGE_LABELS, StageName, StageStatus
from src.pipeline.orchestrator import PipelineConfig, run_pipeline
from src.providers.anthropic_client import AnthropicProvider, ProviderAuthError
from src.report.aggregator import aggregate
from src.report.renderer import write_reports

app = typer.Typer(
    help="AI multi-stage performance analysis: static reading and reasoning only — "
    "submitted code is never executed, compiled, or profiled.",
    add_completion=False,
)
app.add_typer(__import__("src.cli.agent", fromlist=["agent_app"]).agent_app, name="agent")
console = Console()
err_console = Console(stderr=True)

DEFAULT_TIMEOUT_MINUTES = 10.0  # aligned with SC-004


def create_provider() -> AnthropicProvider:
    """Build the real provider from the environment. Tests monkeypatch this symbol."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ProviderAuthError(
            "the ANTHROPIC_API_KEY environment variable is not set; "
            "export it before running an analysis"
        )
    return AnthropicProvider(api_key)


@app.callback()
def main() -> None:
    """perf-ai — a four-stage AI performance analysis pipeline."""


def _progress_printer(stage: StageName, status: StageStatus, detail: str | None) -> None:
    label = STAGE_LABELS[stage]
    if status is StageStatus.RUNNING:
        console.print(f"[cyan]→[/cyan] {label}: running…")
    elif status is StageStatus.COMPLETED:
        suffix = f" ({detail})" if detail else ""
        console.print(f"[green]✓[/green] {label}: done{suffix}")
    elif status in (StageStatus.FAILED, StageStatus.TIMED_OUT):
        reason = detail or "did not complete"
        console.print(f"[red]✗[/red] {label}: did not complete — {reason}")


@app.command()
def analyze(
    path: Annotated[
        Path,
        typer.Argument(help="Local directory or repository root to analyze."),
    ] = Path("."),
    output_dir: Annotated[
        Path,
        typer.Option(
            "--output-dir",
            "-o",
            help="Directory to write perf-report.md and perf-report.html into "
            "(overwrites any prior run's files).",
        ),
    ] = Path("."),
    include: Annotated[
        list[str] | None,
        typer.Option("--include", help="Glob restricting the code scope (repeatable)."),
    ] = None,
    exclude: Annotated[
        list[str] | None,
        typer.Option("--exclude", help="Glob excluded from the code scope (repeatable)."),
    ] = None,
    timeout_minutes: Annotated[
        float,
        typer.Option("--timeout-minutes", min=0.1, help="Overall run timeout in minutes."),
    ] = DEFAULT_TIMEOUT_MINUTES,
) -> None:
    """Analyze a codebase and write perf-report.md / perf-report.html."""
    if not path.exists() or not os.access(path, os.R_OK):
        err_console.print(f"[red]Error:[/red] path does not exist or is not readable: {path}")
        raise typer.Exit(1)

    files = discover_files(path, include=include or (), exclude=exclude or ())
    if not files:
        err_console.print(
            "[red]Error:[/red] no source code in a recognized language was found "
            f"under: {path}"
        )
        raise typer.Exit(1)

    try:
        provider = create_provider()
    except ProviderAuthError as exc:
        err_console.print(f"[red]Configuration error:[/red] {exc}")
        raise typer.Exit(2) from None

    languages = ", ".join(detect_languages(files))
    console.print(
        f"Analyzing [bold]{len(files)}[/bold] file(s) under [bold]{path}[/bold] "
        f"(detected: {languages})"
    )

    try:
        outcome = run_pipeline(
            root=path.resolve(),
            files=files,
            manifests=discover_manifests(path, exclude=exclude or ()),
            provider=provider,
            config=PipelineConfig(timeout_minutes=timeout_minutes),
            on_progress=_progress_printer,
        )
    except ProviderAuthError as exc:
        err_console.print(f"[red]Configuration error:[/red] {exc}")
        raise typer.Exit(2) from None

    report = aggregate(
        outcome.run,
        coverage_notes=outcome.coverage_notes,
        limitations=outcome.limitations,
    )
    outcome.run.report = report
    md_path, html_path = write_reports(report, outcome.run, output_dir)

    console.print(f"\nReport written to [bold]{md_path}[/bold] and [bold]{html_path}[/bold]")

    completed = [s for s in outcome.run.stages if s.status is StageStatus.COMPLETED]
    if not completed:
        err_console.print(
            "[red]Error:[/red] every analysis stage failed or timed out; the report "
            "records the failure details."
        )
        raise typer.Exit(3)


if __name__ == "__main__":
    app()

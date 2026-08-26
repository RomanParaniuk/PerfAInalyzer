"""Shared helpers for integration tests: invoke the CLI in-process with an injected
mock provider (no network, no real API key)."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
ANTI_PATTERN_FIXTURE = FIXTURES_DIR / "anti_pattern_sample"
CLEAN_FIXTURE = FIXTURES_DIR / "clean_sample"


def invoke_analyze(
    monkeypatch,
    provider,
    path: Path,
    output_dir: Path,
    extra_args: tuple[str, ...] = (),
    api_key: str | None = "test-key-not-real",
):
    """Run `perf-ai analyze` in-process with `provider` injected in place of the real
    Anthropic client. Returns the click result object."""
    import src.cli.main as cli_main

    if api_key is None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    else:
        monkeypatch.setenv("ANTHROPIC_API_KEY", api_key)
    if provider is not None:
        monkeypatch.setattr(cli_main, "create_provider", lambda: provider)
    runner = CliRunner()
    args = ["analyze", str(path), "--output-dir", str(output_dir), *extra_args]
    return runner.invoke(cli_main.app, args)


def read_reports(output_dir: Path) -> tuple[str, str]:
    md = (output_dir / "perf-report.md").read_text(encoding="utf-8")
    html = (output_dir / "perf-report.html").read_text(encoding="utf-8")
    return md, html

"""Integration tests (T010): `perf-ai agent render` per contracts/agent-support-cli.md.

Fixture partial results -> exit 0 with both reports written and failed units named;
all-failed results -> exit 3 with a failure-noting report; missing results dir or
absent/unparsable workplan.json -> exit 1."""

from __future__ import annotations

import shutil
from pathlib import Path

import src.cli.main as cli_main
from src.models.stage import STAGE_LABELS, StageName
from typer.testing import CliRunner

from tests.support.helpers import ANTI_PATTERN_FIXTURE, FIXTURES_DIR

PARTIAL_RESULTS = FIXTURES_DIR / "agent_results_partial"
ALL_FAILED_RESULTS = FIXTURES_DIR / "agent_results_all_failed"

runner = CliRunner()


def invoke_render(monkeypatch, results_dir: Path, output_dir: Path, scope: Path | None = None):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return runner.invoke(
        cli_main.app,
        [
            "agent",
            "render",
            "--results-dir",
            str(results_dir),
            "--scope",
            str(scope or ANTI_PATTERN_FIXTURE),
            "--output-dir",
            str(output_dir),
        ],
    )


class TestPartialResults:
    def test_exit_zero_and_both_reports_written(self, monkeypatch, tmp_path: Path):
        result = invoke_render(monkeypatch, PARTIAL_RESULTS, tmp_path)
        assert result.exit_code == 0, result.output
        assert (tmp_path / "perf-report.md").is_file()
        assert (tmp_path / "perf-report.html").is_file()

    def test_failed_units_are_named_in_report(self, monkeypatch, tmp_path: Path):
        invoke_render(monkeypatch, PARTIAL_RESULTS, tmp_path)
        md = (tmp_path / "perf-report.md").read_text(encoding="utf-8")
        # Both concurrency units failed -> the stage appears as incomplete.
        assert STAGE_LABELS[StageName.CONCURRENCY_SCALABILITY] in md
        assert "did not complete" in md
        # resource_io lost partition p1 -> the coverage note names it.
        assert "p1" in md

    def test_successful_findings_survive_partial_failure(self, monkeypatch, tmp_path: Path):
        invoke_render(monkeypatch, PARTIAL_RESULTS, tmp_path)
        md = (tmp_path / "perf-report.md").read_text(encoding="utf-8")
        assert "find_matching_orders" in md  # from the valid algorithmic units

    def test_planted_same_stage_duplicate_appears_exactly_once(
        self, monkeypatch, tmp_path: Path
    ):
        """FR-011: the duplicate planted at orders.py:12 in both algorithmic units is
        merged to one survivor (the higher-severity p1 finding), never repeated."""
        invoke_render(monkeypatch, PARTIAL_RESULTS, tmp_path)
        md = (tmp_path / "perf-report.md").read_text(encoding="utf-8")
        issue_headings = [line for line in md.splitlines() if line.startswith("### ")]
        duplicate_location = [
            line for line in issue_headings if "orders.py:12" in line
        ]
        assert len(duplicate_location) == 1, issue_headings
        assert "[HIGH]" in duplicate_location[0]  # survivor = highest severity
        # The dropped duplicate's distinct description must not appear anywhere.
        assert "neighboring module is invoked per pricing pass" not in md


class TestAllFailed:
    def test_exit_three_with_failure_noting_report(self, monkeypatch, tmp_path: Path):
        result = invoke_render(monkeypatch, ALL_FAILED_RESULTS, tmp_path)
        assert result.exit_code == 3
        md = (tmp_path / "perf-report.md").read_text(encoding="utf-8")
        assert "did not complete" in md
        # Not an empty-but-clean report: every stage is listed as incomplete.
        for stage in StageName:
            assert STAGE_LABELS[stage] in md


class TestExitCode1InvalidInvocation:
    def test_missing_results_dir(self, monkeypatch, tmp_path: Path):
        result = invoke_render(monkeypatch, tmp_path / "nope", tmp_path)
        assert result.exit_code == 1
        assert "Traceback" not in result.output

    def test_results_dir_without_workplan(self, monkeypatch, tmp_path: Path):
        results = tmp_path / "results"
        results.mkdir()
        result = invoke_render(monkeypatch, results, tmp_path)
        assert result.exit_code == 1
        assert "workplan" in result.output.lower()

    def test_unparsable_workplan(self, monkeypatch, tmp_path: Path):
        results = tmp_path / "results"
        results.mkdir()
        (results / "workplan.json").write_text("{broken", encoding="utf-8")
        result = invoke_render(monkeypatch, results, tmp_path)
        assert result.exit_code == 1
        assert "Traceback" not in result.output

    def test_invalid_scope_path(self, monkeypatch, tmp_path: Path):
        results = tmp_path / "results"
        shutil.copytree(PARTIAL_RESULTS, results)
        result = invoke_render(
            monkeypatch, results, tmp_path, scope=tmp_path / "missing-scope"
        )
        assert result.exit_code == 1

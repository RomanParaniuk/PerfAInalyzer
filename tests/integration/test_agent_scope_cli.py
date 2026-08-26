"""Integration tests (T009): `perf-ai agent scope` per contracts/agent-support-cli.md.

Exit 0 + plan JSON on stdout; exit 2 naming the flag and range for a missing/invalid
--max-parallel; exit 1 with problem-and-fix for a bad target; --include/--exclude match
`analyze` semantics; offline (no ANTHROPIC_API_KEY needed); no stack traces."""

from __future__ import annotations

import json
from pathlib import Path

import src.cli.main as cli_main
from typer.testing import CliRunner

from tests.support.helpers import ANTI_PATTERN_FIXTURE

runner = CliRunner()


def invoke_scope(monkeypatch, *args: str):
    # The agent path must never need a hosted credential (FR-002).
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return runner.invoke(cli_main.app, ["agent", "scope", *args])


class TestSuccess:
    def test_plan_json_on_stdout_exit_zero(self, monkeypatch):
        result = invoke_scope(
            monkeypatch, str(ANTI_PATTERN_FIXTURE), "--max-parallel", "4"
        )
        assert result.exit_code == 0
        plan = json.loads(result.output)
        assert plan["max_parallel"] == 4
        assert plan["file_count"] == 3
        assert plan["detected_languages"] == ["javascript", "python"]
        assert plan["units"][0]["unit_id"] == "structural_context--all"
        assert len(plan["partitions"]) == 2

    def test_output_is_deterministic(self, monkeypatch):
        args = (str(ANTI_PATTERN_FIXTURE), "--max-parallel", "4")
        first = invoke_scope(monkeypatch, *args)
        second = invoke_scope(monkeypatch, *args)
        assert first.output == second.output


class TestExitCode2InvalidInvocation:
    def test_missing_max_parallel(self, monkeypatch):
        result = invoke_scope(monkeypatch, str(ANTI_PATTERN_FIXTURE))
        assert result.exit_code == 2
        assert "--max-parallel" in result.output
        assert "1" in result.output and "10" in result.output
        # The message names the interactive alternative (FR-009).
        assert "max-parallel=" in result.output or "interactive" in result.output.lower()

    def test_out_of_range_and_non_integer_values(self, monkeypatch):
        for bad in ("0", "-3", "abc", "2.5", "11"):
            result = invoke_scope(
                monkeypatch, str(ANTI_PATTERN_FIXTURE), "--max-parallel", bad
            )
            assert result.exit_code == 2, f"--max-parallel {bad} must exit 2"
            assert "--max-parallel" in result.output
            assert "10" in result.output, f"range missing for {bad}"
            assert "Traceback" not in result.output


class TestExitCode1InvalidTarget:
    def test_nonexistent_path(self, monkeypatch, tmp_path: Path):
        result = invoke_scope(
            monkeypatch, str(tmp_path / "does-not-exist"), "--max-parallel", "4"
        )
        assert result.exit_code == 1
        assert "does-not-exist" in result.output
        assert "Traceback" not in result.output

    def test_no_recognized_code(self, monkeypatch, tmp_path: Path):
        scope = tmp_path / "docs-only"
        scope.mkdir()
        (scope / "notes.txt").write_text("no code", encoding="utf-8")
        result = invoke_scope(monkeypatch, str(scope), "--max-parallel", "4")
        assert result.exit_code == 1
        assert "Traceback" not in result.output


class TestIncludeExcludeSemantics:
    def test_exclude_removes_files_like_analyze(self, monkeypatch):
        result = invoke_scope(
            monkeypatch,
            str(ANTI_PATTERN_FIXTURE),
            "--max-parallel",
            "4",
            "--exclude",
            "orders.py",
        )
        assert result.exit_code == 0
        plan = json.loads(result.output)
        assert plan["file_count"] == 2
        covered = sorted(f for p in plan["partitions"] for f in p["files"])
        assert covered == ["pricing.py", "search.js"]

    def test_include_restricts_scope(self, monkeypatch):
        result = invoke_scope(
            monkeypatch,
            str(ANTI_PATTERN_FIXTURE),
            "--max-parallel",
            "2",
            "--include",
            "pricing.py",
        )
        assert result.exit_code == 0
        plan = json.loads(result.output)
        assert plan["file_count"] == 1

    def test_include_matching_nothing_is_invalid_target(self, monkeypatch):
        result = invoke_scope(
            monkeypatch,
            str(ANTI_PATTERN_FIXTURE),
            "--max-parallel",
            "2",
            "--include",
            "*.go",
        )
        assert result.exit_code == 1

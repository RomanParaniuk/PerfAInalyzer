"""Integration tests (T011): agent-path reports are structurally identical to
analyze-path reports built from the same findings (FR-004, SC-002).

The same fixture findings are rendered once through `perf-ai agent render` and once by
invoking the existing aggregator + renderer directly on equivalent `StageResult`s (the
hosted path's shape). Sections, ordering, stage labels, and empty-section handling must
match; volatile content (timestamps, prose of failure reasons) is excluded."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import src.cli.main as cli_main
from src.agentrun.dedupe import dedupe_findings
from src.models.report import AnalysisRun, RunStatus
from src.models.stage import (
    STAGE_ORDER,
    AnalysisStage,
    StageName,
    StageResult,
    StageStatus,
)
from src.pipeline.orchestrator import stamp_findings
from src.report.aggregator import aggregate
from src.report.renderer import write_reports
from typer.testing import CliRunner

from tests.support.helpers import ANTI_PATTERN_FIXTURE, FIXTURES_DIR

PARTIAL_RESULTS = FIXTURES_DIR / "agent_results_partial"
ALL_FAILED_RESULTS = FIXTURES_DIR / "agent_results_all_failed"

runner = CliRunner()


def _agent_render(monkeypatch, results_dir: Path, output_dir: Path) -> str:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = runner.invoke(
        cli_main.app,
        [
            "agent",
            "render",
            "--results-dir",
            str(results_dir),
            "--scope",
            str(ANTI_PATTERN_FIXTURE),
            "--output-dir",
            str(output_dir),
        ],
    )
    assert result.exit_code in (0, 3), result.output
    return (output_dir / "perf-report.md").read_text(encoding="utf-8")


def _fixture_stage_result(name: str) -> StageResult:
    data = json.loads((PARTIAL_RESULTS / f"{name}.json").read_text(encoding="utf-8"))
    return StageResult.model_validate(data["result"])


def _analyze_path_md(output_dir: Path, stages: list[AnalysisStage], notes: list[str]) -> str:
    """Build the report exactly as the hosted path does: aggregate + write_reports."""
    incomplete = any(
        s.status in (StageStatus.FAILED, StageStatus.TIMED_OUT) for s in stages
    )
    run = AnalysisRun(
        code_scope_path=str(ANTI_PATTERN_FIXTURE.resolve()),
        started_at=datetime.now(UTC),
        status=RunStatus.COMPLETED_WITH_PARTIAL_RESULTS
        if incomplete
        else RunStatus.COMPLETED,
        detected_languages=["python"],
        stages=stages,
    )
    report = aggregate(run, coverage_notes=notes)
    run.report = report
    write_reports(report, run, output_dir)
    return (output_dir / "perf-report.md").read_text(encoding="utf-8")


def _headings(md: str) -> list[str]:
    return [line for line in md.splitlines() if line.startswith("## ")]

def _issue_headings(md: str) -> list[str]:
    return [line for line in md.splitlines() if line.startswith("### ")]

def _action_items(md: str) -> list[str]:
    return [line for line in md.splitlines() if re.match(r"^\d+\. \*\*\[", line)]

def _section(md: str, title: str) -> str:
    parts = re.split(r"^## ", md, flags=re.MULTILINE)
    for part in parts:
        if part.startswith(title):
            return part
    raise AssertionError(f"section {title!r} missing")

def _header_field(md: str, field: str) -> str:
    for line in md.splitlines():
        if line.startswith(f"- **{field}**"):
            return line
    raise AssertionError(f"header field {field!r} missing")


class TestPartialRunParity:
    def _build_reports(self, monkeypatch, tmp_path: Path) -> tuple[str, str]:
        agent_md = _agent_render(monkeypatch, PARTIAL_RESULTS, tmp_path / "agent")

        # Equivalent hosted-path stage results: per stage, the union of its valid
        # units' findings in sorted-unit order (matching the render union order).
        structural = _fixture_stage_result("structural_context--all")
        # The union carries the planted duplicate; the agent path dedups it before
        # aggregation (FR-011), so the equivalent hosted-path input is the deduped union.
        algo_findings = dedupe_findings(
            _fixture_stage_result("algorithmic_complexity--p1").findings
            + _fixture_stage_result("algorithmic_complexity--p2").findings
        )
        resource_findings = _fixture_stage_result("resource_io_efficiency--p2").findings

        def stage(name: StageName, findings, status=StageStatus.COMPLETED, reason=None):
            record = AnalysisStage(name=name, status=status, failure_reason=reason)
            if findings is not None:
                record.findings = stamp_findings(
                    StageResult(stage_name=name, findings=findings), name
                )
            return record

        stages = [
            stage(StageName.STRUCTURAL_CONTEXT, structural.findings),
            stage(StageName.ALGORITHMIC_COMPLEXITY, algo_findings),
            stage(StageName.RESOURCE_IO_EFFICIENCY, resource_findings),
            stage(
                StageName.CONCURRENCY_SCALABILITY,
                None,
                status=StageStatus.FAILED,
                reason="all of the stage's work units failed",
            ),
        ]
        analyze_md = _analyze_path_md(
            tmp_path / "analyze", stages, ["resource_io_efficiency stage: partition p1 incomplete"]
        )
        return agent_md, analyze_md

    def test_same_sections_in_same_order(self, monkeypatch, tmp_path: Path):
        agent_md, analyze_md = self._build_reports(monkeypatch, tmp_path)
        assert _headings(agent_md) == _headings(analyze_md)

    def test_same_issue_ordering_and_stage_labels(self, monkeypatch, tmp_path: Path):
        agent_md, analyze_md = self._build_reports(monkeypatch, tmp_path)
        assert _issue_headings(agent_md) == _issue_headings(analyze_md)
        agent_stage_lines = [
            line for line in agent_md.splitlines() if line.startswith("- **Stage**")
        ]
        analyze_stage_lines = [
            line for line in analyze_md.splitlines() if line.startswith("- **Stage**")
        ]
        assert agent_stage_lines == analyze_stage_lines

    def test_same_action_items(self, monkeypatch, tmp_path: Path):
        agent_md, analyze_md = self._build_reports(monkeypatch, tmp_path)
        assert _action_items(agent_md) == _action_items(analyze_md)

    def test_same_header_status_and_languages(self, monkeypatch, tmp_path: Path):
        agent_md, analyze_md = self._build_reports(monkeypatch, tmp_path)
        for field in ("Analyzed path", "Run status", "Detected languages"):
            assert _header_field(agent_md, field) == _header_field(analyze_md, field)

    def test_incomplete_stage_named_in_both(self, monkeypatch, tmp_path: Path):
        agent_md, analyze_md = self._build_reports(monkeypatch, tmp_path)
        for md in (agent_md, analyze_md):
            coverage = _section(md, "Analysis Coverage")
            assert "Concurrency & Scalability Analysis** did not complete" in coverage


class TestEmptySectionParity:
    def test_total_failure_reports_use_same_empty_markers(self, monkeypatch, tmp_path: Path):
        agent_md = _agent_render(monkeypatch, ALL_FAILED_RESULTS, tmp_path / "agent")
        stages = [
            AnalysisStage(
                name=name, status=StageStatus.FAILED, failure_reason="unit failed"
            )
            for name in STAGE_ORDER
        ]
        analyze_md = _analyze_path_md(tmp_path / "analyze", stages, [])
        for marker in (
            "No performance issues were found in this analysis run.",
            "No action items were identified in this analysis run.",
            "No valuable findings were recorded in this analysis run.",
        ):
            assert marker in agent_md
            assert marker in analyze_md
        assert _headings(agent_md) == _headings(analyze_md)

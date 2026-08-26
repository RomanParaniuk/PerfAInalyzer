"""Unit tests (T056): the Markdown and HTML renderers produce content-equivalent output
from one `Report` instance, and rendered text is English regardless of system locale
(FR-018)."""

import html as html_lib
import re
from datetime import UTC, datetime
from pathlib import Path

from src.models.action_item import ActionItem
from src.models.finding import Finding
from src.models.report import AnalysisRun, IncompleteStage, Report, RunStatus
from src.models.stage import AnalysisStage, StageName, StageStatus
from src.report.renderer import render_report, write_reports

GENERATED_AT = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)


def sample_report() -> Report:
    issue = Finding.model_validate(
        {
            "finding_id": "algorithmic_complexity-001",
            "originating_stage": "algorithmic_complexity",
            "kind": "issue",
            "description": "Nested loop performs an O(n^2) scan over the orders list.",
            "location": {
                "file_path": "orders.py",
                "symbol": "find_duplicate_orders",
                "line_start": 9,
                "line_end": 17,
            },
            "severity": "critical",
            "suggested_action": "Build a set of seen ids before the loop and use membership checks.",
        }
    )
    valuable = Finding.model_validate(
        {
            "finding_id": "structural_context-001",
            "originating_stage": "structural_context",
            "kind": "valuable_finding",
            "description": "Pricing is cleanly isolated from order processing.",
            "location": {"file_path": "pricing.py"},
            "severity": None,
            "suggested_action": None,
        }
    )
    action = ActionItem(
        action_item_id="action-001",
        related_finding_ids=["algorithmic_complexity-001"],
        recommendation="Build a set of seen ids before the loop and use membership checks.",
        priority="critical",
    )
    return Report(
        issues=[issue],
        action_items=[action],
        valuable_findings=[valuable],
        incomplete_stages=[
            IncompleteStage(stage=StageName.CONCURRENCY_SCALABILITY, reason="simulated timeout")
        ],
        coverage_note="Everything but tests/ was covered.",
        limitations=["broken.py contains syntax errors and was analyzed best-effort."],
        generated_at=GENERATED_AT,
    )


def sample_run() -> AnalysisRun:
    return AnalysisRun(
        code_scope_path="/scope/project",
        started_at=GENERATED_AT,
        status=RunStatus.COMPLETED_WITH_PARTIAL_RESULTS,
        detected_languages=["javascript", "python"],
        stages=[
            AnalysisStage(name=name, status=StageStatus.COMPLETED)
            for name in (
                StageName.STRUCTURAL_CONTEXT,
                StageName.ALGORITHMIC_COMPLEXITY,
                StageName.RESOURCE_IO_EFFICIENCY,
            )
        ]
        + [
            AnalysisStage(
                name=StageName.CONCURRENCY_SCALABILITY,
                status=StageStatus.TIMED_OUT,
                failure_reason="simulated timeout",
            )
        ],
    )


def html_to_text(html: str) -> str:
    text = re.sub(r"<style.*?</style>", " ", html, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(html_lib.unescape(text).split())


ENGLISH_HEADINGS = [
    "Performance Analysis Report",
    "Issues",
    "Action Items",
    "Valuable Findings",
    "Analysis Coverage",
]


class TestContentEquivalence:
    def test_markdown_and_html_carry_identical_content(self):
        markdown, html = render_report(sample_report(), sample_run())
        html_text = html_to_text(html)
        md_text = " ".join(markdown.split())

        core_strings = [
            "Nested loop performs an O(n^2) scan over the orders list.",
            "orders.py:9-17 (find_duplicate_orders)",
            "Build a set of seen ids before the loop and use membership checks.",
            "Pricing is cleanly isolated from order processing.",
            "Concurrency & Scalability Analysis",
            "simulated timeout",
            "Everything but tests/ was covered.",
            "broken.py contains syntax errors and was analyzed best-effort.",
            "javascript, python",
            "completed with partial results",
            "algorithmic_complexity-001",
            *ENGLISH_HEADINGS,
        ]
        for value in core_strings:
            assert value in md_text, f"missing from markdown: {value!r}"
            assert value in html_text, f"missing from html: {value!r}"

    def test_empty_sections_render_explicit_markers_in_both(self):
        report = Report(generated_at=GENERATED_AT)
        run = sample_run()
        markdown, html = render_report(report, run)
        html_text = html_to_text(html)
        for marker in (
            "No performance issues were found in this analysis run.",
            "No action items were identified in this analysis run.",
            "No valuable findings were recorded in this analysis run.",
        ):
            assert marker in markdown
            assert marker in html_text


class TestEnglishRegardlessOfLocale:
    def test_rendering_under_ukrainian_locale_is_english(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("LANG", "uk_UA.UTF-8")
        monkeypatch.setenv("LC_ALL", "uk_UA.UTF-8")
        monkeypatch.setenv("LANGUAGE", "uk_UA")

        md_path, html_path = write_reports(sample_report(), sample_run(), tmp_path)
        markdown = md_path.read_text(encoding="utf-8")
        html_text = html_to_text(html_path.read_text(encoding="utf-8"))

        for heading in ENGLISH_HEADINGS:
            assert heading in markdown
            assert heading in html_text
        assert "No performance issues" not in markdown  # issues exist in the sample
        # No Cyrillic anywhere in the rendered output.
        assert not re.search(r"[Ѐ-ӿ]", markdown)
        assert not re.search(r"[Ѐ-ӿ]", html_text)


class TestWriteReports:
    def test_overwrites_previous_run_files(self, tmp_path: Path):
        (tmp_path / "perf-report.md").write_text("stale", encoding="utf-8")
        (tmp_path / "perf-report.html").write_text("stale", encoding="utf-8")
        md_path, html_path = write_reports(sample_report(), sample_run(), tmp_path)
        assert "stale" not in md_path.read_text(encoding="utf-8")
        assert "stale" not in html_path.read_text(encoding="utf-8")

    def test_creates_output_dir_if_missing(self, tmp_path: Path):
        target = tmp_path / "nested" / "out"
        md_path, html_path = write_reports(sample_report(), sample_run(), target)
        assert md_path.exists() and html_path.exists()

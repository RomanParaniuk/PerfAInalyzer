"""Integration test (T025): a clean codebase yields a report whose Issues section
explicitly states none were found rather than being omitted (FR-010, SC-006)."""

from pathlib import Path

from tests.support.helpers import CLEAN_FIXTURE, invoke_analyze, read_reports
from tests.support.mock_provider import MockProvider, clean_results


def test_empty_issues_section_is_explicit_not_omitted(monkeypatch, tmp_path: Path):
    provider = MockProvider(results=clean_results())
    result = invoke_analyze(monkeypatch, provider, CLEAN_FIXTURE, tmp_path)

    assert result.exit_code == 0, result.output
    md, html = read_reports(tmp_path)
    for report in (md, html):
        assert "Issues" in report
        assert "No performance issues were found" in report
        # The other two sections are present and explicitly marked empty too (SC-006).
        assert "Action Items" in report
        assert "No action items" in report
        assert "Valuable Findings" in report
        assert "No valuable findings" in report

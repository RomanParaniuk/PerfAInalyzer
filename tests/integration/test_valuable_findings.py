"""Integration test (T044): a deliberately well-optimized pattern appears under a
distinct Valuable Findings section, separate from Issues and Action Items (FR-007)."""

from pathlib import Path

from tests.support.helpers import ANTI_PATTERN_FIXTURE, invoke_analyze, read_reports
from tests.support.mock_provider import MockProvider, anti_pattern_results


def test_well_optimized_pattern_in_distinct_section(monkeypatch, tmp_path: Path):
    provider = MockProvider(results=anti_pattern_results())
    result = invoke_analyze(monkeypatch, provider, ANTI_PATTERN_FIXTURE, tmp_path)
    assert result.exit_code == 0, result.output

    md, html = read_reports(tmp_path)
    for report in (md, html):
        assert "Valuable Findings" in report
        assert "lru_cache" in report
        assert "compute_discount" in report

    # The memoization note lives in the Valuable Findings section — not under Issues
    # or Action Items.
    issues_section = md.split("## Issues")[1].split("## Action Items")[0]
    action_section = md.split("## Action Items")[1].split("## Valuable Findings")[0]
    valuable_section = md.split("## Valuable Findings")[1].split("## Analysis Coverage")[0]

    assert "lru_cache" in valuable_section
    assert "lru_cache" not in issues_section
    assert "lru_cache" not in action_section
    # Valuable findings are never rated for severity.
    assert "Severity" not in valuable_section

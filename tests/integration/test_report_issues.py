"""Integration test (T024): CLI run against the anti-pattern fixture produces both
report files listing the planted anti-pattern as an Issue with a location reference,
and never executes/compiles the fixture code (SC-001)."""

import sys
from pathlib import Path

from src.models.stage import STAGE_ORDER

from tests.support.helpers import ANTI_PATTERN_FIXTURE, invoke_analyze, read_reports
from tests.support.mock_provider import MockProvider, anti_pattern_results


def test_reports_identify_planted_anti_pattern(monkeypatch, tmp_path: Path):
    provider = MockProvider(results=anti_pattern_results())
    result = invoke_analyze(monkeypatch, provider, ANTI_PATTERN_FIXTURE, tmp_path)

    assert result.exit_code == 0, result.output
    md_path = tmp_path / "perf-report.md"
    html_path = tmp_path / "perf-report.html"
    assert md_path.exists() and html_path.exists()

    md, html = read_reports(tmp_path)
    for report in (md, html):
        # The planted O(n^2) anti-pattern appears as an Issue with a location reference.
        assert "find_duplicate_orders" in report
        assert "O(n^2)" in report
        assert "orders.py" in report
        assert "Issues" in report

    # Location reference includes the file and line range from the finding.
    assert "orders.py:9-17" in md


def test_all_stages_called_through_mock_provider(monkeypatch, tmp_path: Path):
    provider = MockProvider(results=anti_pattern_results())
    result = invoke_analyze(monkeypatch, provider, ANTI_PATTERN_FIXTURE, tmp_path)

    assert result.exit_code == 0, result.output
    assert len(provider.calls) == len(STAGE_ORDER)
    assert {c.stage_name for c in provider.calls} == set(STAGE_ORDER)


def test_fixture_code_never_executed_or_compiled(monkeypatch, tmp_path: Path):
    """SC-001: the fixture raises at import/run time, so a successful analysis with no
    __pycache__ and no loaded fixture module proves nothing was executed or compiled."""
    provider = MockProvider(results=anti_pattern_results())
    result = invoke_analyze(monkeypatch, provider, ANTI_PATTERN_FIXTURE, tmp_path)

    assert result.exit_code == 0, result.output
    # Not imported: the guard would have raised and failed the run.
    assert "orders" not in sys.modules
    assert "pricing" not in sys.modules
    # Not compiled: no bytecode cache was created inside the fixture tree.
    assert not (ANTI_PATTERN_FIXTURE / "__pycache__").exists()
    assert not list(ANTI_PATTERN_FIXTURE.rglob("*.pyc"))

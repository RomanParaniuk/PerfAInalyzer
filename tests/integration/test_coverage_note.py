"""Integration test (T053): a budget-capped run reports what was and was not covered
via `coverage_note` rather than silently truncating (FR-013, edge case: too large to
fully analyze)."""

from pathlib import Path

from src.models.stage import StageName

from tests.support.helpers import ANTI_PATTERN_FIXTURE, invoke_analyze, read_reports
from tests.support.mock_provider import MockProvider, anti_pattern_results, make_stage_result


def test_budget_capped_stage_coverage_is_reported(monkeypatch, tmp_path: Path):
    results = anti_pattern_results()
    results[StageName.ALGORITHMIC_COMPLEXITY] = make_stage_result(
        StageName.ALGORITHMIC_COMPLEXITY,
        [f.model_dump() for f in results[StageName.ALGORITHMIC_COMPLEXITY].findings],
        coverage_note=(
            "Covered: orders.py and search.js in full. Not covered within the token "
            "budget: pricing.py beyond its first function."
        ),
    )
    provider = MockProvider(results=results)
    result = invoke_analyze(monkeypatch, provider, ANTI_PATTERN_FIXTURE, tmp_path)
    assert result.exit_code == 0, result.output

    md, html = read_reports(tmp_path)
    for report in (md, html):
        assert "Coverage note" in report
        assert "Covered: orders.py" in report
        assert "Not covered within the token budget" in report

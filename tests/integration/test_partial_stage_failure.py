"""Integration test (T026): a failing/timed-out stage degrades gracefully — the report
still includes completed stages' findings, lists the failed stage as incomplete, and the
process exits 0 (FR-012)."""

import html
from pathlib import Path

from src.models.stage import StageName
from src.providers.anthropic_client import StageCallError

from tests.support.helpers import ANTI_PATTERN_FIXTURE, invoke_analyze, read_reports
from tests.support.mock_provider import MockProvider, anti_pattern_results


def test_failed_stage_reported_without_blocking_run(monkeypatch, tmp_path: Path):
    provider = MockProvider(
        results=anti_pattern_results(),
        failures={
            StageName.RESOURCE_IO_EFFICIENCY: StageCallError("simulated provider outage")
        },
    )
    result = invoke_analyze(monkeypatch, provider, ANTI_PATTERN_FIXTURE, tmp_path)

    # Graceful degradation is still a successful CLI outcome (exit 0).
    assert result.exit_code == 0, result.output

    md, html_report = read_reports(tmp_path)
    for report in (md, html.unescape(html_report)):
        # Findings from the completed complexity stage are present.
        assert "find_duplicate_orders" in report
        # The failed stage is listed as incomplete, with its reason.
        assert "Resource & I/O Efficiency" in report
        assert "did not complete" in report or "simulated provider outage" in report
    assert "simulated provider outage" in md

    # The failed stage's findings are absent (it produced none).
    assert "write_audit_log" not in md

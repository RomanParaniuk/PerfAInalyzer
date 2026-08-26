"""Integration test (T054): a multi-language repository has each recognized language
detected and analyzed rather than assuming a single language (FR-014)."""

from pathlib import Path

from tests.support.helpers import ANTI_PATTERN_FIXTURE, invoke_analyze, read_reports
from tests.support.mock_provider import MockProvider, anti_pattern_results


def test_each_recognized_language_detected_and_analyzed(monkeypatch, tmp_path: Path):
    # The anti-pattern fixture deliberately mixes Python and JavaScript.
    provider = MockProvider(results=anti_pattern_results())
    result = invoke_analyze(monkeypatch, provider, ANTI_PATTERN_FIXTURE, tmp_path)
    assert result.exit_code == 0, result.output

    md, _html = read_reports(tmp_path)
    # Both languages are detected and reported.
    assert "javascript, python" in md
    # And both languages' code was actually analyzed: findings exist for each.
    assert "orders.py" in md  # python finding
    assert "search.js" in md  # javascript finding

    # The analyzed scope shipped to the provider includes both languages' files.
    shared_context = provider.calls[0].shared_context
    assert "orders.py (python)" in shared_context
    assert "search.js (javascript)" in shared_context

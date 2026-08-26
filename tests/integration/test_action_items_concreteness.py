"""Integration test (T039): every action item's recommendation is a concrete step, not
a textual (or near-textual) restatement of its related issue's description (FR-006)."""

import re
from pathlib import Path

from src.providers.anthropic_client import is_near_identical

from tests.support.helpers import ANTI_PATTERN_FIXTURE, invoke_analyze, read_reports
from tests.support.mock_provider import MockProvider, anti_pattern_results


def test_recommendations_are_not_restatements(monkeypatch, tmp_path: Path):
    provider = MockProvider(results=anti_pattern_results())
    result = invoke_analyze(monkeypatch, provider, ANTI_PATTERN_FIXTURE, tmp_path)
    assert result.exit_code == 0, result.output

    md, _html = read_reports(tmp_path)

    # Pair every rendered action item with its related issue via the finding id.
    issue_blocks = re.findall(
        r"### \d+\. \[(?:CRITICAL|HIGH|MEDIUM|LOW)\] .+?\n\n(.+?)\n\n- \*\*Severity\*\*.*?"
        r"\*\*Finding ID\*\*: `([^`]+)`",
        md,
        flags=re.DOTALL,
    )
    descriptions_by_id = {fid: desc.strip() for desc, fid in issue_blocks}
    assert descriptions_by_id  # sanity

    action_section = md.split("## Action Items")[1].split("## Valuable Findings")[0]
    action_entries = re.findall(
        r"\*\*\[(?:CRITICAL|HIGH|MEDIUM|LOW)\]\*\* (.+?)\n\s+\(addresses `([^`]+)`",
        action_section,
        flags=re.DOTALL,
    )
    assert action_entries  # sanity

    for recommendation, finding_id in action_entries:
        description = descriptions_by_id[finding_id]
        assert not is_near_identical(description, recommendation.strip()), (
            f"action item for {finding_id} restates its issue description"
        )

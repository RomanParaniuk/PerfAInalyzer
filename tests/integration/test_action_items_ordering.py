"""Integration test (T038): action items for a multi-severity fixture are ordered
highest-priority first (FR-008)."""

import re
from pathlib import Path

from tests.support.helpers import ANTI_PATTERN_FIXTURE, invoke_analyze, read_reports
from tests.support.mock_provider import MockProvider, anti_pattern_results


def test_action_items_ordered_highest_priority_first(monkeypatch, tmp_path: Path):
    provider = MockProvider(results=anti_pattern_results())
    result = invoke_analyze(monkeypatch, provider, ANTI_PATTERN_FIXTURE, tmp_path)
    assert result.exit_code == 0, result.output

    md, _html = read_reports(tmp_path)
    action_section = md.split("## Action Items")[1].split("## Valuable Findings")[0]
    priorities = re.findall(r"\*\*\[(CRITICAL|HIGH|MEDIUM|LOW)\]\*\*", action_section)

    # The fixture mock produces critical, high, medium and low issues.
    assert len(priorities) >= 3
    rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    assert priorities == sorted(priorities, key=lambda p: rank[p])
    assert priorities[0] == "CRITICAL"


def test_every_issue_has_an_associated_action_item(monkeypatch, tmp_path: Path):
    provider = MockProvider(results=anti_pattern_results())
    result = invoke_analyze(monkeypatch, provider, ANTI_PATTERN_FIXTURE, tmp_path)
    assert result.exit_code == 0, result.output

    md, _html = read_reports(tmp_path)
    issue_ids = set(re.findall(r"\*\*Finding ID\*\*: `([^`]+)`", md))
    action_section = md.split("## Action Items")[1].split("## Valuable Findings")[0]
    referenced_ids = set(re.findall(r"`([a-z_]+-\d{3})`", action_section))
    assert issue_ids  # sanity: the fixture produced issues
    assert issue_ids <= referenced_ids

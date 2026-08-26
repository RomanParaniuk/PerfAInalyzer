"""Integration test (T048): every finding in a report spanning multiple stages is
labeled with its originating analysis stage (FR-009)."""

import html as html_lib
import re
from pathlib import Path

from src.models.stage import STAGE_LABELS

from tests.support.helpers import ANTI_PATTERN_FIXTURE, invoke_analyze, read_reports
from tests.support.mock_provider import MockProvider, anti_pattern_results


def test_every_finding_labeled_with_originating_stage(monkeypatch, tmp_path: Path):
    provider = MockProvider(results=anti_pattern_results())
    result = invoke_analyze(monkeypatch, provider, ANTI_PATTERN_FIXTURE, tmp_path)
    assert result.exit_code == 0, result.output

    md, html_report = read_reports(tmp_path)
    html_text = html_lib.unescape(html_report)

    # The fixture mock spans at least three distinct stages.
    labels_present = {label for label in STAGE_LABELS.values() if label in md}
    assert len(labels_present) >= 3

    # Every issue block carries a stage label.
    issue_count = len(re.findall(r"### \d+\. \[", md))
    issue_stage_labels = re.findall(r"- \*\*Stage\*\*: (.+)", md)
    assert issue_count > 0
    assert len(issue_stage_labels) == issue_count

    # Every action item and valuable finding carries a stage label.
    action_section = md.split("## Action Items")[1].split("## Valuable Findings")[0]
    action_count = len(re.findall(r"^\d+\.", action_section, flags=re.MULTILINE))
    assert action_count == len(re.findall(r"stage: \S", action_section))

    valuable_section = md.split("## Valuable Findings")[1].split("## Analysis Coverage")[0]
    valuable_count = len(re.findall(r"^- ", valuable_section, flags=re.MULTILINE))
    assert valuable_count > 0
    assert valuable_count == len(re.findall(r"stage: \S", valuable_section))

    # HTML carries the same labels (content equivalence).
    for label in labels_present:
        assert label in html_text

"""Unit test (T049): the orchestrator stamps `originating_stage` on every finding
before it reaches the aggregator, independent of model output reliability."""

from pathlib import Path

from src.lib.discovery import discover_files
from src.models.stage import StageName, StageResult, StageStatus
from src.pipeline.orchestrator import run_pipeline, stamp_findings
from src.pipeline.stages import get_stage_specs

from tests.support.helpers import ANTI_PATTERN_FIXTURE
from tests.support.mock_provider import MockProvider, anti_pattern_results


def test_stamp_findings_sets_stage_and_stable_ids():
    result = anti_pattern_results()[StageName.ALGORITHMIC_COMPLEXITY]
    stamped = stamp_findings(result, StageName.ALGORITHMIC_COMPLEXITY)

    assert len(stamped) == len(result.findings)
    for i, finding in enumerate(stamped, start=1):
        assert finding.originating_stage is StageName.ALGORITHMIC_COMPLEXITY
        assert finding.finding_id == f"algorithmic_complexity-{i:03d}"


def test_orchestrator_stamps_every_finding_regardless_of_model_output(tmp_path: Path):
    # The tool payload has no originating_stage field at all — attribution can only
    # come from the orchestrator, never from the model.
    payload_fields = set(StageResult.model_fields["findings"].annotation.__args__[0].model_fields)
    assert "originating_stage" not in payload_fields

    provider = MockProvider(results=anti_pattern_results())
    files = discover_files(ANTI_PATTERN_FIXTURE)
    outcome = run_pipeline(
        root=ANTI_PATTERN_FIXTURE,
        files=files,
        provider=provider,
        stage_specs=get_stage_specs(),
    )

    completed = [s for s in outcome.run.stages if s.status is StageStatus.COMPLETED]
    assert len(completed) == 4
    all_findings = [f for stage in outcome.run.stages for f in stage.findings]
    assert all_findings
    for stage in outcome.run.stages:
        for finding in stage.findings:
            assert finding.originating_stage is stage.name
            assert finding.finding_id.startswith(stage.name.value)

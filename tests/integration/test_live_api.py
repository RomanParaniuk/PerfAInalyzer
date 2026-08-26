"""Live-API validation suite (T057): one real Anthropic API call per stage against a
small fixture. Excluded from routine runs by the `live_api` marker (pyproject addopts);
invoke explicitly with:

    pytest -m live_api --override-ini addopts='' tests/integration/test_live_api.py
"""

import os

import pytest
from src.lib.discovery import discover_files
from src.models.stage import StageName
from src.pipeline.context import assemble_context, build_shared_context, build_structural_index
from src.pipeline.stages import get_stage_specs
from src.providers.anthropic_client import AnthropicProvider

from tests.support.helpers import ANTI_PATTERN_FIXTURE

pytestmark = [
    pytest.mark.live_api,
    pytest.mark.skipif(
        not os.environ.get("ANTHROPIC_API_KEY"),
        reason="ANTHROPIC_API_KEY not set; live-API suite requires a real key",
    ),
]


@pytest.fixture(scope="module")
def live_setup():
    files = discover_files(ANTI_PATTERN_FIXTURE)
    index = build_structural_index(ANTI_PATTERN_FIXTURE, files)
    shared = build_shared_context(index, "Small fixture: order processing with planted anti-patterns.")
    provider = AnthropicProvider(os.environ["ANTHROPIC_API_KEY"])
    return provider, index, shared


@pytest.mark.parametrize("stage_name", list(StageName))
def test_live_stage_call_returns_schema_valid_result(live_setup, stage_name: StageName):
    provider, index, shared = live_setup
    spec = get_stage_specs()[stage_name]
    bundle = assemble_context(index, stage_name, shared_context=shared)

    result = provider.run_stage(
        stage_name=stage_name,
        system_prompt=spec.system_prompt,
        shared_context=bundle.shared_context,
        stage_input=f"{spec.instructions}\n\n# Stage-specific code excerpts\n\n{bundle.stage_excerpts}",
    )

    # Schema validity is guaranteed by run_stage (it raises otherwise); assert the
    # semantics: correct stage attribution and grounded locations.
    assert result.stage_name is stage_name
    known_files = {f.rel_path for f in discover_files(ANTI_PATTERN_FIXTURE)}
    for finding in result.findings:
        assert finding.location.file_path in known_files


@pytest.mark.parametrize("stage_name", [StageName.ALGORITHMIC_COMPLEXITY])
def test_live_complexity_stage_finds_planted_anti_pattern(live_setup, stage_name):
    """SC-002 spot check: the planted O(n^2) scan should surface as an issue."""
    provider, index, shared = live_setup
    spec = get_stage_specs()[stage_name]
    bundle = assemble_context(index, stage_name, shared_context=shared)
    result = provider.run_stage(
        stage_name=stage_name,
        system_prompt=spec.system_prompt,
        shared_context=bundle.shared_context,
        stage_input=f"{spec.instructions}\n\n# Stage-specific code excerpts\n\n{bundle.stage_excerpts}",
    )
    issue_files = {f.location.file_path for f in result.findings if f.kind.value == "issue"}
    assert "orders.py" in issue_files

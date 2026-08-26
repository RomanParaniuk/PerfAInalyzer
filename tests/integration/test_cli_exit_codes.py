"""Integration tests (T052): the CLI exit-code contract per contracts/cli-interface.md.

1 = invalid/unreadable PATH or no recognized-language code; 2 = missing/rejected
ANTHROPIC_API_KEY before analysis could proceed; 3 = every stage failed/timed out."""

from pathlib import Path

from src.models.stage import StageName
from src.providers.anthropic_client import ProviderAuthError, StageCallError

from tests.support.helpers import ANTI_PATTERN_FIXTURE, invoke_analyze
from tests.support.mock_provider import MockProvider, anti_pattern_results


class TestExitCode1InvalidInvocation:
    def test_nonexistent_path(self, monkeypatch, tmp_path: Path):
        result = invoke_analyze(
            monkeypatch, MockProvider(results={}), tmp_path / "does-not-exist", tmp_path
        )
        assert result.exit_code == 1

    def test_no_recognized_language_code(self, monkeypatch, tmp_path: Path):
        scope = tmp_path / "docs-only"
        scope.mkdir()
        (scope / "README.txt").write_text("no code here", encoding="utf-8")
        result = invoke_analyze(monkeypatch, MockProvider(results={}), scope, tmp_path)
        assert result.exit_code == 1


class TestExitCode2ConfigurationError:
    def test_missing_api_key(self, monkeypatch, tmp_path: Path):
        # No provider injected: the real create_provider runs and must fail fast.
        result = invoke_analyze(
            monkeypatch, None, ANTI_PATTERN_FIXTURE, tmp_path, api_key=None
        )
        assert result.exit_code == 2
        # No stage ran, so no report was produced.
        assert not (tmp_path / "perf-report.md").exists()

    def test_key_rejected_by_provider(self, monkeypatch, tmp_path: Path):
        provider = MockProvider(
            results={},
            failures={
                StageName.STRUCTURAL_CONTEXT: ProviderAuthError(
                    "the Anthropic API rejected the provided API key"
                )
            },
        )
        result = invoke_analyze(monkeypatch, provider, ANTI_PATTERN_FIXTURE, tmp_path)
        assert result.exit_code == 2


class TestExitCode3TotalPipelineFailure:
    def test_every_stage_failed(self, monkeypatch, tmp_path: Path):
        provider = MockProvider(
            results={},
            failures={
                stage: StageCallError("simulated outage") for stage in StageName
            },
        )
        result = invoke_analyze(monkeypatch, provider, ANTI_PATTERN_FIXTURE, tmp_path)
        assert result.exit_code == 3
        # A report is still written, noting the total failure (FR-012 reporting duty).
        md = (tmp_path / "perf-report.md").read_text(encoding="utf-8")
        assert "did not complete" in md
        assert "No performance issues were found" in md


class TestExitCode0Success:
    def test_successful_run_exits_zero(self, monkeypatch, tmp_path: Path):
        provider = MockProvider(results=anti_pattern_results())
        result = invoke_analyze(monkeypatch, provider, ANTI_PATTERN_FIXTURE, tmp_path)
        assert result.exit_code == 0

    def test_partial_failure_still_exits_zero(self, monkeypatch, tmp_path: Path):
        provider = MockProvider(
            results=anti_pattern_results(),
            failures={StageName.CONCURRENCY_SCALABILITY: StageCallError("boom")},
        )
        result = invoke_analyze(monkeypatch, provider, ANTI_PATTERN_FIXTURE, tmp_path)
        assert result.exit_code == 0

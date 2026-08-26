"""Security hardening tests (T058): the API key is never accepted via CLI flag, never
logged, and never appears in progress/error output."""

import re
from pathlib import Path

import src.cli.main as cli_main
from src.models.stage import StageName
from src.providers.anthropic_client import ProviderAuthError, StageCallError
from typer.testing import CliRunner

from tests.support.helpers import ANTI_PATTERN_FIXTURE, invoke_analyze

SECRET = "sk-ant-super-secret-value-12345"


def test_no_api_key_cli_flag_exists():
    result = CliRunner().invoke(cli_main.app, ["analyze", "--help"])
    assert result.exit_code == 0
    assert "--api-key" not in result.output
    assert "api_key" not in result.output


def test_key_never_appears_in_error_output_on_auth_failure(monkeypatch, tmp_path: Path):
    from tests.support.mock_provider import MockProvider

    provider = MockProvider(
        results={},
        failures={
            StageName.STRUCTURAL_CONTEXT: ProviderAuthError(
                "the Anthropic API rejected the provided API key"
            )
        },
    )
    result = invoke_analyze(
        monkeypatch, provider, ANTI_PATTERN_FIXTURE, tmp_path, api_key=SECRET
    )
    assert result.exit_code == 2
    assert SECRET not in result.output


def test_key_never_appears_in_output_or_report_on_stage_failure(monkeypatch, tmp_path: Path):
    from tests.support.mock_provider import MockProvider, anti_pattern_results

    provider = MockProvider(
        results=anti_pattern_results(),
        failures={StageName.RESOURCE_IO_EFFICIENCY: StageCallError("upstream 500")},
    )
    result = invoke_analyze(
        monkeypatch, provider, ANTI_PATTERN_FIXTURE, tmp_path, api_key=SECRET
    )
    assert result.exit_code == 0
    assert SECRET not in result.output
    for name in ("perf-report.md", "perf-report.html"):
        assert SECRET not in (tmp_path / name).read_text(encoding="utf-8")


def test_source_never_logs_or_prints_the_key():
    """Static audit: the key variable is read from the environment and passed straight
    to the SDK constructor — never interpolated into logs, prints, or exceptions."""
    for module_path in ("src/cli/main.py", "src/providers/anthropic_client.py"):
        source = Path(module_path).read_text(encoding="utf-8")
        for line in source.splitlines():
            if re.search(r"\b(?:logger\.\w+|print|console\.print|err_console\.print)\(", line):
                assert "api_key" not in line, f"key reaches output in {module_path}: {line.strip()}"

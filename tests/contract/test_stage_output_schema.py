"""Contract tests for `report_stage_findings` schema validation and its cross-field
rules against fixture payloads (T018), plus the provider's one-retry-then-fail
semantics exercised over mocked HTTP (T017)."""

import httpx
import pytest
import respx
from pydantic import ValidationError
from src.models.stage import StageName
from src.providers.anthropic_client import (
    REPORT_STAGE_FINDINGS_TOOL,
    STAGE_MODELS,
    TOOL_NAME,
    AnthropicProvider,
    ProviderAuthError,
    StageValidationError,
    is_near_identical,
    payload_quality_problems,
    validate_stage_payload,
)

ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"


def issue_finding(**overrides) -> dict:
    finding = {
        "kind": "issue",
        "description": "Nested loop performs an O(n^2) scan over the orders list.",
        "location": {"file_path": "orders.py", "symbol": "find_duplicates", "line_start": 8, "line_end": 15},
        "severity": "high",
        "suggested_action": "Build a set of seen order ids before the loop and test membership against it.",
    }
    return finding | overrides


def stage_payload(**overrides) -> dict:
    payload = {
        "stage_name": "algorithmic_complexity",
        "findings": [issue_finding()],
        "coverage_note": None,
    }
    return payload | overrides


class TestSchemaValidation:
    def test_valid_issue_payload_accepted(self):
        result = validate_stage_payload(stage_payload(), StageName.ALGORITHMIC_COMPLEXITY)
        assert result.stage_name is StageName.ALGORITHMIC_COMPLEXITY
        assert len(result.findings) == 1

    def test_valid_valuable_finding_payload_accepted(self):
        payload = stage_payload(
            findings=[issue_finding(kind="valuable_finding", severity=None, suggested_action=None)]
        )
        result = validate_stage_payload(payload, StageName.ALGORITHMIC_COMPLEXITY)
        assert result.findings[0].severity is None

    def test_empty_findings_accepted(self):
        result = validate_stage_payload(stage_payload(findings=[]), StageName.ALGORITHMIC_COMPLEXITY)
        assert result.findings == []

    def test_issue_missing_severity_rejected(self):
        with pytest.raises(ValidationError):
            validate_stage_payload(
                stage_payload(findings=[issue_finding(severity=None)]),
                StageName.ALGORITHMIC_COMPLEXITY,
            )

    def test_severity_on_valuable_finding_rejected(self):
        with pytest.raises(ValidationError):
            validate_stage_payload(
                stage_payload(findings=[issue_finding(kind="valuable_finding", suggested_action=None)]),
                StageName.ALGORITHMIC_COMPLEXITY,
            )

    def test_issue_missing_suggested_action_rejected(self):
        with pytest.raises(ValidationError):
            validate_stage_payload(
                stage_payload(findings=[issue_finding(suggested_action=None)]),
                StageName.ALGORITHMIC_COMPLEXITY,
            )

    def test_empty_description_rejected(self):
        with pytest.raises(ValidationError):
            validate_stage_payload(
                stage_payload(findings=[issue_finding(description="")]),
                StageName.ALGORITHMIC_COMPLEXITY,
            )

    def test_missing_file_path_rejected(self):
        with pytest.raises(ValidationError):
            validate_stage_payload(
                stage_payload(findings=[issue_finding(location={"file_path": ""})]),
                StageName.ALGORITHMIC_COMPLEXITY,
            )

    def test_unknown_stage_name_rejected(self):
        with pytest.raises(ValidationError):
            validate_stage_payload(
                stage_payload(stage_name="quantum_vibes"), StageName.ALGORITHMIC_COMPLEXITY
            )

    def test_stage_name_mismatch_rejected(self):
        with pytest.raises(StageValidationError, match="mismatch"):
            validate_stage_payload(stage_payload(), StageName.CONCURRENCY_SCALABILITY)


class TestNearIdenticalRule:
    def test_identical_text_flagged(self):
        assert is_near_identical("Nested O(n^2) loop.", "Nested O(n^2) loop.")

    def test_case_and_whitespace_normalized(self):
        assert is_near_identical("Nested  O(n^2) LOOP", "nested o(n^2) loop.")

    def test_trivial_rephrasing_flagged(self):
        assert is_near_identical(
            "The loop scans the orders list quadratically.",
            "The loop scans the order list quadratically",
        )

    def test_concrete_action_not_flagged(self):
        assert not is_near_identical(
            "Nested loop performs an O(n^2) scan over the orders list.",
            "Replace the inner scan with a set membership check built once before the loop.",
        )

    def test_quality_problems_reported_for_restatement(self):
        payload = stage_payload(
            findings=[
                issue_finding(
                    suggested_action="Nested loop performs an O(n^2) scan over the orders list."
                )
            ]
        )
        result = validate_stage_payload(payload, StageName.ALGORITHMIC_COMPLEXITY)
        problems = payload_quality_problems(result)
        assert len(problems) == 1
        assert "near-identical" in problems[0]


class TestToolDefinitionMatchesContract:
    def test_tool_name_and_required_fields(self):
        assert REPORT_STAGE_FINDINGS_TOOL["name"] == "report_stage_findings"
        schema = REPORT_STAGE_FINDINGS_TOOL["input_schema"]
        assert set(schema["required"]) == {"stage_name", "findings"}
        assert set(schema["properties"]["stage_name"]["enum"]) == {
            "structural_context",
            "algorithmic_complexity",
            "resource_io_efficiency",
            "concurrency_scalability",
        }

    def test_finding_schema_required_fields(self):
        finding_schema = REPORT_STAGE_FINDINGS_TOOL["input_schema"]["properties"]["findings"]["items"]
        assert set(finding_schema["required"]) == {"kind", "description", "location"}
        assert finding_schema["properties"]["location"]["required"] == ["file_path"]

    def test_stage_model_ids_are_verbatim(self):
        assert STAGE_MODELS[StageName.STRUCTURAL_CONTEXT] == "claude-haiku-4-5"
        assert STAGE_MODELS[StageName.ALGORITHMIC_COMPLEXITY] == "claude-sonnet-5"
        assert STAGE_MODELS[StageName.RESOURCE_IO_EFFICIENCY] == "claude-sonnet-5"
        assert STAGE_MODELS[StageName.CONCURRENCY_SCALABILITY] == "claude-sonnet-5"


def _message_json(tool_input: dict) -> dict:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-5",
        "content": [
            {"type": "tool_use", "id": "toolu_1", "name": TOOL_NAME, "input": tool_input}
        ],
        "stop_reason": "tool_use",
        "stop_sequence": None,
        "usage": {"input_tokens": 100, "output_tokens": 50},
    }


def _run_stage(provider: AnthropicProvider):
    return provider.run_stage(
        stage_name=StageName.ALGORITHMIC_COMPLEXITY,
        system_prompt="You are a performance analyst.",
        shared_context="# Repository code map\n",
        stage_input="Analyze the excerpts.",
    )


class TestProviderRetrySemantics:
    """T017: schema-validation-with-one-retry-then-fail, over mocked HTTP responses."""

    @respx.mock
    def test_invalid_then_valid_response_succeeds_with_two_calls(self):
        route = respx.post(ANTHROPIC_MESSAGES_URL).mock(
            side_effect=[
                httpx.Response(200, json=_message_json(stage_payload(findings=[issue_finding(severity=None)]))),
                httpx.Response(200, json=_message_json(stage_payload())),
            ]
        )
        provider = AnthropicProvider(api_key="test-key-not-real", max_retries=0)
        result = _run_stage(provider)
        assert route.call_count == 2
        assert result.findings[0].severity is not None

    @respx.mock
    def test_invalid_twice_fails_stage(self):
        bad = _message_json(stage_payload(findings=[issue_finding(severity=None)]))
        route = respx.post(ANTHROPIC_MESSAGES_URL).mock(
            side_effect=[httpx.Response(200, json=bad), httpx.Response(200, json=bad)]
        )
        provider = AnthropicProvider(api_key="test-key-not-real", max_retries=0)
        with pytest.raises(StageValidationError, match="after one retry"):
            _run_stage(provider)
        assert route.call_count == 2

    @respx.mock
    def test_auth_error_raises_provider_auth_error_without_key_leak(self):
        respx.post(ANTHROPIC_MESSAGES_URL).mock(
            return_value=httpx.Response(
                401,
                json={"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}},
            )
        )
        provider = AnthropicProvider(api_key="sk-super-secret-value", max_retries=0)
        with pytest.raises(ProviderAuthError) as excinfo:
            _run_stage(provider)
        assert "sk-super-secret-value" not in str(excinfo.value)

    @respx.mock
    def test_wrong_stage_attribution_triggers_retry(self):
        route = respx.post(ANTHROPIC_MESSAGES_URL).mock(
            side_effect=[
                httpx.Response(200, json=_message_json(stage_payload(stage_name="concurrency_scalability"))),
                httpx.Response(200, json=_message_json(stage_payload())),
            ]
        )
        provider = AnthropicProvider(api_key="test-key-not-real", max_retries=0)
        result = _run_stage(provider)
        assert route.call_count == 2
        assert result.stage_name is StageName.ALGORITHMIC_COMPLEXITY

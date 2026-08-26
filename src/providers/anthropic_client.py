"""Anthropic API provider: per-stage model selection, forced tool-use with the
`report_stage_findings` schema, prompt caching of the shared context, retry/timeout
handling, and schema-validation-with-one-retry-then-fail semantics (contracts/
stage-output-schema.md).

The API key is read from the environment by the caller and passed in — it is never
accepted via CLI flag, never logged, and never included in raised error messages.
"""

from __future__ import annotations

import difflib
import logging
import re
from collections.abc import Callable
from typing import Any

import anthropic
from pydantic import ValidationError

from src.models.stage import StageName, StageResult

logger = logging.getLogger("perf_ai.provider")

# Exact model IDs per research.md §2 — used verbatim, no date suffixes.
STAGE_MODELS: dict[StageName, str] = {
    StageName.STRUCTURAL_CONTEXT: "claude-haiku-4-5",
    StageName.ALGORITHMIC_COMPLEXITY: "claude-sonnet-5",
    StageName.RESOURCE_IO_EFFICIENCY: "claude-sonnet-5",
    StageName.CONCURRENCY_SCALABILITY: "claude-sonnet-5",
}

TOOL_NAME = "report_stage_findings"

# Mirrors contracts/stage-output-schema.md; cross-field rules that JSON Schema cannot
# express are enforced by the Pydantic models plus the checks below.
REPORT_STAGE_FINDINGS_TOOL: dict[str, Any] = {
    "name": TOOL_NAME,
    "description": "Report the findings this analysis stage produced for the given code scope.",
    "input_schema": {
        "type": "object",
        "required": ["stage_name", "findings"],
        "properties": {
            "stage_name": {
                "type": "string",
                "enum": [
                    "structural_context",
                    "algorithmic_complexity",
                    "resource_io_efficiency",
                    "concurrency_scalability",
                ],
            },
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["kind", "description", "location"],
                    "properties": {
                        "kind": {"type": "string", "enum": ["issue", "valuable_finding"]},
                        "description": {"type": "string", "minLength": 1},
                        "location": {
                            "type": "object",
                            "required": ["file_path"],
                            "properties": {
                                "file_path": {"type": "string", "minLength": 1},
                                "symbol": {"type": ["string", "null"]},
                                "line_start": {"type": ["integer", "null"]},
                                "line_end": {"type": ["integer", "null"]},
                            },
                        },
                        "severity": {
                            "type": ["string", "null"],
                            "enum": ["critical", "high", "medium", "low", None],
                            "description": (
                                "Required (non-null) when kind == issue; must be null when "
                                "kind == valuable_finding."
                            ),
                        },
                        "suggested_action": {
                            "type": ["string", "null"],
                            "description": (
                                "Required (non-null) when kind == issue; a concrete next step, "
                                "not a restatement of description."
                            ),
                        },
                    },
                },
            },
            "coverage_note": {
                "type": ["string", "null"],
                "description": (
                    "Set when this stage could not cover the full code scope within its "
                    "token/time budget; describes what was and was not covered."
                ),
            },
        },
    },
}


class ProviderError(Exception):
    """Base class for provider failures. Messages never contain the API key."""


class ProviderAuthError(ProviderError):
    """The provider rejected the API key (or it is missing)."""


class StageCallError(ProviderError):
    """A stage call failed at the transport/API level after SDK retries."""


class StageValidationError(ProviderError):
    """A stage response failed schema validation even after the one allowed retry."""


_WORD_RE = re.compile(r"[a-z0-9]+")


def _normalize(text: str) -> str:
    return " ".join(_WORD_RE.findall(text.lower()))


def is_near_identical(description: str, suggested_action: str) -> bool:
    """True when a suggested action merely restates the issue description (FR-006).

    Case-insensitive, whitespace/punctuation-normalized comparison plus a similarity
    ratio to catch trivial rephrasings.
    """
    a, b = _normalize(description), _normalize(suggested_action)
    if not a or not b:
        return True
    if a == b or a in b or b in a:
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.9


def payload_quality_problems(result: StageResult) -> list[str]:
    """Soft data-quality problems: violations of the concreteness rule (FR-006).

    These are not hard schema failures — the aggregator logs and rejects the derived
    action item rather than failing the stage (contracts/stage-output-schema.md).
    """
    problems: list[str] = []
    for i, finding in enumerate(result.findings):
        if finding.suggested_action and is_near_identical(
            finding.description, finding.suggested_action
        ):
            problems.append(
                f"findings[{i}]: suggested_action is a near-identical restatement of "
                f"description; it must be a concrete, distinct next step"
            )
    return problems


def validate_stage_payload(payload: Any, expected_stage: StageName) -> StageResult:
    """Validate one `report_stage_findings` payload against the contract.

    Raises `ValidationError` (schema/cross-field) or `StageValidationError` (wrong
    stage attribution) so the caller can drive the one-retry-then-fail loop.
    """
    result = StageResult.model_validate(payload)
    if result.stage_name is not expected_stage:
        raise StageValidationError(
            f"stage_name mismatch: expected '{expected_stage}', got '{result.stage_name}'"
        )
    return result


def _sanitize_api_error(exc: Exception) -> str:
    """API error text safe to surface: never includes credentials."""
    name = type(exc).__name__
    body = str(exc)
    if "sk-" in body or "api_key" in body.lower() or "x-api-key" in body.lower():
        return name
    return f"{name}: {body[:300]}"


class AnthropicProvider:
    """Thin wrapper around the Anthropic SDK implementing the stage-call contract."""

    def __init__(
        self,
        api_key: str,
        *,
        timeout_seconds: float = 300.0,
        max_retries: int = 2,
        client: anthropic.Anthropic | None = None,
    ) -> None:
        if not api_key:
            raise ProviderAuthError("ANTHROPIC_API_KEY is missing or empty")
        self._client = client or anthropic.Anthropic(
            api_key=api_key, timeout=timeout_seconds, max_retries=max_retries
        )

    def run_stage(
        self,
        *,
        stage_name: StageName,
        system_prompt: str,
        shared_context: str,
        stage_input: str,
        max_output_tokens: int = 8192,
        on_first_token: Callable[[], None] | None = None,
    ) -> StageResult:
        """Run one analysis stage call: forced tool-use, cached shared context, and
        schema validation with exactly one corrective retry (then fail).

        `on_first_token` (when given) switches to streaming and fires as soon as the
        provider starts responding — the orchestrator uses it to stagger the Sonnet
        fan-out so the shared prompt-cache entry is written before the sibling stages
        send the same prefix (Principle II).
        """
        model = STAGE_MODELS[stage_name]
        user_content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": shared_context,
                "cache_control": {"type": "ephemeral"},
            },
            {"type": "text", "text": stage_input},
        ]
        messages: list[dict[str, Any]] = [{"role": "user", "content": user_content}]

        payload = self._call_api(
            model=model,
            system_prompt=system_prompt,
            messages=messages,
            max_output_tokens=max_output_tokens,
            on_first_token=on_first_token,
        )

        problems: list[str]
        try:
            result = validate_stage_payload(payload, stage_name)
            problems = payload_quality_problems(result)
            if not problems:
                return result
        except (ValidationError, StageValidationError) as exc:
            result = None
            problems = [str(exc)]

        # One corrective retry: hand the invalid tool call back with the validation
        # errors and force a corrected tool call (contracts/stage-output-schema.md).
        logger.info("stage %s response failed validation; retrying once", stage_name)
        retry_messages = messages + [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "retry_validation",
                        "name": TOOL_NAME,
                        "input": payload if isinstance(payload, dict) else {},
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "retry_validation",
                        "is_error": True,
                        "content": (
                            "Your findings payload failed validation:\n- "
                            + "\n- ".join(problems)
                            + f"\nCall {TOOL_NAME} again with a corrected, complete payload "
                            f"for stage '{stage_name}'."
                        ),
                    }
                ],
            },
        ]
        retry_payload = self._call_api(
            model=model,
            system_prompt=system_prompt,
            messages=retry_messages,
            max_output_tokens=max_output_tokens,
            on_first_token=None,
        )
        try:
            result = validate_stage_payload(retry_payload, stage_name)
        except (ValidationError, StageValidationError) as exc:
            raise StageValidationError(
                f"stage '{stage_name}' response failed schema validation after one retry: {exc}"
            ) from None
        remaining = payload_quality_problems(result)
        if remaining:
            # Otherwise-valid payload with restatement-style actions: accepted here;
            # the aggregator soft-rejects those action items and logs the note.
            logger.warning(
                "stage %s: accepting payload with %d data-quality problem(s) after retry",
                stage_name,
                len(remaining),
            )
        return result

    # ------------------------------------------------------------------
    def _call_api(
        self,
        *,
        model: str,
        system_prompt: str,
        messages: list[dict[str, Any]],
        max_output_tokens: int,
        on_first_token: Callable[[], None] | None,
    ) -> Any:
        request: dict[str, Any] = {
            "model": model,
            "max_tokens": max_output_tokens,
            "system": system_prompt,
            "messages": messages,
            "tools": [REPORT_STAGE_FINDINGS_TOOL],
            "tool_choice": {"type": "tool", "name": TOOL_NAME},
        }
        try:
            if on_first_token is not None:
                with self._client.messages.stream(**request) as stream:
                    fired = False
                    for _event in stream:
                        if not fired:
                            on_first_token()
                            fired = True
                    message = stream.get_final_message()
            else:
                message = self._client.messages.create(**request)
        except anthropic.AuthenticationError:
            # Chain dropped deliberately: auth error bodies/headers may carry the key.
            raise ProviderAuthError(
                "the Anthropic API rejected the provided API key"
            ) from None
        except anthropic.APIError as exc:
            raise StageCallError(_sanitize_api_error(exc)) from None
        except Exception as exc:  # httpx timeouts etc.
            raise StageCallError(_sanitize_api_error(exc)) from None

        for block in message.content:
            if isinstance(block, anthropic.types.ToolUseBlock) and block.name == TOOL_NAME:
                return block.input
        raise StageCallError(
            f"provider response contained no '{TOOL_NAME}' tool call despite forced tool_choice"
        )

"""Contract tests (T007): stage-result file acceptance/rejection per data-model.md
"Stage Result File" and contracts/agent-support-cli.md.

Valid envelope `{"unit_id", "result"}` accepted; unparsable JSON, schema-invalid payload,
`unit_id` != filename stem, and `stage_name` != the unit's stage each rejected with a
human-readable reason."""

from __future__ import annotations

import json
from pathlib import Path

from src.agentrun.results import load_unit_results
from src.agentrun.workplan import build_work_plan
from src.lib.discovery import discover_files

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
ANTI_PATTERN_FIXTURE = FIXTURES_DIR / "anti_pattern_sample"

VALID_PAYLOAD = {
    "stage_name": "structural_context",
    "findings": [
        {
            "kind": "valuable_finding",
            "description": "Two small modules; no shared state.",
            "location": {"file_path": "orders.py"},
        }
    ],
    "coverage_note": None,
}


def _plan():
    files = discover_files(ANTI_PATTERN_FIXTURE)
    return build_work_plan(ANTI_PATTERN_FIXTURE, files, max_parallel=1)


def _outcome_for(outcomes, unit_id):
    return next(o for o in outcomes if o.unit.unit_id == unit_id)


def _write(results_dir: Path, name: str, content: str) -> None:
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / name).write_text(content, encoding="utf-8")


class TestAcceptance:
    def test_valid_envelope_is_accepted(self, tmp_path: Path):
        _write(
            tmp_path,
            "structural_context--all.json",
            json.dumps({"unit_id": "structural_context--all", "result": VALID_PAYLOAD}),
        )
        outcome = _outcome_for(
            load_unit_results(tmp_path, _plan()), "structural_context--all"
        )
        assert outcome.ok
        assert outcome.failure_reason is None
        assert len(outcome.result.findings) == 1


class TestRejection:
    def test_unparsable_json_rejected_with_reason(self, tmp_path: Path):
        _write(tmp_path, "structural_context--all.json", "{not json at all")
        outcome = _outcome_for(
            load_unit_results(tmp_path, _plan()), "structural_context--all"
        )
        assert not outcome.ok
        assert outcome.result is None
        assert "json" in outcome.failure_reason.lower()

    def test_schema_invalid_payload_rejected_with_reason(self, tmp_path: Path):
        # An issue without severity/suggested_action violates the StageResult schema.
        bad = {
            "stage_name": "structural_context",
            "findings": [
                {
                    "kind": "issue",
                    "description": "an issue with no severity or action",
                    "location": {"file_path": "orders.py"},
                }
            ],
        }
        _write(
            tmp_path,
            "structural_context--all.json",
            json.dumps({"unit_id": "structural_context--all", "result": bad}),
        )
        outcome = _outcome_for(
            load_unit_results(tmp_path, _plan()), "structural_context--all"
        )
        assert not outcome.ok
        assert outcome.failure_reason
        assert "Traceback" not in outcome.failure_reason

    def test_unit_id_mismatch_rejected_with_reason(self, tmp_path: Path):
        _write(
            tmp_path,
            "structural_context--all.json",
            json.dumps({"unit_id": "something-else--p9", "result": VALID_PAYLOAD}),
        )
        outcome = _outcome_for(
            load_unit_results(tmp_path, _plan()), "structural_context--all"
        )
        assert not outcome.ok
        assert "unit_id" in outcome.failure_reason

    def test_wrong_stage_rejected_with_reason(self, tmp_path: Path):
        # Payload claims structural_context but the unit is algorithmic_complexity--p1.
        _write(
            tmp_path,
            "algorithmic_complexity--p1.json",
            json.dumps({"unit_id": "algorithmic_complexity--p1", "result": VALID_PAYLOAD}),
        )
        outcome = _outcome_for(
            load_unit_results(tmp_path, _plan()), "algorithmic_complexity--p1"
        )
        assert not outcome.ok
        assert "stage" in outcome.failure_reason.lower()

    def test_missing_file_rejected_with_reason(self, tmp_path: Path):
        tmp_path.mkdir(exist_ok=True)
        outcome = _outcome_for(
            load_unit_results(tmp_path, _plan()), "resource_io_efficiency--p1"
        )
        assert not outcome.ok
        assert outcome.failure_reason

"""The stage-4h verification overlay: file loading tolerance, verdict matching, and
refuted-issue removal — plus the end-to-end render behavior with and without a
usable verification.json (strictly additive: absent/unusable never blocks a render)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import src.cli.main as cli_main
from src.agentrun.verification import (
    VerdictKind,
    VerificationFile,
    apply_verification,
    load_verification,
)
from src.models.finding import Finding, FindingKind, LocationRef, Severity
from src.models.stage import AnalysisStage, StageName
from typer.testing import CliRunner

from tests.support.helpers import ANTI_PATTERN_FIXTURE, FIXTURES_DIR

PARTIAL_RESULTS = FIXTURES_DIR / "agent_results_partial"

REFUTED_DESCRIPTION = (
    "find_matching_orders compares every order against every other order in a "
    "nested loop, giving O(n^2) growth as the order list grows."
)

runner = CliRunner()


def _finding(
    stage: StageName,
    description: str,
    *,
    kind: FindingKind = FindingKind.ISSUE,
    file_path: str = "orders.py",
    index: int = 1,
) -> Finding:
    return Finding(
        kind=kind,
        description=description,
        location=LocationRef(file_path=file_path, line_start=5),
        severity=Severity.HIGH if kind is FindingKind.ISSUE else None,
        suggested_action="Do the concrete fix." if kind is FindingKind.ISSUE else None,
        finding_id=f"{stage.value}-{index:03d}",
        originating_stage=stage,
    )


def _verdict(stage: StageName, description: str, verdict: str, file_path: str = "orders.py"):
    return {
        "stage_name": stage.value,
        "location": {"file_path": file_path, "line_start": 5},
        "description": description,
        "verdict": verdict,
        "reasoning": "checked the surrounding code",
    }


class TestLoadVerification:
    def test_missing_file_is_no_verification_and_no_warning(self, tmp_path: Path):
        parsed, warning = load_verification(tmp_path / "verification.json")
        assert parsed is None and warning is None

    def test_unparsable_file_warns_and_is_ignored(self, tmp_path: Path):
        path = tmp_path / "verification.json"
        path.write_text("{broken", encoding="utf-8")
        parsed, warning = load_verification(path)
        assert parsed is None
        assert warning is not None and "verification" in warning

    def test_schema_invalid_file_warns_and_is_ignored(self, tmp_path: Path):
        path = tmp_path / "verification.json"
        path.write_text(json.dumps({"verdicts": [{"verdict": "maybe"}]}), encoding="utf-8")
        parsed, warning = load_verification(path)
        assert parsed is None and warning is not None

    def test_valid_file_parses(self, tmp_path: Path):
        path = tmp_path / "verification.json"
        path.write_text(
            json.dumps(
                {"verdicts": [_verdict(StageName.ALGORITHMIC_COMPLEXITY, "x", "refuted")]}
            ),
            encoding="utf-8",
        )
        parsed, warning = load_verification(path)
        assert warning is None
        assert parsed is not None and parsed.verdicts[0].verdict is VerdictKind.REFUTED


class TestApplyVerification:
    def test_refuted_issue_is_removed_and_confirmed_kept(self):
        stage = AnalysisStage(
            name=StageName.ALGORITHMIC_COMPLEXITY,
            findings=[
                _finding(StageName.ALGORITHMIC_COMPLEXITY, "bad quadratic scan", index=1),
                _finding(StageName.ALGORITHMIC_COMPLEXITY, "real nested loop", index=2),
            ],
        )
        verification = VerificationFile.model_validate(
            {
                "verdicts": [
                    _verdict(StageName.ALGORITHMIC_COMPLEXITY, "bad quadratic scan", "refuted"),
                    _verdict(StageName.ALGORITHMIC_COMPLEXITY, "real nested loop", "confirmed"),
                ]
            }
        )
        outcome = apply_verification([stage], verification)
        assert [f.description for f in stage.findings] == ["real nested loop"]
        assert outcome.confirmed == 1
        assert outcome.refuted_removed == 1
        assert outcome.unmatched == 0
        assert "1 confirmed" in outcome.note and "1 refuted" in outcome.note

    def test_verdict_for_another_stage_or_file_does_not_match(self):
        stage = AnalysisStage(
            name=StageName.ALGORITHMIC_COMPLEXITY,
            findings=[_finding(StageName.ALGORITHMIC_COMPLEXITY, "quadratic scan")],
        )
        verification = VerificationFile.model_validate(
            {
                "verdicts": [
                    _verdict(StageName.MEMORY_ALLOCATION, "quadratic scan", "refuted"),
                    _verdict(
                        StageName.ALGORITHMIC_COMPLEXITY,
                        "quadratic scan",
                        "refuted",
                        file_path="other.py",
                    ),
                ]
            }
        )
        outcome = apply_verification([stage], verification)
        assert len(stage.findings) == 1
        assert outcome.refuted_removed == 0
        assert outcome.unmatched == 2
        assert "matched no current finding" in outcome.note

    def test_valuable_findings_are_never_removed(self):
        stage = AnalysisStage(
            name=StageName.ALGORITHMIC_COMPLEXITY,
            findings=[
                _finding(
                    StageName.ALGORITHMIC_COMPLEXITY,
                    "nice memoization",
                    kind=FindingKind.VALUABLE_FINDING,
                )
            ],
        )
        verification = VerificationFile.model_validate(
            {"verdicts": [_verdict(StageName.ALGORITHMIC_COMPLEXITY, "nice memoization", "refuted")]}
        )
        outcome = apply_verification([stage], verification)
        assert len(stage.findings) == 1
        assert outcome.refuted_removed == 0


def _invoke_render(monkeypatch, results_dir: Path, output_dir: Path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return runner.invoke(
        cli_main.app,
        [
            "agent",
            "render",
            "--results-dir",
            str(results_dir),
            "--scope",
            str(ANTI_PATTERN_FIXTURE),
            "--output-dir",
            str(output_dir),
        ],
    )


class TestRenderWithVerification:
    def test_refuted_issue_is_dropped_and_noted(self, monkeypatch, tmp_path: Path):
        results = tmp_path / "results"
        shutil.copytree(PARTIAL_RESULTS, results)
        (results / "verification.json").write_text(
            json.dumps(
                {
                    "verdicts": [
                        {
                            "stage_name": "algorithmic_complexity",
                            "location": {"file_path": "orders.py", "line_start": 12},
                            "description": REFUTED_DESCRIPTION,
                            "verdict": "refuted",
                            "reasoning": "the loop is bounded by a constant batch size",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        out = tmp_path / "out"
        result = _invoke_render(monkeypatch, results, out)
        assert result.exit_code == 0, result.output
        md = (out / "perf-report.md").read_text(encoding="utf-8")
        assert "find_matching_orders" not in md
        assert "Adversarial verification" in md
        assert "1 refuted" in md

    def test_unusable_verification_file_never_blocks_the_render(
        self, monkeypatch, tmp_path: Path
    ):
        results = tmp_path / "results"
        shutil.copytree(PARTIAL_RESULTS, results)
        (results / "verification.json").write_text("{broken", encoding="utf-8")
        out = tmp_path / "out"
        result = _invoke_render(monkeypatch, results, out)
        assert result.exit_code == 0, result.output
        md = (out / "perf-report.md").read_text(encoding="utf-8")
        # The overlay is skipped: the finding stays and no verification note appears.
        assert "find_matching_orders" in md
        assert "Adversarial verification" not in md

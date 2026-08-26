"""Optional adversarial-verification overlay for `agent render` (stage 4h).

The verify skill (/perf-exec-verify) re-examines the critical/high issues found by
the execution stages and writes `verification.json` next to the unit result files.
When that file is present, render drops the refuted issues from the report and
records the verification outcome as a limitations note; when it is absent, or
unusable, rendering proceeds exactly as before — verification is strictly additive.

Verdicts are matched to findings by (stage, file_path, description): the verify
skill copies each finding verbatim, so an exact description match is the stable key
(line numbers may legitimately differ between duplicates that dedupe collapsed)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from src.models.finding import FindingKind
from src.models.stage import AnalysisStage, StageName

VERIFICATION_FILENAME = "verification.json"


class VerdictKind(StrEnum):
    CONFIRMED = "confirmed"
    REFUTED = "refuted"


class VerdictLocation(BaseModel):
    file_path: str = Field(min_length=1)
    line_start: int | None = None


class Verdict(BaseModel):
    """One adversarially checked finding, copied verbatim from a unit result file."""

    stage_name: StageName
    location: VerdictLocation
    description: str = Field(min_length=1)
    verdict: VerdictKind
    reasoning: str | None = None


class VerificationFile(BaseModel):
    verdicts: list[Verdict] = Field(default_factory=list)


@dataclass
class VerificationOutcome:
    confirmed: int
    refuted_removed: int
    unmatched: int

    @property
    def note(self) -> str:
        reviewed = self.confirmed + self.refuted_removed + self.unmatched
        text = (
            f"Adversarial verification (stage 4h) reviewed {reviewed} "
            f"high-severity finding(s): {self.confirmed} confirmed, "
            f"{self.refuted_removed} refuted and removed from this report "
            "(verdicts: 04h-verify.md)."
        )
        if self.unmatched:
            text += (
                f" {self.unmatched} verdict(s) matched no current finding — the "
                "verification may predate a re-run of an execution stage."
            )
        return text


def load_verification(path: Path) -> tuple[VerificationFile | None, str | None]:
    """Load `verification.json` if present: (parsed, None), (None, warning), or (None, None)."""
    if not path.is_file():
        return None, None
    try:
        parsed = VerificationFile.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, ValidationError) as exc:
        first_line = str(exc).splitlines()[0]
        return None, (
            f"{path.name} is not a usable verification file ({first_line}); "
            "rendering without the verification overlay"
        )
    return parsed, None


def _key(stage: StageName, file_path: str, description: str) -> tuple[str, str, str]:
    return (stage.value, file_path, description.strip())


def apply_verification(
    stages: list[AnalysisStage], verification: VerificationFile
) -> VerificationOutcome:
    """Drop refuted issues from `stages` in place and tally the verdict outcomes."""
    verdict_by_key = {
        _key(v.stage_name, v.location.file_path, v.description): v
        for v in verification.verdicts
    }
    matched_keys: set[tuple[str, str, str]] = set()
    confirmed = 0
    refuted_removed = 0
    for stage in stages:
        kept = []
        for finding in stage.findings:
            verdict = verdict_by_key.get(
                _key(stage.name, finding.location.file_path, finding.description)
            )
            if verdict is None or finding.kind is not FindingKind.ISSUE:
                kept.append(finding)
                continue
            matched_keys.add(
                _key(stage.name, finding.location.file_path, finding.description)
            )
            if verdict.verdict is VerdictKind.REFUTED:
                refuted_removed += 1
            else:
                confirmed += 1
                kept.append(finding)
        stage.findings = kept
    return VerificationOutcome(
        confirmed=confirmed,
        refuted_removed=refuted_removed,
        unmatched=len(verdict_by_key) - len(matched_keys),
    )

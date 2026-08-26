"""Unit tests (T022): duplicate-finding merge in src/agentrun/dedupe.py.

Merge key `(kind, location.file_path, location.line_start, normalized(symbol))` applied
per stage; survivor by highest severity rank, then longest `suggested_action`, then
first in input (sorted-filename union) order; survivor kept verbatim; cross-stage
findings at the same location are NOT merged (data-model.md "Dedup rule")."""

from __future__ import annotations

from src.agentrun.dedupe import dedupe_findings
from src.models.finding import FindingKind, LocationRef, Severity, StageFinding


def _issue(
    description: str,
    *,
    file_path: str = "orders.py",
    line_start: int | None = 12,
    symbol: str | None = "find_matching_orders",
    severity: Severity = Severity.MEDIUM,
    suggested_action: str = "Index orders by customer_id before the loop.",
) -> StageFinding:
    return StageFinding(
        kind=FindingKind.ISSUE,
        description=description,
        location=LocationRef(file_path=file_path, symbol=symbol, line_start=line_start),
        severity=severity,
        suggested_action=suggested_action,
    )


class TestMergeKey:
    def test_same_location_same_kind_merges(self):
        merged = dedupe_findings([_issue("first"), _issue("second")])
        assert len(merged) == 1

    def test_different_line_start_not_merged(self):
        merged = dedupe_findings([_issue("a", line_start=12), _issue("b", line_start=30)])
        assert len(merged) == 2

    def test_different_file_not_merged(self):
        merged = dedupe_findings(
            [_issue("a", file_path="orders.py"), _issue("b", file_path="pricing.py")]
        )
        assert len(merged) == 2

    def test_symbol_is_normalized_before_comparison(self):
        merged = dedupe_findings(
            [_issue("a", symbol="Find_Matching_Orders"), _issue("b", symbol=" find_matching_orders ")]
        )
        assert len(merged) == 1

    def test_different_kind_not_merged(self):
        valuable = StageFinding(
            kind=FindingKind.VALUABLE_FINDING,
            description="the loop is intentionally bounded",
            location=LocationRef(
                file_path="orders.py", symbol="find_matching_orders", line_start=12
            ),
        )
        merged = dedupe_findings([_issue("a"), valuable])
        assert len(merged) == 2


class TestSurvivorSelection:
    def test_highest_severity_wins_and_is_kept_verbatim(self):
        low = _issue("the low one", severity=Severity.LOW)
        high = _issue("the high one", severity=Severity.HIGH)
        merged = dedupe_findings([low, high])
        assert len(merged) == 1
        assert merged[0].description == "the high one"
        assert merged[0].severity is Severity.HIGH
        # Survivor is the original object's content, never concatenated or rewritten.
        assert merged[0] == high

    def test_severity_tie_longest_suggested_action_wins(self):
        short = _issue("short action", suggested_action="Cache it.")
        long = _issue(
            "long action",
            suggested_action="Cache the computed table per tier and reuse it across items.",
        )
        merged = dedupe_findings([short, long])
        assert len(merged) == 1
        assert merged[0].description == "long action"

    def test_full_tie_first_in_input_order_wins(self):
        first = _issue("first in input order")
        second = _issue("second in input order")
        merged = dedupe_findings([first, second])
        assert len(merged) == 1
        assert merged[0].description == "first in input order"

    def test_output_preserves_first_seen_order(self):
        a = _issue("a", line_start=1, symbol="a")
        b = _issue("b", line_start=2, symbol="b")
        dup_a = _issue("a-dup", line_start=1, symbol="a")
        merged = dedupe_findings([a, b, dup_a])
        assert [f.location.line_start for f in merged] == [1, 2]


class TestCrossStageNotMerged:
    def test_same_location_across_stage_unions_survives_in_each(self):
        # The merge is applied per stage to that stage's union; the same location
        # reported by two different stages therefore survives in both.
        algo_union = [_issue("algorithmic view of the hotspot")]
        io_union = [_issue("io view of the hotspot")]
        assert len(dedupe_findings(algo_union)) == 1
        assert len(dedupe_findings(io_union)) == 1

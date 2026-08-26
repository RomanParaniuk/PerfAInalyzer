"""Unit tests for relevance ranking, token-budget chunking, and context assembly (T015)."""

from pathlib import Path

from src.lib.discovery import discover_files
from src.models.stage import StageName
from src.pipeline.context import (
    DEFAULT_STAGE_INPUT_BUDGETS,
    HAIKU_CONTEXT_WINDOW_TOKENS,
    assemble_context,
    build_shared_context,
    build_structural_index,
    estimate_tokens,
    loop_nesting_depth,
    rank_chunks,
)

NESTED_LOOP_SOURCE = '''\
def find_duplicate_orders(orders):
    duplicates = []
    for order in orders:
        for other in orders:
            if order.id == other.id and order is not other:
                duplicates.append(order)
    return duplicates
'''

IO_SOURCE = '''\
import requests


def sync_orders(order_ids):
    results = []
    for order_id in order_ids:
        response = requests.get(f"https://api.example.com/orders/{order_id}")
        results.append(response.json())
    return results
'''

CONCURRENCY_SOURCE = '''\
import threading

lock = threading.Lock()


def record(event, log):
    with lock:
        log.append(event)
'''

PLAIN_SOURCE = '''\
def add(a, b):
    return a + b
'''


def build_index(tmp_path: Path, sources: dict[str, str]):
    for name, content in sources.items():
        (tmp_path / name).write_text(content, encoding="utf-8")
    files = discover_files(tmp_path)
    return build_structural_index(tmp_path, files)


class TestLoopNestingDepth:
    def test_nested_loops_detected(self):
        assert loop_nesting_depth(NESTED_LOOP_SOURCE) == 2

    def test_flat_code_has_zero_depth(self):
        assert loop_nesting_depth(PLAIN_SOURCE) == 0


class TestRanking:
    def test_complexity_stage_ranks_nested_loops_first(self, tmp_path: Path):
        index = build_index(
            tmp_path, {"hot.py": NESTED_LOOP_SOURCE, "plain.py": PLAIN_SOURCE}
        )
        ranked = rank_chunks(index, StageName.ALGORITHMIC_COMPLEXITY)
        top_score, top_chunk = ranked[0]
        assert top_chunk.file.rel_path == "hot.py"
        assert top_score > 0

    def test_resource_stage_ranks_io_first(self, tmp_path: Path):
        index = build_index(tmp_path, {"io.py": IO_SOURCE, "plain.py": PLAIN_SOURCE})
        ranked = rank_chunks(index, StageName.RESOURCE_IO_EFFICIENCY)
        assert ranked[0][1].file.rel_path == "io.py"

    def test_concurrency_stage_ranks_thread_primitives_first(self, tmp_path: Path):
        index = build_index(
            tmp_path, {"locks.py": CONCURRENCY_SOURCE, "plain.py": PLAIN_SOURCE}
        )
        ranked = rank_chunks(index, StageName.CONCURRENCY_SCALABILITY)
        assert ranked[0][1].file.rel_path == "locks.py"

    def test_structural_stage_scores_every_chunk(self, tmp_path: Path):
        index = build_index(tmp_path, {"plain.py": PLAIN_SOURCE, "main.py": PLAIN_SOURCE})
        ranked = rank_chunks(index, StageName.STRUCTURAL_CONTEXT)
        assert all(score > 0 for score, _chunk in ranked)
        # Entry-point-looking files rank above ordinary ones.
        assert ranked[0][1].file.rel_path == "main.py"


class TestContextAssembly:
    def test_shared_context_is_deterministic_and_reused(self, tmp_path: Path):
        index = build_index(tmp_path, {"hot.py": NESTED_LOOP_SOURCE, "io.py": IO_SOURCE})
        shared = build_shared_context(index, "The repo is a two-module order pipeline.")
        bundles = [
            assemble_context(index, stage, shared_context=shared)
            for stage in (
                StageName.ALGORITHMIC_COMPLEXITY,
                StageName.RESOURCE_IO_EFFICIENCY,
                StageName.CONCURRENCY_SCALABILITY,
            )
        ]
        # Byte-identical prefix across Stages 2-4 is what makes the prompt cache hit.
        assert len({b.shared_context for b in bundles}) == 1
        assert "Architectural summary" in bundles[0].shared_context

    def test_budget_truncation_produces_coverage_note(self, tmp_path: Path):
        sources = {
            f"mod_{i}.py": NESTED_LOOP_SOURCE.replace("find_duplicate_orders", f"find_dup_{i}")
            for i in range(30)
        }
        index = build_index(tmp_path, sources)
        shared = build_shared_context(index)
        bundle = assemble_context(
            index,
            StageName.ALGORITHMIC_COMPLEXITY,
            shared_context=shared,
            token_budget=estimate_tokens(shared) + 200,
        )
        assert bundle.coverage_note is not None
        assert "of" in bundle.coverage_note and "included" in bundle.coverage_note

    def test_no_coverage_note_when_everything_fits(self, tmp_path: Path):
        index = build_index(tmp_path, {"hot.py": NESTED_LOOP_SOURCE})
        shared = build_shared_context(index)
        bundle = assemble_context(index, StageName.ALGORITHMIC_COMPLEXITY, shared_context=shared)
        assert bundle.coverage_note is None
        assert "find_duplicate_orders" in bundle.stage_excerpts

    def test_structural_budget_fits_haiku_context_window(self, tmp_path: Path):
        assert DEFAULT_STAGE_INPUT_BUDGETS[StageName.STRUCTURAL_CONTEXT] < HAIKU_CONTEXT_WINDOW_TOKENS
        index = build_index(tmp_path, {"hot.py": NESTED_LOOP_SOURCE})
        shared = build_shared_context(index)
        bundle = assemble_context(index, StageName.STRUCTURAL_CONTEXT, shared_context=shared)
        total = estimate_tokens(bundle.shared_context) + estimate_tokens(bundle.stage_excerpts)
        assert total < HAIKU_CONTEXT_WINDOW_TOKENS

    def test_excerpts_carry_location_headers(self, tmp_path: Path):
        index = build_index(tmp_path, {"hot.py": NESTED_LOOP_SOURCE})
        shared = build_shared_context(index)
        bundle = assemble_context(index, StageName.ALGORITHMIC_COMPLEXITY, shared_context=shared)
        assert "### hot.py:" in bundle.stage_excerpts

    def test_code_map_is_capped_for_large_repositories(self, tmp_path: Path):
        # Many files: uncapped, the map alone would outgrow the stage budgets.
        sources = {
            f"pkg_{i:04d}.py": NESTED_LOOP_SOURCE.replace(
                "find_duplicate_orders", f"find_dup_{i}"
            )
            for i in range(1200)
        }
        index = build_index(tmp_path, sources)
        shared = build_shared_context(index)
        map_tokens = estimate_tokens(shared)
        smallest_budget = min(DEFAULT_STAGE_INPUT_BUDGETS.values())
        # The capped map leaves at least half of every stage budget for excerpts...
        assert map_tokens <= smallest_budget // 2 + 100
        # ...and the truncation is explicit, never silent.
        assert "map truncated to fit the token budget" in shared
        # Stage assembly therefore still has room for actual code excerpts.
        bundle = assemble_context(index, StageName.ALGORITHMIC_COMPLEXITY, shared_context=shared)
        assert "### pkg_" in bundle.stage_excerpts

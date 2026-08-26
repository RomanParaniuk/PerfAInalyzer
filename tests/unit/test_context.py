"""Unit tests for the tree-sitter structural index builder, including the
fallback-chunker path (T013)."""

from pathlib import Path

from src.lib.discovery import SourceFile, discover_files
from src.pipeline.context import (
    build_structural_index,
    fallback_chunk_file,
    index_file,
)

PYTHON_SOURCE = '''\
import os
from collections import defaultdict


def load_orders(path):
    with open(path) as fh:
        return fh.read().splitlines()


class OrderBook:
    def add(self, order):
        self.orders.append(order)

    def find_duplicates(self):
        seen = []
        for order in self.orders:
            if order in seen:
                yield order
            seen.append(order)
'''


def write_source(tmp_path: Path, name: str, content: str) -> SourceFile:
    target = tmp_path / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    files = discover_files(tmp_path)
    return next(f for f in files if f.rel_path == name)


class TestTreeSitterIndex:
    def test_python_definitions_and_imports_indexed(self, tmp_path: Path):
        source = write_source(tmp_path, "orders.py", PYTHON_SOURCE)
        index = index_file(source)

        assert not index.best_effort
        assert not index.has_syntax_errors
        symbols = {c.symbol for c in index.chunks}
        assert "load_orders" in symbols
        assert "OrderBook" in symbols
        assert any("import os" in imp for imp in index.imports)
        kinds = {c.symbol: c.kind for c in index.chunks}
        assert kinds["OrderBook"] == "class"
        assert kinds["load_orders"] == "function"

    def test_chunks_are_disjoint_top_level(self, tmp_path: Path):
        source = write_source(tmp_path, "orders.py", PYTHON_SOURCE)
        index = index_file(source)
        # Methods inside OrderBook belong to the class chunk, not separate chunks.
        assert {c.symbol for c in index.chunks} == {"load_orders", "OrderBook"}

    def test_line_ranges_are_one_indexed_and_ordered(self, tmp_path: Path):
        source = write_source(tmp_path, "orders.py", PYTHON_SOURCE)
        for chunk in index_file(source).chunks:
            assert 1 <= chunk.line_start <= chunk.line_end

    def test_syntax_error_file_flagged_but_still_indexed(self, tmp_path: Path):
        source = write_source(tmp_path, "broken.py", "def broken(:\n    pass\n\ndef ok():\n    return 1\n")
        index = index_file(source)
        assert index.has_syntax_errors
        assert index.chunks  # partial parse still yields chunks

    def test_script_file_without_definitions_gets_block_chunks(self, tmp_path: Path):
        source = write_source(tmp_path, "script.py", "x = 1\ny = 2\nprint(x + y)\n")
        index = index_file(source)
        assert index.chunks
        assert all(c.kind == "block" for c in index.chunks)


class TestFallbackChunker:
    def _fake_file(self, tmp_path: Path, name: str, content: str) -> SourceFile:
        target = tmp_path / name
        target.write_text(content, encoding="utf-8")
        # A language name no grammar pack provides — forces the fallback path.
        return SourceFile(path=target, rel_path=name, language="mysterylang", size_bytes=len(content))

    def test_unknown_language_uses_fallback_chunker(self, tmp_path: Path):
        content = "\n".join(f"line{i} = {i}" for i in range(300))
        source = self._fake_file(tmp_path, "weird.xyz", content)
        index = index_file(source)
        assert index.best_effort
        assert index.chunks
        assert all(c.best_effort for c in index.chunks)

    def test_fallback_chunks_cover_all_lines_without_overlap(self, tmp_path: Path):
        content = "\n".join(f"line{i} = {i}" for i in range(300))
        source = self._fake_file(tmp_path, "weird.xyz", content)
        chunks = fallback_chunk_file(source, content)
        covered: list[int] = []
        for chunk in chunks:
            covered.extend(range(chunk.line_start, chunk.line_end + 1))
        assert covered == list(range(1, 301))

    def test_fallback_respects_max_chunk_size(self, tmp_path: Path):
        content = "\n".join("    indented = True" for _ in range(500))
        source = self._fake_file(tmp_path, "big.xyz", content)
        for chunk in fallback_chunk_file(source, content):
            assert chunk.line_end - chunk.line_start + 1 <= 150

    def test_empty_file_yields_no_chunks(self, tmp_path: Path):
        source = self._fake_file(tmp_path, "empty.xyz", "")
        assert fallback_chunk_file(source, "") == []


class TestStructuralIndex:
    def test_code_map_lists_files_symbols_and_flags(self, tmp_path: Path):
        write_source(tmp_path, "orders.py", PYTHON_SOURCE)
        (tmp_path / "strange.xyz").write_text("alpha\nbeta\n", encoding="utf-8")
        files = discover_files(tmp_path)
        files.append(
            SourceFile(
                path=tmp_path / "strange.xyz",
                rel_path="strange.xyz",
                language="mysterylang",
                size_bytes=11,
            )
        )
        index = build_structural_index(tmp_path, files)
        code_map = index.code_map_text()

        assert "orders.py (python)" in code_map
        assert "class OrderBook" in code_map
        assert "strange.xyz (mysterylang)" in code_map
        assert "best-effort" in code_map
        assert index.best_effort_files() == ["strange.xyz"]

    def test_multi_language_index(self, tmp_path: Path):
        write_source(tmp_path, "app.py", "def entry():\n    return 1\n")
        write_source(tmp_path, "web.js", "function render() {\n  return 1;\n}\n")
        files = discover_files(tmp_path)
        index = build_structural_index(tmp_path, files)
        symbols = {c.symbol for c in index.all_chunks()}
        assert {"entry", "render"} <= symbols

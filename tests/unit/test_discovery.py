"""Unit tests for language detection and file discovery (T011)."""

from pathlib import Path

from src.lib.discovery import MAX_FILE_BYTES, SourceFile, detect_languages, discover_files


def build_tree(root: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def rel_paths(found: list[SourceFile]) -> set[str]:
    return {f.rel_path for f in found}


class TestDiscovery:
    def test_detects_languages_by_extension(self, tmp_path: Path):
        build_tree(tmp_path, {"app.py": "x = 1\n", "web/index.js": "let x = 1;\n", "notes.txt": "hi"})
        found = discover_files(tmp_path)
        assert rel_paths(found) == {"app.py", "web/index.js"}
        by_rel = {f.rel_path: f.language for f in found}
        assert by_rel == {"app.py": "python", "web/index.js": "javascript"}

    def test_default_excludes_vcs_and_dependency_dirs(self, tmp_path: Path):
        build_tree(
            tmp_path,
            {
                "app.py": "x = 1\n",
                ".git/hooks/sample.py": "x = 1\n",
                "node_modules/lib/index.js": "x\n",
                "venv/lib/site.py": "x\n",
                "__pycache__/app.py": "x\n",
            },
        )
        assert rel_paths(discover_files(tmp_path)) == {"app.py"}

    def test_include_globs_restrict_scope(self, tmp_path: Path):
        build_tree(tmp_path, {"a.py": "1\n", "b.js": "1\n", "pkg/c.py": "1\n"})
        found = discover_files(tmp_path, include=["*.py"])
        assert rel_paths(found) == {"a.py", "pkg/c.py"}

    def test_exclude_globs_remove_matches(self, tmp_path: Path):
        build_tree(tmp_path, {"a.py": "1\n", "generated/g.py": "1\n", "b_test.py": "1\n"})
        found = discover_files(tmp_path, exclude=["generated/*", "*_test.py"])
        assert rel_paths(found) == {"a.py"}

    def test_exclude_directory_name_prunes_subtree(self, tmp_path: Path):
        build_tree(tmp_path, {"a.py": "1\n", "gen/deep/nested.py": "1\n"})
        found = discover_files(tmp_path, exclude=["gen"])
        assert rel_paths(found) == {"a.py"}

    def test_single_file_root(self, tmp_path: Path):
        build_tree(tmp_path, {"only.py": "x = 1\n"})
        found = discover_files(tmp_path / "only.py")
        assert len(found) == 1
        assert found[0].language == "python"

    def test_single_file_root_unrecognized_language(self, tmp_path: Path):
        build_tree(tmp_path, {"README.txt": "hello"})
        assert discover_files(tmp_path / "README.txt") == []

    def test_oversized_files_skipped(self, tmp_path: Path):
        build_tree(tmp_path, {"big.py": "x" * (MAX_FILE_BYTES + 1), "small.py": "x = 1\n"})
        assert rel_paths(discover_files(tmp_path)) == {"small.py"}


class TestDetectLanguages:
    def test_sorted_unique_languages(self, tmp_path: Path):
        build_tree(
            tmp_path,
            {"a.py": "1\n", "b.py": "1\n", "c.ts": "1\n", "d.go": "package main\n"},
        )
        assert detect_languages(discover_files(tmp_path)) == ["go", "python", "typescript"]

    def test_empty_scope_has_no_languages(self, tmp_path: Path):
        assert detect_languages(discover_files(tmp_path)) == []

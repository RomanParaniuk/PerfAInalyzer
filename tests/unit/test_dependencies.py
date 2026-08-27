"""The dependency-footprint stage's local half: manifest discovery, import-target
extraction across language syntaxes, the usage tally, and stage-input assembly.

The invariant under test throughout: dependency *source* is never read — only what the
project declares (manifests) and what it imports (import statements already indexed).
"""

from pathlib import Path

from src.lib.discovery import (
    classify_manifest,
    discover_files,
    discover_manifests,
)
from src.models.stage import StageName
from src.pipeline.context import (
    MAX_INLINE_MANIFEST_BYTES,
    assemble_context,
    build_dependency_input,
    build_structural_index,
    dependency_usage,
    import_targets,
    internal_module_names,
    top_level_package,
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
DEPENDENCY_FIXTURE = FIXTURES_DIR / "dependency_sample"


class TestClassifyManifest:
    def test_known_manifests_and_lockfiles(self):
        assert classify_manifest("package.json") == ("npm", False)
        assert classify_manifest("package-lock.json") == ("npm", True)
        assert classify_manifest("go.mod") == ("go", False)
        assert classify_manifest("Cargo.lock") == ("rust", True)

    def test_pattern_manifests(self):
        assert classify_manifest("requirements.txt") == ("python", False)
        assert classify_manifest("requirements-dev.txt") == ("python", False)
        assert classify_manifest("Api.csproj") == ("dotnet", False)

    def test_source_and_unrelated_files_are_not_manifests(self):
        assert classify_manifest("app.js") is None
        assert classify_manifest("data.json") is None
        assert classify_manifest("README.md") is None


class TestDiscoverManifests:
    def test_finds_the_fixture_manifest(self):
        found = discover_manifests(DEPENDENCY_FIXTURE)
        assert [m.rel_path for m in found] == ["package.json"]
        assert found[0].ecosystem == "npm"
        assert not found[0].is_lockfile
        assert found[0].size_bytes > 0

    def test_manifests_are_not_part_of_the_code_scope(self):
        scope = {f.rel_path for f in discover_files(DEPENDENCY_FIXTURE)}
        assert scope == {"app.js"}

    def test_dependency_directories_are_still_pruned(self, tmp_path: Path):
        (tmp_path / "node_modules" / "left-pad").mkdir(parents=True)
        (tmp_path / "node_modules" / "left-pad" / "package.json").write_text("{}")
        (tmp_path / "package.json").write_text('{"name": "app"}')
        assert [m.rel_path for m in discover_manifests(tmp_path)] == ["package.json"]

    def test_user_excludes_are_honored(self, tmp_path: Path):
        (tmp_path / "tools").mkdir()
        (tmp_path / "tools" / "package.json").write_text("{}")
        (tmp_path / "package.json").write_text('{"name": "app"}')
        found = discover_manifests(tmp_path, exclude=["tools/**"])
        assert [m.rel_path for m in found] == ["package.json"]

    def test_root_manifests_sort_before_nested_ones(self, tmp_path: Path):
        (tmp_path / "packages" / "api").mkdir(parents=True)
        (tmp_path / "packages" / "api" / "package.json").write_text("{}")
        (tmp_path / "package.json").write_text("{}")
        assert [m.rel_path for m in discover_manifests(tmp_path)] == [
            "package.json",
            "packages/api/package.json",
        ]

    def test_large_lockfiles_are_reported_not_dropped(self, tmp_path: Path):
        (tmp_path / "package-lock.json").write_text("x" * 2_000_000)
        found = discover_manifests(tmp_path)
        assert [m.rel_path for m in found] == ["package-lock.json"]
        assert found[0].is_lockfile


class TestImportTargets:
    def test_javascript_and_typescript(self):
        assert import_targets("import React from 'react'") == ["react"]
        assert import_targets('import { format } from "date-fns"') == ["date-fns"]

    def test_python(self):
        assert import_targets("from src.models.stage import StageName") == ["src.models.stage"]
        assert import_targets("import os") == ["os"]
        assert import_targets("import os, sys") == ["os", "sys"]
        assert import_targets("import numpy as np") == ["numpy"]

    def test_go_grouped_imports(self):
        assert import_targets('import ( "fmt" "net/http" )') == ["fmt", "net/http"]

    def test_rust_java_and_c(self):
        assert import_targets("use std::collections::HashMap;") == ["std::collections::HashMap"]
        assert import_targets("import java.util.List;") == ["java.util.List"]
        assert import_targets("#include <stdio.h>") == ["stdio.h"]


class TestTopLevelPackage:
    def test_scoped_npm_packages_keep_two_segments(self):
        assert top_level_package("@aws-sdk/client-s3/commands") == "@aws-sdk/client-s3"

    def test_module_paths_keep_three_segments(self):
        assert top_level_package("github.com/gin-gonic/gin/binding") == "github.com/gin-gonic/gin"

    def test_submodules_collapse_to_their_package(self):
        assert top_level_package("lodash/debounce") == "lodash"
        assert top_level_package("os.path") == "os"
        assert top_level_package("std::collections::HashMap") == "std"

    def test_internal_references_are_dropped(self):
        for internal in ("./util", "../lib/x", "/abs/path", "~/alias", "#private", "@/components"):
            assert top_level_package(internal) is None


class TestDependencyUsage:
    def test_counts_importing_files_per_package(self):
        index = build_structural_index(
            DEPENDENCY_FIXTURE, discover_files(DEPENDENCY_FIXTURE)
        )
        usage = dict(dependency_usage(index))
        assert usage["moment"] == 1
        assert usage["date-fns"] == 1
        assert usage["lodash"] == 1
        assert usage["aws-sdk"] == 1
        assert "left-pad" not in usage  # declared in package.json, never imported

    def test_the_projects_own_modules_are_not_counted_as_dependencies(self):
        root = Path(__file__).parent.parent.parent
        index = build_structural_index(root, discover_files(root))
        usage = dict(dependency_usage(index))
        assert "src" not in usage and "tests" not in usage  # this repo's own packages
        assert usage["pydantic"] > 0  # a real declared dependency still counts

    def test_internal_module_names_cover_packages_and_root_modules(self):
        index = build_structural_index(
            DEPENDENCY_FIXTURE, discover_files(DEPENDENCY_FIXTURE)
        )
        assert internal_module_names(index) == {"app"}  # app.js at the scope root


class TestBuildDependencyInput:
    def _index(self):
        return build_structural_index(DEPENDENCY_FIXTURE, discover_files(DEPENDENCY_FIXTURE))

    def test_inlines_manifests_and_the_import_tally(self):
        text, note = build_dependency_input(self._index(), token_budget=10_000)
        assert "## package.json (npm" in text
        assert '"left-pad"' in text  # the declared-but-unused dependency is visible
        assert "# Imported modules in this scope" in text
        assert "- moment: 1" in text
        assert note is None

    def test_no_manifests_produces_an_explicit_coverage_note(self, tmp_path: Path):
        index = build_structural_index(tmp_path, [])
        text, note = build_dependency_input(index, token_budget=10_000)
        assert "no dependency manifests" in text
        assert note is not None and "No dependency manifest" in note

    def test_lockfiles_are_listed_but_never_inlined(self, tmp_path: Path):
        (tmp_path / "package.json").write_text('{"name": "app"}')
        (tmp_path / "package-lock.json").write_text('{"lockfileVersion": 3, "packages": {}}')
        index = build_structural_index(tmp_path, [])
        text, _note = build_dependency_input(index, token_budget=10_000)
        assert "Lockfiles present" in text
        assert "- package-lock.json (npm, lockfile" in text
        assert "lockfileVersion" not in text

    def test_oversized_manifest_is_skipped_with_a_note(self, tmp_path: Path):
        (tmp_path / "package.json").write_text("x" * (MAX_INLINE_MANIFEST_BYTES + 1))
        index = build_structural_index(tmp_path, [])
        _text, note = build_dependency_input(index, token_budget=10_000)
        assert note is not None and "too large to inline" in note

    def test_token_budget_truncation_is_reported(self):
        _text, note = build_dependency_input(self._index(), token_budget=1)
        assert note is not None and "package.json" in note


class TestAssembleContextForTheDependencyStage:
    def test_uses_manifests_instead_of_ranked_code_chunks(self):
        index = build_structural_index(
            DEPENDENCY_FIXTURE, discover_files(DEPENDENCY_FIXTURE)
        )
        bundle = assemble_context(
            index, StageName.DEPENDENCY_FOOTPRINT, shared_context="ctx", token_budget=10_000
        )
        assert "# Dependency manifests" in bundle.stage_excerpts
        assert "```js" not in bundle.stage_excerpts
        assert "export function stamp" not in bundle.stage_excerpts

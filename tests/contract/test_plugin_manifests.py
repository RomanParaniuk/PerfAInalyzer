"""Contract tests (T005): plugin packaging integrity per contracts/plugin-packaging.md.

Both manifests parse, agree on the plugin name `perf-ai`, the plugin version follows
`pyproject.toml`, the marketplace lists exactly this repository as its one plugin, every
contract-required path exists, and the skill references bundled files only through
`${CLAUDE_PLUGIN_ROOT}` (never assuming `perf-ai` is on PATH)."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
PLUGIN_MANIFEST = REPO_ROOT / ".claude-plugin" / "plugin.json"
MARKETPLACE_MANIFEST = REPO_ROOT / ".claude-plugin" / "marketplace.json"
SKILL_FILE = REPO_ROOT / "skills" / "perf-analyze" / "SKILL.md"
BOOTSTRAP = REPO_ROOT / "scripts" / "plugin_run.py"
PYPROJECT = REPO_ROOT / "pyproject.toml"


def _plugin_manifest() -> dict:
    return json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8"))


def _marketplace_manifest() -> dict:
    return json.loads(MARKETPLACE_MANIFEST.read_text(encoding="utf-8"))


class TestManifestsParseAndAgree:
    def test_plugin_manifest_parses_with_name_perf_ai(self):
        data = _plugin_manifest()
        assert data["name"] == "perf-ai"
        assert data.get("description")
        assert data.get("author")

    def test_marketplace_manifest_parses_with_same_name(self):
        data = _marketplace_manifest()
        assert data["name"] == "perf-ai"

    def test_plugin_version_matches_pyproject(self):
        with PYPROJECT.open("rb") as fh:
            pyproject = tomllib.load(fh)
        assert _plugin_manifest()["version"] == pyproject["project"]["version"]

    def test_marketplace_lists_exactly_one_plugin_sourced_from_repo_root(self):
        plugins = _marketplace_manifest()["plugins"]
        assert len(plugins) == 1
        assert plugins[0]["name"] == "perf-ai"
        assert plugins[0]["source"] == "./"


class TestRequiredPathsExist:
    def test_skill_file_exists(self):
        assert SKILL_FILE.is_file()

    def test_bootstrap_exists(self):
        assert BOOTSTRAP.is_file()

    def test_pyproject_exists(self):
        assert PYPROJECT.is_file()


class TestSkillReferencesBundledFilesPortably:
    def test_skill_uses_claude_plugin_root_for_bundled_files(self):
        content = SKILL_FILE.read_text(encoding="utf-8")
        assert "${CLAUDE_PLUGIN_ROOT}" in content
        assert "plugin_run.py" in content

    def test_skill_never_invokes_bare_perf_ai_on_path(self):
        """Every deterministic-step invocation must go through the bootstrap: any line
        that invokes `perf-ai agent …` as a command must do so via plugin_run.py."""
        for line in SKILL_FILE.read_text(encoding="utf-8").splitlines():
            if re.search(r"\bperf-ai agent\b", line):
                assert "plugin_run.py" in line, (
                    f"SKILL.md invokes the helper CLI without the bootstrap: {line!r}"
                )

    def test_skill_has_yaml_frontmatter(self):
        content = SKILL_FILE.read_text(encoding="utf-8")
        assert content.startswith("---\n")
        frontmatter = content.split("---", 2)[1]
        assert "name:" in frontmatter
        assert "description:" in frontmatter

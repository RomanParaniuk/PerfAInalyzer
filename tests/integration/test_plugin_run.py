"""Integration tests (T012): the stdlib-only bootstrap `scripts/plugin_run.py` per
contracts/plugin-packaging.md.

Interpreter < 3.12 -> non-zero exit naming the required version before any other work;
first invocation provisions the private venv and writes the stamp last; a second
invocation reuses the stamp; a stale stamp (changed pyproject hash) re-provisions; exit
codes from the inner `perf-ai` are forwarded unchanged; no writes outside the plugin
directory."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
SCRIPT = REPO_ROOT / "scripts" / "plugin_run.py"

FAKE_PYPROJECT = """\
[project]
name = "perf-ai"
version = "0.1.0"
"""


def _load_module():
    spec = importlib.util.spec_from_file_location("plugin_run_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def mod():
    return _load_module()


@pytest.fixture()
def fake_root(tmp_path: Path, mod, monkeypatch):
    """A fake plugin checkout with stubbed provisioning/execution helpers."""
    root = tmp_path / "plugin"
    root.mkdir()
    (root / "pyproject.toml").write_text(FAKE_PYPROJECT, encoding="utf-8")
    monkeypatch.setattr(mod, "plugin_root", lambda: root)

    calls = {"create_venv": 0, "pip_install": 0, "exec": []}

    def fake_create_venv(target_root: Path) -> None:
        calls["create_venv"] += 1
        bin_dir = target_root / ".venv" / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        (bin_dir / "perf-ai").write_text("#!/bin/sh\n", encoding="utf-8")

    def fake_pip_install(target_root: Path) -> None:
        calls["pip_install"] += 1

    def fake_run_perf_ai(target_root: Path, args: list[str]) -> int:
        calls["exec"].append(list(args))
        return 0

    monkeypatch.setattr(mod, "_create_venv", fake_create_venv)
    monkeypatch.setattr(mod, "_pip_install", fake_pip_install)
    monkeypatch.setattr(mod, "_run_perf_ai", fake_run_perf_ai)
    return root, calls


class TestVersionGate:
    def test_old_interpreter_rejected_before_any_other_work(self):
        code = (
            "import sys, runpy\n"
            "sys.version_info = (3, 10, 0, 'final', 0)\n"
            f"sys.argv = ['plugin_run.py', 'agent', 'scope', '--max-parallel', '4']\n"
            f"runpy.run_path({str(SCRIPT)!r}, run_name='__main__')\n"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, timeout=60
        )
        assert proc.returncode != 0
        assert "3.12" in proc.stderr
        # How to obtain it is part of the message; provisioning never started.
        assert "python.org" in proc.stderr or "install" in proc.stderr.lower()
        assert "provision" not in proc.stderr.lower()

    def test_current_interpreter_passes_gate(self, mod, fake_root):
        root, calls = fake_root
        assert mod.main(["agent", "--help"]) == 0


class TestProvisioning:
    def test_first_invocation_provisions_and_writes_stamp(self, mod, fake_root):
        root, calls = fake_root
        assert not mod.stamp_path(root).exists()
        assert mod.main(["agent", "--help"]) == 0
        assert calls["create_venv"] == 1
        assert calls["pip_install"] == 1
        assert mod.stamp_path(root).is_file()

    def test_stamp_written_last_no_half_provisioned_state(
        self, mod, fake_root, monkeypatch
    ):
        root, calls = fake_root

        def failing_pip_install(target_root: Path) -> None:
            raise mod.BootstrapError("simulated: no network while downloading dependencies")

        monkeypatch.setattr(mod, "_pip_install", failing_pip_install)
        assert mod.main(["agent", "--help"]) != 0
        assert not mod.stamp_path(root).exists(), "stamp must be written last"
        assert calls["exec"] == [], "inner perf-ai must not run after failed provisioning"

    def test_second_invocation_reuses_stamp(self, mod, fake_root):
        root, calls = fake_root
        assert mod.main(["agent", "--help"]) == 0
        assert mod.main(["agent", "--help"]) == 0
        assert calls["pip_install"] == 1, "second invocation must skip provisioning"

    def test_stale_stamp_reprovisions(self, mod, fake_root):
        root, calls = fake_root
        assert mod.main(["agent", "--help"]) == 0
        (root / "pyproject.toml").write_text(
            FAKE_PYPROJECT.replace("0.1.0", "0.2.0"), encoding="utf-8"
        )
        assert mod.main(["agent", "--help"]) == 0
        assert calls["pip_install"] == 2, "changed pyproject hash must re-provision"


class TestExecution:
    def test_exit_code_forwarded_unchanged(self, mod, fake_root, monkeypatch):
        root, calls = fake_root
        monkeypatch.setattr(mod, "_run_perf_ai", lambda r, a: 7)
        assert mod.main(["agent", "render", "--results-dir", "x"]) == 7

    def test_arguments_forwarded_verbatim(self, mod, fake_root):
        root, calls = fake_root
        args = ["agent", "scope", "some/path", "--max-parallel", "4"]
        mod.main(list(args))
        assert calls["exec"] == [args]

    def test_no_writes_outside_plugin_directory(self, mod, fake_root, tmp_path: Path):
        root, calls = fake_root
        outside_before = {p for p in tmp_path.iterdir()}
        mod.main(["agent", "--help"])
        assert {p for p in tmp_path.iterdir()} == outside_before
        created = [p for p in root.rglob("*")]
        assert all(str(p).startswith(str(root)) for p in created)

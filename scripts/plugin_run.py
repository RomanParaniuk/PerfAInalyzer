#!/usr/bin/env python3
"""Stdlib-only bootstrap for the perf-ai Claude Code plugin (contracts/plugin-packaging.md).

Every deterministic-step invocation from the skill goes through this script:

    python3 "${CLAUDE_PLUGIN_ROOT}/scripts/plugin_run.py" agent <subcommand> [args...]

In order: (1) verify the interpreter is Python >= 3.12, else exit non-zero naming the
required version and how to obtain it — before any other work (FR-014 fail-fast);
(2) provision a private virtual environment inside the plugin checkout on first use or
after a plugin update (stamp = package version + pyproject.toml hash, written last so a
half-provisioned venv is never mistaken for a working one); (3) run the private venv's
`perf-ai` entry point, forwarding all arguments and the exit code unchanged.

The only filesystem writes are inside the plugin's own directory (.venv + stamp): the
developer's project, global interpreter, site-packages, and PATH are never modified.
No third-party imports — this must run on a bare interpreter."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

REQUIRED_PYTHON = (3, 12)


class BootstrapError(Exception):
    """A provisioning/execution failure with a user-facing cause and remediation."""


def plugin_root() -> Path:
    return Path(__file__).resolve().parent.parent


def stamp_path(root: Path) -> Path:
    return root / ".venv" / "perf-ai-stamp.json"


def compute_stamp(root: Path) -> dict:
    """Identity of the provisioned state: package version + pyproject.toml hash."""
    import tomllib  # stdlib since 3.11; imported lazily, after the version gate

    pyproject = root / "pyproject.toml"
    raw = pyproject.read_bytes()
    version = tomllib.loads(raw.decode("utf-8")).get("project", {}).get("version", "")
    return {
        "package_version": version,
        "pyproject_sha256": hashlib.sha256(raw).hexdigest(),
    }


def read_stamp(root: Path) -> dict | None:
    try:
        return json.loads(stamp_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def needs_provisioning(root: Path) -> bool:
    return read_stamp(root) != compute_stamp(root)


def _venv_bin(root: Path) -> Path:
    return root / ".venv" / ("Scripts" if os.name == "nt" else "bin")


def _venv_python(root: Path) -> Path:
    return _venv_bin(root) / ("python.exe" if os.name == "nt" else "python")


def _create_venv(root: Path) -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "venv", str(root / ".venv")], capture_output=True
    )
    if completed.returncode != 0:
        raise BootstrapError(
            "could not create the plugin's private virtual environment at "
            f"{root / '.venv'}: {completed.stderr.decode(errors='replace').strip()}. "
            "Check that the directory is writable and that the `venv` module is "
            "available, then retry."
        )


def _pip_install(root: Path) -> None:
    completed = subprocess.run(
        [str(_venv_python(root)), "-m", "pip", "install", "--quiet", str(root)],
        capture_output=True,
    )
    if completed.returncode != 0:
        raise BootstrapError(
            "installing the bundled perf-ai package into the plugin's private "
            f"environment failed: {completed.stderr.decode(errors='replace').strip()}. "
            "The first run downloads dependencies from PyPI — check your network "
            "connection and retry; later runs are offline."
        )


def provision(root: Path) -> None:
    print(
        "perf-ai plugin: setting up its private environment (first run or plugin "
        "update); this downloads dependencies once and may take a minute...",
        file=sys.stderr,
    )
    if not _venv_python(root).exists():
        _create_venv(root)
    _pip_install(root)
    # Stamp written last: a failure above leaves no stamp, so the next run retries.
    stamp_path(root).write_text(
        json.dumps(compute_stamp(root), indent=2), encoding="utf-8"
    )


def _run_perf_ai(root: Path, args: list[str]) -> int:
    executable = _venv_bin(root) / ("perf-ai.exe" if os.name == "nt" else "perf-ai")
    if not executable.exists():
        raise BootstrapError(
            f"the provisioned environment is missing the perf-ai entry point at "
            f"{executable}; delete {root / '.venv'} and rerun to re-provision."
        )
    return subprocess.run([str(executable), *args]).returncode


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:]) if argv is None else list(argv)
    if tuple(sys.version_info[:2]) < REQUIRED_PYTHON:
        required = ".".join(str(part) for part in REQUIRED_PYTHON)
        current = ".".join(str(part) for part in tuple(sys.version_info[:3]))
        print(
            f"perf-ai plugin: Python {required} or newer is required; this interpreter "
            f"is {current}. Get a current Python from https://www.python.org/downloads/ "
            "or your system package manager, and make sure `python3` points at it.",
            file=sys.stderr,
        )
        return 1
    root = plugin_root()
    try:
        if needs_provisioning(root):
            provision(root)
        return _run_perf_ai(root, argv)
    except BootstrapError as exc:
        print(f"perf-ai plugin: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

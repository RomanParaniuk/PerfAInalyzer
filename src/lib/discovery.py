"""Language detection and file discovery for the submitted code scope (FR-001, FR-014).

Purely local — no AI tokens are spent here. Default excludes cover VCS/dependency/build
directories; `--include`/`--exclude` globs refine the scope (contracts/cli-interface.md).
`discover_manifests` collects the dependency manifests alongside the code scope: the
dependency-footprint stage reads what a project *declares* and imports, never the
dependencies' own source, which stays excluded here.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

# Extension → tree-sitter-compatible language name. Best-effort, not a fixed supported
# list (FR-014): files outside this map are simply not analyzed rather than failing the run.
EXTENSION_LANGUAGES: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".mts": "typescript",
    ".tsx": "tsx",
    ".go": "go",
    ".rb": "ruby",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
    ".cs": "csharp",
    ".rs": "rust",
    ".php": "php",
    ".swift": "swift",
    ".scala": "scala",
    ".sh": "bash",
    ".bash": "bash",
    ".lua": "lua",
    ".pl": "perl",
    ".pm": "perl",
    ".r": "r",
    ".R": "r",
    ".sql": "sql",
    ".hs": "haskell",
    ".ex": "elixir",
    ".exs": "elixir",
    ".erl": "erlang",
    ".clj": "clojure",
    ".dart": "dart",
    ".zig": "zig",
    ".jl": "julia",
}

# Directory names pruned from the walk unconditionally unless the user re-includes them.
DEFAULT_EXCLUDE_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        "venv",
        ".venv",
        "env",
        ".env",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        ".eggs",
        "dist",
        "build",
        "target",
        "vendor",
        ".idea",
        ".vscode",
        ".next",
        ".cache",
        "site-packages",
        "coverage",
        "htmlcov",
    }
)

# Files larger than this are skipped as likely generated/minified artifacts.
MAX_FILE_BYTES = 1_000_000

# Dependency manifests and lockfiles. These are not source code — they never enter the
# code scope, are never partitioned, and no dependency's own source is ever read. They
# are the declared-dependency side of the dependency-footprint stage, which pairs them
# with the import sites already indexed from the product code.
MANIFEST_KINDS: dict[str, tuple[str, bool]] = {  # filename -> (ecosystem, is_lockfile)
    "package.json": ("npm", False),
    "package-lock.json": ("npm", True),
    "npm-shrinkwrap.json": ("npm", True),
    "yarn.lock": ("npm", True),
    "pnpm-lock.yaml": ("npm", True),
    "pnpm-workspace.yaml": ("npm", False),
    "bun.lockb": ("npm", True),
    "deno.json": ("deno", False),
    "deno.lock": ("deno", True),
    "pyproject.toml": ("python", False),
    "setup.py": ("python", False),
    "setup.cfg": ("python", False),
    "Pipfile": ("python", False),
    "Pipfile.lock": ("python", True),
    "poetry.lock": ("python", True),
    "uv.lock": ("python", True),
    "conda.yaml": ("python", False),
    "environment.yml": ("python", False),
    "go.mod": ("go", False),
    "go.sum": ("go", True),
    "Cargo.toml": ("rust", False),
    "Cargo.lock": ("rust", True),
    "Gemfile": ("ruby", False),
    "Gemfile.lock": ("ruby", True),
    "composer.json": ("php", False),
    "composer.lock": ("php", True),
    "pom.xml": ("java", False),
    "build.gradle": ("java", False),
    "build.gradle.kts": ("java", False),
    "gradle.lockfile": ("java", True),
    "mix.exs": ("elixir", False),
    "mix.lock": ("elixir", True),
    "pubspec.yaml": ("dart", False),
    "pubspec.lock": ("dart", True),
    "Package.swift": ("swift", False),
    "Package.resolved": ("swift", True),
}

# Filename patterns that resolve to the same (ecosystem, is_lockfile) pair.
MANIFEST_PATTERNS: tuple[tuple[str, str, bool], ...] = (
    ("requirements*.txt", "python", False),
    ("*.csproj", "dotnet", False),
    ("packages.lock.json", "dotnet", True),
    ("*.gemspec", "ruby", False),
)


@dataclass(frozen=True)
class ManifestFile:
    """One dependency manifest or lockfile found in the scope."""

    path: Path  # absolute
    rel_path: str  # POSIX-style, relative to the scope root
    ecosystem: str  # "npm", "python", "go", ...
    is_lockfile: bool
    size_bytes: int

    @property
    def depth(self) -> int:
        """Directory depth below the scope root; root manifests sort first."""
        return self.rel_path.count("/")


def classify_manifest(filename: str) -> tuple[str, bool] | None:
    """(ecosystem, is_lockfile) for a manifest filename, or None if it is not one."""
    known = MANIFEST_KINDS.get(filename)
    if known is not None:
        return known
    for pattern, ecosystem, is_lockfile in MANIFEST_PATTERNS:
        if fnmatch(filename, pattern):
            return ecosystem, is_lockfile
    return None


@dataclass(frozen=True)
class SourceFile:
    """One discovered source file within the code scope."""

    path: Path  # absolute
    rel_path: str  # POSIX-style, relative to the scope root
    language: str
    size_bytes: int


def _matches_any(rel_path: str, patterns: Sequence[str]) -> bool:
    basename = rel_path.rsplit("/", 1)[-1]
    for pattern in patterns:
        if fnmatch(rel_path, pattern) or fnmatch(basename, pattern):
            return True
        # Allow directory-style patterns like "generated/" or "generated" to match children.
        dir_pattern = pattern.rstrip("/")
        if dir_pattern and (
            rel_path.startswith(dir_pattern + "/") or f"/{dir_pattern}/" in f"/{rel_path}"
        ):
            return True
    return False


def discover_files(
    root: Path,
    include: Sequence[str] = (),
    exclude: Sequence[str] = (),
) -> list[SourceFile]:
    """Walk `root` and return recognized source files, honoring default and user excludes.

    If `root` is a single file, it is returned alone (when its language is recognized).
    """
    root = root.resolve()
    if root.is_file():
        language = EXTENSION_LANGUAGES.get(root.suffix)
        if language is None:
            return []
        return [
            SourceFile(
                path=root,
                rel_path=root.name,
                language=language,
                size_bytes=root.stat().st_size,
            )
        ]

    found: list[SourceFile] = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root).as_posix()
        dirnames[:] = sorted(
            d
            for d in dirnames
            if d not in DEFAULT_EXCLUDE_DIRS
            and not _matches_any(f"{rel_dir}/{d}" if rel_dir != "." else d, exclude)
        )
        for filename in sorted(filenames):
            language = EXTENSION_LANGUAGES.get(Path(filename).suffix)
            if language is None:
                continue
            rel_path = f"{rel_dir}/{filename}" if rel_dir != "." else filename
            if include and not _matches_any(rel_path, include):
                continue
            if _matches_any(rel_path, exclude):
                continue
            full_path = Path(dirpath) / filename
            try:
                size = full_path.stat().st_size
            except OSError:
                continue
            if size > MAX_FILE_BYTES:
                continue
            found.append(
                SourceFile(path=full_path, rel_path=rel_path, language=language, size_bytes=size)
            )
    return found


def discover_manifests(root: Path, exclude: Sequence[str] = ()) -> list[ManifestFile]:
    """Walk `root` and return its dependency manifests and lockfiles.

    Same pruning as `discover_files` (so a manifest inside `node_modules` or a
    user-excluded directory is never returned), but no size cap: a lockfile is worth
    knowing about even when it is far too large to read, and the callers decide how much
    of one to consume. Ordered root-first, then by path, so the plan is deterministic.
    """
    root = root.resolve()
    if root.is_file():
        return []

    found: list[ManifestFile] = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root).as_posix()
        dirnames[:] = sorted(
            d
            for d in dirnames
            if d not in DEFAULT_EXCLUDE_DIRS
            and not _matches_any(f"{rel_dir}/{d}" if rel_dir != "." else d, exclude)
        )
        for filename in sorted(filenames):
            classified = classify_manifest(filename)
            if classified is None:
                continue
            rel_path = f"{rel_dir}/{filename}" if rel_dir != "." else filename
            if _matches_any(rel_path, exclude):
                continue
            try:
                size = (Path(dirpath) / filename).stat().st_size
            except OSError:
                continue
            ecosystem, is_lockfile = classified
            found.append(
                ManifestFile(
                    path=Path(dirpath) / filename,
                    rel_path=rel_path,
                    ecosystem=ecosystem,
                    is_lockfile=is_lockfile,
                    size_bytes=size,
                )
            )
    found.sort(key=lambda m: (m.depth, m.rel_path))
    return found


def detect_languages(files: Sequence[SourceFile]) -> list[str]:
    """Sorted unique languages present in the discovered scope (FR-014)."""
    return sorted({f.language for f in files})

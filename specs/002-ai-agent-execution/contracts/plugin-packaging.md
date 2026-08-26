# Contract: Plugin Packaging & Installation (`perf-ai` plugin)

**Feature**: `002-ai-agent-execution` | **Date**: 2026-08-04

How the repository is packaged as a Claude Code plugin and its own marketplace (FR-001), and
how the installed plugin executes the bundled pipeline code in isolation (FR-014). This is the
installation-facing counterpart of [agent-skill-interface.md](./agent-skill-interface.md).

## Repository layout obligations

The repository root doubles as the plugin and as its own single-plugin marketplace:

| Path | Obligation |
|---|---|
| `.claude-plugin/plugin.json` | Plugin manifest. `name` MUST be `perf-ai`; carries version, description, author. |
| `.claude-plugin/marketplace.json` | Marketplace manifest. Lists exactly one plugin, `name` identical to the plugin manifest's, with `source: "./"` — the repository root **is** the plugin. |
| `skills/perf-analyze/SKILL.md` | The analysis skill (slash command) inside the plugin. MUST reference bundled files only through `${CLAUDE_PLUGIN_ROOT}` so it works from any install location. |
| `scripts/plugin_run.py` | Stdlib-only bootstrap (see below). MUST be runnable by a bare Python ≥ 3.12 with no third-party packages installed. |
| `src/`, `pyproject.toml`, report templates | The complete 001 pipeline package MUST ship in the plugin source so every deterministic step can execute from the installed checkout (FR-014). |

Contract tests assert: both manifests parse, names agree, and every path above exists.

## Installation flow (what the developer runs)

From any project, in a Claude Code session:

```text
/plugin marketplace add <github-owner>/<repo>     # or: /plugin marketplace add /absolute/path/to/checkout
/plugin install perf-ai@perf-ai
```

**Guarantee** (US1 scenario 4): after these two steps, `/perf-analyze` is invocable in that
project's sessions with no further setup — no pip install, no PATH changes, no credentials.
The same flow with the local checkout path serves sessions opened directly in this repository.
Uninstalling the plugin removes everything it added, including its private venv (which lives
inside the plugin directory).

## Bootstrap contract (`scripts/plugin_run.py`)

Every deterministic-step invocation from the skill goes through:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/plugin_run.py" agent <subcommand> [args…]
```

Behavior, in order:

1. **Runtime gate** (FR-014 fail-fast): if the interpreter is < 3.12 (or `python3` is absent —
   detected by the skill's preflight before this script can even run), exit non-zero with a
   message naming the required version and how to obtain it. No other work happens first.
2. **Provisioning**: if `<plugin-root>/.venv` is absent or its stamp (package version /
   `pyproject.toml` hash) is stale (plugin updated), create the venv and `pip install` the
   plugin checkout into it. First provisioning downloads dependencies from PyPI — the one
   network-requiring moment of the plugin path, documented in the README. Provisioning failure
   (e.g. no network) exits non-zero with the cause and remediation; it MUST NOT leave a
   half-provisioned venv that later runs mistake for a working one (stamp written last).
3. **Execution**: run the private venv's `perf-ai` entry point with all remaining arguments
   forwarded verbatim; propagate its exit code unchanged (so the exit-code table of
   [agent-support-cli.md](./agent-support-cli.md) holds through the bootstrap).

**Isolation guarantees** (FR-014): the only filesystem writes are inside the plugin's own
directory (`.venv` + stamp). The developer's project, global interpreter, site-packages, and
PATH are never modified; nothing needs to be installed beforehand.

## Versioning & update

Plugin version lives in `.claude-plugin/plugin.json` and follows the package version in
`pyproject.toml`. A plugin update that changes either triggers re-provisioning on next use via
the stamp check — no manual step. The skill, bootstrap, helper CLI, and manifests ship in
lockstep in one repository; no independent backward-compatibility guarantee across feature
revisions (same policy as 001's stage-output schema).

## Out of scope

Publishing to any central plugin registry, supporting agents other than Claude Code (future
additive packagings per spec Assumptions), and managing/installing the Python runtime itself
(the plugin verifies and instructs, never installs — spec Assumptions).

# Implementation Plan: AI Agent Execution & Parallelism

**Branch**: `002-ai-agent-execution` | **Date**: 2026-08-04 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-ai-agent-execution/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Package the existing four-stage performance-analysis pipeline as a **Claude Code plugin** whose
source is this repository itself, with the repository also serving as its own single-plugin
marketplace: `.claude-plugin/plugin.json` + `.claude-plugin/marketplace.json` at the root, and
the analysis skill (`/perf-analyze`) at `skills/perf-analyze/SKILL.md` inside the plugin. A
developer installs it into any project via `/plugin marketplace add …` + `/plugin install
perf-ai@perf-ai` and runs a complete analysis with the agent's own model access — no
`ANTHROPIC_API_KEY` required. Per FR-014, every deterministic step executes the bundled 001
pipeline code from the installed plugin's own checkout through a stdlib-only bootstrap
(`scripts/plugin_run.py`) that verifies Python ≥ 3.12 (fail-fast with instructions otherwise)
and provisions a private venv inside the plugin directory on first use — no pre-installation,
no changes to the developer's environment. The skill orchestrates: deterministic preflight and
work-plan generation (`perf-ai agent scope`, new additive CLI sub-app reusing the existing
discovery code), a mandatory ask-the-developer parallelism question (no default; values >10
capped; pre-suppliable as `max-parallel=N` for non-interactive runs, which otherwise fail
fast), subagent fan-out in waves of at most N over stage×partition work units (structural
context first, shared by the other three stages), and deterministic consolidation
(`perf-ai agent render`) that schema-validates each subagent's JSON result, merges duplicate
findings by location, and produces `perf-report.md` / `perf-report.html` through the *existing*
aggregator and Jinja2 templates — making skill reports structurally identical to hosted-API CLI
reports by construction. The existing `perf-ai analyze` path is untouched. A rewritten root
README documents both execution paths (including plugin installation), the codebase layout,
testing, and troubleshooting, with every command copy-paste runnable.

## Technical Context

**Language/Version**: Python 3.12 (helper CLI sub-app, bootstrap, models, tests); Markdown with
YAML frontmatter (skill definition); JSON (plugin + marketplace manifests)

**Primary Dependencies**: existing only — Typer (CLI), Pydantic (schema validation of subagent
results), Jinja2 (report templates, reused), Rich (CLI output); no new runtime dependencies.
`scripts/plugin_run.py` is stdlib-only by contract (must run before any dependency exists).
Runtime host for the skill path: Claude Code with its plugin/marketplace system (installed and
licensed by the developer, per spec Assumptions)

**Storage**: N/A — stateless across runs. Intermediate stage-result JSON files are written to a
per-run scratch directory chosen by the skill and are inputs to `agent render`, not retained
artifacts; the only outputs remain `perf-report.md` / `perf-report.html` (overwritten per run).
The plugin's private venv (inside the plugin checkout) is a provisioning cache, not analysis
state

**Testing**: pytest — unit tests (partitioning, dedup, coverage-note synthesis), contract tests
(work-plan JSON shape; stage-result file schema acceptance/rejection; plugin/marketplace
manifest integrity), integration tests (`agent scope` / `agent render` end-to-end on fixture
results, exit codes, CLI-parity of report structure; bootstrap version gate, provisioning,
stamp reuse, exit-code forwarding); scripted manual quickstart validation for in-session plugin
behavior (marketplace install, interactive question, wave concurrency, SC-004 timing); README
command verification on a fresh setup

**Target Platform**: Developer workstation — hosted-API CLI: macOS/Linux/Windows; plugin skill
path: macOS/Linux in this feature (the skill procedure invokes `python3` and POSIX-style
`${CLAUDE_PLUGIN_ROOT}` expansion; Windows would need a `py -3` invocation variant and its own
validation, deferred). Helper CLI and bootstrap are offline and key-free (bootstrap needs
network once, to provision its private venv); skill path additionally requires a working
Claude Code session in a project with the plugin installed

**Project Type**: Single project — CLI tool plus repository-as-plugin-and-marketplace packaging

**Performance Goals**: SC-004 — with ≥4 independent analyzable units, a run allowed 4 parallel
subagents completes ≥30% faster wall-clock than the same run limited to 1; deterministic helper
commands complete in seconds (no model calls); bootstrap adds negligible overhead after first
provisioning; no latency change to the existing CLI path

**Constraints**: skill path must work with zero hosted-provider credentials (FR-002); existing
`analyze` behavior byte-for-byte unchanged (FR-003); every deterministic step executes the
bundled 001 code from the plugin checkout — no reimplementation, no pre-install, no environment
modification, fail-fast on missing runtime (FR-014); documented hard cap of 10 concurrent
subagents with no suggested default (FR-006/FR-007); static analysis only — no execution,
compilation, or profiling of submitted code (inherited from 001); graceful degradation — partial
subagent failure still yields a report naming what did not complete (FR-010)

**Scale/Scope**: same analysis scope as 001 (tens of thousands of LOC, moderate file count);
up to 10 concurrent subagents; 4–(3×⌈N/3⌉+1) work units per run

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Status |
|---|---|---|
| I. Modern AI-First Approaches | The packaging uses the current-generation agent-native mechanism (Claude Code plugin + marketplace distribution + subagent fan-out) rather than a bespoke daemon or prompt-pasting doc; model access is the invoking agent's own, so model-tier currency tracks the agent itself. Choice and alternatives documented in `research.md` §1–§4 for future revisit. | PASS |
| II. Token-Optimal Usage (NON-NEGOTIABLE) | All deterministic work (bootstrap, preflight, partitioning, validation, dedup, aggregation, rendering) is zero-token Python executed from the bundled checkout (`research.md` §2–§3); structural context is built once and shared by all later units (§4); partitions are disjoint so total read volume ≈ one whole-scope pass per stage, with partition count tied to the developer's chosen N (§5); dedup is key-based, not a model call (§7); design-time token estimate recorded (§9). | PASS |
| III. Useful, Actionable Output | Subagent output is accepted only after Pydantic validation against the existing `StageResult` schema — unusable output becomes a *failed unit noted in the report*, never trusted content (`research.md` §8); action-item concreteness rules from 001 (suggested_action ≠ description) apply unchanged because the same aggregator runs; preflight and bootstrap failures name the problem and the fix (FR spec edge cases, FR-014). | PASS |
| IV. Consistent User Experience | Reports are rendered by the *same* deterministic templates as the CLI path, so tone/structure/empty-section handling are identical across execution paths (SC-002 by construction); unit/stage failures map onto the existing `incomplete_stages` / `coverage_note` vocabulary; `agent render` mirrors the CLI's exit-code contract and the bootstrap forwards codes unchanged; error messages are user-facing prose, never stack traces. | PASS |
| V. Performance Requirements | Explicit budget: SC-004's ≥30% wall-clock improvement at N=4 vs N=1, measured via a scripted quickstart scenario before release; waves keep ≤N subagents busy without idle serialization; the skill reports per-wave progress rather than blocking silently; first-run venv provisioning is a one-time cost surfaced to the user, not a per-run tax; CLI-path performance is unaffected (no code it uses changes). | PASS |

No violations requiring justification — Complexity Tracking is empty.

### Post-Phase-1 re-check

Re-evaluated after `data-model.md` and `contracts/` were produced:

| Principle | Post-design confirmation | Status |
|---|---|---|
| I. Modern AI-First Approaches | `contracts/agent-skill-interface.md` keeps the skill's user-facing behavior generic (parallelism limit, consolidated report) so other agents can be added later without changing guarantees; `contracts/plugin-packaging.md` uses the agent's native marketplace flow rather than a custom installer; no legacy fallback path was introduced during design. | PASS |
| II. Token-Optimal Usage | `data-model.md`'s Work Plan entity confirms the structural summary is one shared artifact referenced by every later unit, not recomputed; the Work Unit entity carries a *file list*, not file contents, so no design decision duplicated context into prompts; the bootstrap keeps all FR-014 execution at zero tokens. | PASS |
| III. Useful, Actionable Output | `contracts/agent-support-cli.md` pins the stage-result file schema to 001's `report_stage_findings` contract and specifies rejection behavior per invalid file (unit failed + reason surfaced); `contracts/plugin-packaging.md` requires provisioning failures to state cause and remediation and forbids half-provisioned states. | PASS |
| IV. Consistent User Experience | `contracts/agent-support-cli.md` fixes `agent render` exit codes to mirror the 001 CLI contract (0 report written incl. partial, 1 invalid input, 3 all-units failure) and confirms both report files come from the unchanged 001 renderer; the bootstrap contract guarantees exit-code transparency so failure behavior is identical through either front door. | PASS |
| V. Performance Requirements | `quickstart.md` contains the concrete SC-004 measurement scenario (same scope, N=1 vs N=4, ≥30% delta) and the wave-observation check for FR-008; the bootstrap's stamp check makes post-first-run overhead a no-op; no new synchronous blocking step was added by the design. | PASS |

No new violations were introduced during Phase 1 design. Complexity Tracking remains empty.

## Project Structure

### Documentation (this feature)

```text
specs/002-ai-agent-execution/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   ├── agent-skill-interface.md
│   ├── agent-support-cli.md
│   └── plugin-packaging.md
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
.claude-plugin/
├── plugin.json            # NEW: plugin manifest — name `perf-ai`, version, description, author
└── marketplace.json       # NEW: marketplace manifest — this repo as its own marketplace,
                           # single plugin with source "./"

skills/
└── perf-analyze/
    └── SKILL.md           # NEW: the /perf-analyze skill (plugin component) — orchestration
                           # procedure: runtime + scope preflight via the bootstrap,
                           # parallelism question & validation, wave-based subagent fan-out,
                           # consolidation via `agent render`; bundled files referenced
                           # through ${CLAUDE_PLUGIN_ROOT}

scripts/
└── plugin_run.py          # NEW: stdlib-only bootstrap — Python ≥3.12 gate, private-venv
                           # provisioning inside the plugin checkout (stamped, re-provisions
                           # on update), forwards to the bundled `perf-ai` entry point

src/
├── cli/
│   ├── main.py            # UNCHANGED `analyze`; registers the new `agent` sub-app
│   └── agent.py           # NEW: `perf-ai agent scope` and `perf-ai agent render`
│                          # subcommands (deterministic, offline, no API key)
├── agentrun/              # NEW: agent-path support logic (kept out of pipeline/ to
│   ├── __init__.py        # guarantee the hosted path is untouched)
│   ├── workplan.py        # partition computation (size-balanced bin-pack), work-unit
│   │                      # derivation, work-plan JSON model
│   ├── results.py         # stage-result file loading, StageResult validation,
│   │                      # attribution stamping, unit-failure bookkeeping
│   └── dedupe.py          # location-keyed duplicate-finding merge (FR-011)
├── pipeline/              # UNCHANGED (orchestrator, stages, context)
├── models/                # UNCHANGED (StageResult, Finding, Report, ... reused as-is)
├── providers/             # UNCHANGED (hosted-API client; not imported by agentrun)
├── report/                # UNCHANGED (aggregator + templates reused by `agent render`)
└── lib/                   # UNCHANGED (discovery reused by `agent scope`)

tests/
├── contract/
│   ├── test_workplan_schema.py       # NEW: work-plan JSON shape
│   ├── test_stage_result_files.py    # NEW: result-file acceptance/rejection matrix
│   └── test_plugin_manifests.py      # NEW: manifests parse, names agree, referenced
│                                     # paths exist (skill, bootstrap, pyproject)
├── integration/
│   ├── test_agent_scope_cli.py       # NEW: preflight errors, exit codes, plan output
│   ├── test_agent_render_cli.py      # NEW: fixture results → report; partial/total
│   │                                 # failure; exit-code contract
│   ├── test_agent_report_parity.py   # NEW: agent-path report structurally identical
│   │                                 # to analyze-path report from same findings
│   └── test_plugin_run.py            # NEW: bootstrap version gate, provisioning +
│                                     # stamp reuse, exit-code forwarding
└── unit/
    ├── test_workplan.py              # NEW: partition determinism/balance, N clamping
    ├── test_dedupe.py                # NEW: merge key, survivor selection
    └── test_results.py               # NEW: validation → failed-unit mapping

README.md                  # REWRITTEN: full developer guide (FR-012/FR-013), incl. plugin
                           # marketplace installation
```

**Structure Decision**: Single project, extended in place; the repository root doubles as the
plugin and its own marketplace (FR-001), so the complete `src/` tree ships inside every
installed plugin checkout — which is what lets the skill satisfy FR-014 by executing the
bundled 001 code via `scripts/plugin_run.py`. New agent-path code is isolated in
`src/agentrun/` + `src/cli/agent.py` and only *imports* existing modules (`lib.discovery`,
`models.*`, `report.*`), so the hosted-API path (`pipeline/`, `providers/`, `analyze`) has no
modified files — making FR-003's "unchanged" verifiable by diff. The skill lives under
`skills/perf-analyze/` (a plugin component directory), not `.claude/skills/`, per the plugin
clarification; `.claude/` remains dev tooling only.

## Complexity Tracking

*No entries — Constitution Check reported no violations requiring justification.*

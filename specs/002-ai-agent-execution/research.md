# Phase 0 Research: AI Agent Execution & Parallelism

**Feature**: `002-ai-agent-execution` | **Date**: 2026-08-04

The spec's clarification session already fixed the largest decisions (agent-invokes-pipeline
direction, Claude Code **plugin** packaging with the repository doubling as its own marketplace,
mandatory reuse of the bundled `001-perf-analysis-pipeline` code for every deterministic step,
no-default parallelism prompt with a cap of 10, additive-only relationship to the hosted-API
CLI). This phase resolves the remaining design unknowns. No `NEEDS CLARIFICATION` markers remain
in the Technical Context.

## 1. Packaging form: Claude Code plugin, repository as its own marketplace

**Decision**: Ship the agent packaging as a Claude Code **plugin** whose source is this
repository itself, with the repository also serving as its own single-plugin **marketplace**:

- `.claude-plugin/plugin.json` — plugin manifest at the repository root (name `perf-ai`,
  version, description, author).
- `.claude-plugin/marketplace.json` — marketplace manifest at the repository root, listing
  exactly one plugin whose `source` is `./` (the repository root is the plugin).
- `skills/perf-analyze/SKILL.md` — the analysis skill inside the plugin (plugin component
  directory `skills/` at the plugin root), invocable as the `/perf-analyze` slash command
  (namespaced form `/perf-ai:perf-analyze` when disambiguation is needed).

A developer installs it into any project via the agent's plugin-marketplace flow:
`/plugin marketplace add <repo-or-local-path>` followed by `/plugin install perf-ai@perf-ai`.
Because the plugin's source is the repository root, the installed plugin checkout contains the
complete `src/` tree, `pyproject.toml`, and report templates — which is what makes FR-014's
"execute the bundled 001 code" possible (see §2). For a session opened directly in this
repository, the same flow applies with the local path as the marketplace source.

**Rationale**: Fixed by the spec clarifications ("A Claude Code plugin … a bare skill entry in
the repository is not sufficient" and "the repository doubles as the plugin and its own
marketplace"). Plugins are the current-generation distribution mechanism for agent-invocable
workflows (Constitution I): versioned installation into any project, update flow, and component
discovery without copying files by hand. The skill carries the full orchestration procedure
(preflight, the parallelism question, subagent fan-out, consolidation) as instructions the
agent executes with its own model access (FR-002), and can reference bundled files portably via
the `${CLAUDE_PLUGIN_ROOT}` variable Claude Code substitutes in plugin components.

**Alternatives considered**:
- *Bare repository skill at `.claude/skills/perf-analyze/`* — the earlier clarification answer,
  explicitly superseded: only discoverable in sessions opened inside this repository; no
  install-into-any-project story. Rejected by spec.
- *Separate marketplace repository listing this repo as a plugin* — a second repository to
  maintain for zero user benefit; the clarification pins manifests to this repo's root. Rejected.
- *MCP server exposing the pipeline as a tool* — heavier (long-running process, per-user client
  configuration), and analysis would run on hosted-API credentials unless the server
  re-implemented the pipeline; contradicts the "agent's own model access" clarification.
- *Plain documentation page telling the user what to prompt* — not invocable, not testable, no
  guaranteed procedure; fails FR-001's "agent-invocable packaging".

## 2. Executing the bundled pipeline code from the plugin checkout (FR-014)

**Decision**: Ship a stdlib-only bootstrap script, `scripts/plugin_run.py`, in the plugin. The
skill never assumes `perf-ai` is on PATH; every deterministic step is invoked as:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/plugin_run.py" agent <subcommand> [args…]
```

`plugin_run.py` (no third-party imports, so it runs on a bare Python):

1. Verifies the interpreter is Python ≥ 3.12; otherwise exits non-zero with a message naming
   the required version and how to obtain it (fail-fast edge case; also checked in skill
   preflight before first use).
2. Provisions a **private virtual environment inside the plugin checkout**
   (`<plugin-root>/.venv`) on first use: creates the venv and `pip install`s the plugin
   checkout itself into it (which pulls the pinned dependencies — Typer, Pydantic, Jinja2,
   Rich, tree-sitter — from PyPI; first run needs network, documented in the README). A stamp
   file recording the package version/`pyproject.toml` hash makes re-provisioning automatic
   after a plugin update and a no-op otherwise.
3. Executes the `perf-ai` entry point from that private venv, forwarding all arguments and the
   exit code unchanged.

This is isolated by construction: nothing is installed into the developer's project, global
Python, or PATH — the only write is inside the plugin's own directory (FR-014 "does not modify
the developer's environment"), and the developer never runs an install command themselves
(FR-014 "no prior package installation").

**Rationale**: FR-014 requires the deterministic steps to be performed by the bundled 001 code,
executed from the installed plugin's own checkout, with fail-fast when the runtime is missing.
A stdlib bootstrap is the smallest mechanism that satisfies all three constraints on every
platform Python supports, costs zero tokens (Constitution II), and keeps error messaging in
code where it is testable (Constitution IV). Steps that already exist in 001 — file discovery,
`StageResult` schema validation, aggregation, report rendering — are executed as-is from the
bundled package; the thin new deterministic steps this feature adds (partitioning, dedup,
result-file bookkeeping) live in the same package (`src/agentrun/`) and ship inside the same
checkout, so no deterministic step is ever reimplemented in skill prose.

**Alternatives considered**:
- *Require the developer to `pip install` the package first* — directly violates FR-014's "no
  prior package installation". Rejected.
- *`uv run` against the plugin checkout* — elegant isolation, but adds a hard dependency on a
  tool the spec never requires the developer to have; Python alone is the documented
  prerequisite. Rejected (could be a later optimization).
- *Vendor all dependencies inside the repo* — removes the first-run network need but bloats the
  repository and adds a vendoring maintenance burden; pip-from-pyproject keeps dependency
  management in one place. Rejected.
- *Venv in `~/.cache/perf-ai/`* — writes outside the plugin directory; a venv inside the
  checkout is the more literal reading of "isolated" and is removed automatically when the
  plugin is uninstalled. Rejected.

## 3. Division of labor: agent does analysis, bundled Python does everything deterministic

**Decision**: Add a new, additive `perf-ai agent` Typer sub-app with two subcommands that the
skill invokes through the bootstrap (§2), neither of which touches the network or reads
`ANTHROPIC_API_KEY`:

- `perf-ai agent scope PATH --max-parallel N [--include G]... [--exclude G]...` — deterministic
  preflight (path exists/readable, recognized code present via the existing
  `src/lib/discovery.py`) and emission of a JSON **work plan**: detected languages, file
  partitions, and one work unit per (stage × partition).
- `perf-ai agent render --results-dir DIR --scope PATH --output-dir DIR` — reads the stage-result
  JSON files the subagents wrote, validates each against the existing Pydantic `StageResult`
  schema, stamps `originating_stage` attribution, merges duplicate findings, then calls the
  **existing** `src/report/aggregator.aggregate()` and `src/report/renderer.write_reports()` to
  produce `perf-report.md` / `perf-report.html`.

The agent (and its subagents) perform only the actual code reading and performance reasoning.

**Rationale**: Mandated by FR-014 (every deterministic step executes the bundled 001 pipeline
code, not a reimplementation) and required for FR-004/SC-002: reusing the exact aggregator,
sort keys, empty-section handling, and Jinja2 templates makes skill reports structurally
identical to CLI reports *by construction* instead of by prompt-following. It also satisfies
Constitution II (zero tokens spent on discovery, partitioning, validation, dedup, rendering),
III (subagent output is schema-validated in code, with unusable output demoted to a failed unit
rather than trusted — FR-010), and IV (deterministic formatting identical across paths). The
`analyze` command and everything it calls remain untouched (FR-003) — the sub-app only *imports*
existing modules.

**Alternatives considered**:
- *Skill re-implements the report format in prose instructions* — the agent would hand-write
  Markdown/HTML; drift from the templates is guaranteed over time, SC-002's "100%
  indistinguishable" is unverifiable, and FR-014 forbids it outright. Rejected.
- *Standalone scripts in `scripts/` instead of CLI subcommands* — same code, but outside the
  packaged entry point and the existing test surface; the bootstrap already bridges "no
  pre-install" to the proper CLI. Rejected.
- *Have subagents call the hosted-API pipeline directly* — requires `ANTHROPIC_API_KEY`,
  violating FR-002. Rejected.

## 4. Controlling subagent concurrency inside Claude Code

**Decision**: The skill instructs the orchestrating agent to run work units in **waves**: launch
at most N subagent (Task tool) invocations in a single message — Claude Code executes agents
launched together concurrently — wait for the wave to complete, then launch the next wave, until
all units are done. N is the confirmed parallelism limit. Stage 1 (structural context) always
runs first as a single unit; its output summary is passed into every later unit's prompt.

**Rationale**: Claude Code's native concurrency unit is "multiple tool calls in one assistant
message"; batching by wave is the only lever the skill controls, and it guarantees the invariant
FR-008 requires ("at no point more than N active"). Stage-1-first mirrors the existing
orchestrator's design where structural context is shared, cached context for stages 2–4
(Constitution II: build shared context once, reuse everywhere).

**Alternatives considered**:
- *Fire all units at once and trust the harness queue* — the harness cap is an implementation
  detail of Claude Code, not a user promise; the observable concurrency could exceed the
  developer's answer. Rejected as violating FR-008.
- *OS-level process pool spawning `claude` CLI processes* — spawns nested agent sessions,
  multiplies token cost, and requires the skill to manage processes; rejected (Constitution II).

## 5. Work-unit partitioning strategy

**Decision**: `perf-ai agent scope` computes the work plan deterministically:

- Stage `structural_context`: always exactly **1 unit** covering the whole scope (it produces
  the shared context; splitting it would defeat reuse).
- Stages `algorithmic_complexity`, `resource_io_efficiency`, `concurrency_scalability`: each is
  split into `P = clamp(ceil(N / 3), 1, file_count)` partitions, where N is `--max-parallel`.
  Files are assigned to partitions by greedy size-balanced bin-packing (largest file first into
  the currently smallest bin), keeping partitions disjoint and roughly equal in bytes.

Total parallelizable units = 3 × P, executed in waves of ≤ N. When the scope has fewer files
than requested parallelism, P collapses toward `file_count`, so the skill naturally "uses only
as many subagents as there is work for" (edge case + FR-008).

**Rationale**: Tying P to N keeps subagent-prompt overhead proportional to the parallelism the
developer actually asked for (Constitution II — more units means more repeated per-unit context;
a developer answering "1" gets exactly 3 sequential stage units, the same shape as the hosted
CLI's stage fan-out). Disjoint partitions mean no file is read twice within a stage, bounding
total read volume near the CLI path's. With N=4, stages 2–4 each split in 2 → 6 units in waves
of 4, which is what SC-004's ≥30% wall-clock improvement is measured against.

**Alternatives considered**:
- *P = N partitions per stage (3 × N units)* — maximizes concurrency but triples prompt overhead
  at high N for little wall-clock gain (waves already keep N busy). Rejected on Constitution II.
- *Partition by top-level directory* — intuitive but degenerate on flat or lopsided repos; the
  size-balanced bin-pack handles both. Rejected.
- *Let the orchestrating agent choose partitions ad hoc* — non-deterministic, untestable,
  and risks overlapping partitions (duplicate findings, duplicate token spend). Rejected.

## 6. Parallelism question UX and the non-interactive path

**Decision**: The parallelism limit reaches the skill in exactly one of two ways:

1. **Pre-supplied**: `/perf-analyze [path] max-parallel=N` — the skill parses N from its
   argument string, applies the same validation (integer, ≥1; values >10 capped to 10 with an
   explicit "capped" notice), and proceeds without asking.
2. **Interactive**: when no value was pre-supplied, the skill *must* ask the developer for the
   maximum number of parallel subagents before any analysis work starts, wait for an explicit
   answer, re-ask (with the reason) on invalid input — zero, negative, non-numeric — and cap
   answers above 10 with a notice. No suggested default is shown (spec: developer must choose).

Fail-fast enforcement is **in code, not only in prose**: `perf-ai agent scope` *requires*
`--max-parallel` and exits non-zero with a clear message when it is missing or out of range
(after skill-side capping, out-of-range should never reach it). A non-interactive agent context
that cannot ask and has no pre-supplied value therefore cannot get past preflight — it fails
fast with the remediation message instead of hanging or inventing a number (FR-009).

**Rationale**: Defense in depth — skill instructions handle the conversation (FR-006, FR-007);
the deterministic gate guarantees the invariant even if instructions are skipped. Matches
Constitution IV (consistent, clear error messaging) and the spec's edge cases verbatim.

**Alternatives considered**:
- *Environment variable for the non-interactive value* — invisible state; a run's limit should
  be auditable from the invocation itself. Rejected.
- *Default to 1 when unanswerable* — explicitly forbidden by clarification ("fail fast rather
  than picking a number"). Rejected.

## 7. Duplicate-finding consolidation (FR-011)

**Decision**: `perf-ai agent render` deduplicates findings *before* aggregation using a
deterministic merge key: `(stage, kind, location.file_path, location.line_start,
normalized(symbol))`. Within a duplicate group, the survivor is chosen by highest severity rank,
then longest `suggested_action`, then first in stable input order (result files processed in
sorted filename order); the survivor's description is kept verbatim (no AI rewriting). The
merge is applied only in the agent path — the hosted-CLI path never produces same-stage
duplicates (its partitioning is per-stage whole-scope) and stays byte-for-byte untouched.

**Rationale**: Parallel same-stage subagents can only overlap at partition boundaries or via
whole-scope context leakage; a location-keyed merge collapses exactly those repeats. Choosing
the survivor by severity is the conservative reading of "conflicting findings" — the report
keeps the stronger claim. Deterministic, token-free, unit-testable (Constitution II, III).
Cross-stage findings at the same location are *not* merged — stage attribution is part of the
report contract, and the existing CLI keeps them separate too (SC-002 parity).

**Alternatives considered**:
- *Semantic dedup via an extra model call* — spends tokens on a problem a key-based merge
  solves; violates Constitution II for marginal gain. Rejected.
- *Description-similarity fuzzy matching* — nondeterministic thresholds, hard to test; the
  location key captures the spec's "same code location" wording directly. Rejected.

## 8. Failure semantics for units, stages, and whole runs

**Decision**: Each work unit must write exactly one result file
(`<stage>--<partition-id>.json`) to the run's results directory. At render time:

- Missing, unparsable, or schema-invalid file → that **unit** failed, with the validation error
  recorded (FR-010 "unusable output" edge case).
- A stage with *some* failed units → stage `completed`; the failed partitions are described in
  the report's coverage note (what was and wasn't covered).
- A stage with *all* units failed → stage `failed`, surfaced in the existing
  `incomplete_stages` section exactly as CLI stage failures are (same template, same wording
  conventions).
- All units of all stages failed → `agent render` writes the failure-noting report and exits
  `3`, mirroring the CLI contract's exit-code semantics; the skill reports the run as failed
  rather than presenting an empty-but-clean report (FR-010, edge case "every subagent fails").

**Rationale**: Maps the new unit granularity onto the *existing* report vocabulary
(`incomplete_stages`, `coverage_note`) so the report contract is unchanged (FR-004) while still
telling the reader precisely what did not complete. Exit-code parity keeps scripting behavior
consistent across paths (Constitution IV).

**Alternatives considered**:
- *New report section for unit failures* — changes the report contract; violates FR-004/SC-002.
  Rejected.
- *Retry failed units automatically* — the orchestrating agent may re-run a wave's failures
  once at its discretion (skill instruction), but the render step must not block on it;
  graceful degradation is the guaranteed behavior, retry is best-effort. (Kept as an optional
  skill instruction, not a contract.)

## 9. Token-cost estimate for the skill path (Constitution II gate)

**Decision & estimate**: The skill path's token profile is dominated by subagents reading their
partition's files plus one shared structural summary:

- Structural unit: reads the work plan + skims the scope ≈ comparable to the CLI's Stage 1
  input budget; produces a summary capped by instruction at ~2–4k tokens.
- Each stage×partition unit: shared summary (~2–4k) + its *disjoint* file slice + fixed stage
  instructions (~1k) → total file-reading volume across a stage ≈ one whole-scope pass, same as
  the CLI stage; overhead vs the CLI is the shared summary repeated per unit
  (≈ 3 × P × 3k tokens ≈ 18–36k extra for N=4, P=2).
- Deterministic steps (bootstrap, scope, render, dedup) cost zero tokens.

Net: per-run cost within the same order of magnitude as the hosted CLI path; parallelism raises
the *burst rate* (N concurrent) but not the total volume, because partitions are disjoint and
the plan/consolidation work is code, not model calls. This estimate goes into the review
checklist required by the constitution's Development Workflow gate.

**Alternatives considered**: streaming the full repo into every subagent (rejected — violates
Constitution II's "targeted context" rule and scales cost with N); re-deriving structural
context per unit (rejected — same reason the CLI caches it).

## 10. Testing approach for a plugin whose skill is Markdown

**Decision**: Split the surface by testability:

- **pytest (unit/contract/integration)** for everything in Python: `agent scope` preflight
  errors, partition determinism and balance, `--max-parallel` bounds, work-plan JSON shape;
  `agent render` schema validation, attribution stamping, dedup rules, coverage-note synthesis,
  exit codes; an integration test proving `agent render` output on fixture stage-results is
  structurally identical to an `analyze`-path report built from the same findings (SC-002);
  **plugin-packaging contract tests** — `.claude-plugin/plugin.json` and
  `.claude-plugin/marketplace.json` parse, agree on the plugin name, and point at paths that
  exist (`skills/perf-analyze/SKILL.md`, `scripts/plugin_run.py`); and **bootstrap tests** —
  `plugin_run.py` rejects an under-version interpreter with the documented message, provisions
  its venv into the checkout on first use, reuses it on the second, and forwards exit codes.
- **Quickstart-scripted manual validation** for behavior that only exists inside a live Claude
  Code session: the marketplace install flow, the interactive parallelism question, wave
  concurrency observation, and the SC-004 timing comparison, with exact steps and expected
  outcomes in `quickstart.md`.
- **README command verification** (SC-006): every README command block is executed as written
  on a fresh checkout as part of the quickstart validation pass.

**Rationale**: The Markdown skill cannot be meaningfully unit-tested, but every guarantee the
spec makes is either (a) enforced by a Python component that *is* tested — including FR-014's
bootstrap and the manifests' integrity — or (b) covered by a scripted manual scenario. This
keeps "it looks like it works" out of the merge decision (constitution's quality gates) without
pretending prose is executable.

**Alternatives considered**: end-to-end automation driving a headless Claude Code session —
attractive later, but out of scope for this feature's budget; the deterministic gates make the
untested prose thin. Rejected for now.

## 11. README structure (FR-012, FR-013)

**Decision**: Replace the placeholder root `README.md` with sections in this order: what the
tool does + constraints (static analysis, no code execution); prerequisites (Python 3.12+ for
both paths; Claude Code for the plugin path); installation — hosted-API CLI (venv +
`pip install -e ".[dev]"`) and agent plugin (marketplace add + plugin install, from GitHub or a
local clone path); configuration (hosted-API path: `ANTHROPIC_API_KEY`; plugin path: none —
explicitly no credentials); running an analysis — hosted CLI (`perf-ai analyze`) and plugin
skill (`/perf-analyze`, the parallelism question, the `max-parallel=N` non-interactive
override, the cap of 10, first-run venv provisioning and its one-time network need); where
reports are written and what they contain; codebase layout for contributors
(directory-by-directory, pointing at stages, aggregator, templates, the agent sub-app, the
skill, and where to change report rendering); running the tests (routine suite and the explicit
live-API suite); troubleshooting (missing key on the CLI path, missing/old Python on the plugin
path, no recognized code, all-stages failure, capped parallelism). Every command is written to
be copy-paste runnable in order on a fresh setup and is executed as part of validation (SC-005,
SC-006).

**Rationale**: Directly mirrors FR-012's enumerated minimum content; ordering follows the
new-developer journey (SC-005's 15-minute path). **Alternatives considered**: docs/ tree with a
thin README — rejected; the spec requires the README itself to carry the content.

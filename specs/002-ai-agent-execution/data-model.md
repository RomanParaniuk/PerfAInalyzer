# Phase 1 Data Model: AI Agent Execution & Parallelism

**Feature**: `002-ai-agent-execution` | **Date**: 2026-08-04

These are in-memory / file-interchange schemas (Pydantic models, JSON documents, and manifest
files exchanged between the plugin's skill, its subagents, and the `perf-ai agent` helper
commands). Nothing is persisted across runs beyond the two report files and the plugin's private
venv (a cache, not analysis state) — statelessness from 001 is preserved. Entities from
`001-perf-analysis-pipeline` (`Finding`, `StageResult`, `AnalysisStage`, `AnalysisRun`,
`ActionItem`, `Report`) are **reused unchanged**; this feature adds the entities below around
them.

## Agent Plugin Package

The spec's "Agent Plugin" entity — the installable unit. The repository root doubles as the
plugin and as its own single-plugin marketplace (FR-001, research §1).

| Artifact | Location (repo root) | Rules |
|---|---|---|
| Plugin manifest | `.claude-plugin/plugin.json` | Valid JSON; `name` = `perf-ai`; carries version/description/author. Name MUST match the marketplace entry. |
| Marketplace manifest | `.claude-plugin/marketplace.json` | Valid JSON; lists exactly one plugin with `source: "./"` (the repository root **is** the plugin), same `name` as the plugin manifest. |
| Analysis skill | `skills/perf-analyze/SKILL.md` | The `/perf-analyze` slash command; Markdown with YAML frontmatter; references bundled files only via `${CLAUDE_PLUGIN_ROOT}` (never absolute paths). |
| Bootstrap | `scripts/plugin_run.py` | Stdlib-only Python (runs on a bare ≥3.12 interpreter); see State below. |
| Bundled pipeline code | `src/`, `pyproject.toml`, templates | The complete 001 package ships inside every installed checkout — the object of FR-014. |

**Validation rules** (enforced by plugin-packaging contract tests, research §10):
- Both manifests parse and agree on the plugin name.
- Every path the manifests and skill depend on exists in the checkout (skill file, bootstrap,
  `pyproject.toml`).
- The skill's deterministic-step invocations go through the bootstrap — the skill never assumes
  `perf-ai` is on PATH and never instructs a reimplementation of a deterministic step (FR-014).

**Bootstrap state machine** (`scripts/plugin_run.py`, research §2):
`no venv → provisioning (create <plugin-root>/.venv, pip install the checkout) → provisioned
(stamp = package version / pyproject hash)`. On every invocation: interpreter < 3.12 → exit
non-zero with the required version and how to obtain it, before anything else (FR-014
fail-fast); stamp matches → exec the private venv's `perf-ai` with the forwarded arguments and
propagate its exit code; stamp stale (plugin updated) → re-provision, then exec. The venv lives
entirely inside the plugin checkout — nothing in the developer's project, global interpreter,
or PATH is modified.

## Work Plan

The deterministic output of `perf-ai agent scope` — everything the orchestrating agent needs to
run one analysis, produced before any model work starts. Serialized as JSON to stdout.

| Field | Type | Notes |
|---|---|---|
| `scope_path` | `str` | Absolute path of the validated analysis target (spec: Execution Path / preflight) |
| `detected_languages` | `list[str]` | From existing `lib.discovery.detect_languages`; non-empty (empty scope fails preflight with exit 1) |
| `file_count` | `int` | Number of discovered source files after include/exclude filtering |
| `max_parallel` | `int` | The confirmed Parallelism Limit echoed back, 1–10 (see validation) |
| `partitions` | `list[Partition]` | Disjoint, size-balanced file groups; `len == P = clamp(ceil(max_parallel / 3), 1, file_count)` |
| `units` | `list[WorkUnit]` | Derived: 1 structural unit + one unit per (analysis stage × partition) |

**Validation rules**:
- `--max-parallel` is REQUIRED input: missing → exit non-zero with a message naming the flag and
  the interactive alternative (FR-009 fail-fast); values `< 1` or non-integer → rejected with
  the reason; values `> 10` → rejected (the skill caps before calling; the command enforces the
  documented bound as defense in depth) (FR-007).
- `partitions` MUST be pairwise disjoint and jointly cover every discovered file (no file
  analyzed twice within a stage, none silently dropped).
- `units` ordering is deterministic: the structural unit first, then stage-major
  (`algorithmic_complexity`, `resource_io_efficiency`, `concurrency_scalability`) ×
  partition-index — same inputs always produce the same plan (testability).

### Partition (embedded value)

| Field | Type | Notes |
|---|---|---|
| `partition_id` | `str` | Stable slug, e.g. `p1`, `p2`, … |
| `files` | `list[str]` | Paths relative to `scope_path`; greedy size-balanced assignment (research §5) |
| `total_bytes` | `int` | Sum of member file sizes; used by tests to assert balance |

## Work Unit

One independently executable piece of analysis work — the thing a subagent instance performs.
Spec entity "Subagent Instance" is the *execution* of one Work Unit.

| Field | Type | Notes |
|---|---|---|
| `unit_id` | `str` | `<stage>--<partition_id>` (structural unit: `structural_context--all`); doubles as the result filename stem |
| `stage` | `StageName` (001 enum) | One of the four fixed stages |
| `partition_id` | `str` | `all` for the structural unit |
| `files` | `list[str]` | The partition's file list (relative paths) — a *list*, never file contents (token rule, research §9) |
| `result_file` | `str` | `<unit_id>.json` — where the subagent must write its Stage Result File |

**State (tracked by the orchestrating agent, not serialized)**:
`pending → launched → (result file written | failed | timed out)`. The skill launches units in
waves of ≤ `max_parallel`, structural unit strictly first (its summary feeds all later prompts).
A unit with no readable, valid result file at render time is a failed unit regardless of how it
died (FR-010: failure, timeout, and unusable output converge to the same handling).

## Stage Result File

The JSON document one subagent writes for its Work Unit — the interchange contract between
agent-side analysis and deterministic consolidation. Payload is exactly 001's
`report_stage_findings` schema (validated by the existing `StageResult` Pydantic model) plus a
thin unit envelope.

| Field | Type | Notes |
|---|---|---|
| `unit_id` | `str` | MUST match the filename stem; mismatch → unit failed (unusable output) |
| `result` | `StageResult` (001 model) | `stage_name`, `findings[]`, `coverage_note` — identical rules to 001: severity/suggested_action required iff `kind == issue`, suggested_action not a restatement, etc. |

**Validation rules** (enforced by `perf-ai agent render`, per file):
- Unparsable JSON, schema-invalid payload, `stage_name` ≠ the unit's stage, or missing file →
  the unit is recorded failed with a human-readable reason; the run continues (FR-010).
- Findings from valid files are stamped with `originating_stage` by the *renderer command*, not
  trusted from the model — same structural-attribution guarantee as 001 (FR-004).

## Parallelism Limit

Spec entity, realized as a validated integer flowing skill → `agent scope` → wave scheduling.

| Property | Rule |
|---|---|
| Source | Pre-supplied skill argument `max-parallel=N`, or the developer's interactive answer; never a default (FR-006) |
| Range | 1–10 after validation; answers > 10 are capped to 10 *with an explicit notice* (FR-007); zero/negative/non-numeric answers are explained and re-asked interactively, rejected fatally when pre-supplied (a pre-supplied value can't be re-asked) |
| Non-interactive | No value + no ability to ask → fail fast before any analysis (FR-009); enforced in code by `agent scope`'s required flag |
| Effect | Upper bound on concurrently launched Work Units per wave (FR-008); actual concurrency is `min(N, remaining units)` |

## Consolidated Run (agent path)

How unit outcomes map back onto 001's unchanged `AnalysisRun`/`Report` at render time — no new
report entity is introduced (FR-004).

| Situation | Mapping |
|---|---|
| All units of a stage valid | Stage `completed`; findings = deduped union of its units' findings |
| Some units of a stage failed | Stage `completed`; failed partitions listed in the report `coverage_note` ("what was and was not covered") |
| All units of a stage failed | Stage `failed` with reason; appears in `incomplete_stages` exactly like a CLI stage failure |
| All units of all stages failed | Run reported as failed: failure-noting report written, exit code `3` (FR-010) |

**Dedup rule (FR-011)** — applied to each stage's union before aggregation:
- Merge key: `(stage, kind, location.file_path, location.line_start, normalized(symbol))`.
- Survivor: highest severity rank → longest `suggested_action` → first in sorted-filename input
  order. Survivor kept verbatim; duplicates dropped (never concatenated or rewritten).
- Cross-stage findings at one location are NOT merged (stage attribution is part of the report
  contract; matches existing CLI behavior).

## Entity relationship summary

```text
Agent Plugin Package 1 ── contains ──> 1 analysis skill + 1 bootstrap + bundled 001 src/
Agent Plugin Package 1 ── listed by ──> 1 marketplace manifest (same repo, source "./")
Work Plan 1 ──── * Partition ──── * file path (disjoint cover of the scope)
Work Plan 1 ──── * Work Unit (1 structural + 3 stages × P partitions)
Work Unit 1 ──── 0..1 Stage Result File ──── 1 StageResult (001) ──── * StageFinding (001)
Stage Result Files * ──── render ────> AnalysisRun (001) ──── 1 Report (001, unchanged contract)
Parallelism Limit 1 ──── bounds ────> concurrent Work Unit executions per wave
```

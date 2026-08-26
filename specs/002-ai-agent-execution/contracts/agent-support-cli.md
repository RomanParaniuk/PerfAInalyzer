# Contract: Agent Support CLI (`perf-ai agent`)

**Feature**: `002-ai-agent-execution` | **Date**: 2026-08-04

The deterministic helper surface the skill shells out to. Both subcommands are offline: they
never call a model, never read `ANTHROPIC_API_KEY`, and complete in seconds. They are additive —
`perf-ai analyze` and its contract (001 `contracts/cli-interface.md`) are unchanged (FR-003).
Though designed for the skill, they are ordinary CLI commands and behave sanely when run by hand.

**Invocation contexts** (same code, two front doors):

- **Installed plugin** (the skill's path, FR-014): invoked through the bootstrap —
  `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/plugin_run.py" agent <subcommand> …` — which
  executes the bundled checkout's `perf-ai` from a private venv and forwards exit codes
  unchanged (see [plugin-packaging.md](./plugin-packaging.md)).
- **Developer checkout** (tests, hand runs): `perf-ai agent <subcommand> …` after the usual
  editable install.

Everything below is stated in terms of `perf-ai agent …` and holds identically through the
bootstrap.

## `perf-ai agent scope`

Preflight + work-plan generation (zero tokens).

```text
perf-ai agent scope [PATH] --max-parallel N [OPTIONS]
```

| Argument/Option | Required | Default | Description |
|---|---|---|---|
| `PATH` | No | current working directory | Analysis target; must exist and be readable. |
| `--max-parallel N` | **Yes** | none — intentionally no default | Confirmed Parallelism Limit. Missing → error naming the flag (this is the coded fail-fast gate of FR-009). Accepted range 1–10; out-of-range or non-integer → error explaining the bound (FR-007). |
| `--include GLOB` (repeatable) | No | none | Same semantics as `perf-ai analyze`. |
| `--exclude GLOB` (repeatable) | No | same defaults as `analyze` | Same semantics as `perf-ai analyze`. |

**stdout**: on success, a single JSON document — the Work Plan of `data-model.md` (scope path,
detected languages, file count, echoed `max_parallel`, disjoint size-balanced `partitions`,
ordered `units` with `unit_id`/`stage`/`files`/`result_file`). Deterministic: identical inputs
produce an identical plan.

**Exit codes**:

| Code | Meaning |
|---|---|
| `0` | Plan written to stdout. |
| `1` | Invalid target — `PATH` missing/unreadable, or no source code in a recognized language found. Message names the problem and the fix. |
| `2` | Invalid invocation — `--max-parallel` missing, non-integer, or outside 1–10. Message states the accepted range and (when missing) the interactive alternative. |

## `perf-ai agent render`

Validation + consolidation + report rendering (zero tokens).

```text
perf-ai agent render --results-dir DIR --scope PATH [--output-dir DIR]
```

| Option | Required | Default | Description |
|---|---|---|---|
| `--results-dir DIR` | Yes | — | Directory containing the Stage Result Files (`<unit_id>.json`) subagents wrote, plus the run's work plan (`workplan.json`) so render knows the expected unit set. |
| `--scope PATH` | Yes | — | The analyzed scope path (recorded in the report header, as in 001). |
| `--output-dir DIR` | No | current working directory | Where `perf-report.md` / `perf-report.html` are written, overwriting prior runs' files. |

**Behavior**:

1. Load the work plan; every expected unit with a missing, unparsable, schema-invalid, or
   wrong-stage result file is recorded as a **failed unit** with a human-readable reason — the
   run continues (FR-010).
2. Valid findings are stamped with `originating_stage` structurally (never trusted from the
   model), exactly as 001's orchestrator does (FR-004).
3. Per stage: findings from its units are unioned and deduplicated with the merge rule of
   `data-model.md` (location-keyed; severity-first survivor) (FR-011).
4. Stage status mapping: all units valid → `completed`; some failed → `completed` with the
   failed partitions described in the report's coverage note; all failed → stage `failed`,
   listed in `incomplete_stages` like any 001 stage failure.
5. The **existing** aggregator (`src/report/aggregator.aggregate`) and renderer
   (`src/report/renderer.write_reports`) produce both report files — the skill path cannot
   diverge from the CLI report contract because it executes the same code (SC-002).

**Exit codes** (mirrors the 001 CLI contract's semantics):

| Code | Meaning |
|---|---|
| `0` | Report written — including partial-results runs where some units/stages failed. |
| `1` | Invalid invocation — results dir missing/unreadable, work plan absent or unparsable, or scope path invalid. |
| `3` | Total failure — every unit of every stage failed. A failure-noting report is still written; the exit code signals failure to the orchestrating skill (which then reports the run as failed, FR-010). |

Exit code `2` is reserved (configuration error in 001); it is not used here because the agent
path has no credential configuration by design (FR-002).

## Stage Result File schema (input to `render`)

Defined normatively in `data-model.md` ("Stage Result File"): a JSON object
`{"unit_id": str, "result": <001 report_stage_findings payload>}` written to
`<results-dir>/<unit_id>.json`. The payload is validated by the existing `StageResult` Pydantic
model with all 001 cross-field rules (severity/suggested_action iff issue; suggested_action not
a restatement — restatements drop the derived action item as a logged data-quality note, exactly
as in 001).

## Versioning

Internal contract between the skill and the helper CLI, shipped in lockstep in one repository.
Changes require updating the skill, the subcommands, and their tests in the same change set; no
independent backward-compatibility guarantee across feature revisions (same policy as 001's
stage-output schema).

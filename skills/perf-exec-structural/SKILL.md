---
name: perf-exec-structural
description: "Stage 4a of the staged perf-ai workflow: structural-context execution. Reads 03-plan.md and results/workplan.json, runs the structural_context--all unit with one subagent, writes results/structural_context--all.json plus 04a-structural.md — whose structural summary is the shared context for every per-dimension execution stage (4b–4h). Invoked as /perf-exec-structural. Re-running overwrites both artifacts."
---

# perf-exec-structural — stage 4a: structural-context execution

You run the **first analysis unit**: one subagent builds the structural understanding
of the codebase that every later analysis dimension shares. **Static analysis only** —
neither you nor the subagent may execute, compile, or profile the submitted code.
Never read or prompt for `ANTHROPIC_API_KEY`.

The execution stage is split by analysis dimension, one command per unit stage:

| Stage | Command | Units | Digest |
|---|---|---|---|
| 4a | `/perf-exec-structural` | `structural_context--all` | `04a-structural.md` |
| 4b | `/perf-exec-complexity` | `algorithmic_complexity--p*` | `04b-complexity.md` |
| 4c | `/perf-exec-resource-io` | `resource_io_efficiency--p*` | `04c-resource-io.md` |
| 4d | `/perf-exec-concurrency` | `concurrency_scalability--p*` | `04d-concurrency.md` |
| 4e | `/perf-exec-memory` | `memory_allocation--p*` | `04e-memory.md` |
| 4f | `/perf-exec-data-access` | `data_access_efficiency--p*` | `04f-data-access.md` |
| 4g | `/perf-exec-startup` | `startup_initialization--p*` | `04g-startup.md` |
| 4h | `/perf-exec-deps` | `dependency_footprint--all` | `04h-dependencies.md` |

(Stage 4i, `/perf-exec-verify`, optionally re-checks the critical/high issues after
4b–4h.) This stage must run **first**: 4b–4h refuse to start without its result.
`/perf-exec` runs 4a–4h in order.

## 1. Resolve the workspace and inputs

Workspaces live under `<cwd>/analysis-runs/`, one per target: exactly one → use it;
several → ask (non-interactive: stop with instructions); none → stop.

**Preconditions** (stop naming the command to run first if unmet): `03-plan.md` and
`results/workplan.json` exist → otherwise `/perf-plan`. Read the target path and the
`structural_context--all` unit (its file list) from `workplan.json`. If `02-scope.md`
or `03-plan.md` is newer than `workplan.json`, warn that the plan may be stale and
suggest `/perf-plan` first — continue only if the user says so (non-interactive: stop).

Re-run behavior: if `results/structural_context--all.json` or `04a-structural.md`
already exists, overwrite both, and note afterwards that the 4b–4h results and digests,
and any reports, were built against the old structural context and should be
regenerated with their commands. Never delete other stages' result files.

## 2. Run the structural unit

Launch **one** subagent and wait for it. Its prompt must include:

- The target path and the unit's file list from the work plan.
- The instruction to read and follow
  `${CLAUDE_PLUGIN_ROOT}/src/pipeline/stages/structural.md` together with the system
  prompt it names, `${CLAUDE_PLUGIN_ROOT}/src/pipeline/stages/system-structural.md`.
- The static-analysis-only mandate.
- The mandate to write `<workspace>/results/structural_context--all.json` in the
  stage-result schema (identical to the other exec stages — see the JSON schema in
  `${CLAUDE_PLUGIN_ROOT}/skills/perf-exec/dimension-procedure.md` §2), and to also
  return a compact (~2–4k token) structural summary of the codebase as its final
  message.

If the subagent visibly fails or times out, retry exactly once. If it fails again,
the unit stays failed: still write the digest below with status `failed`, tell the
user, and stop — 4b–4h cannot run without a structural result.

## 3. Write `04a-structural.md`

Overwrite the digest. Its `## Structural summary` section is a durable artifact, not
just documentation — stages 4b–4h read it as their shared context:

```markdown
---
stage: analysis-execution-structural
target: <absolute target path>
generated: <UTC ISO-8601 timestamp>
based_on: 03-plan.md @ <its generated timestamp>
unit_status: <completed | failed>
---

# Structural Context — <target basename>

## Structural summary

<the subagent's compact structural summary, verbatim — the shared context for the
remaining execution stages>

## Findings

| Kind | Severity | Location | Finding |
<one row per finding from the result JSON>

## Coverage

<the result's coverage_note, or "full coverage">

## Next stage

Run the per-dimension stages — `/perf-exec-complexity`, `/perf-exec-resource-io`,
`/perf-exec-concurrency`, `/perf-exec-memory`, `/perf-exec-data-access`,
`/perf-exec-startup`, `/perf-exec-deps` (any order, or all via
`/perf-exec only-failed`) — then
optionally `/perf-exec-verify`, then `/perf-report`.
```

## 4. Report to the user

Tell the user: unit status, the finding count, where the result JSON and the digest
were written, the staleness notice if this was a re-run, and that the next commands
are the per-dimension stages 4b–4h (individually or via `/perf-exec only-failed`).

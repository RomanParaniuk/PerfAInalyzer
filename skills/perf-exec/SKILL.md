---
name: perf-exec
description: "Stage 4 of the staged perf-ai workflow: analysis execution. Reads 03-plan.md and results/workplan.json, runs the four-dimension performance analysis unit by unit with parallel subagents honoring each component's review depth, writes one results/<unit>.json per unit plus the 04-findings.md digest — the inputs for /perf-report. Invoked as /perf-exec [only-failed]. Default re-run redoes every unit; only-failed redoes just missing/failed ones."
---

# perf-exec — stage 4: analysis execution

You orchestrate the expensive stage: subagents read the code and reason about
performance, checkpointing one result file per work unit. **Static analysis only** —
neither you nor any subagent may execute, compile, or profile the submitted code. Never
read or prompt for `ANTHROPIC_API_KEY`.

## 1. Resolve the workspace and inputs

Workspaces live under `<cwd>/analysis-runs/`, one per target: exactly one → use it;
several → ask (non-interactive: stop with instructions); none → stop.

**Preconditions** (stop naming the command to run first if unmet): `03-plan.md` and
`results/workplan.json` exist → otherwise `/perf-plan`; `02-scope.md` exists (for depth
guidance) → otherwise `/perf-scope`. Read the target path, N (`max_parallel`), and the
ordered `units` from `workplan.json`; read the component→depth mapping from
`02-scope.md`. If `02-scope.md` or `03-plan.md` is newer than `workplan.json`, warn
that the plan may be stale and suggest `/perf-plan` first — continue only if the user
says so (non-interactive: stop).

**Unit selection**:

- Default: analyze **all** units. Delete existing `results/<unit>.json` files first
  (never `workplan.json`) so the stage's output is rewritten cleanly.
- `only-failed` argument: keep every existing result file that parses as the schema
  below with the correct `unit_id`; analyze only units whose file is missing or
  invalid. Report which units are reused and which will run before starting.

## 2. Run the structural unit first

If the `structural_context--all` unit is selected, launch **one** subagent for it and
wait for it before anything else — its summary is shared context for every later unit.
(If it is being reused under `only-failed`, derive the shared summary by reading its
existing JSON.) The subagent prompt must include:

- The target path and the unit's file list from the work plan.
- The instruction to read and follow
  `${CLAUDE_PLUGIN_ROOT}/src/pipeline/stages/structural.md` together with the system
  prompt it names, `${CLAUDE_PLUGIN_ROOT}/src/pipeline/stages/system-structural.md`.
- The static-analysis-only mandate.
- The mandate to write `<workspace>/results/structural_context--all.json` in the
  stage-result schema below, and to also return a compact (~2–4k token) structural
  summary as its final message.

## 3. Run the remaining units in waves of at most N

Stage instruction files (each names its system prompt in frontmatter —
`system-sonnet.md` for all three):

| Unit stage | Instructions file |
|---|---|
| `algorithmic_complexity` | `${CLAUDE_PLUGIN_ROOT}/src/pipeline/stages/complexity.md` |
| `resource_io_efficiency` | `${CLAUDE_PLUGIN_ROOT}/src/pipeline/stages/resource_io.md` |
| `concurrency_scalability` | `${CLAUDE_PLUGIN_ROOT}/src/pipeline/stages/concurrency.md` |

Scheduling — hard guarantees, identical to the one-shot skill: waves of at most N,
wait for a whole wave before the next, never more than N active, never invent work to
fill a wave, report per-wave progress (launched / completed / failed), no raw stack
traces. After the final wave, one single retry pass over visibly failed/timed-out
units, still in waves of at most N; units that fail again stay failed.

Each subagent prompt must carry:

- The shared structural summary.
- The target path and **its unit's** file list only.
- **Depth directives**: using the scope table's globs, state for each group of the
  unit's files its component's depth — `deep`: read every listed file fully and apply
  the stage's checks thoroughly; `standard`: normal coverage; `skim`: examine only
  entry points and obvious hot paths among these files, and say so in the
  coverage_note. (Skip components have no files here by construction.)
- The instruction to read and follow its stage's instructions file plus the system
  prompt it names.
- The static-analysis-only mandate.
- The mandate to write exactly one file, `<workspace>/results/<unit_id>.json`:

```json
{
  "unit_id": "<the unit's unit_id, exactly>",
  "result": {
    "stage_name": "<the unit's stage, exactly>",
    "findings": [
      {
        "kind": "issue | valuable_finding",
        "description": "what was found and why it matters",
        "location": {
          "file_path": "path relative to the scope root",
          "symbol": "function/class name or null",
          "line_start": 1,
          "line_end": 1
        },
        "severity": "critical | high | medium | low — required for issues, null otherwise",
        "suggested_action": "a concrete fix, not a restatement — required for issues, null otherwise"
      }
    ],
    "coverage_note": "what could not be covered, or null"
  }
}
```

A unit whose subagent fails, times out, or writes an unusable file is a **failed
unit**: do not abort the run — record it and continue.

## 4. Write `04-findings.md`

Overwrite the digest (a human summary; the JSONs stay the machine input for stage 5):

```markdown
---
stage: analysis-execution
target: <absolute target path>
generated: <UTC ISO-8601 timestamp>
based_on: 03-plan.md @ <its generated timestamp>
units_completed: <n>/<total>
---

# Findings Digest — <target basename>

## Totals

<issues by severity; valuable findings; per analysis dimension>

## Top issues

| Severity | Location | Issue | Suggested action |
<the critical and high issues, one row each>

## Unit status

| Unit | Status | Findings |
<completed / failed / reused per unit>

## Not covered

<failed units, skim-limited components, and components skipped by scope — or "full
coverage">

## Next stage

Run `/perf-report [output-dir]` to build perf-report.md / perf-report.html.
```

## 5. Report to the user

Tell the user: units completed / failed / reused, the severity totals, where the digest
and result files were written, and that the next command is `/perf-report`.

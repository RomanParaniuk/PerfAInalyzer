# Shared procedure for the per-dimension execution stages (4b–4g)

This is the single procedure behind `/perf-exec-complexity`, `/perf-exec-resource-io`,
`/perf-exec-concurrency`, `/perf-exec-memory`, `/perf-exec-data-access`, and
`/perf-exec-startup`. Each of those skills defines only a **parameter table** —
`Stage`, `Units`, `Instructions file`, `Digest file`, `Digest stage value`, and
`Digest title` — and points here. Wherever this file says `<Stage>`, `<Units>`,
`<Instructions file>`, `<Digest file>`, `<Digest stage value>`, or `<Digest title>`,
substitute the invoking skill's value. The stages may run in any order relative to
each other once `/perf-exec-structural` has run; `/perf-exec` runs all of them in
sequence.

**Static analysis only** — neither you nor any subagent may execute, compile, or
profile the submitted code. Never read or prompt for `ANTHROPIC_API_KEY`.

## 1. Resolve the workspace and inputs

Workspaces live under `<cwd>/analysis-runs/`, one per target: exactly one → use it;
several → ask (non-interactive: stop with instructions); none → stop.

**Preconditions** (stop naming the command to run first if unmet):

- `03-plan.md` and `results/workplan.json` exist → otherwise `/perf-plan`.
- `02-scope.md` exists (for depth guidance) → otherwise `/perf-scope`.
- `results/structural_context--all.json` exists and parses → otherwise
  `/perf-exec-structural`.

Read the target path, N (`max_parallel`), and this stage's ordered units from
`workplan.json`; the component→depth mapping from `02-scope.md`; and the **shared
structural summary** from `04a-structural.md`'s `## Structural summary` section (if
that file is missing, derive a compact summary from the structural result JSON's
findings instead). If `02-scope.md` or `03-plan.md` is newer than `workplan.json`,
warn that the plan may be stale and suggest `/perf-plan` first — continue only if the
user says so (non-interactive: stop).

**Unit selection** (this stage's units only — never touch other stages' files):

- Default: analyze **all** of this stage's units. Delete existing
  `results/<Stage>--*.json` files first (never `workplan.json`, never
  other stages' results) so the stage's output is rewritten cleanly.
- `only-failed`: keep every existing result file of this stage that parses as the
  schema below with the correct `unit_id`; analyze only units whose file is missing or
  invalid. Report which units are reused and which will run before starting.

## 2. Run the units in waves of at most N

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
- The instruction to read and follow this stage's `<Instructions file>` plus the
  system prompt its frontmatter names (`system-sonnet.md` for every dimension).
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

## 3. Write the digest

Overwrite `<Digest file>` (a human summary; the JSONs stay the machine input for
`/perf-report`):

```markdown
---
stage: <Digest stage value>
target: <absolute target path>
generated: <UTC ISO-8601 timestamp>
based_on: 03-plan.md @ <its generated timestamp>
units_completed: <n>/<total of this stage's units>
---

<Digest title> — <target basename>

## Totals

<issues by severity; valuable findings>

## Top issues

| Severity | Location | Issue | Suggested action |
<the critical and high issues, one row each>

## Unit status

| Unit | Status | Findings |
<completed / failed / reused per unit>

## Not covered

<failed units, skim-limited components — or "full coverage">

## Next stage

Run any remaining execution stages (4b–4g, see `/perf-exec`) if not done yet, then
optionally `/perf-exec-verify`, then `/perf-report [output-dir]`.
```

## 4. Report to the user

Tell the user: units completed / failed / reused, the severity totals, where the
digest and result files were written, and which execution stages (4a–4g) still lack
results before `/perf-report`.

---
name: perf-exec
description: "Stage 4 of the staged perf-ai workflow: analysis execution, umbrella over the seven per-dimension execution stages. Runs /perf-exec-structural, then /perf-exec-complexity, /perf-exec-resource-io, /perf-exec-concurrency, /perf-exec-memory, /perf-exec-data-access, and /perf-exec-startup in order — each writes its results/<unit>.json files and its own 04a–04g digest. Invoked as /perf-exec [only-failed]. Default re-run redoes every unit of every dimension; only-failed redoes just missing/failed ones."
---

# perf-exec — stage 4: analysis execution (umbrella)

The execution stage is **split by analysis dimension**, one command per unit stage.
This command is the umbrella: it runs all seven in order. Run the sub-commands
directly instead when you want to execute, inspect, or re-run one dimension at a time.

| Stage | Command | Units | Digest |
|---|---|---|---|
| 4a | `/perf-exec-structural` | `structural_context--all` | `04a-structural.md` |
| 4b | `/perf-exec-complexity` | `algorithmic_complexity--p*` | `04b-complexity.md` |
| 4c | `/perf-exec-resource-io` | `resource_io_efficiency--p*` | `04c-resource-io.md` |
| 4d | `/perf-exec-concurrency` | `concurrency_scalability--p*` | `04d-concurrency.md` |
| 4e | `/perf-exec-memory` | `memory_allocation--p*` | `04e-memory.md` |
| 4f | `/perf-exec-data-access` | `data_access_efficiency--p*` | `04f-data-access.md` |
| 4g | `/perf-exec-startup` | `startup_initialization--p*` | `04g-startup.md` |

There is also an **optional** stage 4h, `/perf-exec-verify`, which adversarially
re-checks the critical/high issues found by 4b–4g; this umbrella does **not** run it
automatically — invoke it separately after execution when you want verified findings.

**Static analysis only** — neither you nor any subagent may execute, compile, or
profile the submitted code. Never read or prompt for `ANTHROPIC_API_KEY`.

## Procedure

1. Resolve the workspace and check the stage-3 preconditions exactly as
   `${CLAUDE_PLUGIN_ROOT}/skills/perf-exec-structural/SKILL.md` §1 describes
   (workspace under `<cwd>/analysis-runs/`; `03-plan.md` + `results/workplan.json`
   exist, else `/perf-plan`; `02-scope.md` exists, else `/perf-scope`; staleness
   warning if the plan predates its inputs). Perform the staleness check **once
   here** — do not repeat it per sub-stage.
2. Run stage 4a: follow the procedure in
   `${CLAUDE_PLUGIN_ROOT}/skills/perf-exec-structural/SKILL.md` (skipping its
   already-done workspace/staleness checks). With `only-failed`, reuse an existing
   valid `results/structural_context--all.json` instead of re-running it, deriving
   the shared summary from `04a-structural.md` or the JSON. If the structural unit
   ends failed, **stop** after writing its digest — 4b–4g cannot run without it.
3. Run stages 4b–4g in order. All six share one procedure,
   `${CLAUDE_PLUGIN_ROOT}/skills/perf-exec/dimension-procedure.md`; each dimension's
   skill (`${CLAUDE_PLUGIN_ROOT}/skills/perf-exec-<name>/SKILL.md`) holds only its
   parameter table (stage key, units, instructions file, digest). Read the shared
   procedure once, then execute it per dimension with that dimension's parameters
   (again skipping the repeated workspace/staleness checks), passing `only-failed`
   through to each. Every scheduling guarantee in the shared procedure holds
   unchanged — waves of at most N, one retry pass, failed units recorded, never
   aborting the run. A failed dimension never blocks the remaining dimensions.
4. Report to the user, per dimension: units completed / failed / reused and where
   its digest was written — then the overall severity totals, that
   `/perf-exec-verify` can optionally re-check the critical/high issues before
   reporting, and that the next command is `/perf-report [output-dir]`.

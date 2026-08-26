---
name: perf-exec-startup
description: "Stage 4g of the staged perf-ai workflow: startup & initialization execution. Reads results/workplan.json, the depth table from 02-scope.md, and the structural summary from 04a-structural.md, runs the startup_initialization--p* units in waves of at most N parallel subagents, writes one results/<unit>.json per unit plus the 04g-startup.md digest. Invoked as /perf-exec-startup [only-failed]. Default re-run redoes all its units; only-failed redoes just missing/failed ones."
---

# perf-exec-startup — stage 4g: startup & initialization execution

You run every **`startup_initialization`** work unit — one of the per-dimension execution stages
(4b–4g) that follow `/perf-exec-structural`. **Static analysis only** — neither you
nor any subagent may execute, compile, or profile the submitted code. Never read or
prompt for `ANTHROPIC_API_KEY`.

**Parameters** for the shared procedure:

| Parameter | Value |
|---|---|
| Stage | `startup_initialization` |
| Units | `startup_initialization--p*` |
| Instructions file | `${CLAUDE_PLUGIN_ROOT}/src/pipeline/stages/startup.md` |
| Digest file | `04g-startup.md` |
| Digest stage value | `analysis-execution-startup` |
| Digest title | `# Startup & Initialization Findings` |

## Procedure

Read `${CLAUDE_PLUGIN_ROOT}/skills/perf-exec/dimension-procedure.md` and follow
every step in it with the parameters above — workspace/precondition checks, unit
selection (honoring an `only-failed` argument), waves of at most N subagents, the
result-file schema, the digest, and the user report. Every hard guarantee in that
file applies unchanged.

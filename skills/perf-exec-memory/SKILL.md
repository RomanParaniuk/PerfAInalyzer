---
name: perf-exec-memory
description: "Stage 4e of the staged perf-ai workflow: memory & allocation execution. Reads results/workplan.json, the depth table from 02-scope.md, and the structural summary from 04a-structural.md, runs the memory_allocation--p* units in waves of at most N parallel subagents, writes one results/<unit>.json per unit plus the 04e-memory.md digest. Invoked as /perf-exec-memory [only-failed]. Default re-run redoes all its units; only-failed redoes just missing/failed ones."
---

# perf-exec-memory — stage 4e: memory & allocation execution

You run every **`memory_allocation`** work unit — one of the per-dimension execution stages
(4b–4g) that follow `/perf-exec-structural`. **Static analysis only** — neither you
nor any subagent may execute, compile, or profile the submitted code. Never read or
prompt for `ANTHROPIC_API_KEY`.

**Parameters** for the shared procedure:

| Parameter | Value |
|---|---|
| Stage | `memory_allocation` |
| Units | `memory_allocation--p*` |
| Instructions file | `${CLAUDE_PLUGIN_ROOT}/src/pipeline/stages/memory.md` |
| Digest file | `04e-memory.md` |
| Digest stage value | `analysis-execution-memory` |
| Digest title | `# Memory & Allocation Findings` |

## Procedure

Read `${CLAUDE_PLUGIN_ROOT}/skills/perf-exec/dimension-procedure.md` and follow
every step in it with the parameters above — workspace/precondition checks, unit
selection (honoring an `only-failed` argument), waves of at most N subagents, the
result-file schema, the digest, and the user report. Every hard guarantee in that
file applies unchanged.

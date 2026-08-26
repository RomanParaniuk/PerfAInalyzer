---
name: perf-exec-resource-io
description: "Stage 4c of the staged perf-ai workflow: resource & I/O efficiency execution. Reads results/workplan.json, the depth table from 02-scope.md, and the structural summary from 04a-structural.md, runs the resource_io_efficiency--p* units in waves of at most N parallel subagents, writes one results/<unit>.json per unit plus the 04c-resource-io.md digest. Invoked as /perf-exec-resource-io [only-failed]. Default re-run redoes all its units; only-failed redoes just missing/failed ones."
---

# perf-exec-resource-io — stage 4c: resource & I/O efficiency execution

You run every **`resource_io_efficiency`** work unit — one of the per-dimension execution stages
(4b–4g) that follow `/perf-exec-structural`. **Static analysis only** — neither you
nor any subagent may execute, compile, or profile the submitted code. Never read or
prompt for `ANTHROPIC_API_KEY`.

**Parameters** for the shared procedure:

| Parameter | Value |
|---|---|
| Stage | `resource_io_efficiency` |
| Units | `resource_io_efficiency--p*` |
| Instructions file | `${CLAUDE_PLUGIN_ROOT}/src/pipeline/stages/resource_io.md` |
| Digest file | `04c-resource-io.md` |
| Digest stage value | `analysis-execution-resource-io` |
| Digest title | `# Resource & I/O Efficiency Findings` |

## Procedure

Read `${CLAUDE_PLUGIN_ROOT}/skills/perf-exec/dimension-procedure.md` and follow
every step in it with the parameters above — workspace/precondition checks, unit
selection (honoring an `only-failed` argument), waves of at most N subagents, the
result-file schema, the digest, and the user report. Every hard guarantee in that
file applies unchanged.

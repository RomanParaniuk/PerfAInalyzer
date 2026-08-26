---
name: perf-exec-data-access
description: "Stage 4f of the staged perf-ai workflow: data access & query efficiency execution. Reads results/workplan.json, the depth table from 02-scope.md, and the structural summary from 04a-structural.md, runs the data_access_efficiency--p* units in waves of at most N parallel subagents, writes one results/<unit>.json per unit plus the 04f-data-access.md digest. Invoked as /perf-exec-data-access [only-failed]. Default re-run redoes all its units; only-failed redoes just missing/failed ones."
---

# perf-exec-data-access — stage 4f: data access & query efficiency execution

You run every **`data_access_efficiency`** work unit — one of the per-dimension execution stages
(4b–4g) that follow `/perf-exec-structural`. **Static analysis only** — neither you
nor any subagent may execute, compile, or profile the submitted code. Never read or
prompt for `ANTHROPIC_API_KEY`.

**Parameters** for the shared procedure:

| Parameter | Value |
|---|---|
| Stage | `data_access_efficiency` |
| Units | `data_access_efficiency--p*` |
| Instructions file | `${CLAUDE_PLUGIN_ROOT}/src/pipeline/stages/data_access.md` |
| Digest file | `04f-data-access.md` |
| Digest stage value | `analysis-execution-data-access` |
| Digest title | `# Data Access & Query Efficiency Findings` |

## Procedure

Read `${CLAUDE_PLUGIN_ROOT}/skills/perf-exec/dimension-procedure.md` and follow
every step in it with the parameters above — workspace/precondition checks, unit
selection (honoring an `only-failed` argument), waves of at most N subagents, the
result-file schema, the digest, and the user report. Every hard guarantee in that
file applies unchanged.

---
name: perf-exec-concurrency
description: "Stage 4d of the staged perf-ai workflow: concurrency & scalability execution. Reads results/workplan.json, the depth table from 02-scope.md, and the structural summary from 04a-structural.md, runs the concurrency_scalability--p* units in waves of at most N parallel subagents, writes one results/<unit>.json per unit plus the 04d-concurrency.md digest. Invoked as /perf-exec-concurrency [only-failed]. Default re-run redoes all its units; only-failed redoes just missing/failed ones."
---

# perf-exec-concurrency — stage 4d: concurrency & scalability execution

You run every **`concurrency_scalability`** work unit — one of the per-dimension execution stages
(4b–4g) that follow `/perf-exec-structural`. **Static analysis only** — neither you
nor any subagent may execute, compile, or profile the submitted code. Never read or
prompt for `ANTHROPIC_API_KEY`.

**Parameters** for the shared procedure:

| Parameter | Value |
|---|---|
| Stage | `concurrency_scalability` |
| Units | `concurrency_scalability--p*` |
| Instructions file | `${CLAUDE_PLUGIN_ROOT}/src/pipeline/stages/concurrency.md` |
| Digest file | `04d-concurrency.md` |
| Digest stage value | `analysis-execution-concurrency` |
| Digest title | `# Concurrency & Scalability Findings` |

## Procedure

Read `${CLAUDE_PLUGIN_ROOT}/skills/perf-exec/dimension-procedure.md` and follow
every step in it with the parameters above — workspace/precondition checks, unit
selection (honoring an `only-failed` argument), waves of at most N subagents, the
result-file schema, the digest, and the user report. Every hard guarantee in that
file applies unchanged.

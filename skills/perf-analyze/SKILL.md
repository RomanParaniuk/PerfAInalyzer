---
name: perf-analyze
description: Run a four-stage static performance analysis of a codebase using parallel subagents and produce perf-report.md / perf-report.html. Use when the user asks to analyze performance, find performance issues or bottlenecks, or run perf-ai on a path. Invoked as /perf-analyze [path] [max-parallel=N]. Uses the invoking agent's own model access — never an API key.
---

# perf-analyze — agent-path performance analysis

You orchestrate the perf-ai analysis pipeline: deterministic steps run the **bundled
pipeline code** through the plugin bootstrap (never re-implement them, never assume
`perf-ai` is on PATH), and the actual code reading and performance reasoning is done by
subagents with your own model access. Never read, require, or prompt for
`ANTHROPIC_API_KEY` or any hosted-provider credential. Static analysis only: neither you
nor any subagent may execute, compile, or profile the submitted code.

Every deterministic step is invoked as:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/plugin_run.py" agent <subcommand> [args...]
```

On the first run this provisions a private virtual environment inside the plugin
directory (one-time network need; tell the user it may take a minute). It never modifies
their project, global Python, or PATH.

## 1. Parse the arguments

From the invocation `/perf-analyze [path] [max-parallel=N]`:

- `path` — the directory to analyze. Default: the current working directory.
- `max-parallel=N` — pre-supplied parallelism limit (optional).

Validate a pre-supplied N before anything else:

- Not an integer, zero, or negative → **stop** and report: the value is invalid, the
  accepted range is 1–10 (there is no one to re-ask when the value was pre-supplied).
- Greater than 10 → **cap it to 10** and tell the user explicitly: "your value N was
  capped to 10 (the documented maximum)". Continue with 10.

### The parallelism question (when no `max-parallel` was pre-supplied)

Before **any** analysis work starts, ask the developer:

> "How many subagents may run in parallel for this analysis? (1–10)"

and **wait for an explicit answer**. Rules — these are hard guarantees:

- Show **no suggested default** and never proceed on an implied one. The developer must
  choose the number.
- Invalid answers — zero, negative, non-numeric — are rejected with the reason ("0 would
  run nothing; the accepted range is 1–10", "that is not a number; the accepted range is
  1–10") and the question is asked again.
- Answers above 10 are **capped to 10** with an explicit notice: "your value N was
  capped to 10 (the documented maximum)".
- **Non-interactive contexts fail fast**: if the question cannot be presented or no
  answer arrives (e.g. a headless `claude -p` run), do not pick a number and do not
  hang — stop immediately with: "no parallelism limit was provided and this session
  cannot ask; re-invoke as `/perf-analyze [path] max-parallel=N`."

## 2. Preflight (before any analysis work)

1. Check the runtime: run `python3 --version`. If `python3` is missing or older than
   3.12, **stop** and tell the user exactly what is missing and how to get it (install
   Python 3.12+ from https://www.python.org/downloads/ or their package manager). Never
   start a run that is known to die midway.
2. Validate the target and get the work plan:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/plugin_run.py" agent scope <path> --max-parallel <N>
   ```

   Append any `--include`/`--exclude` globs the user asked for. On a non-zero exit,
   **stop** and relay the problem-and-fix message it printed (bad path, no recognized
   source code, invalid limit). On success, stdout is the work-plan JSON: the partitions
   and the ordered list of work units (`unit_id`, `stage`, `files`, `result_file`).

## 3. Set up the run

- Create a per-run scratch directory (e.g. with `mktemp -d`). All intermediate files
  live there; the only durable artifacts of the run are the two report files.
- Save the work-plan JSON into it as `workplan.json` (the render step requires it).

## 4. Run the structural unit first

Launch **one** subagent for the `structural_context--all` unit and wait for it to finish
before anything else — its summary is shared context for every later unit. The subagent
prompt must include:

- The scope path and the unit's file list from the work plan.
- The stage instructions: read
  `${CLAUDE_PLUGIN_ROOT}/src/pipeline/stages/structural.md` (its body is the stage's
  instructions) together with the system-prompt file its frontmatter names,
  `${CLAUDE_PLUGIN_ROOT}/src/pipeline/stages/system-structural.md`, and follow both.
- The mandate to perform **static analysis only** (read code; never run it).
- The mandate to write its result to `<scratch-dir>/structural_context--all.json` in the
  stage-result schema below, and to also return a compact (~2–4k token) structural
  summary of the codebase as its final message.

## 5. Run the remaining units in waves of at most N

The remaining units (from the work plan, in order) are `<stage>--<partition>` units for
the three analysis stages. Stage instruction files:

| Stage | Instructions file |
|---|---|
| `algorithmic_complexity` | `${CLAUDE_PLUGIN_ROOT}/src/pipeline/stages/complexity.md` |
| `resource_io_efficiency` | `${CLAUDE_PLUGIN_ROOT}/src/pipeline/stages/resource_io.md` |
| `concurrency_scalability` | `${CLAUDE_PLUGIN_ROOT}/src/pipeline/stages/concurrency.md` |

Each stage file is frontmatter plus an instruction body; the frontmatter's `system`
key names the shared system-prompt file — for all three stages that is
`${CLAUDE_PLUGIN_ROOT}/src/pipeline/stages/system-sonnet.md`. Subagents follow the
system prompt's rules together with their stage's instruction body.

Scheduling rules (the concurrency bound is a hard guarantee):

- Launch subagents in **waves of at most N** — start a wave by launching up to N
  subagents together, then wait for the whole wave to finish before launching the next.
  At no point may more than N subagents be active.
- When fewer units remain than N, launch only that many (never invent extra work to
  fill a wave).
- Report per-wave progress to the user (units launched / completed / failed) rather than
  going silent. Never surface raw stack traces or internal tool syntax.
- **Single retry pass**: after the final wave, collect the units whose subagent visibly
  failed or timed out and re-run each of them exactly once, still in waves of at most N.
  Units that fail again stay failed — the render step records them and the report names
  what did not complete. Never retry more than once and never block the render step on
  further recovery attempts.

Each subagent prompt must carry:

- The shared structural summary from step 4.
- The scope path and **its unit's** file list (only those files are in its scope).
- The instruction to read and follow its stage's instructions file (table above) plus
  the system-prompt file its frontmatter names.
- The static-analysis-only mandate.
- The mandate to write exactly one file, `<scratch-dir>/<unit_id>.json`, in the
  stage-result schema below.

### Stage-result file schema

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

A unit whose subagent fails, times out, or writes an unusable file is a **failed unit**:
do not abort the run — the render step records it and the report names what did not
complete.

## 6. Consolidate and render (deterministic)

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/plugin_run.py" agent render \
  --results-dir <scratch-dir> --scope <path> --output-dir <current-working-directory>
```

This validates every result file against the bundled schema, merges the findings, and
writes `perf-report.md` / `perf-report.html` through the same aggregator and templates
as the hosted CLI. Interpret its exit code:

- `0` — report written (including partial-results runs).
- `1` — invalid invocation (relay the message; this is a bug in the orchestration, not
  the user's code).
- `3` — every unit of every stage failed. The failure-noting report was still written:
  report the run as **failed**, never as a clean empty result.

## 7. Report to the user

Tell the user:

- Where both report files were written.
- Run status: complete, or partial with exactly what did not complete (failed units /
  stages, from the wave results and the render exit code).
- The parallelism actually used, including the "capped to 10" notice when it applied.

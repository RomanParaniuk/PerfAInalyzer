---
name: perf-report
description: "Stage 5 (final) of the staged perf-ai workflow: report finalization. Aggregates, de-duplicates, and prioritizes the results/<unit>.json findings from /perf-exec into perf-report.md and perf-report.html through the bundled deterministic renderer. Use after /perf-exec, or to re-render reports anytime. Invoked as /perf-report [output-dir]; default output is the current directory, with a copy kept in the workspace. Re-running overwrites the previous reports."
---

# perf-report — stage 5: report finalization

You turn the accumulated findings into the final deliverables. The consolidation and
rendering are deterministic bundled code — never aggregate findings yourself, never
re-implement the templates. Never read or prompt for `ANTHROPIC_API_KEY`.

## 1. Resolve the workspace and inputs

Workspaces live under `<cwd>/analysis-runs/`, one per target: exactly one → use it;
several → ask (non-interactive: stop with instructions); none → stop.

**Preconditions**: `results/workplan.json` exists → otherwise stop, run `/perf-plan`;
at least one `results/<unit>.json` exists → otherwise stop, run `/perf-exec`. Take the
target path from `workplan.json`'s `scope_path`.

**Staleness check** (report, don't block): compare artifact timestamps. If
`01-architecture.md`, `02-scope.md`, or `03-plan.md` is newer than the newest
`results/<unit>.json`, the findings predate an upstream change — say which artifact is
newer and that `/perf-exec` would refresh the findings; render anyway if the user
proceeds (non-interactive: render, and flag the staleness prominently in your final
message).

- `output-dir` argument — where the canonical reports go. Default: the current working
  directory.

## 2. Render (deterministic)

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/plugin_run.py" agent render \
  --results-dir <workspace>/results --scope <target> --output-dir <output-dir>
```

Exit codes:

- `0` — reports written (including partial-results runs).
- `1` — invalid invocation: relay the message (an orchestration bug, not the user's
  code).
- `3` — every unit of every stage failed. The failure-noting reports were still
  written: report the run as **failed**, never as a clean empty result.

Then copy the two fresh reports into the workspace as well
(`<workspace>/perf-report.md`, `<workspace>/perf-report.html`), overwriting previous
copies, so the workspace stays a complete self-contained record of the run.

## 3. Report to the user

Tell the user:

- Where both report files were written (canonical location and workspace copy).
- Run status: complete, or partial with exactly which units/stages did not complete.
- Coverage beyond the report's own coverage section: components marked `skip` or
  `skim` in `02-scope.md` are named as deliberately excluded/limited — never silently
  omitted.
- Any staleness flag from step 1.
- That any stage can be re-run at any time by its command (`/perf-arch`, `/perf-scope`,
  `/perf-plan`, `/perf-exec`, `/perf-report`) — each overwrites its own artifact and
  downstream stages are then regenerated on request, never automatically.

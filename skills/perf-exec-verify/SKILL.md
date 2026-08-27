---
name: perf-exec-verify
description: "Stage 4i (optional) of the staged perf-ai workflow: adversarial verification of high-severity findings. Reads every execution stage's results/<unit>.json, re-examines each critical/high issue with an independent refuter subagent (waves of at most N), and writes results/verification.json plus the 04i-verify.md digest. /perf-report automatically drops the refuted issues when verification.json is present. Invoked as /perf-exec-verify. Re-running overwrites both artifacts."
---

# perf-exec-verify — stage 4i: adversarial verification (optional)

You re-examine every **critical or high issue** the execution stages reported, one
independent skeptic subagent per finding, and record which findings survive.
**Static analysis only** — neither you nor any subagent may execute, compile, or
profile the submitted code. Never read or prompt for `ANTHROPIC_API_KEY`.

This stage is optional and runs after any or all of the per-dimension stages
(4b–4h). Its output is an overlay: `/perf-report`'s renderer detects
`results/verification.json` automatically, drops the refuted issues from the final
report, and records the outcome in the report's limitations section. A missing or
deleted `verification.json` simply means the report keeps every finding.

## 1. Resolve the workspace and inputs

Workspaces live under `<cwd>/analysis-runs/`, one per target: exactly one → use it;
several → ask (non-interactive: stop with instructions); none → stop.

**Preconditions** (stop naming the command to run first if unmet):

- `results/workplan.json` exists → otherwise `/perf-plan`.
- At least one per-dimension result file exists and parses — `results/<stage>--p*.json`
  for the partitioned stages 4b–4g, or `results/dependency_footprint--all.json` for
  stage 4h → otherwise `/perf-exec` (or a per-dimension command).

Read the target path and N (`max_parallel`) from `workplan.json`. Collect the
verification queue: every finding across all existing, parsable
`results/<unit>.json` files with `"kind": "issue"` and severity `critical` or
`high`. Record for each: its stage name, its unit file, and the finding's
`location` and `description` **verbatim** — exact copies are what lets the renderer
match verdicts back to findings.

If the queue is empty, write `results/verification.json` with an empty `verdicts`
list and the digest below saying there was nothing to verify, then stop.

If some execution stages have no result files yet, proceed, but list them in the
digest and your final message: their future findings will be unverified until this
command is re-run.

Re-run behavior: overwrite `results/verification.json` and `04i-verify.md`. If any
execution stage re-ran after the last verification, its findings changed — that is
exactly when a re-run of this command is needed.

## 2. Verify in waves of at most N

Scheduling — the same hard guarantees as the execution stages: waves of at most N
subagents, wait for a whole wave before the next, never more than N active, report
per-wave progress, no raw stack traces. One retry pass over failed/timed-out
verifications; a verification that fails again leaves its finding **unverified**
(it stays in the report — a failed verifier must never suppress a finding).

Each subagent prompt must carry:

- The finding, verbatim: stage, description, severity, suggested_action, and
  location (file, lines, symbol).
- The target path, with the instruction to read the cited file around the cited
  lines **plus enough surrounding context** (callers, guards, the data structures
  involved) to judge the claim.
- The adversarial mandate: *your job is to refute this finding.* Check that the
  claimed pattern actually exists at the location, that no guard, cache, bound, or
  early exit above it already neutralizes it, that the code is actually reachable
  on a path where the cost matters, and that the severity is not premised on a
  misreading. Confirm only when the issue survives a genuine attempt to kill it —
  but do **not** refute merely because impact is uncertain; refute only with a
  concrete reason the finding is wrong.
- The static-analysis-only mandate.
- The mandate to end with exactly one fenced JSON block, no prose after it:

```json
{
  "verdict": "confirmed | refuted",
  "reasoning": "one short paragraph: the concrete evidence for the verdict"
}
```

Collect each subagent's verdict. A response with no parsable verdict block counts
as a failed verification (retry once as above).

## 3. Write the artifacts

Write `<workspace>/results/verification.json` — the machine input for
`/perf-report` — copying `stage_name`, `location.file_path` (and `line_start` when
present), and `description` **exactly** as they appear in the unit result files:

```json
{
  "verdicts": [
    {
      "stage_name": "<the finding's stage, exactly>",
      "location": {"file_path": "<exactly as in the result file>", "line_start": 1},
      "description": "<the finding's description, verbatim>",
      "verdict": "confirmed | refuted",
      "reasoning": "<the subagent's reasoning>"
    }
  ]
}
```

Unverified findings (failed verifier) get **no** entry. Then overwrite
`04i-verify.md`:

```markdown
---
stage: analysis-execution-verify
target: <absolute target path>
generated: <UTC ISO-8601 timestamp>
verified: <confirmed + refuted>/<queue size>
---

# Verification — <target basename>

## Totals

<queue size> critical/high issue(s) reviewed: <n> confirmed, <n> refuted,
<n> unverified (verifier failed).

## Verdicts

| Verdict | Severity | Location | Issue | Reasoning |
<one row per verdict; refuted rows first>

## Not covered

<execution stages with no results yet, unverified findings — or "all
critical/high issues verified">

## Next stage

Run `/perf-report [output-dir]` — it will drop the refuted issue(s) above and note
the verification in the report. Re-run `/perf-exec-verify` after re-running any
execution stage.
```

## 4. Report to the user

Tell the user: how many findings were reviewed, confirmed, refuted, and
unverified; which execution stages (if any) had no results to verify; where
`verification.json` and the digest were written; and that `/perf-report` will now
exclude the refuted issues (deleting `results/verification.json` undoes that).

---
name: perf-scope
description: "Stage 2 of the staged perf-ai workflow: depth survey. Reads 01-architecture.md, proposes a review depth (deep/standard/skim/skip) per component with a reason, has the developer confirm or adjust, and writes 02-scope.md — the input for /perf-plan. Use after /perf-arch, or to re-aim an analysis. Invoked as /perf-scope [accept]. Re-running overwrites the previous artifact."
---

# perf-scope — stage 2: depth survey

You produce the **scope artifact**: a per-component review-depth assignment that aims
the expensive analysis before it is paid for. Static analysis only; never read or
prompt for `ANTHROPIC_API_KEY`.

## 1. Resolve the workspace

Workspaces live under `<cwd>/analysis-runs/`, one directory per target. If exactly one
exists, use it. If several exist, ask the user which target (list them); in a
non-interactive session, stop and ask for re-invocation from the right directory. If
none exists, **stop**: "no staged analysis found — start one with `/perf-arch <path>`."

**Precondition**: `01-architecture.md` must exist in the workspace. If it is missing,
stop and say to run `/perf-arch` first. Read it — the `target:` frontmatter field and
the Components table (as currently on disk, including any hand edits) are the
authoritative input. If the table cannot be understood (e.g. edited into an unreadable
state), stop, name the file and the specific problem, and change nothing.

If `02-scope.md` already exists, you are re-running the stage: overwrite it, and note
afterwards that `03-plan.md`, `results/`, the `04a`–`04d` digests, and any reports now
predate the new scope and should be regenerated with their commands.

## 2. Propose depths

Assign every component exactly one depth with a one-line reason:

| Depth | Meaning in the analysis stage |
|---|---|
| `deep` | Every file is read fully; all analysis dimensions applied thoroughly. |
| `standard` | Normal coverage — the default for ordinary application code. |
| `skim` | Only entry points and obvious hot paths are examined. |
| `skip` | Excluded entirely — no work units; named as excluded in the final report. |

Ground the proposal in the architecture artifact: high perf-relevance → `deep` or
`standard`; config/docs/generated/vendored code and test suites → `skim` or `skip`.

## 3. Confirm with the developer

Never choose the scope silently:

- If the `accept` argument was given, take the proposal as confirmed as-is.
- Otherwise, present the proposed table and ask the developer to confirm or adjust
  (accept all, or name changes like "make api deep, skip tests"). Apply adjustments and
  proceed.
- **Non-interactive session**: write the artifact with `confirmed: pending` and stop
  with: "review/edit `<workspace>/02-scope.md`, then run `/perf-plan` — that invocation
  counts as confirmation." Do not guess.

## 4. Write `02-scope.md`

Overwrite the file with exactly this shape:

```markdown
---
stage: depth-survey
target: <absolute target path, copied from 01-architecture.md>
generated: <UTC ISO-8601 timestamp>
based_on: 01-architecture.md @ <its generated timestamp>
confirmed: <yes | pending>
---

# Review Depth Assignment — <target basename>

| Component | Paths (globs) | Depth | Reason |
|-----------|---------------|-------|--------|

Depths: deep = full read, standard = normal coverage, skim = entry points and hot
paths only, skip = excluded entirely (named in the report's coverage section).

Edit this table freely — the file on disk is the authoritative input for `/perf-plan`.

## Next stage

Run `/perf-plan [max-parallel=N]` to turn this scope into an executable work plan.
```

Copy each component's **Paths (globs)** verbatim from the architecture table — later
stages use them mechanically.

## 5. Report to the user

Tell the user: where the artifact was written, the depth distribution (how many
components at each depth), roughly what fraction of the codebase's files was skipped or
skimmed, the staleness notice if this was a re-run, and that the next command is
`/perf-plan`.

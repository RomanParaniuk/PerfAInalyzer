---
name: perf-plan
description: "Stage 3 of the staged perf-ai workflow: analysis plan. Reads the confirmed 02-scope.md, builds the deterministic work plan (excluding skipped components, adding the whole-scope dependency unit when the project declares dependencies), and writes 03-plan.md plus results/workplan.json — the inputs for /perf-exec. Use after /perf-scope, or to rebuild the plan after editing the scope. Invoked as /perf-plan [max-parallel=N]. Re-running overwrites the previous plan."
---

# perf-plan — stage 3: analysis plan

You turn the confirmed depth assignment into an executable, costed work plan. The
partitioning itself is deterministic bundled code — never re-implement it. Static
analysis only; never read or prompt for `ANTHROPIC_API_KEY`.

## 1. Resolve the workspace and inputs

Workspaces live under `<cwd>/analysis-runs/`, one per target: exactly one → use it;
several → ask (non-interactive: stop with instructions); none → stop, run `/perf-arch`
first.

**Preconditions** (stop with the missing command's name if unmet):

- `02-scope.md` exists. Read it from disk — hand edits are authoritative. Take the
  target path from its frontmatter and the component/depth table from its body. If
  `confirmed: pending`, this invocation **is** the confirmation: proceed and set it to
  `yes` when you touch the file's downstream note (edit only that frontmatter value).
- The table parses into components each with paths-globs and a depth from
  {deep, standard, skim, skip}. If not, stop, name `02-scope.md` and the specific
  problem (e.g. "component 'api' has depth 'medium', which is not in the vocabulary"),
  and change nothing.

If `03-plan.md` or `results/workplan.json` already exist, you are re-running: overwrite
both, and note that `results/<unit>.json` findings, the `04a`–`04d` digests, and
reports now predate the new plan and should be regenerated.

## 2. The parallelism limit

`max-parallel=N` argument: validate like the one-shot skill — integer 1–10; above 10 is
capped to 10 with an explicit "your value N was capped to 10 (the documented maximum)";
zero/negative/non-numeric is rejected. If absent, ask "How many subagents may run in
parallel for the analysis? (1–10)" with no suggested default and wait; in a
non-interactive session stop with: "re-invoke as `/perf-plan max-parallel=N`."

## 3. Build the work plan (deterministic)

Collect the paths-globs of every component whose depth is `skip` and run:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/plugin_run.py" agent scope <target> \
  --max-parallel <N> --exclude <glob> [--exclude <glob> ...]
```

On non-zero exit, stop and relay its problem-and-fix message (if *everything* was
excluded it reports "no source code … found" — say the scope skips too much and point
at `02-scope.md`). On success, stdout is the work-plan JSON: `partitions`, ordered
`units` (`unit_id`, `stage`, `files`, `result_file`), and `manifests` — the dependency
manifests found outside the code scope. Create `<workspace>/results/` and save it there
as `workplan.json` (overwriting any previous one).

Two units are whole-scope rather than partitioned: `structural_context--all`, and
`dependency_footprint--all` over the manifests. The dependency unit is absent when the
scope declares no dependencies at all (or the excludes covered every manifest) — that
is normal, and stage 4h then has nothing to run.

## 4. Write `03-plan.md`

Map each unit's files to components using the scope table's globs, then overwrite:

```markdown
---
stage: analysis-plan
target: <absolute target path>
generated: <UTC ISO-8601 timestamp>
based_on: 02-scope.md @ <its generated timestamp>
max_parallel: <N>
---

# Analysis Plan — <target basename>

## Work units (execution order)

| # | Unit | Analysis | Files | Components covered (depth) |
|---|------|----------|-------|----------------------------|
<one row per unit from workplan.json: unit_id; stage; file count; the components whose
files it contains, each with its depth>

## Scope summary

- Included: <file count> files in <partition count> partition(s), N=<max_parallel>.
- Work units by depth: <counts of units touching deep / standard / skim components>
- Skipped components (no work units): <names, or "none">
- Dependency manifests: <count and names, or "none found — stage 4h will not run">

## Estimated cost

~<low>–<high> tokens for the analysis stage (input estimate: total included bytes / 4
chars-per-token × 7 stage passes over the code, halved for skim-dominated units, plus
the dependency unit's manifest bytes / 4; plus output). Stated so the actual spend can
be compared after `/perf-exec`.

## Next stage

Run `/perf-exec` to execute all eight analysis dimensions, or go dimension by
dimension: `/perf-exec-structural`, then `/perf-exec-complexity`,
`/perf-exec-resource-io`, `/perf-exec-concurrency`, `/perf-exec-memory`,
`/perf-exec-data-access`, `/perf-exec-startup`, `/perf-exec-deps` — then optionally
`/perf-exec-verify`. Machine-readable plan:
`results/workplan.json` (regenerate with `/perf-plan` rather than editing it by hand).
```

## 5. Report to the user

Tell the user: where the artifacts were written, the unit count and partition count,
which components are skipped, whether a dependency unit was planned, the token estimate,
the cap notice if it applied, the staleness notice if this was a re-run, and that the
next command is `/perf-exec`
(or `/perf-exec-structural` to execute one dimension at a time).

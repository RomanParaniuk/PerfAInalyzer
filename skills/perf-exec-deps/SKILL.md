---
name: perf-exec-deps
description: "Stage 4h of the staged perf-ai workflow: dependency-footprint execution. Reads results/workplan.json, the depth table from 02-scope.md, and the structural summary from 04a-structural.md, runs the whole-scope dependency_footprint--all unit with one subagent over the project's manifests and its own import sites, and writes results/dependency_footprint--all.json plus the 04h-dependencies.md digest. Finds overlapping libraries, heavy imports on hot paths, unused declared dependencies, and duplicate versions — never reading a dependency's own source. Invoked as /perf-exec-deps. Re-running overwrites both artifacts."
---

# perf-exec-deps — stage 4h: dependency-footprint execution

You run the **dependency unit**: one subagent judges what the project declares, ships,
and imports. Dependency code is *not* analyzed and is not in scope — `node_modules`,
`vendor`, `site-packages` and their kin are excluded from discovery by design, and
neither you nor the subagent may go read them. What is analyzed is the project's own
manifests and its own import sites, because that is where a dependency problem is
fixable. **Static analysis only** — never execute, compile, install, or profile
anything. Never read or prompt for `ANTHROPIC_API_KEY`.

This stage is whole-scope (one unit, like 4a) rather than partitioned: a dependency
footprint split across partitions would show each subagent a fraction of the imports and
hide exactly the overlaps and totals it exists to find. It depends only on
`/perf-exec-structural`, so it may run any time after 4a.

## 1. Resolve the workspace and inputs

Workspaces live under `<cwd>/analysis-runs/`, one per target: exactly one → use it;
several → ask (non-interactive: stop with instructions); none → stop.

**Preconditions** (stop naming the command to run first if unmet):

- `03-plan.md` and `results/workplan.json` exist → otherwise `/perf-plan`.
- `02-scope.md` exists (for depth guidance) → otherwise `/perf-scope`.
- `results/structural_context--all.json` exists and parses → otherwise
  `/perf-exec-structural`.

Read from `workplan.json`: the target path, the `manifests` list, and the
`dependency_footprint--all` unit. Read the component→depth mapping from `02-scope.md`
and the shared structural summary from `04a-structural.md`'s `## Structural summary`
section (if that file is missing, derive a compact summary from the structural result
JSON). If `02-scope.md` or `03-plan.md` is newer than `workplan.json`, warn that the
plan may be stale and suggest `/perf-plan` first — continue only if the user says so
(non-interactive: stop).

**No dependency unit in the plan** means the deterministic scan found no manifest under
the target (or every manifest fell under an excluded glob). That is a finished stage,
not a failure: write the digest below with `unit_status: not-applicable`, say plainly
that declared dependencies were not analyzed and why, and stop without launching a
subagent.

Re-run behavior: overwrite `results/dependency_footprint--all.json` and
`04h-dependencies.md`; note afterwards that any report predates the new results. Never
delete other stages' result files.

## 2. Run the dependency unit

Launch **one** subagent and wait for it. Its prompt must include:

- The target path and the unit's file list — the manifests and lockfiles.
- The shared structural summary, so it knows which files are entry points and hot paths.
- **The import-site mandate**: the subagent gathers the project's import statements
  itself, by searching the target for import/require/use statements across the analyzed
  components. Components marked `skip` in `02-scope.md` are out of scope here too;
  imports that appear only in `skim` components carry correspondingly less weight.
- **The dependency-source prohibition**, stated explicitly: it must never read, list, or
  descend into `node_modules`, `vendor`, `site-packages`, or any other installed
  dependency directory, and must never inline a lockfile's contents. A lockfile's size,
  and duplicate-version evidence found by targeted search within it, are fair game.
- The instruction to read and follow
  `${CLAUDE_PLUGIN_ROOT}/src/pipeline/stages/dependencies.md` together with the system
  prompt its frontmatter names, `${CLAUDE_PLUGIN_ROOT}/src/pipeline/stages/system-sonnet.md`.
- The static-analysis-only mandate.
- The mandate to write exactly one file,
  `<workspace>/results/dependency_footprint--all.json`, in the stage-result schema (see
  `${CLAUDE_PLUGIN_ROOT}/skills/perf-exec/dimension-procedure.md` §2), with
  `stage_name` exactly `dependency_footprint`. Every finding's `location.file_path` is
  the manifest that declares the dependency or the file that imports it — never a path
  inside a dependency.

If the subagent visibly fails or times out, retry exactly once. If it fails again, the
unit stays failed: write the digest with status `failed`, record it, and continue —
this stage never blocks the others or the report.

## 3. Write `04h-dependencies.md`

Overwrite the digest:

```markdown
---
stage: analysis-execution-dependencies
target: <absolute target path>
generated: <UTC ISO-8601 timestamp>
based_on: 03-plan.md @ <its generated timestamp>
unit_status: <completed | failed | not-applicable>
---

# Dependency Footprint — <target basename>

## Declared dependencies

| Manifest | Ecosystem | Declared | Imported somewhere | Never imported |
<one row per manifest analyzed; counts from the subagent's findings, or "—" when it
could not determine one>

## Totals

<issues by severity; valuable findings>

## Top issues

| Severity | Location | Issue | Suggested action |
<the critical and high issues, one row each>

## Not covered

<lockfiles not inspected, manifests too large to read, skipped components whose imports
were not counted — or "full coverage">

## Next stage

Run any remaining execution stages (4a–4h, see `/perf-exec`) if not done yet, then
optionally `/perf-exec-verify`, then `/perf-report [output-dir]`.
```

## 4. Report to the user

Tell the user: unit status, the finding count and severity totals, the headline
dependency facts (overlapping libraries, never-imported declarations, heavy imports on
entry paths), where the result JSON and digest were written, and which execution stages
still lack results before `/perf-report`.

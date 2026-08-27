---
name: perf-arch
description: "Stage 1 of the staged perf-ai workflow: architecture review. Maps the target codebase into components with entry points, sizes, and performance relevance, and writes 01-architecture.md — the input for /perf-scope. Use when the user starts a staged performance analysis or asks to (re)build the architecture map. Invoked as /perf-arch [path]. Re-running overwrites the previous artifact."
---

# perf-arch — stage 1: architecture review

You produce the **architecture artifact** for the staged perf-ai workflow. Static
analysis only: read code, never execute, compile, or profile it. Never read or prompt
for `ANTHROPIC_API_KEY` — all reasoning uses your own model access.

The staged workflow runs one stage per command, each writing a durable Markdown
artifact that the next stage consumes:

| Stage | Command | Artifact |
|---|---|---|
| 1. Architecture review | `/perf-arch [path]` | `01-architecture.md` |
| 2. Depth survey | `/perf-scope` | `02-scope.md` |
| 3. Analysis plan | `/perf-plan [max-parallel=N]` | `03-plan.md` + `results/workplan.json` |
| 4a. Structural-context execution | `/perf-exec-structural` | `results/structural_context--all.json` + `04a-structural.md` |
| 4b. Algorithmic-complexity execution | `/perf-exec-complexity [only-failed]` | `results/<unit>.json` + `04b-complexity.md` |
| 4c. Resource & I/O execution | `/perf-exec-resource-io [only-failed]` | `results/<unit>.json` + `04c-resource-io.md` |
| 4d. Concurrency execution | `/perf-exec-concurrency [only-failed]` | `results/<unit>.json` + `04d-concurrency.md` |
| 4e. Memory & allocation execution | `/perf-exec-memory [only-failed]` | `results/<unit>.json` + `04e-memory.md` |
| 4f. Data-access execution | `/perf-exec-data-access [only-failed]` | `results/<unit>.json` + `04f-data-access.md` |
| 4g. Startup & initialization execution | `/perf-exec-startup [only-failed]` | `results/<unit>.json` + `04g-startup.md` |
| 4h. Dependency-footprint execution | `/perf-exec-deps` | `results/dependency_footprint--all.json` + `04h-dependencies.md` |
| 4i. Verification (optional) | `/perf-exec-verify` | `results/verification.json` + `04i-verify.md` |
| 5. Report finalization | `/perf-report [output-dir]` | `perf-report.md` / `perf-report.html` |

(`/perf-exec [only-failed]` is the umbrella that runs 4a–4h in order.)

## 1. Resolve target and workspace

- `path` argument — the directory to analyze. Default: the current working directory.
- Workspace: `<cwd>/analysis-runs/<basename of target>/`. Create it if missing.
- If `01-architecture.md` already exists in the workspace, you are **re-running the
  stage**: overwrite it, and afterwards tell the user that any existing downstream
  artifacts (`02-scope.md`, `03-plan.md`, `results/`, the `04a`–`04d` digests,
  reports) now predate the new architecture and should be regenerated with their
  commands. Never
  delete or modify downstream artifacts yourself.

## 2. Preflight (deterministic)

Validate the target and get the authoritative file list through the bundled pipeline
code (never re-implement discovery):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/plugin_run.py" agent scope <path> --max-parallel 1
```

(On the first plugin run this provisions a private venv — one-time network need; tell
the user it may take a minute.) On a non-zero exit, **stop** and relay the printed
problem-and-fix message (bad path, no recognized source code). On success, stdout is a
work-plan JSON; use only its `detected_languages`, `file_count`, and the structural
unit's `files` list here — do **not** save this throwaway plan (the real one is built by
`/perf-plan` from the confirmed scope).

## 3. Review the architecture

Read the codebase structure — directory layout, manifests/build files, the discovered
file list, and selectively the key source files (entry points, routing, main modules).
Identify 5–15 product **components**: meaningful parts (app, package, service, layer),
plus the non-product ones carved out below (tests, generated code, vendored code,
tooling). For each determine:

- **Paths** — one or more glob patterns relative to the target root that exactly cover
  the component's files (e.g. `apps/portal/src/**`). These globs are consumed
  mechanically by later stages (skip-exclusion, depth mapping), so they must be valid
  and mutually disjoint; every discovered file should fall under exactly one component.
  **Never mix product and non-product code in one component.** Non-product code — tests,
  fixtures, mocks, benchmarks, examples and demo apps, build/CI/tooling scripts,
  generated code, vendored code, docs — gets its own component(s), and so do
  non-product files co-located with product code (`src/**/*_test.go`,
  `**/__tests__/**`, `**/*.spec.ts`): carve them out with their own globs and exclude
  them from the product component's globs. `/perf-scope` skips non-product code by
  default and can only do so when its globs are separable here.
- **Entry points** — main files/functions where execution or requests enter.
- **Size** — approximate file count under its globs.
- **Performance relevance** — high / medium / low, with a one-line reason (hot paths,
  I/O surfaces, algorithmic cores vs. config, generated code, tests). Say "non-product"
  in the reason for the carved-out components, so the depth survey can act on it.

For large codebases you may fan the reading out to a few parallel subagents (one per
top-level area), each returning component candidates; merge their answers yourself.

## 4. Write `01-architecture.md`

Overwrite the file with exactly this shape (plain Markdown, hand-editable):

```markdown
---
stage: architecture-review
target: <absolute target path>
generated: <UTC ISO-8601 timestamp>
languages: [<detected_languages>]
file_count: <file_count>
---

# Architecture Review — <target basename>

## Components

| # | Component | Paths (globs) | Files | Entry points | Perf relevance | Why |
|---|-----------|---------------|-------|--------------|----------------|-----|

## Performance-relevant surfaces

<short prose: the hot paths, I/O boundaries, and concurrency surfaces that deserve
attention, referencing components by name>

## Next stage

Run `/perf-scope` to assign a review depth to each component. You can edit this file
first — it is the authoritative input for the next stage.
```

## 5. Report to the user

Tell the user: where the artifact was written, the component count and languages, which
components look performance-relevant, the downstream-staleness notice if this was a
re-run, and that the next command is `/perf-scope`.

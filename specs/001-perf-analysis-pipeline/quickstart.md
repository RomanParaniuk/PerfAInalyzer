# Quickstart: Validating the AI Multi-Stage Performance Analysis Pipeline

**Feature**: `001-perf-analysis-pipeline` | **Date**: 2026-08-04

This guide proves the feature works end-to-end once implemented. It exercises the CLI contract
in `contracts/cli-interface.md` and checks the output against the acceptance scenarios in
`spec.md`. It is a validation/run guide, not an implementation walkthrough — see `tasks.md`
(generated separately by `/speckit-tasks`) for build steps.

## Prerequisites

- Python 3.12+ installed.
- The package installed in a virtual environment (`pip install -e .` from the repo root, once
  the implementation exists).
- A valid Anthropic API key exported as `ANTHROPIC_API_KEY` (FR-016; see
  `contracts/cli-interface.md`).
- A small fixture codebase for validation (create under, e.g., `./fixtures/quickstart-sample/`)
  containing:
  - One deliberate performance anti-pattern, e.g. a nested loop performing an O(n²) scan over a
    list that could be a set/dict lookup.
  - One deliberate well-optimized pattern, e.g. a function using a cache/memoization or an
    appropriate data structure for its access pattern.

## Run

```bash
export ANTHROPIC_API_KEY=sk-...
perf-ai analyze ./fixtures/quickstart-sample --output-dir ./fixtures/quickstart-sample
```

Expected console behavior: incremental per-stage progress is printed (structural → the three
deeper stages), and the command exits `0` (per `contracts/cli-interface.md`).

## Expected outcomes (mapped to spec acceptance scenarios)

1. **User Story 1 — core report** (spec §User Story 1): `./fixtures/quickstart-sample/
   perf-report.md` and `perf-report.html` both exist and both describe the planted O(n²)
   anti-pattern as an Issue, with a location reference pointing at the offending function
   (`data-model.md` → `Finding.location`). Confirm no part of the fixture code was ever executed
   or compiled during the run (SC-001) — e.g., by using a fixture written in a language/form that
   would error if actually run, and confirming the run still succeeds.
2. **User Story 2 — prioritized action items** (spec §User Story 2): the report's action items
   section lists a concrete next step for the O(n²) issue (e.g., "replace the linear scan on
   `line X` with a set membership check"), not a restatement of the issue description, and it is
   the top-ordered item if it is the highest-severity issue present (FR-008).
3. **User Story 3 — valuable findings** (spec §User Story 3): the report includes a "Valuable
   Findings" section, distinct from Issues/Action Items, calling out the planted well-optimized
   pattern.
4. **User Story 4 — stage attribution** (spec §User Story 4): every finding in the report is
   labeled with the analysis stage that produced it (one of the four names in
   `contracts/stage-output-schema.md`).
5. **Empty-section handling** (FR-010, SC-006): re-run against a fixture with no planted issues
   and confirm the Issues section explicitly states none were found, rather than being omitted.
6. **Partial-failure handling** (FR-012): simulate a single stage failure (e.g., temporarily
   revoke network access mid-run in a controlled test, or inject a forced timeout in a test
   double) and confirm the report still contains findings from the stages that did complete, and
   explicitly lists the stage that did not.

## Timing check (SC-004, Principle V)

Run the same command against a fixture sized to represent a "typical" project (tens of thousands
of LOC, per spec Assumptions) and confirm the run completes in under 10 minutes. Record the
measured wall-clock time and per-stage token usage — this is the design-time estimate from
`research.md` ("Estimated token cost per run") being replaced with a measured figure, per the
Development Workflow gate in the constitution.

## Where to look next

- Stage output shape: `contracts/stage-output-schema.md`
- CLI flags and exit codes: `contracts/cli-interface.md`
- Entity fields and validation rules: `data-model.md`
- Technology/design rationale: `research.md`

# Implementation Plan: AI Multi-Stage Performance Analysis Pipeline

**Branch**: `001-perf-analysis-pipeline` | **Date**: 2026-08-04 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-perf-analysis-pipeline/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

A developer runs a CLI command against a local directory or repository. The tool auto-detects
the programming language(s) present, builds a compact local structural index (no AI tokens
spent), then runs a four-stage AI analysis pipeline against Anthropic's Claude API — structural/
context understanding first, followed by algorithmic complexity, resource/I/O efficiency, and
concurrency/scalability analysis running concurrently against the cached Stage 1 context. No
submitted code is ever executed, compiled, or profiled — every stage performs static reading and
reasoning only, returning schema-validated structured findings. A deterministic (non-AI)
aggregation and templating step merges all completed stages' findings into one severity-ordered
report, explicitly marking empty sections, and writes it to disk as both `perf-report.md` and
`perf-report.html`. A stage that fails or times out is recorded as incomplete without blocking
the rest of the run.

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies**: Anthropic Python SDK (Claude API client), Typer (CLI), Rich (progress/
terminal output), `tree-sitter` + a multi-language grammar pack (local structural indexing),
Pydantic (schema-validated stage I/O), Jinja2 (deterministic Markdown/HTML report templates)

**Storage**: N/A — stateless across runs; only output artifacts (`perf-report.md`,
`perf-report.html`) are written to disk in the invocation working directory, overwriting any
prior run's files (no run history is persisted, per spec's Key Entities note)

**Testing**: pytest — unit tests (deterministic components, no network), contract tests
(stage-output schema conformance against recorded/mocked API responses), integration tests (full
CLI run against fixture repositories with planted anti-patterns), with live-API validation kept
in a separate, explicitly-invoked suite to control token cost in routine runs

**Target Platform**: Cross-platform developer workstation CLI (macOS/Linux/Windows), Python
3.12+ runtime, outbound network access to the Anthropic API

**Project Type**: Single project — command-line tool

**Performance Goals**: Complete a typical-sized project analysis (tens of thousands of LOC,
moderate file count, per Assumptions) and produce a report in under 10 minutes (SC-004); show
incremental per-stage progress rather than a single blocking wait, per Principle V

**Constraints**: Zero code execution/compilation/profiling of submitted code at any stage
(FR-003); all AI calls go to an external hosted provider, subject to that provider's data-
handling terms (FR-016); per-run token cost bounded via local pre-processing, prompt caching of
shared context, and per-stage token budgets (Principle II); a single stage's failure/timeout must
not block the rest of the run (FR-012)

**Scale/Scope**: Tens of thousands of LOC across a moderate number of files per run (Assumptions);
substantially larger monorepos are explicitly out of scope for this revision

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Status |
|---|---|---|
| I. Modern AI-First Approaches | Uses current-generation Claude models (Haiku 4.5, Sonnet 5) selected deliberately per stage rather than a single inherited default; rationale documented in `research.md` §2 for future revisit. | PASS |
| II. Token-Optimal Usage (NON-NEGOTIABLE) | Local, zero-token structural indexing (tree-sitter); Stage 1 output cached and reused by Stages 2–4 instead of re-derived; per-stage token budgets with relevance-ranked excerpts instead of full-repo dumps; smallest capable model tier chosen per stage; design-time token estimate captured in `research.md`. | PASS |
| III. Useful, Actionable Output | Every stage response is schema-validated via forced tool-use + Pydantic (`contracts/`); action items required by schema to reference a concrete step, not a restatement of the issue (FR-006); no claims are made about external system state beyond the code being read. | PASS |
| IV. Consistent User Experience | Report rendering is deterministic (Jinja2 templates, no AI involvement in formatting) so tone/structure is identical across runs; stage failures degrade gracefully with a clear "did not complete" note rather than raw exceptions/stack traces reaching the user (FR-012). | PASS |
| V. Performance Requirements | Explicit budget: <10 minutes for a typical-sized project (SC-004), background/batch interaction context; Stages 2–4 run concurrently to reduce wall-clock time; Rich-based incremental progress output instead of a single blocking call; measurement against the budget deferred to implementation validation (see Development Workflow gate). | PASS |

No violations requiring justification. Complexity Tracking table is not needed.

### Post-Phase-1 re-check

Re-evaluated after `data-model.md` and `contracts/` were produced:

| Principle | Post-design confirmation | Status |
|---|---|---|
| I. Modern AI-First Approaches | `contracts/stage-output-schema.md` confirms model output is consumed via structured tool-use, not free-text scraping — no legacy-heuristic fallback was introduced during design. | PASS |
| II. Token-Optimal Usage | `data-model.md`'s `Analysis Stage` entity confirms Stage 1 output is a single shared context object reused by Stages 2–4, not recomputed per stage; no design decision added an extra round-trip. | PASS |
| III. Useful, Actionable Output | `contracts/stage-output-schema.md` now precisely defines the cross-field rule (`suggested_action` required and non-identical to `description` for issues) and the aggregator-level rejection behavior for violations — this is stronger than the Phase 0 intent, not weaker. | PASS |
| IV. Consistent User Experience | `data-model.md`'s `Report` entity requires the Markdown and HTML renderings to be content-equivalent from one shared object, and requires an explicit "none found" marker for empty sections — both concretely specified, not just asserted. | PASS |
| V. Performance Requirements | No new synchronous, blocking call was introduced by the data model or contracts; `contracts/cli-interface.md` confirms progress is streamed incrementally and the timeout/partial-result path is exit-code `0`, not a hard failure. | PASS |

No new violations were introduced during Phase 1 design. Complexity Tracking remains empty.

## Project Structure

### Documentation (this feature)

```text
specs/001-perf-analysis-pipeline/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   ├── cli-interface.md
│   └── stage-output-schema.md
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
src/
├── cli/                  # Typer entrypoint: argument parsing, Rich progress display
├── pipeline/
│   ├── stages/            # one module per analysis stage:
│   │                      #   structural.py, complexity.py, resource_io.py, concurrency.py
│   ├── orchestrator.py    # stage sequencing, Stage 2-4 concurrency, timeout/failure handling
│   └── context.py         # local structural index (tree-sitter), relevance ranking, chunking,
│                          # prompt-cache context assembly
├── models/                # Pydantic schemas: Finding, Issue, ValuableFinding, ActionItem,
│                          # StageResult, Report
├── providers/              # Anthropic API client wrapper: per-stage model selection, prompt
│                          # caching, forced tool-use schema, retries/timeouts
├── report/
│   ├── aggregator.py       # merge stage findings, severity ordering, empty-section handling
│   └── templates/          # Jinja2 templates: perf-report.md.j2, perf-report.html.j2
└── lib/                   # shared utilities: language detection, file discovery/ignore rules

tests/
├── contract/              # Pydantic schema conformance tests against recorded API responses
├── integration/            # full-pipeline CLI runs against fixture repos with known
│                          # anti-patterns / well-optimized patterns
└── unit/                   # structural index, relevance ranking, aggregator, template renderers
```

**Structure Decision**: Single project (Option 1). This is a self-contained CLI tool with no
separate frontend/backend or mobile split — `src/` holds the pipeline, provider integration,
schemas, and report rendering; `tests/` mirrors it with contract/integration/unit layers as
described in `research.md` §8.

## Complexity Tracking

*No entries — Constitution Check reported no violations requiring justification.*

---

description: "Task list for AI Multi-Stage Performance Analysis Pipeline"
---

# Tasks: AI Multi-Stage Performance Analysis Pipeline

**Input**: Design documents from `/specs/001-perf-analysis-pipeline/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/cli-interface.md, contracts/stage-output-schema.md, quickstart.md

**Tests**: Included. `plan.md`'s Technical Context and `research.md` §8 commit to a three-layer
pytest strategy (unit, contract, integration, with a separately-invoked live-API suite) as part
of the accepted design, so test tasks are generated alongside implementation tasks.

**Organization**: Tasks are grouped by user story (spec.md priorities P1–P4) to enable
independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no unresolved dependency)
- **[Story]**: Which user story this task belongs to (US1–US4)
- File paths follow the structure defined in `plan.md`'s Project Structure section

## Path Conventions

Single project layout per `plan.md`: `src/` and `tests/` at repository root.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [X] T001 Create project directory structure per `plan.md` (`src/cli/`, `src/pipeline/stages/`,
      `src/models/`, `src/providers/`, `src/report/templates/`, `src/lib/`, `tests/contract/`,
      `tests/integration/`, `tests/unit/`, `tests/fixtures/`) with `__init__.py` files where
      needed
- [X] T002 Initialize the Python 3.12 project (`pyproject.toml`) declaring runtime dependencies
      (Anthropic Python SDK, Typer, Rich, `tree-sitter` + a multi-language grammar pack,
      Pydantic, Jinja2) and dev dependencies (pytest, a mocking/response-recording library for
      contract/integration tests)
- [X] T003 [P] Configure linting and formatting (ruff, mypy) in `pyproject.toml`
- [X] T004 [P] Configure pytest markers separating routine (mocked) tests from the
      explicitly-invoked live-API suite, per `research.md` §8, in `pyproject.toml`/`pytest.ini`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core schemas, local analysis machinery, provider client, and orchestrator that every
user story depends on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T005 [P] Create `Finding` and `LocationRef` models with `kind`/`severity` cross-field
      validation (severity non-null iff `kind == issue`) in `src/models/finding.py`
- [X] T006 [P] Create `AnalysisStage` and `StageResult` models plus the stage-name/status enums
      in `src/models/stage.py`
- [X] T007 [P] Create `ActionItem` model with the priority enum in `src/models/action_item.py`
- [X] T008 Create `Report` and `AnalysisRun` models aggregating `Finding`/`ActionItem`/
      `AnalysisStage`, including `incomplete_stages` and `coverage_note` fields, in
      `src/models/report.py` (depends on T005–T007)
- [X] T009 [P] Unit tests for `Finding`/`ActionItem`/`Report` model validation rules (severity
      iff issue, `suggested_action` iff issue, non-empty `file_path`) in `tests/unit/test_models.py`
- [X] T010 [P] Implement language detection and file discovery/ignore rules (default excludes
      for `.git`/`node_modules`/`venv`, `--include`/`--exclude` glob support) in
      `src/lib/discovery.py`
- [X] T011 [P] Unit tests for language detection and file discovery in
      `tests/unit/test_discovery.py`
- [X] T012 Implement the tree-sitter local structural index builder (files, modules,
      function/class boundaries, import graph) with a generic line/indentation fallback chunker
      for languages without an available grammar, in `src/pipeline/context.py`
- [X] T013 [P] Unit tests for the structural index builder, including the fallback-chunker path,
      in `tests/unit/test_context.py`
- [X] T014 Implement stage-specific relevance ranking, token-budget-capped chunking, and
      prompt-cache context assembly (per `research.md` §4 heuristics: loop-nesting/collection-
      growth, I/O/network call-sites, thread/lock/async-primitive usage) in
      `src/pipeline/context.py` (depends on T012, same file); the structural stage's assembled
      input budget MUST fit `claude-haiku-4-5`'s 200K-token context window (Sonnet stages have
      1M available, but budgets stay capped per Principle II)
- [X] T015 [P] Unit tests for relevance ranking, token-budget chunking, and context assembly in
      `tests/unit/test_ranking.py`
- [X] T016 Implement the Anthropic API provider client wrapper: per-stage model selection using
      the exact model IDs `claude-haiku-4-5` for the structural stage and `claude-sonnet-5` for
      the other three stages (use these ID strings verbatim — do not append date suffixes),
      forced tool-use with the `report_stage_findings` schema, prompt caching of the shared
      Stage 1 context, and retry/timeout handling, in `src/providers/anthropic_client.py`
- [X] T017 Implement schema-validation-with-one-retry-then-fail semantics and cross-field rule
      enforcement (`severity` required iff issue; `suggested_action` required iff issue and not
      near-identical to `description`) in `src/providers/anthropic_client.py` (depends on T005,
      T016)
- [X] T018 [P] Contract tests for `report_stage_findings` schema validation and its cross-field
      rules against fixture payloads in `tests/contract/test_stage_output_schema.py`
- [X] T019 [P] Implement a mock/recorded Anthropic provider test double that returns fixture
      `StageResult` payloads with no network calls, for use by integration tests, in
      `tests/support/mock_provider.py`
- [X] T020 Implement the pipeline orchestrator: Stage 1 runs first and its output is cached,
      Stages 2–4 run concurrently against that cached context, each stage call is wrapped in a
      timeout, a failing/timed-out stage is recorded without blocking the rest of the run, and
      `originating_stage` is stamped on every finding by the orchestrator (not the model), in
      `src/pipeline/orchestrator.py` (depends on T008, T014, T017). Prompt-cache mechanics:
      caches are model-scoped, so the shared Stage 1 context is cached on the `claude-sonnet-5`
      side with a byte-identical prefix across Stages 2–4; stagger the fan-out (send one Sonnet
      stage, await its first streamed token so the cache entry is written, then fire the other
      two) so the shared context is not paid at full price three times (Principle II)
- [X] T021 Implement the CLI entrypoint scaffold (Typer): `analyze` command with `PATH` argument,
      `--output-dir`/`-o`, repeatable `--include`/`--exclude`, `--timeout-minutes`,
      `ANTHROPIC_API_KEY` environment-variable read, Rich incremental per-stage progress display,
      and the exit-code mapping skeleton (0/1/2/3 per `contracts/cli-interface.md`), in
      `src/cli/main.py` (depends on T020)

**Checkpoint**: Foundation ready — user story implementation can now begin in priority order

---

## Phase 3: User Story 1 - Get a Performance Analysis Report for My Code (Priority: P1) 🎯 MVP

**Goal**: End-to-end pipeline that produces `perf-report.md`/`perf-report.html` with a populated
Issues section, without ever executing, compiling, or profiling submitted code.

**Independent Test**: Submit a fixture codebase with a known performance anti-pattern and confirm
the generated report identifies it as an Issue; submit a clean fixture and confirm the report
states no issues were found; confirm no submitted code was ever executed or compiled.

### Tests for User Story 1

> Write these tests FIRST, ensure they FAIL before implementation

- [X] T022 [P] [US1] Create a fixture repository with a planted O(n²) anti-pattern, written so it
      would raise/error if actually executed, under `tests/fixtures/anti_pattern_sample/`
- [X] T023 [P] [US1] Create a fixture repository with no significant performance issues under
      `tests/fixtures/clean_sample/`
- [X] T024 [P] [US1] Integration test: CLI run against the anti-pattern fixture (mocked provider,
      via T019) asserts both `perf-report.md` and `perf-report.html` list the anti-pattern as an
      Issue with a location reference, and asserts the fixture file was never executed/compiled
      (SC-001), in `tests/integration/test_report_issues.py`
- [X] T025 [P] [US1] Integration test: CLI run against the clean fixture (mocked provider) asserts
      the Issues section explicitly states none were found rather than being omitted, in
      `tests/integration/test_report_empty_issues.py`
- [X] T026 [P] [US1] Integration test: CLI run with one stage's mocked provider call forced to
      fail/time out asserts the report still includes findings from the completed stages, lists
      the failed stage under `incomplete_stages`, and the process exits `0` (FR-012), in
      `tests/integration/test_partial_stage_failure.py`

### Implementation for User Story 1

- [X] T027 [P] [US1] Implement the structural/context-understanding stage prompt and response
      handling (code map + architectural summary) in `src/pipeline/stages/structural.py` —
      served by `claude-haiku-4-5` via the T016 provider
- [X] T028 [P] [US1] Implement the algorithmic complexity analysis stage prompt in
      `src/pipeline/stages/complexity.py` — served by `claude-sonnet-5` via the T016 provider
- [X] T029 [P] [US1] Implement the resource/I/O efficiency analysis stage prompt in
      `src/pipeline/stages/resource_io.py` — served by `claude-sonnet-5` via the T016 provider
- [X] T030 [P] [US1] Implement the concurrency/scalability analysis stage prompt in
      `src/pipeline/stages/concurrency.py` — served by `claude-sonnet-5` via the T016 provider
- [X] T031 [US1] Wire the four stage modules into the orchestrator's Stage 1 → Stages 2–4
      concurrent execution in `src/pipeline/orchestrator.py` (depends on T027–T030)
- [X] T032 [US1] Implement the report aggregator: merge `StageResult`s into `Report.issues`
      (severity-sorted, then stage order), plus `incomplete_stages` and `coverage_note`, in
      `src/report/aggregator.py`
- [X] T033 [P] [US1] Implement the Markdown template rendering the Issues section (description,
      location, severity), with an explicit "none found" marker and incomplete-stage/coverage
      notes, in `src/report/templates/perf-report.md.j2`
- [X] T034 [P] [US1] Implement the self-contained HTML template rendering the Issues section,
      content-equivalent to the Markdown template, with an explicit "none found" marker, in
      `src/report/templates/perf-report.html.j2`
- [X] T035 [US1] Implement the report renderer: render both templates from one `Report` instance
      and write `perf-report.md`/`perf-report.html` to `--output-dir`, overwriting any prior
      run's files, in `src/report/renderer.py` (depends on T033, T034)
- [X] T036 [US1] Wire the CLI `analyze` command end-to-end (invoke orchestrator, write report
      files via the renderer) and handle unparseable/syntax-error files by noting the limitation
      in the report instead of failing the run, in `src/cli/main.py` (depends on T031, T032, T035)

**Checkpoint**: User Story 1 is fully functional and independently testable

---

## Phase 4: User Story 2 - Prioritized, Actionable Recommendations (Priority: P2)

**Goal**: Report includes an Action Items section derived from Issues, ordered so the
highest-impact recommendation appears first, with concrete next steps rather than restatements.

**Independent Test**: Given a report for a fixture with issues of varying severity, confirm every
issue has an associated action item, and the highest-severity issue's action item appears first.

### Tests for User Story 2

> Write these tests FIRST, ensure they FAIL before implementation

- [X] T037 [P] [US2] Extend the anti-pattern fixture with issues of at least two different
      severities under `tests/fixtures/anti_pattern_sample/`
- [X] T038 [P] [US2] Integration test: report for the multi-severity fixture asserts action items
      are ordered highest-priority first, in `tests/integration/test_action_items_ordering.py`
- [X] T039 [P] [US2] Integration test: asserts each action item's recommendation is not textually
      identical or near-identical to its related issue's description, in
      `tests/integration/test_action_items_concreteness.py`

### Implementation for User Story 2

- [X] T040 [US2] Extend the report aggregator to derive `Report.action_items` from Issue
      findings' `suggested_action` (priority derived from the related issue's severity,
      priority-sorted), rejecting near-identical `suggested_action`/`description` pairs as a
      logged data-quality note rather than a hard failure, in `src/report/aggregator.py`
- [X] T041 [P] [US2] Update the Markdown template to render the priority-ordered Action Items
      section with an explicit "none found" marker in `src/report/templates/perf-report.md.j2`
- [X] T042 [P] [US2] Update the HTML template to render the Action Items section matching the
      Markdown content in `src/report/templates/perf-report.html.j2`

**Checkpoint**: User Stories 1 AND 2 both work independently

---

## Phase 5: User Story 3 - Valuable Findings Beyond Issues (Priority: P3)

**Goal**: Report calls out valuable findings (well-optimized patterns, notable design choices) in
a section distinct from Issues and Action Items.

**Independent Test**: Submit a fixture with a deliberately well-optimized pattern and confirm the
report surfaces it under a distinct Valuable Findings section.

### Tests for User Story 3

> Write these tests FIRST, ensure they FAIL before implementation

- [X] T043 [P] [US3] Extend the fixture repository with a deliberate well-optimized pattern
      (e.g., a memoized function or an appropriate data structure choice) under
      `tests/fixtures/anti_pattern_sample/`
- [X] T044 [P] [US3] Integration test: report for the fixture containing the well-optimized
      pattern asserts it appears under a distinct Valuable Findings section, separate from
      Issues/Action Items, in `tests/integration/test_valuable_findings.py`

### Implementation for User Story 3

- [X] T045 [US3] Extend the report aggregator to populate `Report.valuable_findings` from
      findings with `kind == valuable_finding` in `src/report/aggregator.py`
- [X] T046 [P] [US3] Update the Markdown template to render the Valuable Findings section,
      distinct from Issues/Action Items, with an explicit "none found" marker in
      `src/report/templates/perf-report.md.j2`
- [X] T047 [P] [US3] Update the HTML template to render the Valuable Findings section matching
      the Markdown content in `src/report/templates/perf-report.html.j2`

**Checkpoint**: User Stories 1–3 are all independently functional

---

## Phase 6: User Story 4 - Understand Which Analysis Stage Produced Each Finding (Priority: P4)

**Goal**: Every finding in the report is labeled with the analysis stage/skill that produced it.

**Independent Test**: Given a report with findings from at least two different analysis stages,
confirm each finding is labeled with its originating stage.

### Tests for User Story 4

> Write these tests FIRST, ensure they FAIL before implementation

- [X] T048 [P] [US4] Integration test: report generated from a fixture producing findings from at
      least two different stages asserts every finding (issues and valuable findings) is labeled
      with its originating stage, in `tests/integration/test_stage_attribution.py`

### Implementation for User Story 4

- [X] T049 [US4] Unit test verifying the orchestrator stamps `originating_stage` on every finding
      before it reaches the aggregator, independent of model output reliability, in
      `tests/unit/test_orchestrator_attribution.py`
- [X] T050 [P] [US4] Update the Markdown template to display the originating-stage label on each
      Issue, Action Item (via its related finding), and Valuable Finding in
      `src/report/templates/perf-report.md.j2`
- [X] T051 [P] [US4] Update the HTML template to display the originating-stage label matching the
      Markdown content in `src/report/templates/perf-report.html.j2`

**Checkpoint**: All four user stories are independently functional

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Contract edge cases, robustness, and validation that span multiple stories

- [X] T052 [P] Integration tests for CLI exit codes: `1` (invalid/unreadable `PATH` or no
      recognized-language code), `2` (missing/rejected `ANTHROPIC_API_KEY` before any stage
      starts), `3` (every stage failed/timed out), per `contracts/cli-interface.md`, in
      `tests/integration/test_cli_exit_codes.py`
- [X] T053 [P] Integration test for the too-large-to-analyze edge case: a token/time-budget-capped
      run reports what was and was not covered via `coverage_note` rather than silently
      truncating, in `tests/integration/test_coverage_note.py`
- [X] T054 [P] Integration test for a multi-language repository, asserting each recognized
      language present is detected and analyzed, in `tests/integration/test_multi_language.py`
- [X] T055 [P] Unit tests for aggregator severity/priority sorting edge cases (ties, mixed
      stages) in `tests/unit/test_aggregator.py`
- [X] T056 [P] Unit tests asserting the Markdown and HTML renderers produce content-equivalent
      output from the same `Report` instance, and that rendered report text is English
      regardless of the system locale (run the renderer under a non-English locale, e.g.
      `uk_UA`, and assert section headings/markers are English, FR-018), in
      `tests/unit/test_templates.py`
- [X] T057 [P] Add a live-API validation test suite (explicitly invoked, excluded from routine
      runs via the T004 pytest marker) exercising one real Anthropic API call per stage against a
      small fixture, in `tests/integration/test_live_api.py`
- [X] T058 Security hardening: verify `ANTHROPIC_API_KEY` is never accepted via a CLI flag, never
      logged, and never appears in Rich progress/error output, in `src/cli/main.py` and
      `src/providers/anthropic_client.py`
- [X] T059 Run the `quickstart.md` validation guide end-to-end against the fixture sample and
      confirm all six expected outcomes (validated via the mocked provider; live-API rerun
      pending an `ANTHROPIC_API_KEY`)
- [X] T060 Timing validation: run against a typical-sized fixture (tens of thousands of LOC),
      confirm completion under 10 minutes (SC-004), and record the measured wall-clock time and
      per-stage token usage to replace the design-time estimate in `research.md` (local
      pipeline measured at ~1.0s for ~47K LOC; API-dependent wall-clock/token measurement
      pending an `ANTHROPIC_API_KEY` — see research.md §Measured figures)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends only on Foundational
- **User Story 2 (Phase 4)**: Depends on Foundational; extends the aggregator/templates built in
  US1 (`src/report/aggregator.py`, `perf-report.*.j2`), so is built after US1 in priority order
- **User Story 3 (Phase 5)**: Depends on Foundational; extends the same aggregator/templates,
  built after US2
- **User Story 4 (Phase 6)**: Depends on Foundational; extends the same templates, built after US3
- **Polish (Phase 7)**: Depends on all four user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: No dependency on other stories — the true MVP
- **User Story 2 (P2)**: Shares `src/report/aggregator.py` and the Jinja2 templates with US1, so
  is sequenced after it, but is independently testable (Action Items section can be verified on
  its own)
- **User Story 3 (P3)**: Same shared-file relationship, sequenced after US2, independently
  testable
- **User Story 4 (P4)**: Same shared-file relationship, sequenced after US3, independently
  testable

### Within Each User Story

- Tests are written before implementation and MUST fail first
- Models/schemas (Foundational) before stage modules
- Stage modules before orchestrator wiring
- Orchestrator wiring before aggregator changes
- Aggregator changes before template changes
- Templates before renderer/CLI wiring

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel
- Within Foundational, the four model files (T005–T007, then T008) can start in parallel, and
  T009–T011 (tests, discovery) can run in parallel with each other once their targets exist
- Once Foundational completes, US1's four stage modules (T027–T030) can be implemented in
  parallel by different people/agents
- Within each story, Markdown/HTML template updates (e.g., T033/T034, T041/T042, T046/T047,
  T050/T051) can run in parallel since they touch different files
- Different user stories should NOT be worked on fully in parallel by default, since US2–US4 edit
  the same aggregator and template files US1 creates — parallel teams should coordinate on those
  shared files or serialize story completion

---

## Parallel Example: User Story 1

```bash
# Launch US1 tests together:
Task: "Create fixture repository with planted O(n²) anti-pattern in tests/fixtures/anti_pattern_sample/"
Task: "Create fixture repository with no significant issues in tests/fixtures/clean_sample/"
Task: "Integration test for issue identification in tests/integration/test_report_issues.py"
Task: "Integration test for empty-issues report in tests/integration/test_report_empty_issues.py"
Task: "Integration test for partial stage failure in tests/integration/test_partial_stage_failure.py"

# Launch US1's four stage modules together:
Task: "Structural/context stage in src/pipeline/stages/structural.py"
Task: "Algorithmic complexity stage in src/pipeline/stages/complexity.py"
Task: "Resource/I/O efficiency stage in src/pipeline/stages/resource_io.py"
Task: "Concurrency/scalability stage in src/pipeline/stages/concurrency.py"

# Launch US1's two output templates together (after the aggregator, T032, is done):
Task: "Markdown Issues section in src/report/templates/perf-report.md.j2"
Task: "HTML Issues section in src/report/templates/perf-report.html.j2"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: run the User Story 1 independent test (fixture with anti-pattern →
   Issue in report; clean fixture → explicit "none found"; confirm no execution occurred)
5. Demo/ship the MVP: a working CLI that turns a codebase into a report with a real Issues section

### Incremental Delivery

1. Setup + Foundational → foundation ready
2. Add User Story 1 → validate independently → MVP
3. Add User Story 2 → validate Action Items ordering/concreteness independently
4. Add User Story 3 → validate Valuable Findings section independently
5. Add User Story 4 → validate stage attribution independently
6. Phase 7 Polish → exit-code contract, edge cases, timing validation against SC-004

---

## Notes

- [P] tasks = different files, no unresolved dependency
- [Story] label maps a task to its user story for traceability
- US2–US4 intentionally share `src/report/aggregator.py` and the two Jinja2 templates with US1 —
  each still has its own independent test criteria and checkpoint, but true file-level parallelism
  across stories is limited by design (the Report entity's sections are additive)
- Verify each story's tests fail before implementing that story
- Commit after each task or logical group
- Stop at any checkpoint to validate a story independently

---

## Phase 8: Convergence

**Purpose**: Remaining work identified by `/speckit-converge` on 2026-08-04 — repo-level
execution documentation (per user direction: the tool must be executable by an AI agent such as
Claude, with instructions for running it against a repository) and the pending live-API
validation.

- [ ] T061 Write an "Installation & Usage" section in `README.md` documenting how to execute
      the tool against a local repository: prerequisites (Python 3.12+, virtualenv,
      `pip install -e .`), exporting `ANTHROPIC_API_KEY`, the
      `perf-ai analyze PATH --output-dir DIR` invocation with `--include`/`--exclude`/
      `--timeout-minutes`, the two output artifacts (`perf-report.md`, `perf-report.html`), and
      the 0/1/2/3 exit-code contract, consistent with `contracts/cli-interface.md` and
      `quickstart.md`, per user input / FR-015 (missing)
- [ ] T062 Add a "Running via an AI agent (e.g. Claude)" section to `README.md` documenting the
      non-interactive execution contract an agent relies on: no prompts or TTY required,
      authentication only via the `ANTHROPIC_API_KEY` environment variable, machine-checkable
      exit codes for success/partial/failure, and reading `perf-report.md` from `--output-dir`
      as the machine-consumable result of a run, per user input / FR-015 (missing)
- [ ] T063 Run the explicitly-invoked live-API suite
      (`pytest -m live_api --override-ini addopts=''`) and the `quickstart.md` timing check once
      an `ANTHROPIC_API_KEY` is available, and replace the design-time estimate in
      `research.md` §Measured figures with measured wall-clock time and per-stage token usage,
      per SC-004 / Constitution V (partial)

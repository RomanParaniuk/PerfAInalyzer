# Tasks: AI Agent Execution & Parallelism

**Input**: Design documents from `/specs/002-ai-agent-execution/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/ (agent-skill-interface.md, agent-support-cli.md, plugin-packaging.md), quickstart.md

**Tests**: INCLUDED — plan.md's Technical Context explicitly specifies the pytest surface (unit, contract, integration) plus scripted manual quickstart validation, and the constitution's quality gates require verified (not assumed) behavior. Test tasks are written first within each story and must fail before implementation.

**Organization**: Tasks are grouped by user story so each story is independently implementable and testable. US1 (skill runs end-to-end from an agent) is the MVP; US2 (parallelism question, wave bound, dedup, graceful degradation) layers on top; US3 (README) documents both paths.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story the task belongs to (US1, US2, US3) — user-story phases only
- Every task names its exact file path(s)

## Path Conventions

Single project at repository root (per plan.md): `src/`, `tests/`, plus plugin packaging at the root (`.claude-plugin/`, `skills/`, `scripts/`). New agent-path code is isolated in `src/agentrun/` and `src/cli/agent.py`; `src/pipeline/`, `src/providers/`, `src/models/`, `src/report/`, `src/lib/`, and the `analyze` command are **never modified** (FR-003).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the new directory skeletons and capture the baseline that makes FR-003's "unchanged" claim verifiable later (the repo is not under git, so the baseline must be recorded explicitly).

- [X] T001 Create the new skeletons: package `src/agentrun/__init__.py` (empty, with module docstring), and empty directories `.claude-plugin/`, `skills/perf-analyze/`, `scripts/` at the repository root
- [X] T002 [P] Record the pre-change baseline: run `pytest` in `.venv` and confirm the existing 001 suite is green; save the passing-test list and a checksum manifest of all files under `src/pipeline/`, `src/providers/`, `src/models/`, `src/report/`, `src/lib/`, and `src/cli/main.py` to `specs/002-ai-agent-execution/baseline-checksums.txt` (used by T029 to prove FR-003)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The additive CLI mount point and the shared test fixtures every story's tests consume. No user story work can begin until this phase is complete.

- [X] T003 Scaffold the additive `perf-ai agent` Typer sub-app: create `src/cli/agent.py` with an `agent` Typer app exposing stub `scope` and `render` commands, and register it in `src/cli/main.py` via `app.add_typer(...)` — the `analyze` command and all its imports must remain byte-for-byte unchanged — the `add_typer` registration line is the only permitted delta in `src/cli/main.py`, matching T029 (FR-003)
- [X] T004 [P] Build the shared agent-result fixture sets per data-model.md "Stage Result File": `tests/fixtures/agent_results_partial/` (a `workplan.json` plus a mix of valid stage-result files, one schema-invalid file, one wrong-stage file, and one missing expected unit; include two same-stage files with a planted duplicate finding at the same location for later dedup tests) and `tests/fixtures/agent_results_all_failed/` (a `workplan.json` whose expected units all have missing or invalid result files) — referenced by quickstart.md §6 and the integration tests

**Checkpoint**: Foundation ready — user story phases can begin.

---

## Phase 3: User Story 1 - Run the Analysis Pipeline from Inside an AI Agent (Priority: P1) 🎯 MVP

**Goal**: A developer installs the `perf-ai` plugin from this repository (repo doubles as its own marketplace), invokes `/perf-analyze <path> max-parallel=N` in a Claude Code session with **no hosted credentials**, and gets `perf-report.md` / `perf-report.html` structurally identical to hosted-CLI reports — with every deterministic step executed by the bundled 001 code through the stdlib bootstrap (FR-001, FR-002, FR-003, FR-004, FR-014).

**Independent Test**: In a Claude Code session in another project with `ANTHROPIC_API_KEY` unset, run `/plugin marketplace add <path>`, `/plugin install perf-ai@perf-ai`, then `/perf-analyze <fixture> max-parallel=2`; confirm a complete report with the same sections and stage labels as an `analyze`-path report (quickstart.md §3).

### Tests for User Story 1 (write first — must fail before implementation)

- [X] T005 [P] [US1] Contract test for plugin packaging in `tests/contract/test_plugin_manifests.py`: `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` parse, plugin name is `perf-ai` in both, `plugin.json` `version` equals `project.version` in `pyproject.toml` (currently 0.1.0), marketplace lists exactly one plugin with `source: "./"`, and every contract-required path exists (`skills/perf-analyze/SKILL.md`, `scripts/plugin_run.py`, `pyproject.toml`); also assert `SKILL.md` references bundled files only via `${CLAUDE_PLUGIN_ROOT}` and never bare `perf-ai` on PATH (plugin-packaging.md)
- [X] T006 [P] [US1] Contract test for the work-plan JSON shape in `tests/contract/test_workplan_schema.py`: all fields of data-model.md "Work Plan" present; partitions pairwise disjoint and jointly covering all discovered files; units ordered structural-first then stage-major × partition-index; `P = clamp(ceil(max_parallel/3), 1, file_count)`; identical inputs → identical plan
- [X] T007 [P] [US1] Contract test for stage-result file acceptance/rejection in `tests/contract/test_stage_result_files.py`: valid envelope `{"unit_id", "result"}` accepted; unparsable JSON, schema-invalid payload, `unit_id` ≠ filename stem, and `stage_name` ≠ unit's stage each rejected with a human-readable reason (data-model.md "Stage Result File"; agent-support-cli.md)
- [X] T008 [P] [US1] Unit test for validation → failed-unit mapping in `tests/unit/test_results.py`: missing/unparsable/invalid/wrong-stage result files each become a failed unit with reason recorded while valid files load; `originating_stage` is stamped structurally by code, never trusted from the payload
- [X] T009 [P] [US1] Integration test for `perf-ai agent scope` in `tests/integration/test_agent_scope_cli.py`: exit 0 + plan JSON on stdout for `tests/fixtures/anti_pattern_sample --max-parallel 4`; exit 2 with message naming the flag and range when `--max-parallel` is missing, 0, negative, non-integer, or > 10; exit 1 with problem-and-fix message for a nonexistent path and for a directory with no recognized code; `--include`/`--exclude` semantics match `analyze`; no stack traces in any error output
- [X] T010 [P] [US1] Integration test for `perf-ai agent render` in `tests/integration/test_agent_render_cli.py`: `tests/fixtures/agent_results_partial` → exit 0, both report files written, failed units named in coverage note / incomplete stages; `tests/fixtures/agent_results_all_failed` → exit 3 with a failure-noting (not empty-but-clean) report; missing results dir or absent/unparsable `workplan.json` → exit 1
- [X] T011 [P] [US1] Integration test for report parity in `tests/integration/test_agent_report_parity.py`: build the same findings once through `agent render` fixtures and once through the analyze-path report pipeline (aggregator + renderer invoked directly on equivalent `StageResult`s) and assert the two `perf-report.md` outputs are structurally identical — same sections, ordering, stage labels, empty-section handling (FR-004, SC-002)
- [X] T012 [P] [US1] Integration test for the bootstrap in `tests/integration/test_plugin_run.py`: interpreter < 3.12 (subprocess with a stubbed `sys.version_info` or a fake `python3` shim) → non-zero exit naming the required version and how to obtain it before any other work; first invocation provisions `.venv` inside the checkout and writes the stamp last; second invocation skips provisioning (stamp reuse); stale stamp (changed `pyproject.toml` hash) re-provisions; exit codes from the inner `perf-ai` are forwarded unchanged; no writes outside the plugin directory

### Implementation for User Story 1

- [X] T013 [P] [US1] Implement `src/agentrun/workplan.py`: Pydantic models `Partition`, `WorkUnit`, `WorkPlan` per data-model.md; partition computation `P = clamp(ceil(N/3), 1, file_count)` with greedy size-balanced bin-packing (largest file first into currently smallest bin, disjoint cover); unit derivation (1 `structural_context--all` unit first, then stage-major × partition order); deterministic serialization (research.md §5)
- [X] T014 [P] [US1] Implement `src/agentrun/results.py`: load `<unit_id>.json` files from a results dir against the work plan's expected unit set; validate payloads with the existing `StageResult` model from `src/models/`; check `unit_id`-vs-filename and stage match; stamp `originating_stage` structurally; record each failed unit with a human-readable reason; map unit outcomes to stage status (all valid → completed; some failed → completed + coverage-note text naming failed partitions; all failed → stage failed) per data-model.md "Consolidated Run"
- [X] T015 [US1] Implement `perf-ai agent scope` in `src/cli/agent.py`: REQUIRED `--max-parallel` (missing/non-integer/out-of-1–10 → exit 2 with range and the interactive alternative — the coded FR-009 gate), optional PATH defaulting to cwd, repeatable `--include`/`--exclude` with `analyze` semantics; preflight via existing `src/lib/discovery.py` (path exists/readable, recognized code present — else exit 1 with problem and fix); emit the work-plan JSON from T013 to stdout; offline, never reads `ANTHROPIC_API_KEY` (agent-support-cli.md)
- [X] T016 [US1] Implement `perf-ai agent render` in `src/cli/agent.py`: `--results-dir` (must contain `workplan.json`), `--scope`, `--output-dir`; consume T014 to validate and classify units; union each stage's valid findings; call the **existing** `src/report/aggregator.aggregate()` and `src/report/renderer.write_reports()` to produce `perf-report.md`/`perf-report.html`; exit 0 on any written report incl. partial, 1 on invalid invocation, 3 when every unit of every stage failed (failure-noting report still written) (agent-support-cli.md; dedup pass is added in US2/T024)
- [X] T017 [P] [US1] Implement the stdlib-only bootstrap `scripts/plugin_run.py`: Python ≥ 3.12 gate first (else non-zero exit naming required version + how to obtain it); provision private venv at `<plugin-root>/.venv` by `pip install`-ing the checkout, stamp file (package version + `pyproject.toml` hash) written last so half-provisioned states are impossible; stale stamp → re-provision; then exec the venv's `perf-ai` entry point forwarding all args and the exit code unchanged; zero third-party imports; only writes inside the plugin directory (plugin-packaging.md, research.md §2)
- [X] T018 [P] [US1] Create the plugin packaging manifests: `.claude-plugin/plugin.json` (name `perf-ai`, version matching `pyproject.toml`, description, author) and `.claude-plugin/marketplace.json` (single plugin, same name, `source: "./"`) per plugin-packaging.md
- [X] T019 [US1] Author the analysis skill `skills/perf-analyze/SKILL.md` (YAML frontmatter + procedure): parse optional `[path]` and `max-parallel=N` arguments; validate a pre-supplied N (cap > 10 to 10 with an explicit notice; otherwise-invalid pre-supplied values end the run with the validation message); preflight — check `python3` ≥ 3.12 exists, then run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/plugin_run.py" agent scope <path> --max-parallel N` and stop with the reported problem+fix on failure; create a per-run scratch results dir, copy the plan there as `workplan.json`; launch the structural unit first, then remaining units in waves of ≤ N subagents, each subagent prompt carrying the shared structural summary, its unit's file list, the 001 stage instructions, and the mandate to write `<unit_id>.json` in the stage-result schema; finish via `plugin_run.py agent render` and report where both reports were written, run status (complete/partial + what failed), and the parallelism used incl. any capped-value notice (agent-skill-interface.md; interactive question flow is added in US2/T025)
- [X] T020 [US1] Validate US1 end-to-end per quickstart.md §2–§3 *(automatable parts done; the live-session `/plugin marketplace add` + `/plugin install` flow and PATH-shim runtime check remain manual — see quickstart.md "Validation record")*: helper-CLI and bootstrap smoke from a bare interpreter (provisioning then stamp reuse); in a Claude Code session in another project with `ANTHROPIC_API_KEY` unset — marketplace add, plugin install, `/perf-analyze <fixture> max-parallel=2` produces a structurally CLI-identical report; prerequisite-failure and missing-runtime checks stop before analysis with problem+fix; `perf-ai analyze` still behaves exactly as before (FR-003 spot check)

**Checkpoint**: US1 fully functional — credential-free plugin install + skill run yields a CLI-indistinguishable report. MVP deliverable.

---

## Phase 4: User Story 2 - Run Multiple Subagents in Parallel with a Per-Run Limit (Priority: P2)

**Goal**: The skill asks for (or accepts) a per-run parallelism limit with no default, validates and caps it at 10, never exceeds it (wave scheduling), merges duplicate findings from parallel subagents, and degrades gracefully on partial failure (FR-005–FR-011).

**Independent Test**: Invoke `/perf-analyze` without `max-parallel`; confirm it asks and waits, rejects `abc`/`0`/`-3` with reasons, caps `15` to 10 with a notice, and at answer `2` never has more than 2 subagents active; corrupt one unit's result file and confirm the report keeps successful findings and names what failed (quickstart.md §4).

### Tests for User Story 2 (write first — must fail before implementation)

- [X] T021 [P] [US2] Unit test for partitioning in `tests/unit/test_workplan.py`: determinism (same inputs → identical plan), size balance of the greedy bin-pack (bounded byte spread across partitions), `P` clamping at `file_count` when N exceeds available work (edge case "more parallelism than work"), N=1 → exactly 4 units, N=4 → P=2 → 7 units
- [X] T022 [P] [US2] Unit test for dedup in `tests/unit/test_dedupe.py`: merge key `(stage, kind, location.file_path, location.line_start, normalized(symbol))`; survivor by highest severity rank, then longest `suggested_action`, then first in sorted-filename order; survivor kept verbatim; cross-stage findings at the same location NOT merged (data-model.md "Dedup rule")

### Implementation for User Story 2

- [X] T023 [US2] Implement `src/agentrun/dedupe.py`: location-keyed duplicate-finding merge applied per stage to the union of its units' findings, with the survivor-selection rule above; deterministic and token-free (research.md §7)
- [X] T024 [US2] Wire the dedup pass into `perf-ai agent render` in `src/cli/agent.py` (between per-stage union and aggregation), and extend `tests/integration/test_agent_render_cli.py` to assert that the planted same-stage duplicate in `tests/fixtures/agent_results_partial/` appears exactly once in the rendered report (FR-011, quickstart.md §6)
- [X] T025 [US2] Extend `skills/perf-analyze/SKILL.md` with the parallelism-question flow: when no `max-parallel` was pre-supplied, ask the developer for the maximum parallel subagents before any analysis and wait — no suggested default displayed; re-ask on zero/negative/non-numeric with the reason; cap answers > 10 at 10 with an explicit notice; treat the context as non-interactive when the question cannot be presented or no answer arrives (e.g., headless `claude -p` runs); in that case, with no pre-supplied value, fail fast with a message naming the `max-parallel=N` override; report per-wave progress (launched/completed/failed); after the final wave, re-run each unit whose subagent visibly failed or timed out exactly once (a single retry pass, still bounded by N); units that fail again stay failed for rendering (agent-skill-interface.md guarantees 3–7)
- [X] T026 [US2] Validate US2 per quickstart.md §4–§6 *(coded gates, wave bound, clamping, dedup, and failure semantics verified; SC-004 numbers recorded in quickstart.md "Validation record" — the ≥30% comparison is confounded by headless notification latency and must be re-measured in a live session; interactive ask/re-ask/cap is likewise a live-session check)*: interactive question/re-ask/cap behavior; wave bound observed at answer 2 (never > 2 active); more-parallelism-than-work run completes without erroring; partial-failure run still reports successful findings and names the failure; SC-004 timing — same scope at `max-parallel=1` vs `max-parallel=4`, N=4 at least 30% faster, both numbers recorded under "Done when" in `specs/002-ai-agent-execution/quickstart.md` (Constitution V)

**Checkpoint**: US1 and US2 both work — parallel runs respect the confirmed limit, consolidate duplicates, and degrade gracefully.

---

## Phase 5: User Story 3 - Learn to Work with the Project from the README (Priority: P3)

**Goal**: A complete root README that takes a new developer from clone to a successful analysis run on either path, and to making changes, without outside help (FR-012, FR-013).

**Independent Test**: A developer who has never seen the project follows README top-to-bottom on a fresh setup: every command works as written, first successful run in under 15 minutes, and the layout section points them to the right code for a described change (quickstart.md §7).

### Implementation for User Story 3

- [X] T027 [US3] Rewrite root `README.md` per research.md §11, in this order: what the tool does + constraints (static analysis, no code execution); prerequisites (Python 3.12+ both paths; Claude Code for the plugin path; plugin path supported on macOS/Linux); installation — hosted CLI (venv + `pip install -e ".[dev]"`) and plugin (`/plugin marketplace add` GitHub-or-local-path + `/plugin install perf-ai@perf-ai`); configuration (CLI: `ANTHROPIC_API_KEY`; plugin: explicitly none); running an analysis — `perf-ai analyze` and `/perf-analyze` incl. the parallelism question, the `max-parallel=N` override, the cap of 10, and first-run venv provisioning with its one-time network need; where reports are written and what they contain; codebase layout for contributors (stages, aggregator, templates, `src/agentrun/`, `src/cli/agent.py`, `skills/perf-analyze/SKILL.md`, `scripts/plugin_run.py`, where to change report rendering); running the tests (`pytest` and the explicit live-API suite); troubleshooting (missing key on CLI path, missing/old Python on plugin path, no recognized code, all-stages failure, capped parallelism) — every command copy-paste runnable in order
- [X] T028 [US3] Validate US3 per quickstart.md §7 *(every offline command block executed as written; all layout-section paths verified to exist; the plugin-install blocks and the 15-minute fresh-developer timing need the live session)*: on a fresh clone/clean checkout, execute every README command block exactly as written, in order (SC-006); confirm the clone-to-first-report path fits in 15 minutes (SC-005) and the layout section correctly locates report rendering, stages, aggregator, agent sub-app, and skill; fix README defects found

**Checkpoint**: All three user stories independently functional and documented.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Prove the additive-only guarantee, and run the full validation gate.

- [X] T029 [P] Verify FR-003 against the T002 baseline: re-run the checksum manifest over `src/pipeline/`, `src/providers/`, `src/models/`, `src/report/`, `src/lib/`, `src/cli/main.py` (only permitted delta in `src/cli/main.py`: the `add_typer` registration of the agent sub-app) and compare with `specs/002-ai-agent-execution/baseline-checksums.txt`; run the full `pytest` suite green, pre-existing 001 tests untouched and passing
- [X] T030 Run the complete quickstart.md validation pass *(results and the token-cost estimate recorded in quickstart.md "Validation record (2026-08-05)"; three items deferred to a live Claude Code session: marketplace-install flow, interactive parallelism question, and a clean SC-004 timing)* (§1–§7) and confirm its "Done when" checklist: automated suite green incl. packaging + bootstrap tests, helper-CLI gates correct, credential-free install + run parity, parallelism contract behavior, recorded ≥30% SC-004 speedup, graceful failure semantics, README walkthrough on a fresh setup; record the token-cost estimate (research.md §9) and SC-004 numbers for the constitution's review gate

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: T003 depends on T001; T004 independent — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Phase 2; no dependencies on other stories
- **US2 (Phase 4)**: Depends on Phase 2; builds on US1's `render` (T024 edits `src/cli/agent.py`) and `SKILL.md` (T025 extends T019) — schedule after US1
- **US3 (Phase 5)**: Depends on Phase 2; documents US1/US2 behavior, so final validation (T028) needs both, though drafting T027 can start from the contracts once US1 is stable
- **Polish (Phase 6)**: Depends on all completed stories

### Within-Story Dependencies

- **US1**: T005–T012 (tests) before T013–T019 (implementation); T015 depends on T013; T016 depends on T014; T019 depends on T015–T018; T020 last
- **US2**: T021–T022 before T023; T024 depends on T023; T025 independent of T023/T024 (different file); T026 last
- **US3**: T027 before T028

### Parallel Opportunities

- Phase 1: T002 parallel with T001
- Phase 2: T004 parallel with T003
- US1: all eight test tasks T005–T012 in parallel; then T013, T014, T017, T018 in parallel (four different files)
- US2: T021 and T022 in parallel; T025 in parallel with T023/T024 (different files)
- Polish: T029 parallel with T030's early sections

---

## Parallel Example: User Story 1

```bash
# Launch all US1 test tasks together (8 different files):
Task: "Contract test plugin manifests in tests/contract/test_plugin_manifests.py"
Task: "Contract test work-plan schema in tests/contract/test_workplan_schema.py"
Task: "Contract test stage-result files in tests/contract/test_stage_result_files.py"
Task: "Unit test results mapping in tests/unit/test_results.py"
Task: "Integration test agent scope CLI in tests/integration/test_agent_scope_cli.py"
Task: "Integration test agent render CLI in tests/integration/test_agent_render_cli.py"
Task: "Integration test report parity in tests/integration/test_agent_report_parity.py"
Task: "Integration test bootstrap in tests/integration/test_plugin_run.py"

# Then launch the four independent implementation files together:
Task: "Implement src/agentrun/workplan.py"
Task: "Implement src/agentrun/results.py"
Task: "Implement scripts/plugin_run.py"
Task: "Create .claude-plugin/plugin.json and .claude-plugin/marketplace.json"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 (Setup) → Phase 2 (Foundational)
2. Phase 3 complete: credential-free plugin install + `/perf-analyze <path> max-parallel=N` producing a CLI-identical report
3. **STOP and VALIDATE** with T020 (quickstart §2–§3) — this alone delivers the core requested capability

### Incremental Delivery

1. Setup + Foundational → skeletons and fixtures ready
2. US1 → validate → MVP: agent-path analysis works end to end
3. US2 → validate → interactive parallelism, wave bound, dedup, graceful degradation, SC-004 measured
4. US3 → validate → README-only onboarding works on a fresh setup
5. Polish → FR-003 checksum proof + full quickstart pass

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks
- Tests are written first within each story and must fail before their implementation tasks begin
- The repository is not under git: the FR-003 "unchanged" guarantee is enforced via the T002/T029 checksum manifest instead of `git diff`
- The dedup pass deliberately lands in US2 (T023/T024): US1's independent test runs at `max-parallel=2` → one partition per stage → no same-stage duplicates are possible, so US1 is complete and testable without it
- `SKILL.md` and `src/cli/agent.py` are each touched by two stories (T019→T025, T016→T024); those pairs are sequential by design, never parallel

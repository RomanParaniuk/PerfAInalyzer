# Quickstart Validation: AI Agent Execution & Parallelism

**Feature**: `002-ai-agent-execution` | **Date**: 2026-08-04

Runnable scenarios proving the feature works end-to-end. Contracts referenced:
[agent-skill-interface.md](./contracts/agent-skill-interface.md),
[agent-support-cli.md](./contracts/agent-support-cli.md),
[plugin-packaging.md](./contracts/plugin-packaging.md); entity rules in
[data-model.md](./data-model.md).

## Prerequisites

- Python 3.12+ on PATH as `python3`.
- For the developer-checkout scenarios (§1–§2): project installed editable with dev extras:

  ```bash
  python -m venv .venv && source .venv/bin/activate
  pip install -e ".[dev]"
  ```

- Claude Code installed and signed in (only for the in-agent scenarios §3–§6; the helper-CLI
  and test scenarios are offline).
- **No `ANTHROPIC_API_KEY` in the environment** for every plugin-path scenario — that absence
  is itself part of what is being validated (FR-002):

  ```bash
  unset ANTHROPIC_API_KEY
  ```

## 1. Automated suite (offline, fast)

```bash
pytest
```

**Expected**: all tests pass, including the new unit/contract/integration tests for
`agent scope` (preflight errors, plan determinism, `--max-parallel` bounds), `agent render`
(schema rejection matrix, dedup, exit codes 0/1/3), the report-parity test asserting the agent
path and the analyze path produce structurally identical reports from the same findings
(SC-002), the plugin-packaging contract tests (manifests parse, names agree, referenced paths
exist), and the bootstrap tests (version gate message, first-use provisioning, stamp reuse,
exit-code forwarding). The pre-existing 001 suite passes untouched — evidence for FR-003.

## 2. Helper CLI + bootstrap smoke (offline, no agent needed)

```bash
# Preflight + work plan on the bundled fixture repo
perf-ai agent scope tests/fixtures/anti_pattern_sample --max-parallel 4
```

**Expected**: exit 0; JSON work plan on stdout with detected languages, ≥1 partition,
and units ordered structural-first (see data-model.md "Work Plan").

```bash
# Fail-fast gates
perf-ai agent scope tests/fixtures/anti_pattern_sample; echo "exit=$?"           # missing flag
perf-ai agent scope tests/fixtures/anti_pattern_sample --max-parallel 0; echo "exit=$?"
perf-ai agent scope /nonexistent --max-parallel 4; echo "exit=$?"
```

**Expected**: exit 2 with a message naming `--max-parallel` and the accepted range (first two);
exit 1 naming the bad path and the fix (third). No stack traces (Constitution IV).

```bash
# Bootstrap runs the same command from a bare interpreter (no activated venv)
deactivate 2>/dev/null; python3 scripts/plugin_run.py agent scope tests/fixtures/anti_pattern_sample --max-parallel 4; echo "exit=$?"
```

**Expected**: on first use, a one-time provisioning message while `.venv` is created inside the
checkout; then the identical work-plan JSON and exit 0. A second invocation skips provisioning
(stamp reuse). Nothing outside the checkout is modified (FR-014).

## 3. User Story 1 — install the plugin and run a full analysis (P1)

In a Claude Code session opened in **another** project (not this repository), with
`ANTHROPIC_API_KEY` unset:

```text
/plugin marketplace add /absolute/path/to/Perf-AI
/plugin install perf-ai@perf-ai
/perf-analyze /absolute/path/to/Perf-AI/tests/fixtures/anti_pattern_sample max-parallel=2
```

**Expected**:
1. After the two install commands, `/perf-analyze` is invocable with no further setup
   (US1 scenario 4); no credential prompt or error at any point (FR-002, SC-001).
2. Preflight passes (Python found; scope valid); on first run a brief one-time provisioning
   note may appear (bootstrap creating its private venv).
3. Per-wave progress is reported; structural context completes before other stages.
4. `perf-report.md` and `perf-report.html` are written and contain the Issues, Action Items,
   and Valuable Findings sections with stage labels — same structure as an `analyze`-path
   report (FR-004; the fixture's planted anti-patterns should surface as issues).
5. Compare section headings against a CLI-produced report (or the parity test's golden output):
   indistinguishable in structure (SC-002).

**Prerequisite-failure check** (edge case): `/perf-analyze /nonexistent max-parallel=2` →
stops before any analysis with a message naming the problem and fix.

**Missing-runtime check** (FR-014 edge case): with `python3` shadowed by a stub that reports
version 3.10 (`PATH` manipulation in a throwaway shell), invoke the skill → it stops before
any analysis, naming the required Python version and how to obtain it.

**CLI-unchanged check** (FR-003): with a valid `ANTHROPIC_API_KEY` exported,
`perf-ai analyze tests/fixtures/anti_pattern_sample` behaves exactly as before this feature.

## 4. User Story 2 — parallelism question and bound (P2)

Interactive, in Claude Code, **without** pre-supplying a value:

```text
/perf-analyze tests/fixtures/anti_pattern_sample
```

**Expected** (FR-006, FR-007, SC-003):
1. Before any analysis, the skill asks for the maximum parallel subagents and waits — no
   suggested default is displayed, and nothing proceeds until an explicit answer.
2. Answer `abc`, then `0`, then `-3`: each is rejected with the reason and re-asked.
3. Answer `15`: the skill states the value was capped to 10, then proceeds with 10.
4. Re-run and answer `2` on a scope with more than 2 pending units: observe launched subagents
   in the session — never more than 2 active at once, work proceeding in waves (FR-008).
5. More-parallelism-than-work check: run against a scope with one analyzable file and answer
   `8` — the run uses only as many subagents as there are units, without erroring.

**Partial-failure check** (FR-010): during a parallel run, corrupt one unit's result JSON in the
scratch results dir before the render step (or use the render-level scenario in §6). The final
report still contains successful units' findings and names what did not complete.

## 5. SC-004 timing measurement (≥30% speedup at N=4)

On a scope with ≥4 independent analyzable units (the fixture set, or `src/` of this repo):

1. Run `/perf-analyze src max-parallel=1` — record wall-clock duration of the analysis phase.
2. Fresh session, same scope: `/perf-analyze src max-parallel=4` — record duration.

**Expected**: the N=4 run completes at least 30% faster than the N=1 run. Record both numbers in
the release notes/review (Constitution V requires the measurement, not the assumption).

## 6. Render-path failure semantics without an agent (offline)

Using the fixture stage-result sets under `tests/fixtures/` (created by this feature's tests):

```bash
# Mixed success/failure results → partial report, exit 0
perf-ai agent render --results-dir tests/fixtures/agent_results_partial \
  --scope tests/fixtures/anti_pattern_sample --output-dir /tmp/perf-partial; echo "exit=$?"

# Every unit failed → failure-noting report, exit 3
perf-ai agent render --results-dir tests/fixtures/agent_results_all_failed \
  --scope tests/fixtures/anti_pattern_sample --output-dir /tmp/perf-failed; echo "exit=$?"
```

**Expected**: first command exits 0, report notes the failed portion (coverage note /
incomplete stages); second exits 3 and the report clearly records the total failure — it does
not look like a clean empty result (FR-010). Duplicate findings planted across two same-stage
result files appear once in the report (FR-011).

## 7. User Story 3 — README walkthrough (P3)

On a fresh clone (or `git clean -xdf` equivalent), follow the rewritten root `README.md` top to
bottom, executing every command block exactly as written, in order.

**Expected** (FR-012, FR-013, SC-005, SC-006):
1. Every command succeeds as written — installation of both paths (hosted CLI with a key;
   plugin via `/plugin marketplace add` + `/plugin install`), the parallelism prompt and the
   `max-parallel=N` override, and the first-run provisioning note with its one-time network
   need.
2. A developer new to the project reaches a first successful analysis in under 15 minutes.
3. The codebase-layout section correctly points to where report rendering, stages, the
   aggregator, the agent sub-app, and the skill live, and the test instructions (`pytest`, and
   the explicit live-API invocation) work as documented.

## Done when

All seven sections pass: automated suite green (including packaging and bootstrap tests),
helper-CLI and bootstrap gates correct, a credential-free marketplace install + skill run
produces a CLI-indistinguishable report, the parallelism question/cap/bound behaves per
contract, the ≥30% speedup is measured and recorded, failure semantics degrade gracefully, and
the README walkthrough completes on a fresh setup.

### Validation record (2026-08-05)

- **§1 automated suite**: PASS — 196 tests green (117 pre-existing 001 tests untouched +
  79 new unit/contract/integration tests), `ruff` and `mypy` clean.
- **§2 helper CLI + bootstrap smoke**: PASS — scope plan/exit-code gates verified by hand;
  bootstrap provisioned its venv on first use (stderr notice, clean plan JSON on stdout),
  reused the stamp silently on the second run, and forwarded inner exit codes (exit 1
  observed through the bootstrap for a bad path).
- **§3 skill-procedure run**: PASS for the orchestration procedure — executed with real
  subagents at `max-parallel=2` on the fixture with no `ANTHROPIC_API_KEY` (structural
  unit strictly first, waves of ≤ 2, schema-validated result files, `agent render` exit 0,
  report with all sections and stage labels). The `/plugin marketplace add` +
  `/plugin install` install flow and the missing-runtime PATH-shim check still need a live
  interactive Claude Code session.
- **§4 parallelism contract**: coded gate fully verified (exit-2 matrix for missing/0/-3/
  abc/2.5/11); more-parallelism-than-work verified (1-file scope at N=8 → 1 partition,
  4 units). The interactive ask/re-ask/cap conversation is skill prose — live-session check
  pending.
- **§5 SC-004 timing**: MEASURED BUT NOT VALID IN THIS ENVIRONMENT — attempted N=1 vs
  N=4 on the fixture (same model per unit both runs). Analysis phase from work-plan start
  to last result-file write: N=1 = 328 s, N=4 = 797 s. Per-unit work was 21–80 s and the
  wave of 4 demonstrably ran concurrently (its 4 result files landed within 50 s of each
  other), but headless orchestration added 200–400 s of completion-notification latency
  per wave, which dominates the totals. The ≥30% comparison must be re-run inside a live
  Claude Code session (where a wave is one message and control returns when the wave
  completes) before release.
- **§6 render-path failure semantics**: PASS — partial fixture → exit 0, report names the
  failed partition and the incomplete stage; all-failed fixture → exit 3 with a
  failure-noting report; planted same-stage duplicate appears exactly once (FR-011).
- **§7 README walkthrough**: command blocks verified offline (venv install, pytest,
  layout paths all exist, missing-key error matches); full fresh-clone walkthrough with
  the plugin-install steps needs the live session above.
- **Token-cost estimate (research.md §9, Constitution II gate)**: observed per-unit
  subagent cost in the §3/§5 runs was ≈ 19k–30k tokens on the 3-file fixture; a
  max-parallel=4 run (7 units) cost ≈ 180k subagent tokens total, consistent with the
  design estimate that the agent path stays within the same order of magnitude as the
  hosted path with ≈ 3 × P × 3k shared-summary overhead.

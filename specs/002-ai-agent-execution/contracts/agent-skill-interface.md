# Contract: Agent Skill Interface (`/perf-analyze`)

**Feature**: `002-ai-agent-execution` | **Date**: 2026-08-04

The user-facing contract of the analysis skill shipped inside the `perf-ai` Claude Code plugin —
what a developer can rely on when invoking the analysis from inside an agent session. The
skill's behavior is described generically (per spec Assumptions) so packagings for other agents
can be added later under the same guarantees; Claude Code is the reference integration.
Installation and packaging are governed by [plugin-packaging.md](./plugin-packaging.md).

## Invocation

```text
/perf-analyze [path] [max-parallel=N]
```

(Namespaced form `/perf-ai:perf-analyze` when another installed command shares the name.)

| Argument | Required | Default | Description |
|---|---|---|---|
| `path` | No | current working directory | Directory or repository root to analyze. Must exist, be readable, and contain source code in at least one recognized language. |
| `max-parallel=N` | No | none — deliberately no default | Pre-supplies the Parallelism Limit (1–10) so no interactive question is asked. Required in effect for non-interactive contexts (FR-009). |

Discovery: the skill is available in any Claude Code session of a project where the `perf-ai`
plugin is installed via the marketplace flow of `plugin-packaging.md` — including a session
opened directly in this repository after adding the checkout itself as a local marketplace.

## Credentials

The skill performs analysis with the invoking agent's own model access. It MUST NOT read,
require, or prompt for `ANTHROPIC_API_KEY` or any hosted model provider credential (FR-002).
The hosted-API CLI (`perf-ai analyze`) is a separate, unchanged execution path (FR-003).

## Behavior guarantees

1. **Preflight before any analysis** (FR spec edge cases, FR-014): the skill validates
   prerequisites before any model work starts — first that a Python ≥ 3.12 interpreter is
   available to execute the bundled pipeline code (missing/old → stop with what is missing and
   how to install it), then target validity via the bundled `perf-ai agent scope` invoked
   through the plugin bootstrap. On failure it stops and reports what is missing and how to
   resolve it (e.g. path missing/unreadable, no recognized source code, runtime unavailable).
   It never starts a run that is known to die midway.
2. **Deterministic steps run bundled code** (FR-014): prerequisite checking, work partitioning,
   subagent-result validation, duplicate merging, aggregation, and report rendering are
   performed by executing the pipeline code inside the installed plugin's own checkout (via
   `${CLAUDE_PLUGIN_ROOT}/scripts/plugin_run.py`) — never re-implemented in skill prose, never
   requiring the developer to pre-install the package, never modifying the developer's
   environment.
3. **The parallelism question** (FR-006, FR-007): when `max-parallel` was not pre-supplied, the
   skill asks the developer for the maximum number of subagents allowed to run in parallel
   and waits for an explicit answer — it never proceeds on a suggested or implied default.
   Invalid answers (zero, negative, non-numeric) are explained and re-asked. Answers above 10
   are capped to 10 with an explicit "your value was capped" notice. A pre-supplied
   `max-parallel=N` undergoes the same validation; above 10 it is likewise capped-with-notice,
   otherwise-invalid values end the run with the validation message (there is no one to re-ask).
4. **Non-interactive fail-fast** (FR-009): where no interactive answer is possible and no value
   was pre-supplied, the skill fails fast with a message naming the `max-parallel=N` override —
   it neither picks a number nor hangs waiting for input that cannot arrive. The skill treats
   the context as non-interactive when its question cannot be presented or receives no answer
   (e.g., headless runs).
5. **Concurrency bound** (FR-008): at no point during the run are more than N subagents active.
   Work is launched in waves of at most N; when fewer independent work units remain than N,
   only that many run. The structural-context unit always completes first and its summary is
   shared with every later unit.
6. **Progress visibility**: the skill reports per-wave progress (units launched / completed /
   failed) rather than going silent until the end. Raw stack traces or internal tool syntax
   never reach the developer (Constitution IV).
7. **Graceful degradation** (FR-010): failed, timed-out, or unusable-output subagents do not
   abort the run. The final report includes results from successful units and identifies what
   did not complete. If *every* unit fails, the skill reports the run as failed (and the
   failure-noting report `agent render` wrote), never an empty-but-clean-looking report.
8. **Consolidated report** (FR-004, FR-011, SC-002): the skill's final step is
   `perf-ai agent render` (via the bootstrap), which produces `perf-report.md` and
   `perf-report.html` with the same required sections (Issues, Action Items, Valuable
   Findings), stage attribution, ordering, empty-section markers, and output-file conventions
   as the hosted-API CLI. Duplicate findings for the same location from parallel subagents are
   merged, not repeated.
9. **Statelessness**: intermediate stage-result files live in a per-run scratch directory; the
   only durable artifacts are the two report files, overwriting any prior run's (as in 001).
   (The plugin's private venv is an implementation cache inside the plugin checkout, not
   analysis state.)

## Completion message

On success the skill tells the developer: where both report files were written, the run status
(complete vs partial with what didn't complete), and the parallelism actually used (including a
capped-value notice when applicable). On failure it states the failure reason and the remediation.

## Out of scope for this contract

Automatic invocation (CI hooks), other agent integrations (future additive packagings), retry
policies beyond the optional single re-run of a failed wave, and any change to the
`perf-ai analyze` hosted-API contract (001 `contracts/cli-interface.md` remains authoritative
and unchanged).

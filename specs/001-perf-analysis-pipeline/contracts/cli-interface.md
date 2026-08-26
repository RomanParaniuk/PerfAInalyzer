# Contract: CLI Interface

**Feature**: `001-perf-analysis-pipeline` | **Date**: 2026-08-04

This is the external interface the project exposes to its user (FR-015: on-demand,
developer-initiated CLI invocation against a local directory/repository). No web UI, API, or CI
trigger is in scope for this revision (spec Assumptions).

## Command

```text
perf-ai analyze [PATH] [OPTIONS]
```

| Argument/Option | Required | Default | Description |
|---|---|---|---|
| `PATH` | No | current working directory | Local directory or repository root to analyze (FR-001). Must exist and be readable. |
| `--output-dir`, `-o PATH` | No | current working directory | Directory to write `perf-report.md` and `perf-report.html` into. Overwrites any prior run's files there (no history retained, per spec Key Entities). |
| `--include GLOB` (repeatable) | No | none (analyze everything detected) | Restrict the code scope to paths matching the given glob(s). |
| `--exclude GLOB` (repeatable) | No | common VCS/dependency dirs (e.g. `.git`, `node_modules`, `venv`) | Exclude paths matching the given glob(s) from the code scope. |
| `--timeout-minutes N` | No | a fixed default aligned with SC-004 | Overall run timeout; if exceeded, the run still produces a report from whatever stages completed (FR-012, FR-013). |

Authentication: the Anthropic API key is read from the `ANTHROPIC_API_KEY` environment variable
(FR-016 — external hosted provider). It is never read from a CLI flag, to avoid leaking secrets
into shell history.

## Standard output / progress

While running, the CLI prints incremental, per-stage progress (e.g., "Structural analysis:
done", "Algorithmic complexity: running…") via Rich, rather than blocking silently until
completion (Principle V). Progress output MUST NOT include raw exceptions, stack traces, or
unrendered tool-call syntax (Principle IV) — internal errors are caught and mapped to the
user-facing messages below.

## Output artifacts

On every completed run (including partial-results runs), exactly two files are written to
`--output-dir` (FR-017):

- `perf-report.md` — Markdown report
- `perf-report.html` — self-contained HTML report, openable directly in a browser

Both are rendered from the same underlying `Report` (see `data-model.md`) and MUST be content-
equivalent, differing only in markup (Principle IV). Both are always written in English
regardless of the invoking environment's locale (FR-018).

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Analysis completed and a report was written — includes the case where one or more stages did not complete but at least the pipeline produced a report (FR-012 graceful degradation is still a successful CLI outcome). |
| `1` | Invalid invocation — `PATH` does not exist, is not readable, or contains no code in any recognized language. |
| `2` | Configuration error — `ANTHROPIC_API_KEY` is missing or rejected by the provider before any stage could start. |
| `3` | Total pipeline failure — every stage failed or timed out; no findings could be produced. A report is still written noting the total failure, but the exit code signals failure to scripts/CI consumers. |

## Non-goals for this contract

Automated CI/PR triggering, a persistent daemon/server mode, and any non-CLI interface (web UI,
network API) are explicitly out of scope for this specification (FR-015, spec Assumptions).

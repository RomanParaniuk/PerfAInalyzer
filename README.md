# Perf AI

Perf AI is a multi-stage AI performance analysis pipeline for codebases. It reads your
source code and reasons about it — **static analysis only**: the submitted code is never
executed, compiled, or profiled. Each run produces two reports, `perf-report.md` and
`perf-report.html`, listing performance issues (with severity and a concrete suggested
action), prioritized action items, and valuable findings.

There are two independent ways to run an analysis:

| Path | Command | Credentials | Runs where |
|---|---|---|---|
| **Hosted-API CLI** | `perf-ai analyze` | `ANTHROPIC_API_KEY` required | Your terminal |
| **Claude Code plugin** | `/perf-analyze` | **None** — uses the agent's own model access | A Claude Code session |

The seven analysis stages are the same on both paths: structural/context analysis
first, then algorithmic complexity, resource & I/O efficiency, concurrency &
scalability, memory & allocation, data access & query efficiency, and startup &
initialization. Both paths render reports through the same deterministic templates,
so their output structure is identical. (The staged plugin workflow adds an optional
adversarial-verification pass on top — see below.)

## Prerequisites

- **Python 3.12+** — both paths. Verify with `python3 --version`.
- **Claude Code** (installed and signed in) — plugin path only. The plugin path is
  supported on macOS and Linux.
- An **Anthropic API key** — hosted-CLI path only. The plugin path needs no key.

## Installation

### Hosted-API CLI (developer checkout)

```bash
git clone https://github.com/RomanParaniuk/PerfAInalyzer.git Perf-AI
cd Perf-AI
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Claude Code plugin

The repository doubles as the plugin and as its own single-plugin marketplace. In a
Claude Code session in **any** project:

```text
/plugin marketplace add RomanParaniuk/PerfAInalyzer
/plugin install perf-ai@perf-ai
```

For a local clone, use the absolute path instead of the GitHub reference:

```text
/plugin marketplace add /absolute/path/to/Perf-AI
/plugin install perf-ai@perf-ai
```

After these two commands, `/perf-analyze` is available in that project's sessions — no
pip install, no PATH changes, no credentials. Uninstalling the plugin removes everything
it added, including its private environment.

## Configuration

- **Hosted-API CLI**: export your API key before running (it is read only from the
  environment, never from a flag):

  ```bash
  export ANTHROPIC_API_KEY=sk-ant-...
  ```

- **Claude Code plugin**: none. Explicitly no credentials — the skill performs analysis
  with the invoking agent's own model access and never reads `ANTHROPIC_API_KEY`.

## Running an analysis

### Hosted-API CLI

```bash
perf-ai analyze path/to/your/project
```

Useful options: `--output-dir DIR` (where reports go), `--include GLOB` / `--exclude
GLOB` (repeatable scope filters), `--timeout-minutes N`.

### Claude Code plugin

In a session of a project where the plugin is installed:

```text
/perf-analyze [path] [max-parallel=N]
```

- With no `max-parallel`, the skill **asks you** for the maximum number of parallel
  subagents (1–10) before any analysis starts and waits for your answer — there is no
  default. Invalid answers are explained and re-asked.
- `max-parallel=N` pre-supplies the limit and skips the question — required in effect
  for non-interactive (headless) runs, which otherwise fail fast.
- Values above 10 are capped to 10 with an explicit notice.
- On the **first run**, the plugin provisions a private virtual environment inside its
  own directory and downloads dependencies from PyPI — the one moment the plugin path
  needs the network. Later runs are offline and skip this step.

### Staged workflow (plugin, one command per stage)

`/perf-analyze` does everything in one invocation. The staged commands run the same
analysis as separate stages, each writing a durable, hand-editable Markdown artifact
that the next stage consumes — so you can stop after any stage, inspect or edit its
output, and continue (or re-run just that stage) at any time. The execution stage is
split by analysis dimension, one command per unit stage:

| # | Command | Reads | Writes |
|---|---------|-------|--------|
| 1 | `/perf-arch [path]` | the codebase | `01-architecture.md` — components, entry points, sizes, perf relevance |
| 2 | `/perf-scope [accept]` | `01-architecture.md` | `02-scope.md` — review depth per component (deep / standard / skim / skip), confirmed by you; product code only, with tests, tooling, generated and vendored code skipped by default |
| 3 | `/perf-plan [max-parallel=N]` | `02-scope.md` | `03-plan.md` + `results/workplan.json` — ordered work units, skipped components excluded, token estimate |
| 4a | `/perf-exec-structural` | `03-plan.md`, `results/workplan.json` | `results/structural_context--all.json` + `04a-structural.md` — the structural summary shared by 4b–4g |
| 4b | `/perf-exec-complexity [only-failed]` | `results/workplan.json`, `02-scope.md`, `04a-structural.md` | `results/algorithmic_complexity--*.json` + `04b-complexity.md` digest |
| 4c | `/perf-exec-resource-io [only-failed]` | `results/workplan.json`, `02-scope.md`, `04a-structural.md` | `results/resource_io_efficiency--*.json` + `04c-resource-io.md` digest |
| 4d | `/perf-exec-concurrency [only-failed]` | `results/workplan.json`, `02-scope.md`, `04a-structural.md` | `results/concurrency_scalability--*.json` + `04d-concurrency.md` digest |
| 4e | `/perf-exec-memory [only-failed]` | `results/workplan.json`, `02-scope.md`, `04a-structural.md` | `results/memory_allocation--*.json` + `04e-memory.md` digest |
| 4f | `/perf-exec-data-access [only-failed]` | `results/workplan.json`, `02-scope.md`, `04a-structural.md` | `results/data_access_efficiency--*.json` + `04f-data-access.md` digest |
| 4g | `/perf-exec-startup [only-failed]` | `results/workplan.json`, `02-scope.md`, `04a-structural.md` | `results/startup_initialization--*.json` + `04g-startup.md` digest |
| 4h | `/perf-exec-verify` *(optional)* | every `results/<stage>--*.json` | `results/verification.json` + `04h-verify.md` — adversarial re-check of critical/high issues |
| 5 | `/perf-report [output-dir]` | `results/*.json` | `perf-report.md` / `perf-report.html` — same renderer and structure as the one-shot path |

`/perf-exec [only-failed]` is the umbrella over stage 4: it runs 4a–4g in order
(the optional 4h verification pass is invoked separately). Stage 4a must run first
(its structural summary is the shared context); 4b–4g can then run in any order,
individually or together. When `results/verification.json` exists, `/perf-report`
automatically drops the issues the verification refuted and notes the outcome in
the report's limitations section; delete the file to render without the overlay.

All artifacts for a target live in one reusable workspace,
`analysis-runs/<target-name>/`, under the directory where you invoke the commands.
Rules of the workflow:

- **Stages run in order**; each command checks that its input artifact exists and
  otherwise names the command to run first.
- **Any stage can be re-run at any time**; it overwrites its own artifact only, and
  tells you which downstream artifacts are now out of date — nothing downstream is
  regenerated without you asking for it.
- **Hand edits are authoritative**: adjust depths in `02-scope.md` (or fix the
  component map in `01-architecture.md`) in your editor, then run the next stage.
- **Components marked `skip` get no work units** and are named as deliberately
  excluded in the final report; `skim` components get entry-points-only review.
- The execution stages checkpoint one JSON per work unit, so an interrupted run can
  continue with `/perf-exec only-failed` (or a single dimension's command with
  `only-failed`), re-running only missing or failed units.
- Each execution stage touches only its own dimension's result files and digest —
  re-running `/perf-exec-complexity` never disturbs the resource-I/O or concurrency
  results.

## Reports

Both paths write `perf-report.md` and `perf-report.html` to the chosen output directory
(the current directory by default), overwriting any previous run's files. Each report
contains:

- **Issues** — performance problems, ordered by severity, each with location, stage
  attribution, and severity.
- **Action Items** — concrete recommendations derived from the issues, priority-ordered.
- **Valuable Findings** — notable non-issue observations (e.g. well-optimized paths).
- **Analysis Coverage** — which stages completed; anything that did not complete is
  named there, never silently dropped.

## Codebase layout (for contributors)

```text
src/
├── cli/main.py          # `perf-ai` CLI: the `analyze` command (hosted path)
├── cli/agent.py         # `perf-ai agent scope|render`: deterministic helpers for the plugin path
├── pipeline/            # hosted-path orchestrator and the seven stage definitions
│   └── stages/          # stage definitions as markdown: frontmatter + instructions
│                        # (both paths read these; system-*.md hold the system prompts)
├── agentrun/            # plugin-path support: work-plan partitioning, result
│                        # validation, duplicate-finding merge
├── providers/           # Anthropic API client (hosted path only)
├── models/              # Pydantic models: findings, stages, report, action items
├── report/              # aggregator + Jinja2 templates — change report rendering here
│   └── templates/       # perf-report.md.j2 / perf-report.html.j2
└── lib/discovery.py     # language detection and file discovery (both paths)

skills/perf-analyze/SKILL.md   # the one-shot /perf-analyze skill (plugin orchestration procedure)
skills/perf-{arch,scope,plan,exec,exec-*,report}/  # the staged workflow: one skill per stage, one per execution dimension (plus the optional exec-verify pass)
scripts/plugin_run.py          # stdlib-only plugin bootstrap (venv provisioning + dispatch)
.claude-plugin/                # plugin.json + marketplace.json manifests
tests/                         # unit, contract, and integration suites
```

Typical change entry points: report wording/format → `src/report/templates/`; stage
behavior → `src/pipeline/stages/`; aggregation/ordering rules → `src/report/aggregator.py`;
plugin orchestration → `skills/perf-analyze/SKILL.md`; work partitioning or duplicate
merging → `src/agentrun/`. The six per-dimension execution skills share one procedure,
`skills/perf-exec/dimension-procedure.md` — each `skills/perf-exec-*/SKILL.md` holds only
that dimension's parameter table, so procedure changes are made once in the shared file.

## Running the tests

```bash
pytest
```

The routine suite is fully offline (the pre-existing pipeline tests plus the agent-path
suites). Tests that call the real Anthropic API are excluded by default; run them
explicitly (they spend tokens and need a valid key):

```bash
pytest -m live_api --override-ini addopts=''
```

## Troubleshooting

- **`Configuration error: the ANTHROPIC_API_KEY environment variable is not set`**
  (CLI path) — export the key first; see Configuration. The CLI exits with code 2
  before any analysis.
- **`Python 3.12 or newer is required`** (plugin path) — the plugin verified your
  runtime and stopped before doing anything. Install Python 3.12+ from
  https://www.python.org/downloads/ or your package manager and make sure `python3`
  points at it.
- **`no source code in a recognized language was found`** — the target directory has no
  files in a supported language, or your `--include`/`--exclude` globs filtered
  everything out. Point at a source directory or loosen the globs. Exit code 1.
- **Every stage failed (exit code 3)** — the report is still written and records each
  stage's failure reason; start there. On the plugin path this usually means every
  subagent's result file was missing or invalid.
- **"your value was capped to 10"** — parallelism above 10 is not supported; the run
  proceeded with the documented maximum of 10.
- **First plugin run is slow or fails with a network error** — the one-time environment
  provisioning downloads dependencies from PyPI. Check connectivity and re-run; the
  bootstrap never leaves a half-provisioned environment behind.

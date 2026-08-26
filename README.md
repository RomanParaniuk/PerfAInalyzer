# Perf AI

Perf AI is a four-stage AI performance analysis pipeline for codebases. It reads your
source code and reasons about it — **static analysis only**: the submitted code is never
executed, compiled, or profiled. Each run produces two reports, `perf-report.md` and
`perf-report.html`, listing performance issues (with severity and a concrete suggested
action), prioritized action items, and valuable findings.

There are two independent ways to run an analysis:

| Path | Command | Credentials | Runs where |
|---|---|---|---|
| **Hosted-API CLI** | `perf-ai analyze` | `ANTHROPIC_API_KEY` required | Your terminal |
| **Claude Code plugin** | `/perf-analyze` | **None** — uses the agent's own model access | A Claude Code session |

The four stages are the same on both paths: structural/context analysis first, then
algorithmic complexity, resource & I/O efficiency, and concurrency & scalability. Both
paths render reports through the same deterministic templates, so their output structure
is identical.

## Prerequisites

- **Python 3.12+** — both paths. Verify with `python3 --version`.
- **Claude Code** (installed and signed in) — plugin path only. The plugin path is
  supported on macOS and Linux.
- An **Anthropic API key** — hosted-CLI path only. The plugin path needs no key.

## Installation

### Hosted-API CLI (developer checkout)

```bash
git clone <this-repository-url> Perf-AI
cd Perf-AI
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Claude Code plugin

The repository doubles as the plugin and as its own single-plugin marketplace. In a
Claude Code session in **any** project:

```text
/plugin marketplace add <github-owner>/<repo>
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
├── pipeline/            # hosted-path orchestrator and the four stage definitions
│   └── stages/          # stage definitions as markdown: frontmatter + instructions
│                        # (both paths read these; system-*.md hold the system prompts)
├── agentrun/            # plugin-path support: work-plan partitioning, result
│                        # validation, duplicate-finding merge
├── providers/           # Anthropic API client (hosted path only)
├── models/              # Pydantic models: findings, stages, report, action items
├── report/              # aggregator + Jinja2 templates — change report rendering here
│   └── templates/       # perf-report.md.j2 / perf-report.html.j2
└── lib/discovery.py     # language detection and file discovery (both paths)

skills/perf-analyze/SKILL.md   # the /perf-analyze skill (plugin orchestration procedure)
scripts/plugin_run.py          # stdlib-only plugin bootstrap (venv provisioning + dispatch)
.claude-plugin/                # plugin.json + marketplace.json manifests
tests/                         # unit, contract, and integration suites
```

Typical change entry points: report wording/format → `src/report/templates/`; stage
behavior → `src/pipeline/stages/`; aggregation/ordering rules → `src/report/aggregator.py`;
plugin orchestration → `skills/perf-analyze/SKILL.md`; work partitioning or duplicate
merging → `src/agentrun/`.

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

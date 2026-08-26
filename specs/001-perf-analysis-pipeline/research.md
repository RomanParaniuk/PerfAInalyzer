# Phase 0 Research: AI Multi-Stage Performance Analysis Pipeline

**Feature**: `001-perf-analysis-pipeline` | **Date**: 2026-08-04

This is a greenfield project (no existing code or dependency manifests), so every entry in
Technical Context is a design decision rather than a discovered constraint. Each decision below
is checked against the constitution's five principles, in particular Principle I (Modern
AI-First), Principle II (Token-Optimal, NON-NEGOTIABLE), and Principle V (Performance
Requirements).

## 1. Runtime language & CLI framework

- **Decision**: Python 3.12, with Typer (Click-based) for the CLI surface and Rich for
  progress/output rendering.
- **Rationale**: Python has mature, first-class libraries for every subsystem this feature needs
  simultaneously: the official Anthropic SDK, `tree-sitter` bindings for multi-language static
  parsing, Pydantic for schema-validated structured output, and Jinja2 for deterministic report
  templating. Typer gives a low-boilerplate, type-hinted CLI (single command + options, matching
  FR-015's on-demand CLI invocation) and composes with Rich to show live per-stage progress
  instead of a silent multi-minute block, satisfying Principle V's requirement to avoid blocking
  the user on one long synchronous call.
- **Alternatives considered**: Node.js/TypeScript — comparable AI SDK support, but weaker native
  multi-language static-parsing ecosystem and no first-class Pydantic-equivalent schema
  enforcement out of the box. Go — strong CLI ergonomics and single-binary distribution, but
  static analysis and structured-LLM-output tooling is far less mature; rejected for this
  feature's analysis-heavy workload.

## 2. AI provider and per-stage model selection

- **Decision**: Anthropic Claude API (external hosted provider, per FR-016). Use Claude Haiku 4.5
  (exact API model ID: `claude-haiku-4-5`) for the structural/context-understanding stage, and
  Claude Sonnet 5 (exact API model ID: `claude-sonnet-5`) for the three deeper reasoning stages
  (algorithmic complexity, resource/I/O efficiency, concurrency/scalability). These ID strings
  are used verbatim — no date suffixes are appended. Constraint to respect at implementation
  time: `claude-haiku-4-5` has a 200K-token context window and 64K max output (vs 1M/128K for
  `claude-sonnet-5`), so the structural stage's input budget must fit within it.
- **Rationale**: Principle I requires defaulting to current-generation models; Principle II
  requires the smallest capable tier per task rather than defaulting to the largest. Structural
  mapping (identifying modules, call graphs, language boundaries) is comparatively mechanical and
  fits a smaller, faster model. The three analytical stages require deeper reasoning about
  algorithmic behavior, I/O patterns, and concurrency correctness, which justifies Sonnet-tier
  model quality. Opus-tier is not justified for any stage given the task shape and would violate
  Principle II's smallest-capable-tier rule; this is documented here so the choice can be
  revisited if a future stage's accuracy is shown to require it (Principle I).
- **Alternatives considered**: Opus 5 for all stages — rejected as unnecessarily expensive per
  Principle II without a demonstrated quality gap from Sonnet 5. A single model tier for all four
  stages — simpler, but forfeits the cost savings Haiku 4.5 offers for the mechanical structural
  stage; rejected in favor of the mixed-tier approach.

## 3. Multi-language static parsing strategy

- **Decision**: Use `tree-sitter` via a language-pack binding (grammars resolved dynamically by
  detected file extension) to build a compact structural index (files, modules, function/class
  boundaries, import graph) entirely locally, with zero AI tokens spent on this step. When a
  detected language has no available grammar, fall back to a generic line/indentation-based
  chunker and explicitly flag that file's analysis as best-effort in the report.
- **Rationale**: FR-014 requires automatic language detection and best-effort analysis without a
  fixed supported-language list; tree-sitter's grammar-per-language model matches this directly
  and runs free of API cost. Producing the structural index locally (rather than asking the model
  to re-derive it from raw text) is a direct Principle II token-saving measure: the index is
  computed once, reused across the four analysis stages via prompt caching, and is far smaller
  than raw source.
- **Alternatives considered**: Ask the model to infer structure directly from raw source in every
  stage — rejected as token-wasteful (repeats the same structural reasoning four times) and
  violates Principle II. A single fixed-language parser (e.g., only Python via `ast`) — rejected
  because it would not satisfy FR-014's multi-language, auto-detected scope.

## 4. Large-codebase handling / token-budget strategy

- **Decision**: Build the local structural index first, then rank files/functions per stage by a
  heuristic relevance score specific to that stage's skill (e.g., loop-nesting depth and
  collection-growth patterns for algorithmic complexity; file I/O and network-call call-sites for
  resource/I/O; thread/lock/async-primitive usage for concurrency). Each stage call is capped to a
  fixed input-token budget; only top-ranked files/functions within budget are sent as source
  excerpts, and the report explicitly lists what was and was not covered, per the "too large to
  fully analyze" edge case and FR-013's bounded-time requirement.
- **Rationale**: This keeps per-run token cost bounded and predictable regardless of repository
  size (Principle II, SC-004's 10-minute target) while still giving each stage the excerpts most
  likely to contain relevant findings, rather than an arbitrary or naive truncation (e.g., first N
  files alphabetically).
- **Alternatives considered**: Send the entire codebase to every stage — simplest, but violates
  Principle II for anything beyond small codebases and risks exceeding practical context/latency
  budgets for the "typical-sized project" scale in the Assumptions section. Fixed per-file
  chunking without prioritization — rejected because it would silently miss the most relevant
  code in a large repo without any better-than-random rationale.

## 5. Structured output validation

- **Decision**: Every analysis-stage call uses Anthropic tool-use with a forced tool choice whose
  input schema is generated from a Pydantic model (`StageResult`, containing `Finding` entries).
  Responses are parsed and re-validated against the Pydantic model before being handed to the
  report aggregator.
- **Rationale**: Constitution Principle III requires schema-validated output wherever the
  consumer is programmatic — here, the report aggregator is a deterministic downstream consumer.
  Forcing tool-use with a schema (rather than asking for free-text JSON and parsing hopefully)
  eliminates a whole class of malformed-output failures and gives a precise, typed contract
  between each stage and the aggregator (see `contracts/`).
- **Alternatives considered**: Free-text Markdown output per stage, parsed with regex/heuristics
  — rejected as fragile and unverifiable, conflicting with Principle III's schema-validation
  requirement. JSON-mode without a strict schema — rejected because it still allows structurally
  valid-but-semantically-wrong shapes (missing required fields) to slip through.

## 6. Stage orchestration, concurrency, and partial-failure handling

- **Decision**: Stage 1 (structural/context understanding) runs first and its output (the code
  map + architectural summary) is cached and passed as shared context to Stages 2–4, which then
  run concurrently against each other (they are independent of one another, only depending on
  Stage 1's output). Each stage call is wrapped in a timeout; a stage that raises or times out is
  recorded as "did not complete" with its exception/timeout reason, while the pipeline proceeds to
  render a report from whichever stages did complete.
- **Rationale**: FR-012 requires graceful per-stage degradation without failing the whole run.
  Running Stages 2–4 concurrently (rather than sequentially) reduces wall-clock latency toward
  the SC-004 10-minute budget, directly serving Principle V. Caching Stage 1's output for reuse
  by Stages 2–4 (instead of each stage re-deriving its own structural understanding) is a
  Principle II token-saving measure.
- **Alternatives considered**: Fully sequential pipeline (each stage builds on the previous
  stage's full output) — rejected because Stages 2–4 do not have a genuine content dependency on
  each other, so serializing them would only add latency without adding accuracy. A single
  monolithic prompt asking for all four skills at once — rejected because it collapses the
  per-stage attribution required by FR-009 and makes partial-failure isolation (FR-012)
  impossible.

## 7. Report rendering (Markdown + HTML)

- **Decision**: The report aggregator merges validated `StageResult` objects into one in-memory
  `Report` model (severity-sorted issues, action items, valuable findings, with explicit
  "none found" markers for empty sections per FR-010), then renders it through two Jinja2
  templates — one producing `perf-report.md`, one producing a self-contained `perf-report.html`
  — with no further AI involvement in this step.
- **Rationale**: Deterministic, non-AI templating guarantees the two output files are always
  structurally consistent with each other and across runs (Principle IV: consistent formatting
  regardless of model output variance), and keeps this step's cost at zero tokens (Principle II).
- **Alternatives considered**: Ask the model to directly author the final Markdown/HTML — rejected
  because it reintroduces formatting inconsistency across runs (Principle IV risk) and spends
  tokens on a purely mechanical transformation the aggregator can do deterministically and for
  free.

## 8. Testing strategy

- **Decision**: pytest, with three layers: (a) unit tests for the deterministic components
  (tree-sitter index builder, relevance ranking, report aggregator, Jinja2 renderers) using no
  network calls; (b) contract tests validating that stage-output shapes conform to the Pydantic
  schemas in `contracts/`, run against recorded/mocked API responses; (c) integration tests that
  run the full CLI pipeline against small fixture repositories containing known, deliberately
  planted anti-patterns (quadratic nested loop, unbounded in-memory collection) and a
  well-optimized pattern, asserting the acceptance scenarios in the spec's User Stories 1–4.
  Integration tests hit the real Anthropic API only in a separate, explicitly-invoked suite (to
  control token cost in routine CI runs); day-to-day CI runs use recorded fixtures/cassettes.
- **Rationale**: Matches the Development Workflow gate's requirement to verify outputs and
  performance rather than assume correctness, while keeping routine test-suite token cost near
  zero (Principle II) by defaulting to recorded responses and reserving live-API runs for
  deliberate validation.
- **Alternatives considered**: Always hitting the live API in CI — rejected as it makes routine
  test runs expensive and non-deterministic. Testing only at the unit level with no live-API
  validation ever — rejected because it would never verify the actual model-integration behavior
  the feature depends on.

## Estimated token cost per run (Principle II design-time estimate)

For a "typical-sized project" (Assumptions: tens of thousands of LOC, moderate file count): the
local structural index costs zero tokens. Stage 1 is estimated at roughly 15–20K input tokens
(compact code map + representative excerpts) and ~2K output tokens. Stages 2–4 each read the
cached Stage 1 context plus a stage-specific, budget-capped excerpt set, estimated at ~30–40K
input tokens each (largely cache-hit after Stage 1) and ~3–5K output tokens each. Total estimated
per-run cost is in the low hundreds of thousands of tokens, dominated by Sonnet-tier Stages 2–4.
This is a design-time estimate to be replaced with a measured figure during implementation
validation (Development Workflow gate item 1), not a committed budget.

### Measured figures (implementation validation, 2026-08-04)

Measured against a synthetic typical-sized fixture (1,650 files, ~47K LOC, Python +
JavaScript) on a developer workstation:

- **Local zero-token pipeline** (discovery, tree-sitter indexing, 4× relevance ranking +
  context assembly, aggregation, dual-template rendering): **~1.0s total wall-clock** —
  negligible against the 10-minute SC-004 budget.
- **Assembled per-stage input** (estimated tokens, budgets enforced by the token-capped
  code map + excerpt assembly): structural ~24.0K (at its 24K cap, well inside
  `claude-haiku-4-5`'s 200K window), algorithmic complexity ~40.3K (at cap), resource/I-O
  ~40.3K (at cap), concurrency ~12.0K (under cap). Truncation is reported via explicit
  coverage notes, never silent.
- **API-dependent wall-clock and billed token usage**: pending — no `ANTHROPIC_API_KEY`
  was available in the implementation environment. Run the explicitly-invoked live suite
  (`pytest -m live_api --override-ini addopts=''`) and re-run the timing fixture with a
  key to finalize this number. With ~1s of local overhead, effectively the entire
  10-minute budget remains for the four model calls (three of which run concurrently
  against the cached shared context).

## Outcome

All Technical Context items are resolved below; no `NEEDS CLARIFICATION` markers remain.

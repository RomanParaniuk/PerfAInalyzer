<!--
Sync Impact Report
==================
Version change: [none, template unfilled] → 1.0.0 (initial ratification)
Bump rationale: MAJOR — first concrete adoption of all governing principles for this
  project (moves from placeholder template to binding constitution).

Modified principles: n/a (initial fill; all five principle slots newly defined)
  - PRINCIPLE_1 → I. Modern AI-First Approaches
  - PRINCIPLE_2 → II. Token-Optimal Usage (NON-NEGOTIABLE)
  - PRINCIPLE_3 → III. Useful, Actionable Output
  - PRINCIPLE_4 → IV. Consistent User Experience
  - PRINCIPLE_5 → V. Performance Requirements

Added sections:
  - Technology & Model Standards (SECTION_2)
  - Development Workflow & Quality Gates (SECTION_3)
  - Governance (dates, versioning policy, compliance review)

Removed sections: none

Deferred / TODO placeholders: none — RATIFICATION_DATE set to the date of this
  initial adoption since no prior ratified version exists.

Templates checked for alignment (not modified by this command):
  - .specify/templates/plan-template.md — generic, references constitution at runtime; OK
  - .specify/templates/spec-template.md — generic; OK
  - .specify/templates/tasks-template.md — generic; OK
  - .specify/templates/checklist-template.md — generic; OK
  Consider adding explicit "token budget" / "performance budget" / "output verification"
  checklist items next time those templates are edited, to mirror Principles II, III, V.
-->

# Perf AI Constitution

## Core Principles

### I. Modern AI-First Approaches
The project MUST default to current-generation AI models and techniques over legacy or
hand-rolled heuristics when an AI-based approach is more robust, maintainable, or accurate.
Model and technique choices (model tier, structured outputs, tool use, extended context,
prompt caching, retrieval) MUST be re-evaluated against the current state of the art before
building custom workarounds for problems a capable model call already solves well. Deprecated
or superseded models/APIs MUST NOT be adopted in new work; existing usages MUST be migrated
when a superseding option is verified to be a strict improvement for the use case.

**Rationale**: AI capabilities move quickly; locking into a technique or model version by
default accumulates technical debt and forfeits accuracy, cost, and UX gains that newer
approaches provide.

### II. Token-Optimal Usage (NON-NEGOTIABLE)
Every AI-invoking code path MUST minimize token consumption without sacrificing correctness.
This means: reuse and cache repeated context (e.g., prompt caching) instead of resending it;
avoid redundant model round-trips; pass targeted, relevant context instead of full documents
or transcripts when an excerpt suffices; and select the smallest capable model tier for a
given task rather than defaulting to the largest. Token cost per feature MUST be estimated
during design and MUST be reviewed as an explicit dimension in code review — not treated as
an unmeasured side effect.

**Rationale**: Token usage is a direct, recurring cost and latency driver; treating it as a
first-class constraint rather than an afterthought keeps the product both affordable and fast
to run at scale.

### III. Useful, Actionable Output
All AI-generated output surfaced to users or consumed by downstream systems MUST be directly
actionable: concrete next steps, valid data conforming to the schema the consumer expects, and
free of vague filler, hedging, or padding that adds no decision-relevant information. Outputs
that make a claim about system or external state (e.g., "this file exists," "this API supports
X") MUST be verified against that state before being presented, rather than shipped on
plausibility alone. Purely conversational responses are exempt from schema requirements but
still MUST directly address the user's request.

**Rationale**: Output that looks helpful but isn't actionable or isn't verified erodes trust
faster than an explicit "I don't know" — usefulness must be demonstrated, not assumed.

### IV. Consistent User Experience
Interaction patterns — tone, formatting, terminology, error handling, and latency expectations
— MUST remain consistent across all AI-driven surfaces of the product. Any deviation from an
established UX convention MUST be explicitly justified in the change that introduces it.
Failures and errors MUST degrade gracefully with clear, consistent user-facing messaging;
raw internal errors, stack traces, or model-internal artifacts (e.g., unrendered tool-call
syntax) MUST NOT reach the user.

**Rationale**: Users build trust in an AI product through predictability; inconsistent tone,
formatting, or error behavior across features reads as unreliability even when the underlying
logic is correct.

### V. Performance Requirements
Every AI-dependent feature MUST define an explicit latency/throughput budget appropriate to
its interaction context (e.g., a synchronous chat turn vs. a background batch job), and MUST
be measured against that budget before release — not assumed to be acceptable. Where
synchronous latency would exceed the budget, the feature MUST use streaming or incremental
responses instead of blocking the user on a single long-running call. Performance regressions
identified against a previously measured baseline MUST block release until resolved or
explicitly accepted with rationale.

**Rationale**: Perceived responsiveness is a core part of AI product quality; without a
measured budget, performance silently degrades as models, prompts, and context sizes grow.

## Technology & Model Standards

Model and technique selection MUST be made deliberately per task, not inherited by default:
choose the smallest/cheapest model tier that meets the task's quality bar (Principle II),
and prefer structured/schema-validated outputs over free-text parsing wherever a consumer is
programmatic (Principle III). Prompt caching MUST be used for any context that is reused
across multiple calls within a session or workflow. New integrations with AI providers or
models MUST document the model/version chosen and the reason it was selected over
alternatives, so the choice can be revisited as the state of the art advances (Principle I).

## Development Workflow & Quality Gates

Any change that adds or modifies an AI model call, prompt, or agent workflow MUST include,
in its review: (1) an estimate or measurement of token cost impact, (2) confirmation that
outputs are schema-validated or otherwise verified where consumed programmatically, (3) a
check against existing UX conventions for tone/formatting/error handling, and (4) a latency
budget and, where feasible, a measurement against it. A change MUST NOT be merged solely on
"it looks like it works" — outputs and performance claims MUST be checked, not assumed.

## Governance

This constitution supersedes ad hoc practice for all AI-related design and implementation
decisions in this project. Amendments require: (1) a documented rationale for the change,
(2) an explicit version bump following the semantic versioning policy below, and (3) an
update to this file's Sync Impact Report recording what changed and why.

Versioning policy — MAJOR.MINOR.PATCH:
- MAJOR: Backward-incompatible governance changes, or removal/redefinition of a principle.
- MINOR: A new principle or section is added, or existing guidance is materially expanded.
- PATCH: Wording clarifications, typo fixes, or non-semantic refinements.

Compliance review: every feature plan, spec, and task breakdown produced under this project
MUST be checked against these five principles before implementation begins, and any complexity
or deviation introduced MUST be justified explicitly rather than left implicit. Reviewers MUST
treat this constitution as the baseline for evaluating whether a change is ready to merge.

**Version**: 1.0.0 | **Ratified**: 2026-08-04 | **Last Amended**: 2026-08-04

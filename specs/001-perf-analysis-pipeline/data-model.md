# Phase 1 Data Model: AI Multi-Stage Performance Analysis Pipeline

**Feature**: `001-perf-analysis-pipeline` | **Date**: 2026-08-04

These are in-memory/structured schemas (Pydantic models), not a persistent database schema — the
system is stateless across runs (see spec Key Entities: no Analysis Run history is retained).
Field types are illustrative Python/Pydantic types for the design; exact implementation types are
an implementation-phase detail.

## Analysis Run

Represents a single execution of the pipeline against one defined code scope.

| Field | Type | Notes |
|---|---|---|
| `code_scope_path` | `str` | Local directory/repo path the developer invoked the CLI against (FR-001, FR-015) |
| `started_at` | `datetime` | Run start timestamp |
| `status` | `enum{in_progress, completed, completed_with_partial_results}` | `completed_with_partial_results` when one or more stages did not complete (FR-012) |
| `detected_languages` | `list[str]` | Languages auto-detected in the code scope (FR-014) |
| `stages` | `list[AnalysisStage]` | Exactly the four fixed stages defined for this feature (FR-002) |
| `report` | `Report` | Exactly one Report is produced per completed run (FR-004) |

**Validation rules**:
- `status` MUST be `completed` only if all stages reached a terminal state (`completed` or
  `failed`); it is `completed_with_partial_results` if at least one stage is `failed`, and no
  run may report `completed` while masking a failed stage.
- A run is never persisted beyond producing its two output files; there is no run-ID lookup or
  history store (explicit non-goal, see spec Assumptions).

## Analysis Stage

A discrete step in the pipeline associated with one performance-analysis skill.

| Field | Type | Notes |
|---|---|---|
| `name` | `enum{structural_context, algorithmic_complexity, resource_io_efficiency, concurrency_scalability}` | Fixed set of four stages per FR-002 |
| `status` | `enum{pending, running, completed, failed, timed_out}` | Drives partial-failure handling (FR-012) |
| `failure_reason` | `str \| None` | Populated when `status` is `failed`/`timed_out`; surfaced in the report so the reader knows which stage didn't complete |
| `findings` | `list[Finding]` | Zero or more; empty is valid and distinct from "stage failed" |
| `model_used` | `str` | Which Claude model tier served this stage (per `research.md` §2), recorded for traceability, not shown to the end user as a requirement |

**Relationships**: Stage `structural_context` runs first; its output is passed as shared,
cached context to the other three stages, which are otherwise independent of one another (see
`research.md` §6).

**State transitions**: `pending → running → (completed | failed | timed_out)`. No stage
transitions back to an earlier state within a run.

## Finding

An individual observation produced by a stage — the base shape shared by Issues and Valuable
Findings.

| Field | Type | Notes |
|---|---|---|
| `finding_id` | `str` | Stable within a single run (for cross-referencing an Issue to its Action Item) |
| `kind` | `enum{issue, valuable_finding}` | Determines which report section it belongs to (FR-005, FR-007) |
| `description` | `str` | Human-readable explanation; MUST NOT be empty |
| `location` | `LocationRef` | See below; required for every finding (FR-005) |
| `severity` | `enum{critical, high, medium, low} \| None` | Required (non-null) when `kind == issue` (FR-005); MUST be `None` when `kind == valuable_finding` (valuable findings are not rated for severity) |
| `originating_stage` | `enum{structural_context, algorithmic_complexity, resource_io_efficiency, concurrency_scalability}` | Required on every finding (FR-009) |

### LocationRef (embedded value, not a standalone entity)

| Field | Type | Notes |
|---|---|---|
| `file_path` | `str` | Relative to the submitted code scope |
| `symbol` | `str \| None` | Function/method/class name, when identifiable |
| `line_start` | `int \| None` | 1-indexed; `None` only when the finding is file-scoped rather than line-scoped |
| `line_end` | `int \| None` | |

**Validation rules**:
- `severity` MUST be non-null iff `kind == issue` (enforced by the schema, not left to prompt
  instruction alone, per Principle III).
- `location.file_path` MUST be non-empty for every Finding.

## Action Item

A concrete recommendation derived from one or more Issues.

| Field | Type | Notes |
|---|---|---|
| `action_item_id` | `str` | Stable within a run |
| `related_finding_ids` | `list[str]` | One or more `Finding.finding_id` values with `kind == issue` this action item addresses (FR-006) |
| `recommendation` | `str` | MUST describe a specific, concrete next step, not a restatement of the issue description (FR-006) — enforced procedurally by the stage prompt contract in `contracts/stage-output-schema.md`, since free-text quality cannot be fully schema-validated |
| `priority` | `enum{critical, high, medium, low}` | Drives ordering in the report; MUST match or derive from the highest severity among `related_finding_ids` (FR-008) |

**Validation rules**:
- `related_finding_ids` MUST reference at least one Finding with `kind == issue` present in the
  same run.
- `recommendation` MUST NOT be textually identical or near-identical to the related Issue's
  `description` (checked at the contract-test layer against fixture cases, per `research.md` §8).

## Report

The final human-readable artifact for one Analysis Run.

| Field | Type | Notes |
|---|---|---|
| `issues` | `list[Finding]` (kind == issue) | Sorted by `severity` descending, then by stage order (FR-005, FR-008) |
| `action_items` | `list[ActionItem]` | Sorted by `priority` descending so the highest-impact item is first (FR-006, FR-008) |
| `valuable_findings` | `list[Finding]` (kind == valuable_finding) | FR-007 |
| `incomplete_stages` | `list[{stage: str, reason: str}]` | Derived from any `AnalysisStage` with `status in {failed, timed_out}` (FR-012) |
| `coverage_note` | `str \| None` | Populated when a token/time budget caused some files/functions to be skipped, per the "too large to fully analyze" edge case and FR-013 |
| `generated_at` | `datetime` | |

**Validation rules**:
- Each of `issues`, `action_items`, `valuable_findings` MUST render an explicit "none found"
  marker in the output when empty, rather than omitting the section (FR-010, SC-006) — this is a
  rendering-layer rule (Jinja2 templates always emit the section heading), not a field-presence
  rule, since an empty list is a valid value distinct from a missing field.
- Rendered twice from the same `Report` instance: once to `perf-report.md`, once to
  `perf-report.html` — both MUST reflect identical content (Principle IV consistency), differing
  only in markup.

## Entity relationship summary

```text
Analysis Run 1 ──── * Analysis Stage ──── * Finding (kind=issue) ──── * Action Item (via related_finding_ids)
                                       └── * Finding (kind=valuable_finding)
Analysis Run 1 ──── 1 Report (aggregates all Findings + Action Items across all Stages)
```

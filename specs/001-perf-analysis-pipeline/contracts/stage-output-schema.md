# Contract: Analysis Stage Output Schema

**Feature**: `001-perf-analysis-pipeline` | **Date**: 2026-08-04

This is the internal contract between each of the four analysis stages (each a distinct prompt/
skill, per FR-002) and the deterministic report aggregator. It is enforced by forcing Anthropic
tool-use (`tool_choice`) with the input schema below on every stage call — a stage's response is
only accepted if it validates against this schema (Principle III: schema-validated output for a
programmatic consumer). This is what makes the four stages swappable/independently implementable
skill modules rather than free-text generators the aggregator must interpret heuristically.

## Tool: `report_stage_findings`

JSON Schema (illustrative; exact field types mirror the Pydantic models in `data-model.md`):

```json
{
  "name": "report_stage_findings",
  "description": "Report the findings this analysis stage produced for the given code scope.",
  "input_schema": {
    "type": "object",
    "required": ["stage_name", "findings"],
    "properties": {
      "stage_name": {
        "type": "string",
        "enum": [
          "structural_context",
          "algorithmic_complexity",
          "resource_io_efficiency",
          "concurrency_scalability"
        ]
      },
      "findings": {
        "type": "array",
        "items": { "$ref": "#/$defs/finding" }
      },
      "coverage_note": {
        "type": ["string", "null"],
        "description": "Set when this stage could not cover the full code scope within its token/time budget; describes what was and was not covered."
      }
    },
    "$defs": {
      "finding": {
        "type": "object",
        "required": ["kind", "description", "location"],
        "properties": {
          "kind": { "type": "string", "enum": ["issue", "valuable_finding"] },
          "description": { "type": "string", "minLength": 1 },
          "location": {
            "type": "object",
            "required": ["file_path"],
            "properties": {
              "file_path": { "type": "string", "minLength": 1 },
              "symbol": { "type": ["string", "null"] },
              "line_start": { "type": ["integer", "null"] },
              "line_end": { "type": ["integer", "null"] }
            }
          },
          "severity": {
            "type": ["string", "null"],
            "enum": ["critical", "high", "medium", "low", null],
            "description": "Required (non-null) when kind == issue; must be null when kind == valuable_finding."
          },
          "suggested_action": {
            "type": ["string", "null"],
            "description": "Required (non-null) when kind == issue; a concrete next step, not a restatement of description. Consumed by the aggregator to build Action Items."
          }
        }
      }
    }
  }
}
```

## Cross-field rules enforced at validation time (not fully expressible in JSON Schema alone)

- `severity` MUST be present and non-null when `kind == "issue"`; MUST be `null` when
  `kind == "valuable_finding"`.
- `suggested_action` MUST be present and non-null when `kind == "issue"`; MUST NOT be textually
  identical (case-insensitive, whitespace-normalized) to `description` — the aggregator rejects
  and logs (as a stage data-quality note, not a hard pipeline failure) any finding that violates
  this, per FR-006's requirement that action items be concrete steps, not restatements.
- A stage response that fails schema validation after one retry is treated identically to a
  stage timeout: the stage is marked `failed` with the validation error as `failure_reason`, and
  the pipeline proceeds with the remaining stages (FR-012).

## `originating_stage` attribution (FR-009)

The orchestrator — not the model — stamps each returned `finding` with the `stage_name` from the
enclosing `StageResult` before it reaches the aggregator, so attribution is structurally
guaranteed rather than dependent on the model reliably repeating it per finding.

## Versioning

This schema is internal (not exposed to third parties). Changes to required fields are expected
to accompany a corresponding change to the four stage prompts and the aggregator in the same
change set; no independent backward-compatibility guarantee is made across feature revisions.

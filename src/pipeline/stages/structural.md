---
name: structural_context
system: structural
---
# Stage task: structural & context understanding

Build the architectural summary of this repository for the downstream analysis stages:
1. Identify the major modules/components and each one's responsibility.
2. Sketch the primary data/control flow between them (who calls whom, what data moves).
3. Flag the components most likely to matter for performance analysis (entry points,
   loops over collections, I/O boundaries, concurrency primitives) so later stages know
   where to look.

Report each observation as a separate finding via `report_stage_findings`.

# Feature Specification: Staged Resumable Analysis with Durable Artifacts

**Feature Branch**: `003-staged-resumable-analysis`

**Created**: 2026-08-05

**Status**: Draft

**Input**: User description: "I need to have multiple stages, each of them should generate md artifacts to have ability re-run, fix, or continue execution later +saving tokens after each stage. Originally I see: review of repo architecture. Next survey - clarify how deep each part must be reviewed. then - plan. then - implementation. then - finalyzing of plan. Feel free to change stages if you see better options"

## Clarifications

### Session 2026-08-05

- Q: Does the staged workflow apply to the AI-agent (plugin) path, the hosted-API CLI path, or
  both? → A: Both — every execution path runs the same five stages, writes the same artifacts,
  and resumes the same way. Because the CLI cannot ask a question mid-run, scope confirmation
  there is given by re-invoking after reviewing (and optionally editing) the scope artifact.
- Q: Is there one reusable workspace per target that each run overwrites, or is each run kept
  as its own dated directory? → A: Each run is its own dated directory and all runs are
  retained; previous runs stay readable. An invocation continues the most recent run if it is
  incomplete, and starts a new dated run if it is complete.
- Q: When a stage is re-run or its artifact is edited after downstream stages already
  completed, are the stale downstream stages regenerated automatically? → A: No — they are
  marked out of date and the developer is asked before any regeneration happens. Continuing
  never spends model usage the developer did not approve.
- Q: How long may the three decision stages (architecture review, depth survey, plan) take on a
  ~200-file codebase before the developer is asked to confirm scope? → A: Under 5 minutes
  total, with each stage's completion visible as it happens rather than only at the end.
- Q: How are several runs of the same target on the same day kept apart? → A: Each run's
  workspace is named with its start date and time to the second, so names never collide and
  sort chronologically; "most recent" needs no separate index.
- Q: At what granularity is a source-code change since an artifact was produced detected? → A:
  Per component / work unit — the system names exactly which components changed and offers to
  refresh only those, leaving unaffected components' findings intact.
- Q: What must the plan artifact state about the cost of the analysis stage? → A: The number of
  work units broken down by review depth, plus an estimated token range for the stage — the
  same unit the run records per stage, so estimate and actual are directly comparable.
- Q: How is a run that crashed while marked "in progress" distinguished from one that is still
  running? → A: The system checks whether the run that placed the marker is still alive; if it
  is gone, the run is treated as interrupted and resumed normally with a notice. Only a
  genuinely still-running run is refused.

## Overview

Today an analysis is one indivisible run: everything happens in a single session, nothing
durable is written until the final reports appear, and any interruption, mistake, or wish to
adjust the analysis means paying for the whole run again. This feature turns a run into a
sequence of checkpointed stages. Each stage reads the previous stages' written artifacts
instead of re-deriving their context, and writes its own human-readable Markdown artifact
before the next stage starts. Those artifacts are the resume point, the audit trail, and the
correction surface: a developer can stop after any stage, inspect what was produced, edit it
by hand, and continue — or come back the next day and continue — without repeating completed
work.

The staged shape also lets the analysis be *aimed* before it is paid for: an architecture
review comes first, then an explicit decision about how deeply each part of the codebase
deserves to be reviewed, then a plan, and only then the expensive per-unit analysis.

### Stage sequence

| # | Stage | Produces | Purpose |
|---|-------|----------|---------|
| 1 | **Architecture Review** | Architecture artifact | Map the codebase: components, entry points, languages, size, and which surfaces are performance-relevant. |
| 2 | **Depth Survey** | Scope artifact | Assign each component a review depth (deep / standard / skim / skip) with a stated reason; the developer confirms or adjusts it. |
| 3 | **Analysis Plan** | Plan artifact | Turn the depth decisions into an ordered list of work units (which parts get which kind of analysis), with a work-unit count by depth and an estimated token range. |
| 4 | **Analysis Execution** | One findings artifact per work unit | Perform the actual performance analysis, unit by unit, checkpointing after each. |
| 5 | **Report Finalization** | Final reports | Aggregate, de-duplicate, and prioritize the findings artifacts into the existing report deliverables. |

Stages 1–3 are cheap and small; stage 4 is where the cost is. Checkpointing before stage 4
and inside it is what makes an interrupted or misaimed run recoverable instead of wasted.

The same five stages apply on every execution path, each run keeps its own dated workspace so
earlier runs stay readable, and nothing expensive is ever regenerated without the developer
agreeing to it first.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Continue an Interrupted Analysis Instead of Restarting It (Priority: P1)

As a developer whose analysis was interrupted — the session ended, the machine slept, a stage
failed, or I simply stopped for the day — I want to re-invoke the analysis on the same target
and have it pick up from the first stage that has not completed, so that I keep everything
already produced and pay only for what is left.

**Why this priority**: This is the core of the request. Without durable per-stage artifacts
and a resume path, every other benefit (editing, re-aiming, cost control) is impossible.

**Independent Test**: Start an analysis on a sample codebase, interrupt it after the plan
stage completes, re-invoke it on the same target, and confirm that stages 1–3 are reported as
already complete and are not re-derived, that no model work is spent re-producing them, and
that the run proceeds directly into the analysis stage.

**Acceptance Scenarios**:

1. **Given** a run whose first three stages completed and whose artifacts are present,
   **When** the developer re-invokes the analysis on the same target, **Then** the system
   reports which stages are already complete, reuses their artifacts as-is, and starts work at
   the first incomplete stage.
2. **Given** a run interrupted partway through the analysis-execution stage with some work
   units finished, **When** the developer resumes, **Then** only the unfinished work units are
   analyzed and the finished ones are reused from their artifacts.
3. **Given** the most recent run for a target completed every stage, **When** the developer
   invokes the analysis again, **Then** a new dated run is started and the completed run's
   artifacts and reports remain readable and untouched.
4. **Given** an incomplete run exists but the developer asks for a fresh run, **When** the
   analysis starts, **Then** a new dated run begins from stage 1 and the incomplete run is
   left intact for later inspection.
5. **Given** a resumed run, **When** it finishes, **Then** the final reports are the same in
   structure and content quality as an equivalent uninterrupted run.

---

### User Story 2 - Aim the Analysis Before Paying for It (Priority: P2)

As a developer with a large codebase, I want to see an architecture review first and then
decide — from a proposed depth assignment I can adjust — how deeply each part is reviewed,
so that expensive analysis is spent on the parts I care about instead of spread evenly over
vendored code, generated files, and areas I know are irrelevant.

**Why this priority**: This is where the token and time savings actually come from, and it is
the stage the user explicitly asked for ("clarify how deep each part must be reviewed"). It
depends on staged execution (User Story 1) existing first.

**Independent Test**: Run the analysis on a codebase with clearly distinct areas, stop after
the depth survey, mark a substantial portion of the codebase as skip, continue the run, and
confirm the analysis stage produces no work units for the skipped areas and that the final
report states those areas were intentionally not reviewed.

**Acceptance Scenarios**:

1. **Given** a target codebase, **When** the architecture review stage completes, **Then** its
   artifact names the codebase's components, their entry points, their relative size, and
   which of them are performance-relevant, in a form a developer can read and check.
2. **Given** a completed architecture review, **When** the depth survey stage runs, **Then**
   it proposes a review depth for every component with a one-line reason, and asks the
   developer to confirm or adjust before the plan is built.
3. **Given** a depth assignment where some components are marked skip, **When** the plan and
   analysis stages run, **Then** no analysis work is performed on the skipped components.
4. **Given** a completed run in which components were skipped or only skimmed, **When** the
   developer reads the final report, **Then** the coverage section states which parts were
   reviewed at which depth and which were deliberately excluded — never silently omitted.

---

### User Story 3 - Fix a Stage's Output by Hand and Continue (Priority: P3)

As a developer who spots a mistake in an intermediate artifact — a mis-identified entry point,
a component the survey misjudged, a plan that misses an area — I want to edit that artifact
directly in my editor and continue the run, so that the correction propagates into everything
downstream without me having to restart or fight the tool through prompts.

**Why this priority**: Turns the artifacts from a passive log into a control surface, and is
explicitly requested ("re-run, fix"). It builds on artifacts existing (User Story 1) and is
still valuable on its own.

**Independent Test**: Complete the architecture and survey stages, hand-edit the scope
artifact to change one component's depth, continue the run, and confirm the plan and analysis
stages honor the edited value rather than the originally proposed one.

**Acceptance Scenarios**:

1. **Given** a completed stage artifact that the developer has edited, **When** the run
   continues, **Then** downstream stages use the edited content as the authoritative input.
2. **Given** an edited artifact whose content can no longer be understood by the next stage,
   **When** the run continues, **Then** it stops with a clear message naming the artifact and
   what about it could not be understood, and leaves every other artifact untouched.
3. **Given** any completed stage, **When** the developer explicitly asks to re-run that stage,
   **Then** that stage is re-executed and stages before it are left untouched.
4. **Given** an edited or re-run stage whose downstream stages had already completed, **When**
   the run continues, **Then** the system names the now out-of-date downstream stages and asks
   whether to regenerate them, and regenerates nothing until the developer agrees.
5. **Given** the developer declines to regenerate an out-of-date stage, **When** a report is
   produced, **Then** it states which parts are based on out-of-date material rather than
   presenting them as current.

---

### User Story 4 - See Where the Run Stands and What It Cost (Priority: P4)

As a developer managing analysis cost, I want a single place that shows each stage's status,
when it completed, and what it consumed, so that I can decide whether to continue now, adjust
the scope, or stop.

**Why this priority**: Makes the savings visible and the resume decision informed, but the
feature delivers its value without it.

**Independent Test**: After completing part of a run, open the run's status artifact and
confirm it lists every stage with an unambiguous status, and that the statuses match what
actually happened.

**Acceptance Scenarios**:

1. **Given** a run in any state, **When** the developer opens the run's status artifact,
   **Then** every stage is listed with a status of not started, in progress, completed, or
   failed, plus a completion timestamp for completed stages.
2. **Given** a stage that failed, **When** the developer reads its entry, **Then** the reason
   for failure is stated in plain language, with no raw internal error text.
3. **Given** a completed stage, **When** the developer reads its entry, **Then** the model
   usage attributed to that stage is recorded, so the cost of continuing can be estimated.

---

### Edge Cases

- **Source code changed between stages**: the artifacts describe a codebase that no longer
  matches. The system detects this on resume per component, names which components changed and
  which stages and work units were based on the older code, and requires an explicit choice to
  continue with stale artifacts or refresh just those — it never silently mixes analysis of two
  different code states, and never invalidates components the change did not touch.
- **Artifact edited into an unreadable state**: the run stops at the stage that consumes it,
  names the file and the problem, and preserves all other artifacts (User Story 3, scenario 2).
- **Artifact deleted or missing on resume**: the stage that owns it is treated as not started
  and is re-run; stages before it are untouched.
- **The whole run workspace is deleted**: re-invoking starts a fresh run from stage 1 with a
  clear notice that no previous run state was found.
- **Several incomplete runs exist for one target**: continuing without naming a run continues
  the most recent one, and says which one it chose rather than picking silently.
- **Run workspaces accumulate over time**: nothing is deleted automatically; the documented
  layout keeps every run for a target in one place so they can be removed in one action, and
  the newest reports always stay at the canonical output location.
- **The developer declines to regenerate out-of-date stages**: the run continues with what
  exists, and the resulting report states which material is out of date.
- **Every work unit in the analysis stage fails**: the run still reaches the finalization stage
  and produces reports that state the total failure and name what did not complete, matching
  the existing pipeline's graceful-degradation behavior.
- **A single work unit fails repeatedly**: its failure is recorded in the run status and named
  in the report's coverage section; the remaining units' findings are still reported.
- **Non-interactive session reaches the depth survey**: with no way to ask the developer, the
  run does not silently guess a scope — it either uses a depth assignment supplied up front or
  stops with instructions on how to supply one.
- **Two analyses of the same target at the same time**: the second invocation detects the
  active run and refuses to write over its artifacts rather than corrupting them.
- **A run crashed while marked in progress**: the next invocation finds the marker, sees that
  the run behind it is no longer alive, reports the run as interrupted, and resumes it — a
  crash never leaves the target permanently locked.
- **Resuming a run whose artifacts were produced by an older version of the tool**: the
  mismatch is detected and reported with the option to start fresh, rather than being consumed
  as if it were current.
- **Artifacts cannot be written (permissions, full disk)**: the run stops immediately with a
  clear message, before spending model work whose result could not be saved.

## Requirements *(mandatory)*

### Functional Requirements

**Staged execution and artifacts**

- **FR-001**: The system MUST execute an analysis as an ordered sequence of five stages:
  architecture review, depth survey, analysis plan, analysis execution, and report
  finalization.
- **FR-002**: Each stage MUST write its output as one or more human-readable Markdown
  artifacts into the run's workspace before the next stage begins.
- **FR-003**: The analysis-execution stage MUST write a separate artifact per work unit as
  that unit completes, so an interruption loses at most the units still in flight.
- **FR-004**: Each stage MUST take the previous stages' artifacts as its primary input rather
  than re-deriving their content from the source code.
- **FR-005**: Artifact content MUST be understandable and editable by a developer without
  running the tool — plain Markdown, no opaque encodings.
- **FR-006**: The system MUST maintain a run status record listing every stage with its status
  (not started, in progress, completed, failed), completion time for completed stages, and the
  model usage attributed to it.
- **FR-006a**: The system MUST report each stage's completion to the developer as it happens,
  so progress through the decision stages is visible without waiting for the whole sequence.

**Resume, re-run, and correction**

- **FR-007**: On invocation, the system MUST look for the most recent run of that target: if it
  is incomplete, the system MUST resume it at the first stage that is not complete and MUST NOT
  re-execute completed stages; if it is complete, the system MUST start a new run and leave the
  completed one intact.
- **FR-007a**: The developer MUST be able to override that choice explicitly — to force a fresh
  run even when an incomplete one exists, and to name a specific earlier run to continue or to
  re-run a stage in.
- **FR-008**: On resume, the system MUST report which run it is continuing, which stages are
  being reused, and which will be executed, before doing any work.
- **FR-009**: Resuming the analysis-execution stage MUST re-analyze only the work units without
  a completed artifact.
- **FR-010**: The system MUST allow a developer to explicitly re-run a chosen stage, leaving
  the artifacts of earlier stages untouched.
- **FR-011**: The system MUST treat hand-edited artifacts as authoritative input for downstream
  stages.
- **FR-012**: When an artifact cannot be interpreted by the stage that consumes it, the system
  MUST stop with a message naming the artifact and the specific problem, and MUST NOT overwrite
  or discard any artifact.
- **FR-013**: When a stage is re-run or its artifact is edited after downstream stages already
  completed, the system MUST mark those downstream artifacts as out of date and MUST NOT
  present a final report that mixes current and out-of-date material without stating so.
- **FR-013a**: The system MUST NOT regenerate an out-of-date stage without the developer's
  explicit agreement: on continuing, it MUST name the affected stages, state that regenerating
  them costs model usage, and wait for a decision. Declining leaves those artifacts in place and
  marked out of date.
- **FR-013b**: In a non-interactive session where the out-of-date question cannot be asked, the
  system MUST stop with instructions rather than regenerate silently — unless the developer
  supplied the decision at invocation time.
- **FR-014**: The system MUST detect when the target's source code has changed since an
  artifact was produced and MUST require an explicit decision before continuing on that basis.
- **FR-014a**: That detection MUST be per component: the system MUST name which components
  changed, MUST identify the stages and work units whose artifacts depend on them, and MUST
  offer to refresh only those — components whose code is unchanged MUST keep their existing
  artifacts and MUST NOT be re-analyzed as a side effect of an unrelated change.
- **FR-015**: The system MUST refuse to write into a run workspace that another active run is
  using.
- **FR-015a**: The system MUST distinguish a still-running run from one that ended without
  clearing its in-progress marker. When the run that placed the marker is no longer running,
  the system MUST treat that run as interrupted, say so, and resume it normally, without
  requiring the developer to clear anything by hand. Only a run that is genuinely still in
  progress MUST be refused.

**Depth survey and scope control**

- **FR-016**: The architecture review stage MUST identify the codebase's components, their
  entry points, their relative size, and which are performance-relevant.
- **FR-017**: The depth survey stage MUST propose a review depth for every identified component
  together with a stated reason.
- **FR-018**: The system MUST let the developer confirm or adjust the proposed depths before
  the plan stage runs, and MUST NOT run the plan or analysis stages on an unconfirmed scope.
- **FR-018a**: Confirmation MUST be possible in each execution context: by answering in-session
  where the run can ask a question, and by halting after the depth survey and treating the next
  invocation as the confirmation where it cannot. In the halting case the system MUST tell the
  developer where the scope artifact is and how to continue.
- **FR-019**: The system MUST NOT choose a review scope silently. A run may proceed through the
  survey without stopping only when the developer supplied a depth assignment at invocation
  time, or explicitly asked for the proposed depths to be accepted as-is.
- **FR-020**: The plan stage MUST derive its work units solely from the confirmed depth
  assignment, producing no work for components marked skip.
- **FR-021**: The plan artifact MUST state, before execution begins, the number of work units
  broken down by review depth and an estimated token range for the analysis stage, expressed in
  the same unit the run status records per stage, so the developer can decide whether to
  continue or narrow the scope and can later compare the estimate against what was actually
  spent.

**Output and continuity**

- **FR-022**: The finalization stage MUST produce the same report deliverables as an
  unstaged run — the same required sections, severity ordering, and stage attribution.
- **FR-023**: The final report's coverage section MUST state which components were reviewed at
  which depth and which were deliberately excluded or failed to complete.
- **FR-024**: Every execution path — the AI-agent path and the hosted-API path alike — MUST run
  the same five stages, write the same artifact set, and support the same resume, re-run, and
  correction behavior, so a run started on one path is understandable and continuable in the
  same terms on the other.
- **FR-024a**: A developer MUST be able to complete all five stages in a single uninterrupted
  invocation by supplying or accepting the depth assignment up front (FR-019), so existing
  start-to-finish usage keeps working; artifacts are still written after every stage.
- **FR-025**: Each run MUST own its own workspace directory under a documented,
  perf-ai-dedicated location, named with the run's start date and time to the second so that
  runs of the same target on the same day never collide and sort chronologically by name.
  Completed runs MUST be retained — a new run MUST NOT overwrite or delete a previous run's
  artifacts.
- **FR-025a**: The finalization stage MUST write the run's reports into that run's workspace
  and MUST also refresh the canonical report files at the output location, so the newest
  reports are always in the expected place while every run's own copy remains available.
- **FR-025b**: The system MUST let the developer see the existing runs for a target, with each
  run's start date and time and its completion state, so they can choose which one to continue
  or inspect.
- **FR-026**: Retention MUST be under the developer's control: the system MUST NOT delete run
  workspaces on its own, and the documented layout MUST make all runs for a target removable in
  a single, obvious action.

### Key Entities

- **Run**: One analysis of one target codebase. Owns a workspace directory named with its start
  date and time, a status record, and all stage artifacts. Identified by its target and its
  start timestamp; retained after completion alongside earlier runs of the same target.
- **Stage**: One of the five ordered steps. Has a status, an input set (earlier artifacts), an
  output artifact set, a completion time, and attributed model usage.
- **Stage Artifact**: A Markdown document written by a stage — the durable, human-readable,
  editable representation of that stage's result and the unit of resume.
- **Component**: A meaningful part of the target codebase identified by the architecture
  review (module, package, service, layer) with an entry point, size, and performance
  relevance. Carries a record of the state of its source at the time it was reviewed, so a
  later change to that component alone can be detected.
- **Depth Assignment**: The review depth chosen for a component (deep, standard, skim, skip)
  with the reason for that choice; confirmed or adjusted by the developer.
- **Work Unit**: A single analyzable piece of the plan — a component (or file group) paired
  with a kind of analysis — with its own findings artifact and its own completion status.
- **Finding**: A performance observation attributed to a work unit, carrying severity,
  location, and a concrete suggested action, as in the existing reports.
- **Run Status Record**: The single readable summary of stage statuses, timings, model usage,
  and failures for the run.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Resuming a run that was interrupted after stage N re-executes zero of the stages
  1..N and produces final reports that a reviewer cannot distinguish in structure or coverage
  from an uninterrupted run of the same scope.
- **SC-002**: Continuing an interrupted run consumes no more than 110% of the model usage that
  the remaining stages would have consumed inside a single uninterrupted run.
- **SC-003**: Marking half of a codebase's components as excluded in the depth survey reduces
  the analysis stage's model usage by at least 40% compared with reviewing all components at
  standard depth.
- **SC-004**: A developer can determine which stages completed, which remain, and what has been
  spent so far within 30 seconds of opening the run workspace, without re-running anything.
- **SC-005**: An edit made by hand to a stage artifact is reflected in the final report in 100%
  of continued runs, with no silent reversion to the originally generated content.
- **SC-006**: Every completed stage leaves an artifact on disk before the next stage starts, so
  an interruption at any point loses at most one stage's — and within analysis execution, at
  most one wave of work units' — progress.
- **SC-007**: For a codebase of at least 200 source files, the architecture review, depth
  survey, and plan stages together account for no more than 20% of a full run's total model
  usage, keeping the decision-making phase cheap relative to the analysis itself.
- **SC-008**: 100% of components excluded or failed are named in the final report's coverage
  section; none are silently dropped.
- **SC-009**: Zero regenerations of out-of-date stages occur without an explicit developer
  decision — no continue operation ever spends model usage the developer did not approve.
- **SC-010**: After ten consecutive analyses of the same target, all ten runs' artifacts and
  reports are still readable, and the canonical report files reflect the tenth run.
- **SC-011**: A run started on one execution path can be inspected and continued on the other
  with identical stage names, artifact layout, and resume behavior.
- **SC-012**: For a codebase of about 200 source files, the architecture review, depth survey,
  and plan stages together complete in under 5 minutes, and each of them reports its completion
  as it happens rather than the developer waiting without feedback until the scope question.

## Assumptions

- The staged workflow is an evolution of the existing four analysis stages, not a replacement:
  the analysis-execution stage still performs structural, algorithmic-complexity, resource/IO,
  and concurrency analysis, and static-analysis-only remains absolute — no submitted code is
  executed, compiled, or profiled at any stage.
- The final deliverables remain the existing `perf-report.md` and `perf-report.html` at the
  output location, refreshed by each run; the new stage artifacts are additional working files,
  not replacements for the reports. Retaining a copy of each run's reports inside its own
  workspace is what makes previous runs readable without changing where the current reports
  live — an intentional refinement of the earlier "no history" decision, which was about not
  accumulating reports at the output location.
- Artifacts are stored on the local filesystem of the machine running the analysis; no remote
  storage, service, or database is introduced.
- Run workspaces live under the analysis output location in a single perf-ai-dedicated
  directory, one date-and-time-stamped subdirectory per run, so all runs for a target are found
  and removed together.
- Reports and artifacts are written in English, consistent with the existing pipeline decision.
- "Model usage" is measured in tokens consumed; recording it per stage is what makes the
  token-saving claims verifiable rather than assumed.
- A run is scoped to one target path; analyzing a different path starts an independent run with
  its own workspace.
- Review depths are a small fixed vocabulary (deep, standard, skim, skip) rather than a free
  numeric scale, so the survey is quick to confirm and unambiguous to act on.
- The developer confirming depths is the same person invoking the analysis; no multi-user
  review or approval flow is introduced.
- Concurrency limits for the analysis stage continue to follow the existing per-run parallelism
  rules; this feature changes when work is checkpointed, not how many workers run at once.
- On the hosted-API path the analysis is performed by the hosted model and on the agent path by
  the agent's own subagents, exactly as today; staging changes the run's shape on both paths,
  not who does the reasoning.
- "The most recent run" is determined by run start timestamp; date-and-time-stamped directory
  names make the ordering visible to the developer without any extra index, and keep several
  runs of the same target on the same day distinct.

## Dependencies

- Builds directly on the existing four-stage analysis pipeline and its report rendering,
  aggregation, and coverage-reporting behavior.
- Builds on the existing agent-path orchestration, including its work partitioning, result
  validation, duplicate merging, and parallelism limit.

## Out of Scope

- Comparing runs over time, diffing two runs, or trend reporting. Runs are retained and can be
  listed and opened, but nothing analyzes them against each other.
- Automatic pruning, archiving, or size-capping of retained run workspaces.
- Sharing or syncing run workspaces between machines or developers.
- Automatically applying suggested fixes to the analyzed code.
- Any change to what counts as a performance issue or how severity is judged.

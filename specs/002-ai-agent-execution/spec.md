# Feature Specification: AI Agent Execution & Parallelism

**Feature Branch**: `002-ai-agent-execution`

**Created**: 2026-08-04

**Status**: Draft

**Input**: User description: "Add posibility to use the pipeline with AI Agents, like claude code. Add possibility to run multiple agents in parallel (and ask before each execution how much is max). Add human-readable full described readme how to work with code"

## Clarifications

### Session 2026-08-04

- Q: Should "use the pipeline with AI Agents" mean the locally installed agent acts as the analysis engine the pipeline delegates to, rather than packaging the pipeline as a tool agents can invoke? → A: Package the pipeline as a tool that agents invoke — the agent is in charge; the pipeline is the callee.
- Q: When an agent invokes the pipeline as a tool, what performs the actual AI analysis? → A: The invoking agent's own model access — it fans out its own subagents for the stage analysis; no separate hosted-API credentials are required.
- Q: What form should the agent-invocable packaging take in the first version? → A: A Claude Code skill (slash command) shipped in the repository; other agents may be added later.
- Q: What default and upper bound apply when asking for the maximum number of parallel subagents? → A: No suggested default — the developer must choose the value themselves before each execution; a documented cap of 10 applies; non-interactive runs with no pre-supplied value fail fast rather than picking a number.
- Q: Does the existing hosted-API CLI remain unchanged, with the skill as an additive alternative producing the same report format? → A: Yes — additive; the skill produces reports with the same required sections, stage attribution, and output file conventions as the CLI.
- Q: Should the agent packaging be a bare repository skill or a full plugin? → A: A Claude Code plugin (supersedes the earlier "skill shipped in the repository" answer): the deliverable is a plugin whose analysis skill is the slash command; a bare skill entry in the repository is not sufficient.
- Q: How should the plugin be structured and distributed so a developer can install it? → A: The repository doubles as the plugin and its own marketplace — the plugin and marketplace manifests live at the repository root and the analysis skill ships inside the plugin — so a developer installs it into any project through the agent's plugin-marketplace flow.
- Q: Must the code generated in `001-perf-analysis-pipeline` be used by the plugin? → A: Yes — every deterministic step of a run (prerequisite checking, work partitioning, subagent-result validation, duplicate merging, aggregation, report rendering) executes the existing 001 pipeline code shipped with the plugin; only the AI analysis itself is performed by the agent and its subagents.
- Q: How does the plugin's skill execute that 001 code when installed in another project? → A: Directly from the installed plugin's own checkout, in an isolated manner that requires no prior package installation and does not modify the developer's environment; when the required Python runtime is missing, preflight fails fast with instructions.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run the Analysis Pipeline from Inside an AI Agent (Priority: P1)

As a developer working inside an AI coding agent (such as Claude Code), I want to invoke the
performance analysis pipeline as a tool of that agent — a slash-command skill shipped in this
project's agent plugin, which I can install into any of my projects — with the agent's own
model access performing the analysis, so that I can get the same analysis report using the
agent subscription I already have, without setting up separate hosted model provider
credentials.

**Why this priority**: This is the core new capability requested. It opens the pipeline to
users whose model access comes through an agent subscription rather than a raw API key, and
every other part of this feature (parallelism) builds on it.

**Independent Test**: In a Claude Code session where the plugin is installed from this
repository (or a session opened directly in this repository), invoke the analysis skill
against a sample codebase and confirm a complete report is produced with the same required
sections (issues, action items, valuable findings) and stage labels as a run of the existing
hosted-API CLI — without any hosted model provider credentials configured.

**Acceptance Scenarios**:

1. **Given** a Claude Code session in a project where the plugin is installed, **When** the
   developer invokes the analysis skill, **Then** the agent performs the analysis using its
   own model access and produces the same kind of human-readable report (same sections, stage
   attribution, and output files) as a run of the existing hosted-API CLI.
2. **Given** the skill's prerequisites are not met (for example, the target to analyze is
   missing or unreadable), **When** the developer invokes the skill, **Then** it stops before
   analysis begins and shows a clear message explaining what is missing and how to resolve it.
3. **Given** an existing user who runs the hosted-API CLI as before, **When** they run it,
   **Then** the system behaves exactly as it does today — the plugin is purely additive and
   changes nothing for existing usage.
4. **Given** a project that does not yet have the plugin, **When** the developer installs it
   from this repository through the agent's plugin-marketplace flow, **Then** the analysis
   skill becomes invocable in that project's agent sessions without any further setup.

---

### User Story 2 - Run Multiple Subagents in Parallel with a Per-Run Limit (Priority: P2)

As a developer analyzing a multi-part codebase, I want the skill to distribute analysis work
across several subagents running at the same time, and I want to be asked before each
execution how many subagents may run in parallel at most — a value I choose myself — so that
analysis finishes faster while I stay in control of the load on my machine and my agent usage.

**Why this priority**: Parallelism is the main speed and scalability win of agent execution,
but it only makes sense once single-invocation skill execution (User Story 1) works.

**Independent Test**: Invoke the skill on a project with multiple analyzable units, confirm
it asks for a maximum parallel-subagent count before analysis starts and does not proceed
until a value is given, answer with a number, and verify by observing the run that the number
of concurrently active subagents never exceeds that answer.

**Acceptance Scenarios**:

1. **Given** a skill invocation is about to start analysis, **When** the run begins, **Then**
   the skill first asks the developer for the maximum number of subagents allowed to run in
   parallel and waits for an explicit answer — it does not proceed on an implied default.
2. **Given** the developer answers with a valid number N (1 through 10), **When** analysis
   proceeds, **Then** at no point are more than N subagents active at the same time.
3. **Given** the developer enters an invalid value (zero, negative, or not a number), **When**
   the skill reads the answer, **Then** it explains why the value is invalid and asks again
   rather than failing the run.
4. **Given** the developer asks for more than 10, **When** the skill reads the answer,
   **Then** it caps the value at 10 and tells the developer the value was capped.
5. **Given** one subagent fails or times out during a parallel run, **When** the run
   completes, **Then** findings from the successful subagents are still included in the
   report and the failed portion is explicitly noted, consistent with the pipeline's existing
   graceful-degradation behavior.

---

### User Story 3 - Learn to Work with the Project from the README (Priority: P3)

As a developer new to this project, I want a complete, human-readable README that explains
what the tool does, how to set it up, how to run it in every supported way, and how to work
on the code itself, so that I can go from cloning the project to a successful analysis run —
and to making changes — without asking anyone for help.

**Why this priority**: Documentation multiplies the value of the other two stories and was
explicitly requested, but the product functions without it.

**Independent Test**: Give the README to a developer who has never seen the project and
confirm they can install the tool, configure it, complete an analysis run via at least one
supported path, and locate where in the codebase they would make a described change — using
only the README.

**Acceptance Scenarios**:

1. **Given** the project's README, **When** a new developer follows it from the beginning,
   **Then** they can complete installation, configuration, and a first successful analysis
   run without consulting any other source.
2. **Given** the README's description of the supported execution paths, **When** the
   developer reads it, **Then** both the existing hosted-API CLI and the agent plugin's skill
   (including plugin installation, the parallel-subagents prompt, and its non-interactive
   override) are explained with working, copyable commands.
3. **Given** the README's project-structure section, **When** a developer wants to change a
   specific behavior (for example, how a report section is rendered), **Then** the README
   points them to the right part of the codebase and explains how to run the tests.

---

### Edge Cases

- What happens when the skill is invoked but its prerequisites are not met (for example, the
  analysis target is missing or unreadable)? The skill MUST detect this before starting
  analysis and fail fast with a message that names the problem and the fix, rather than
  starting a run that dies midway.
- What happens when the plugin is installed and invoked in a project, but the runtime needed
  to execute the bundled pipeline code is not available on the developer's machine? Preflight
  MUST detect this and fail fast — naming what is missing and how to install it — before any
  analysis work starts.
- What happens when the skill runs in a non-interactive agent context (no one to answer the
  parallelism question)? The skill MUST use a pre-supplied parallelism value when one was
  given; when none was given, it MUST fail fast with a clear message rather than choosing a
  number itself or hanging while waiting for input that can never arrive.
- What happens when the requested parallel count exceeds the amount of available analysis
  work (for example, 8 subagents for a project with 3 analyzable units)? The skill MUST use
  only as many subagents as there is work for, without erroring.
- What happens when the developer asks for more than the documented cap of 10 parallel
  subagents? The skill MUST cap the value at 10 and tell the developer the value was capped.
- What happens when two parallel subagents report the same or conflicting findings for the
  same code location? The final report MUST remain a single coherent report — duplicates
  merged, not repeated verbatim.
- What happens when a subagent produces output that does not match the expected result
  structure? The affected portion MUST be treated like a failed stage — noted in the report —
  while the rest of the run continues.
- What happens when every subagent in a parallel run fails? The skill MUST end the run with a
  clear failure summary rather than producing an empty report that looks like a clean result.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Project MUST provide an agent-invocable packaging of the analysis pipeline as a
  Claude Code plugin shipped from this repository: the repository doubles as the plugin and
  its own marketplace (plugin and marketplace manifests at the repository root, with the
  analysis skill — a slash command — inside the plugin), so that a developer can install it
  into any project through the agent's plugin-marketplace flow and run a complete analysis
  from inside the agent.
- **FR-002**: The skill MUST perform the analysis using the invoking agent's own model
  access, and MUST NOT require hosted model provider credentials to be configured.
- **FR-003**: The existing hosted-API CLI MUST remain unchanged and fully supported; the
  skill is additive, and existing usage behaves exactly as it does today.
- **FR-004**: Reports produced via the skill MUST satisfy all report requirements of the
  existing pipeline specification — same required sections, stage attribution, ordering,
  empty-section handling, and output files — so the execution path is invisible in the final
  artifact.
- **FR-005**: The skill MUST be able to run multiple subagents concurrently within one
  analysis run, distributing independent analysis work among them.
- **FR-006**: Before each execution, the skill MUST ask the developer for the maximum number
  of subagents allowed to run in parallel, and MUST wait for the developer's explicit answer
  — it MUST NOT proceed on a suggested or implied default.
- **FR-007**: The skill MUST validate the parallelism answer (reject zero, negative, and
  non-numeric values by explaining and re-asking) and MUST enforce a documented upper bound
  of 10 concurrent subagents, informing the developer when their requested value is capped.
- **FR-008**: The skill MUST never run more concurrent subagents than the confirmed maximum,
  and MUST use fewer when there is less independent work than the allowed maximum.
- **FR-009**: The skill MUST support non-interactive invocation by accepting the parallelism
  value up front; when running where no interactive answer is possible and no value was
  supplied, it MUST fail fast with a clear message rather than choosing a value itself.
- **FR-010**: When individual subagents fail, time out, or return unusable output during a
  parallel run, the skill MUST still deliver a report containing results from the successful
  subagents and MUST identify what did not complete; when all subagents fail, it MUST report
  the run as failed rather than emitting an empty-but-clean-looking report.
- **FR-011**: The skill MUST consolidate findings arriving from parallel subagents into one
  coherent report, merging duplicate findings for the same location rather than listing them
  repeatedly.
- **FR-012**: Project MUST include a README at the project root, written in plain English for
  a developer audience, covering at minimum: what the tool does and its constraints (static
  analysis, no code execution), prerequisites, installation (including installing the agent
  plugin from this repository), configuration of each execution path, how to run an analysis
  via each path (the hosted-API CLI and the plugin's skill, including the parallel-subagents
  prompt and its non-interactive override), where reports are written and what they contain,
  an overview of the codebase layout for contributors, how to run the tests, and common
  problems with their fixes.
- **FR-013**: Every command shown in the README MUST work as written when followed in order
  on a fresh setup.
- **FR-014**: Every deterministic step of a plugin-skill run — prerequisite checking, work
  partitioning, subagent-result validation, duplicate merging, aggregation, and report
  rendering — MUST be performed by executing the `001-perf-analysis-pipeline` code bundled in
  the installed plugin's own checkout, not by a reimplementation of any of it. The skill MUST
  invoke that code from the plugin's install directory without requiring the developer to
  pre-install the package and without modifying the developer's environment; when the runtime
  needed to execute it is unavailable, the run MUST fail fast before analysis begins with
  instructions for obtaining it.

### Key Entities

- **Execution Path**: The way an analysis is performed — the existing hosted-API CLI or the
  new agent plugin's skill. Exactly one path applies to a given run; the CLI path is
  unchanged by this feature.
- **Agent Plugin**: The Claude Code plugin shipped from this repository — the repository
  doubles as the plugin and its own marketplace — containing the analysis skill (the slash
  command a supported agent discovers and executes). The skill orchestrates the analysis
  using the agent's own model access and executes the bundled `001-perf-analysis-pipeline`
  code from the plugin's own checkout for every deterministic step.
- **Subagent Instance**: One concurrently running unit of analysis work spawned by the
  invoking agent during a skill run; has an outcome (succeeded, failed, timed out, unusable
  output) that feeds the report's completeness notes.
- **Parallelism Limit**: The per-run maximum number of subagents allowed to run at once;
  explicitly chosen by the developer before each execution (or pre-supplied for
  non-interactive runs) and bounded by a documented cap of 10.
- **README**: The project-root document that teaches a new developer to install, configure,
  run (via every supported path), and modify the project.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A developer with a working AI coding agent and no separately configured model
  provider credentials can complete a full analysis run via the skill and receive a complete
  report.
- **SC-002**: 100% of skill-produced reports contain all required report sections and stage
  labels, indistinguishable in structure from hosted-API CLI reports.
- **SC-003**: 100% of interactive skill executions ask for the maximum parallel-subagent
  count before analysis starts and receive an explicit answer before proceeding, and no run
  ever exceeds the confirmed limit.
- **SC-004**: On a project with at least 4 independent analyzable units, a run allowed 4
  parallel subagents completes in measurably less wall-clock time than the same run limited
  to 1 subagent (at least 30% faster).
- **SC-005**: A developer who has never used the project can go from obtaining the code to a
  first successful analysis run in under 15 minutes using only the README.
- **SC-006**: 100% of commands printed in the README succeed when executed as written on a
  fresh setup.

## Assumptions

- Per clarification, "use the pipeline with AI Agents" means packaging the pipeline as a tool
  the agent invokes: the agent is in charge, runs the analysis with its own model access, and
  the pipeline's analysis method and report contract define what the skill must produce. The
  alternative reading — the pipeline calling out to an agent as its analysis engine — is out
  of scope.
- The AI coding agent is installed, signed in, and licensed by the developer independently of
  this project; the skill runs inside the agent and does not install, update, or authenticate
  it.
- The set of supported agents starts with a single agent (Claude Code) as the reference
  integration; the skill's user-facing behavior is described generically so packagings for
  other agents can be added later without changing the guarantees described here.
- Executing the bundled deterministic pipeline code requires a suitable Python runtime on the
  developer's machine; the plugin does not install or manage that runtime itself — preflight
  verifies it and fails fast with instructions when it is missing.
- The parallelism question is asked once per execution (per run), not once per stage or per
  subagent.
- There is deliberately no suggested default for the parallelism value: the developer must
  choose it themselves each execution (or pre-supply it for non-interactive runs). The
  documented cap is 10.
- Independent analysis work units for parallel distribution (e.g., stages or partitions of
  the codebase) are an internal design decision; the user-visible guarantees are only the
  concurrency limit and the single consolidated report.
- The existing hosted-API CLI, report formats, and statelessness across runs (from the
  pipeline specification `001-perf-analysis-pipeline`) remain unchanged; this feature adds to
  that behavior rather than modifying it.
- The README replaces the current placeholder README; English is its only required language,
  consistent with the report-language decision in the pipeline specification.

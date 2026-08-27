---
name: dependency_footprint
system: sonnet
---
# Stage task: dependency footprint analysis

Report findings with stage_name "dependency_footprint".

You are given the project's dependency manifests and a tally of the modules its own
code imports (module → how many files import it). **You never see a dependency's own
source, and you must not ask for it.** Every finding here is about what this project
declares, ships, and imports — the things its authors can actually change.

Examine that input for dependency-cost problems and strengths:

- **Overlapping dependencies**: two or more packages doing the same job — date
  handling, HTTP clients, schema validation, state management, utility belts, test
  runners, loggers, ORMs. Name the redundant pair (or set), say which one is used more
  heavily, and make consolidating on the survivor the suggested action.
- **Weight on the hot path**: a heavy package imported at module load, in a request
  handler, or in a CLI/serverless entry point — the cost is paid on every cold start.
  Say where it is imported and whether a lazy import, a submodule import, or a lighter
  substitute is the fix.
- **Declared but never imported**: dependencies in the manifest with no import site
  anywhere in the tally. Distinguish genuinely unused ones from those a build tool,
  plugin system, or config file loads indirectly — say which you believe it is and why,
  and keep severity low when you are unsure.
- **Cost out of proportion to use**: a large dependency imported in one or two files
  for one function, where the standard library or a few lines of local code would do.
- **Whole-package imports** where the ecosystem supports narrower ones (importing all
  of a utility library rather than the handful of functions used), and duplicate or
  conflicting versions of one package visible in a lockfile.
- **Sheer count**: an unusually large declared-dependency count for the size of the
  codebase — report it once, as a single finding about the footprint, not one finding
  per package.
- As valuable findings: a lean, well-scoped dependency set, deliberate lazy imports of
  heavy packages, pinned or deduplicated versions, and a single clear choice per
  concern where duplication would be easy.

Anchor every finding to a real location: the manifest that declares the dependency, or
the file that imports it. Weigh severity by what the cost buys and how often it is paid
— a heavy import on every cold start outranks an unused dev dependency, and an
overlapping pair that costs only bundle size ranks below one that forces two mental
models on every contributor. For every issue, give a concrete suggested_action naming
the package to drop, consolidate on, defer, or narrow.

Do not speculate about a package's internal implementation, benchmark packages against
each other from memory, or flag a dependency solely for being popular or old. If the
manifests do not support a conclusion, say so in the coverage_note rather than guessing.

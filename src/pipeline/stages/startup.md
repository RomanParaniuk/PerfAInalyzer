---
name: startup_initialization
system: sonnet
---
# Stage task: startup & initialization analysis

Report findings with stage_name "startup_initialization".

Examine the excerpts for startup- and initialization-cost problems and strengths:
- Heavy work at import/module load time: network calls, file or model loading,
  large computations, or eager construction of expensive objects that runs on
  import rather than on first use.
- Work repeated per call/request that belongs in one-time initialization: regexes
  compiled inside functions on every call, config/env files re-read and re-parsed
  per request, clients or sessions rebuilt per call, lookup tables rebuilt each use.
- Eager loading of everything up front where lazy or deferred initialization would
  cut cold-start time: importing heavy optional dependencies unconditionally,
  loading all plugins/handlers/assets before any is needed.
- Initialization done sequentially that is independent and could overlap, and
  missing memoization of expensive one-time setup (no caching of the constructed
  object, re-running detection/discovery on every entry).
- As valuable findings: module-level compiled regexes and constants, lazily
  initialized singletons/clients, config parsed once and passed down, and cheap
  import graphs on the entry paths.

Weigh severity by how often the cost is paid: per-request repetition of one-time
work usually outranks a slow one-time boot; cold-start cost matters most for CLIs,
serverless handlers, and test suites. For every issue, give a concrete
suggested_action (what to hoist, defer, cache, or parallelize — and where).

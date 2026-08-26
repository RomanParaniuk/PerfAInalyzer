---
name: concurrency_scalability
system: sonnet
---
# Stage task: concurrency & scalability analysis

Report findings with stage_name "concurrency_scalability".

Examine the excerpts for concurrency- and scalability-relevant problems and strengths:
- Lock contention risks: coarse-grained or long-held locks, locks around I/O,
  shared mutable state accessed without synchronization.
- Blocking calls inside async code paths (sync I/O awaited contexts, sleeps in
  event loops); sequential awaits that could run concurrently.
- Thread/process-pool misuse: unbounded task submission, pools sized without regard
  to workload, missing backpressure on queues.
- Global state, module-level caches, or singletons that serialize otherwise parallel
  work or prevent horizontal scaling.
- Race conditions or check-then-act patterns on shared data visible in the excerpts.
- As valuable findings: sound synchronization choices, well-bounded queues and pools,
  and designs that scale horizontally without shared-state bottlenecks.

If the code has no meaningful concurrency surface, an empty findings list is the
correct answer — do not invent speculative concurrency issues for sequential code.
For every issue, give a concrete suggested_action naming the primitive or restructure
to apply.

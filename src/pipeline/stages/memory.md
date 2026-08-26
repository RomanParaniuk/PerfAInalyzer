---
name: memory_allocation
system: sonnet
---
# Stage task: memory & allocation analysis

Report findings with stage_name "memory_allocation".

Examine the excerpts for memory- and allocation-behavior problems and strengths:
- Allocation churn in hot paths: string concatenation inside loops, intermediate
  list/dict copies per iteration, objects constructed per call that could be reused
  or hoisted out of the loop.
- Retention leaks: caches and registries that only ever grow (no eviction, no TTL,
  no weak references), listeners/subscribers registered but never removed, closures
  or default arguments capturing large objects for the process lifetime.
- Unnecessary materialization: whole files or result sets read into memory where a
  generator/iterator/stream would do; `readlines()`/`.tolist()`-style full copies
  followed by a single pass; slicing that copies where a view would do.
- Copy-heavy idioms: `deepcopy` where a shallow copy or no copy is needed; repeated
  defensive copies of the same structure; DataFrame/array pipelines that produce a
  new full copy at every step.
- As valuable findings: effective object reuse or pooling, streaming/iterator
  pipelines, bounded caches with an explicit eviction policy, and builder-style
  string/buffer accumulation (`join`, StringIO/StringBuilder).

Distinguish this stage from algorithmic complexity: report the *memory* cost of a
pattern (peak footprint, allocation rate, retention), not its time complexity.
For every issue, set severity by the practical footprint or leak risk and give a
concrete suggested_action (what to stream, bound, reuse, or stop copying — and where).

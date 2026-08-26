---
name: algorithmic_complexity
system: sonnet
---
# Stage task: algorithmic complexity analysis

Report findings with stage_name "algorithmic_complexity".

Examine the excerpts for algorithmic-efficiency problems and strengths:
- Nested iteration over the same or correlated collections (quadratic or worse
  behavior), including hidden linear scans inside loops (`in` on lists, indexOf,
  repeated .index/.count/.find calls).
- Unbounded growth of in-memory collections (append/push inside loops with no cap,
  caches without eviction).
- Repeated recomputation of results that could be computed once or memoized;
  recursion without memoization on overlapping subproblems.
- Sorting or rebuilding data structures inside loops when a single pass or a
  better-suited structure (set/dict/heap) would do.
- As valuable findings: appropriate data-structure choices, effective memoization,
  and algorithms well-matched to their access patterns.

For every issue, estimate the practical impact in the severity and give a concrete
rewrite step in suggested_action (name the exact structure/approach to switch to).

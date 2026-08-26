---
name: resource_io_efficiency
system: sonnet
---
# Stage task: resource & I/O efficiency analysis

Report findings with stage_name "resource_io_efficiency".

Examine the excerpts for resource- and I/O-efficiency problems and strengths:
- I/O performed inside loops: files re-opened per iteration, per-item network
  requests that could be batched, per-row database queries (N+1 patterns).
- Missing buffering, streaming, or pagination when reading/writing large payloads;
  loading entire files/result sets into memory when iteration would suffice.
- Resources not reused or not released: connections/handles opened per call instead
  of pooled or kept in a context manager; missing timeouts on network calls.
- Redundant serialization/deserialization or repeated filesystem scans
  (listdir/walk/glob) of unchanged directories.
- As valuable findings: effective batching, connection reuse/pooling, streaming
  processing, and well-placed caching of I/O results.

For every issue, set severity by likely real-world cost and give a concrete
suggested_action (what to open once, batch, buffer, pool, or stream — and where).

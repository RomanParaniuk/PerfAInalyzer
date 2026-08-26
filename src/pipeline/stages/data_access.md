---
name: data_access_efficiency
system: sonnet
---
# Stage task: data access & query efficiency analysis

Report findings with stage_name "data_access_efficiency".

Examine the excerpts for database- and datastore-access problems and strengths:
- Unbounded queries: reads with no LIMIT/pagination on tables or collections that
  grow with usage; `SELECT *` (or full-document fetches) where a projection of the
  needed columns/fields would do.
- Work done on the wrong side: filtering, joining, aggregating, or sorting rows in
  application code that the database can do in the query; per-row round trips where
  one set-based statement would do (beyond the plain N+1 case: chatty
  read-modify-write loops, per-item EXISTS checks).
- ORM traps: lazy-loaded relations accessed in loops (missing
  select_related/prefetch/joinedload-style eager loading), implicit per-attribute
  queries, saving entities one by one where a bulk operation exists.
- Missing-index candidates: predicates and orderings visible in the code
  (WHERE/ORDER BY columns, lookup fields) that the schema or migrations in scope do
  not index — flag only what the excerpts actually support.
- Transaction scope: transactions held open across network calls, user waits, or
  long computations; autocommit-per-row where one transaction should batch.
- As valuable findings: set-based operations, well-placed eager loading, bulk
  writes, keyset pagination, and query results cached with sound invalidation.

If the scope has no database or datastore access at all, an **empty findings list is
the correct answer** — do not invent speculative data-access issues, and say in the
coverage_note that no data-access surface was found.
For every issue, set severity by likely real-world cost at production data sizes and
give a concrete suggested_action (the query, index, eager-load, or batching change
to make — and where).

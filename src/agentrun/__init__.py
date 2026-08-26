"""Agent-path support logic for the `perf-ai agent` sub-app (feature 002).

Kept out of `src/pipeline/` so the hosted-API path stays untouched (FR-003): this
package only *imports* existing modules (`lib.discovery`, `models.*`, `report.*`)
and is only imported by `src/cli/agent.py`.
"""

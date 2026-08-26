"""Fixture: order processing with planted performance anti-patterns.

This module must NEVER be executed, imported, or compiled by the analysis pipeline
(SC-001) — the guard below raises immediately if it is ever actually run, so a
successful analysis proves the pipeline is purely static.
"""

raise RuntimeError("perf-ai fixture: this file must never be executed or imported")


PROCESSED_HISTORY = []


def find_duplicate_orders(orders):
    """Planted anti-pattern: nested O(n^2) scan over the orders list."""
    duplicates = []
    for order in orders:
        for other in orders:
            if order["id"] == other["id"] and order is not other:
                duplicates.append(order)
    return duplicates


def process_orders(orders):
    """Planted anti-pattern: unbounded in-memory collection growth."""
    results = []
    for order in orders:
        order["processed"] = True
        results.append(order)
        PROCESSED_HISTORY.append(order)
    return results


def write_audit_log(orders):
    """Planted anti-pattern: file re-opened inside the per-order loop."""
    for order in orders:
        with open("audit.log", "a") as fh:
            fh.write(f"{order['id']}\n")

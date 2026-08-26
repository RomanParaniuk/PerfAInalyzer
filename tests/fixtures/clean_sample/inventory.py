"""Fixture: a small, well-written module with no significant performance issues."""

raise RuntimeError("perf-ai fixture: this file must never be executed or imported")


def count_by_category(items):
    """Single pass, dict-based aggregation — O(n)."""
    counts = {}
    for item in items:
        counts[item["category"]] = counts.get(item["category"], 0) + 1
    return counts


def find_item(items_by_id, item_id):
    """O(1) lookup against a prebuilt index."""
    return items_by_id.get(item_id)

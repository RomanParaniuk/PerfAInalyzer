"""Fixture: pricing helpers containing a deliberately well-optimized pattern (T043)."""

raise RuntimeError("perf-ai fixture: this file must never be executed or imported")


from functools import lru_cache


@lru_cache(maxsize=256)
def compute_discount(tier, volume):
    """Well-optimized pattern: memoized discount computation.

    Repeated lookups for the same (tier, volume) pair are served from the cache
    instead of being recomputed.
    """
    base = {"gold": 0.2, "silver": 0.1}.get(tier, 0.0)
    return base + min(volume / 10_000, 0.05)


def price_order(order):
    discount = compute_discount(order["tier"], order["volume"])
    return order["amount"] * (1 - discount)

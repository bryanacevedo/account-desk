"""Small, exact statistics for the results pages. No dependencies.

- Wilson score interval for one proportion.
- Newcombe's hybrid score interval (method 10) for a difference of two proportions.
- Accounts needed per arm to detect a given lift (normal approximation, two-sided).
"""
from __future__ import annotations

import math
from statistics import NormalDist

_N = NormalDist()


def z(conf: float) -> float:
    return _N.inv_cdf(1 - (1 - conf) / 2)


def wilson(k: int, n: int, conf: float = 0.90) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    zz = z(conf)
    p = k / n
    denom = 1 + zz * zz / n
    centre = (p + zz * zz / (2 * n)) / denom
    half = zz * math.sqrt(p * (1 - p) / n + zz * zz / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def newcombe(k1: int, n1: int, k2: int, n2: int, conf: float = 0.90) -> tuple[float, float, float]:
    """Difference p1 - p2 with Newcombe's hybrid score interval. Returns (diff, low, high)."""
    p1 = k1 / n1 if n1 else 0.0
    p2 = k2 / n2 if n2 else 0.0
    l1, u1 = wilson(k1, n1, conf)
    l2, u2 = wilson(k2, n2, conf)
    d = p1 - p2
    low = d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    high = d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)
    return (d, max(-1.0, low), min(1.0, high))


def n_per_arm(base: float, lift: float, *, alpha: float = 0.10, power: float = 0.80, ratio: float = 4.0) -> int:
    """Holdout accounts needed for a two-sided test to detect `base` -> `base + lift`, with `ratio` treated
    accounts per holdout account. Returns the holdout size; treated is ratio times that."""
    p1 = min(0.999, base + lift)
    p2 = max(0.0001, base)
    za, zb = z(1 - alpha), _N.inv_cdf(power)
    pbar = (ratio * p1 + p2) / (ratio + 1)
    num = (za * math.sqrt(pbar * (1 - pbar) * (1 + 1 / ratio)) + zb * math.sqrt(p1 * (1 - p1) / ratio + p2 * (1 - p2))) ** 2
    return math.ceil(num / (p1 - p2) ** 2)


def lift_report(treated_k: int, treated_n: int, hold_k: int, hold_n: int, *, conf: float = 0.90) -> dict:
    """Everything the Results page shows about one comparison. The difference worth detecting is a doubling of the
    observed base rate (at least 2 points); below the sample that needs, it says how many accounts are still needed."""
    base = hold_k / hold_n if hold_n else (treated_k / treated_n if treated_n else 0.02)
    base = max(base, 0.01)
    assumed_lift = max(0.02, base)
    ratio = (treated_n / hold_n) if hold_n else 4.0
    need_hold = n_per_arm(base, assumed_lift, ratio=max(ratio, 1.0))
    need_treated = math.ceil(need_hold * max(ratio, 1.0))
    enough = hold_n >= need_hold and treated_n >= need_treated
    d, lo, hi = newcombe(treated_k, treated_n, hold_k, hold_n, conf)
    return {"treated": {"meetings": treated_k, "accounts": treated_n,
                        "rate": treated_k / treated_n if treated_n else None},
            "holdout": {"meetings": hold_k, "accounts": hold_n, "rate": hold_k / hold_n if hold_n else None},
            "difference": d if (treated_n and hold_n) else None, "interval": [lo, hi] if (treated_n and hold_n) else None,
            "enough": enough, "needed": {"holdout": need_hold, "treated": need_treated},
            "still_needed": {"holdout": max(0, need_hold - hold_n), "treated": max(0, need_treated - treated_n)},
            "detectable_lift": assumed_lift, "confidence": conf}


def fisher_greater(k: int, n_in: int, m: int, total: int) -> float:
    """One-sided Fisher exact test: the chance of seeing k or more of the m accounts that heard something inside a
    group of n_in, out of `total` accounts, if hearing it had nothing to do with the group (the hypergeometric upper
    tail). The 2x2 table is [[k, n_in - k], [m - k, total - n_in - m + k]]. Exact integers, no dependency."""
    if not (0 <= k <= m <= total and k <= n_in <= total) or total - n_in - m + k < 0:
        raise ValueError("not a 2x2 table")
    top = min(m, n_in)
    hits = sum(math.comb(m, x) * math.comb(total - m, n_in - x) for x in range(k, top + 1))
    return hits / math.comb(total, n_in)


def within_reach(lift: dict, room: int) -> dict:
    """Marks a comparison that cannot settle at this desk's size: the accounts it still needs (worked plus held back)
    are more than the accounts left that have never been offered it. Counting is intention to treat on the first
    assignment, so offering an account again adds nothing; only a larger list or a bigger difference can settle it."""
    need = lift["still_needed"]["treated"] + lift["still_needed"]["holdout"]
    lift["room"] = room
    lift["out_of_reach"] = (not lift["enough"]) and need > room
    return lift

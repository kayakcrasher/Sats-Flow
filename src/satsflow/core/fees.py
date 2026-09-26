"""Fee tier logic for SatsFlow.

"Loyalty is Royalty" — the fee drops the longer a creator stays.

Tiers (checked in order, first match wins):
    Days  0-14  :  3.5%   Launch
    Days 14-60  :  2.5%   Growth
    Days 60+    :  2.0%   Permanent

Per-creator override for Friends of the Dev (1%) and Cofounders (0%).
"""
from __future__ import annotations

import time

FEE_TIERS: list[tuple[int | None, float]] = [
    (14, 0.035),
    (60, 0.025),
    (None, 0.020),
]

FRIENDS_OF_DEV_FEE = 0.010
COFOUNDER_FEE = 0.000

SECONDS_PER_DAY = 86400


def fee_percent_for(
    created_at: int,
    override: float | None = None,
    now: int | None = None,
) -> float:
    if override is not None:
        if not (0.0 <= override < 1.0):
            raise ValueError(f"fee_override out of range: {override}")
        return override

    current_time = now if now is not None else int(time.time())
    age_seconds = max(0, current_time - created_at)
    age_days = age_seconds / SECONDS_PER_DAY

    for threshold, pct in FEE_TIERS:
        if threshold is None or age_days < threshold:
            return pct

    return FEE_TIERS[-1][1]


def days_until_next_tier(
    created_at: int,
    override: float | None = None,
    now: int | None = None,
) -> int | None:
    if override is not None:
        return None

    current_time = now if now is not None else int(time.time())
    age_seconds = max(0, current_time - created_at)
    age_days = age_seconds / SECONDS_PER_DAY

    for threshold, _pct in FEE_TIERS:
        if threshold is None:
            return None
        if age_days < threshold:
            remaining = threshold - age_days
            return max(0, int(remaining + 0.999))

    return None


def tier_name(
    created_at: int,
    override: float | None = None,
    now: int | None = None,
) -> str:
    if override is not None:
        if override <= COFOUNDER_FEE:
            return "Cofounder"
        if override <= FRIENDS_OF_DEV_FEE:
            return "Friends of the Dev"
        return "Custom"

    pct = fee_percent_for(created_at, override, now)
    if pct >= 0.035:
        return "Launch"
    if pct >= 0.025:
        return "Growth"
    return "Permanent"

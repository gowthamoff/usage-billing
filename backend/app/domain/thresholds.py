"""Allowance threshold crossings and the usage state shown in the UI."""

from __future__ import annotations

from decimal import ROUND_DOWN, Decimal
from typing import Iterable

DEFAULT_THRESHOLDS: tuple[int, ...] = (50, 80, 100)

WITHIN_ALLOWANCE = "within_allowance"
APPROACHING_LIMIT = "approaching_limit"
IN_OVERAGE = "in_overage"

_TWO_PLACES = Decimal("0.01")


def crossed_thresholds(
    before: int, after: int, allowance: int, thresholds: Iterable[int] = DEFAULT_THRESHOLDS
) -> list[int]:
    """Return the thresholds (percent of allowance) first reached going from `before` to `after`.

    Integer arithmetic only: percent t is reached when usage * 100 >= allowance * t.
    """
    if allowance <= 0 or after <= before:
        return []
    return [t for t in sorted(thresholds) if before * 100 < allowance * t <= after * 100]


def percent_used(used: int, allowance: int) -> Decimal:
    """Return percent of allowance used, truncated to two decimals so display never rounds across a
    state boundary."""
    if allowance <= 0:
        return Decimal(100) if used > 0 else Decimal(0)
    return (Decimal(used) * 100 / Decimal(allowance)).quantize(_TWO_PLACES, rounding=ROUND_DOWN)


def usage_state(percent: Decimal | int | float) -> str:
    """Map a percent-used value to the usage state shown in the UI."""
    if percent < 80:
        return WITHIN_ALLOWANCE
    if percent < 100:
        return APPROACHING_LIMIT
    return IN_OVERAGE

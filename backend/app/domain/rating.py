"""Overage-only pricing: amount = round_once(max(0, used - allowance) * rate)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Mapping

from app.domain.money import to_minor


@dataclass(frozen=True)
class PlanMeterRate:
    """Allowance and overage rate for one meter on a plan."""

    meter_id: str
    allowance: int
    rate_minor: Decimal


@dataclass(frozen=True)
class RatedLine:
    """Rated usage for one meter: overage units and the amount owed."""

    meter_id: str
    quantity: int
    allowance: int
    overage_units: int
    rate_minor: Decimal
    amount_minor: int


def rate_meter(meter_id: str, used: int, allowance: int, rate_minor: Decimal) -> RatedLine:
    """Rate one meter's usage against its allowance."""
    overage_units = max(0, used - allowance)
    return RatedLine(
        meter_id=meter_id,
        quantity=used,
        allowance=allowance,
        overage_units=overage_units,
        rate_minor=rate_minor,
        amount_minor=to_minor(Decimal(overage_units) * rate_minor),
    )


def rate_period(usage_by_meter: Mapping[str, int], plan_meters: Iterable[PlanMeterRate]) -> list[RatedLine]:
    """Rate every plan meter for a period. Emits a line even at zero usage so an invoice explains
    every meter."""
    return [
        rate_meter(pm.meter_id, usage_by_meter.get(pm.meter_id, 0), pm.allowance, pm.rate_minor)
        for pm in plan_meters
    ]

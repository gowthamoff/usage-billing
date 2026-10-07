"""Usage reads. Always aggregated from raw usage_events (never the counters)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Sequence

from sqlalchemy import Date, cast, func, select
from sqlalchemy.orm import Session

from app.db.models import Customer, Meter, PlanMeter, UsageEvent
from app.domain.cycles import Period, current_period, to_customer_time
from app.domain.rating import rate_meter
from app.domain.thresholds import percent_used, usage_state
from app.errors import NotFound

CURRENCY = "INR"


@dataclass(frozen=True)
class MeterUsage:
    """Current-period usage, state and cost for one meter."""

    meter: str
    display_name: str
    unit: str
    used: int
    allowance: int
    remaining: int
    overage_units: int
    percent: Decimal
    state: str
    rate_minor: Decimal
    cost_minor: int


@dataclass(frozen=True)
class UsageSummary:
    """Current-period usage across every meter on the customer's plan."""

    period: Period
    timezone: str
    currency: str
    meters: list[MeterUsage]
    total_cost_minor: int


@dataclass(frozen=True)
class TimeseriesPoint:
    """Usage for one local calendar day."""

    date: date
    quantity: int


@dataclass(frozen=True)
class Timeseries:
    """Daily usage points for one meter over the current period."""

    meter: str
    bucket: str
    points: list[TimeseriesPoint]


def load_plan_meters(db: Session, plan_id: str) -> list[tuple[PlanMeter, Meter]]:
    """Return a plan's (PlanMeter, Meter) pairs ordered by meter id."""
    rows = db.execute(
        select(PlanMeter, Meter)
        .join(Meter, Meter.id == PlanMeter.meter_id)
        .where(PlanMeter.plan_id == plan_id)
        .order_by(PlanMeter.meter_id)
    ).all()
    return [(plan_meter, meter) for plan_meter, meter in rows]


def usage_by_period_and_meter(
    db: Session, customer_id: str, period_starts: Sequence[datetime], late_only: bool = False
) -> dict[tuple[datetime, str], int]:
    """Sum quantity per (billing_period_start, meter) over raw events; keys normalised to UTC."""
    if not period_starts:
        return {}
    stmt = (
        select(UsageEvent.billing_period_start, UsageEvent.meter_id, func.sum(UsageEvent.quantity))
        .where(UsageEvent.customer_id == customer_id, UsageEvent.billing_period_start.in_(period_starts))
        .group_by(UsageEvent.billing_period_start, UsageEvent.meter_id)
    )
    if late_only:
        stmt = stmt.where(UsageEvent.is_late.is_(True))
    return {
        (period_start.astimezone(timezone.utc), meter_id): int(total)
        for period_start, meter_id, total in db.execute(stmt).all()
    }


def usage_by_meter(db: Session, customer_id: str, period_start: datetime, late_only: bool = False) -> dict[str, int]:
    """Sum quantity per meter for one billing period."""
    totals = usage_by_period_and_meter(db, customer_id, [period_start], late_only)
    return {meter_id: quantity for (_, meter_id), quantity in totals.items()}


def current_usage(db: Session, customer: Customer, now: datetime) -> UsageSummary:
    """Build the customer's current-period usage summary with per-meter state and cost."""
    period = current_period(customer, now)
    used_by_meter = usage_by_meter(db, customer.id, period.start_utc)
    meters: list[MeterUsage] = []
    for plan_meter, meter in load_plan_meters(db, customer.plan_id):
        rated = rate_meter(meter.id, used_by_meter.get(meter.id, 0), plan_meter.allowance, plan_meter.overage_rate_minor)
        percent = percent_used(rated.quantity, rated.allowance)
        meters.append(
            MeterUsage(
                meter=meter.id,
                display_name=meter.display_name,
                unit=meter.unit,
                used=rated.quantity,
                allowance=rated.allowance,
                remaining=max(0, rated.allowance - rated.quantity),
                overage_units=rated.overage_units,
                percent=percent,
                state=usage_state(percent),
                rate_minor=rated.rate_minor,
                cost_minor=rated.amount_minor,
            )
        )
    return UsageSummary(
        period=period,
        timezone=customer.timezone,
        currency=CURRENCY,
        meters=meters,
        total_cost_minor=sum(m.cost_minor for m in meters),
    )


def timeseries(db: Session, customer: Customer, meter_id: str, now: datetime) -> Timeseries:
    """Return daily quantities for the current period in local dates, zero-filled up to today."""
    if meter_id not in {plan_meter.meter_id for plan_meter, _ in load_plan_meters(db, customer.plan_id)}:
        raise NotFound(f"meter {meter_id!r} is not on the customer's plan", code="unknown_meter")
    period = current_period(customer, now)
    local_day = cast(func.timezone(customer.timezone, UsageEvent.occurred_at), Date)
    rows = db.execute(
        select(local_day, func.sum(UsageEvent.quantity))
        .where(
            UsageEvent.customer_id == customer.id,
            UsageEvent.meter_id == meter_id,
            UsageEvent.billing_period_start == period.start_utc,
        )
        .group_by(local_day)
    ).all()
    totals = {day: int(quantity) for day, quantity in rows}

    first = to_customer_time(period.start_utc, customer.timezone).date()
    last = min(to_customer_time(now, customer.timezone).date(), to_customer_time(period.end_utc, customer.timezone).date() - timedelta(days=1))
    points = [
        TimeseriesPoint(date=day, quantity=totals.get(day, 0))
        for day in (first + timedelta(days=offset) for offset in range((last - first).days + 1))
    ]
    return Timeseries(meter=meter_id, bucket="day", points=points)

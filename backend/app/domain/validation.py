"""Per-event classification. Pure: callers pass plain data looked up in bulk beforehand."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Mapping

from app.domain.cycles import period_containing

INVALID_EVENT = "invalid_event"
UNKNOWN_CUSTOMER = "unknown_customer"
UNKNOWN_METER = "unknown_meter"
INVALID_QUANTITY = "invalid_quantity"
FUTURE_TIMESTAMP = "future_timestamp"
LATE_EVENT_TOO_OLD = "late_event_too_old"

_REQUIRED_FIELDS = ("event_id", "customer_id", "meter", "quantity", "occurred_at")


@dataclass(frozen=True)
class CustomerContext:
    """Customer data needed to classify an event, looked up in bulk by the caller."""

    id: str
    timezone: str
    signup_date: date
    plan_meters: Mapping[str, int]  # meter_id -> allowance
    invoiced_period_starts: frozenset[datetime]


@dataclass(frozen=True)
class ValidEvent:
    """An accepted event with its billing period resolved."""

    event_id: str
    customer_id: str
    meter_id: str
    quantity: int
    occurred_at: datetime
    billing_period_start: datetime
    is_late: bool


@dataclass(frozen=True)
class Rejection:
    """Why an event was rejected; `event_id` is None when it could not be read from the payload."""

    event_id: str | None
    code: str
    message: str


def classify_event(
    raw: Any,
    now: datetime,
    customers: Mapping[str, CustomerContext],
    future_tolerance_seconds: int = 300,
) -> ValidEvent | Rejection:
    """Validate one raw event and resolve its billing period, or explain why it is rejected."""
    if not isinstance(raw, Mapping):
        return Rejection(None, INVALID_EVENT, "event must be an object")
    event_id = raw.get("event_id")
    if not isinstance(event_id, str) or not event_id:
        return Rejection(None, INVALID_EVENT, "event_id must be a non-empty string")
    missing = [field for field in _REQUIRED_FIELDS if raw.get(field) is None]
    if missing:
        return Rejection(event_id, INVALID_EVENT, f"missing field(s): {', '.join(missing)}")

    occurred_at = _parse_timestamp(raw["occurred_at"])
    if occurred_at is None:
        return Rejection(event_id, INVALID_EVENT, "occurred_at must be an ISO 8601 datetime with a timezone offset")

    customer_id = raw["customer_id"]
    customer = customers.get(customer_id) if isinstance(customer_id, str) else None
    if customer is None:
        return Rejection(event_id, UNKNOWN_CUSTOMER, f"unknown customer {customer_id!r}")

    meter_id = raw["meter"]
    if not isinstance(meter_id, str) or meter_id not in customer.plan_meters:
        return Rejection(event_id, UNKNOWN_METER, f"meter {meter_id!r} is not priced in the customer's plan")

    quantity = raw["quantity"]
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
        return Rejection(event_id, INVALID_QUANTITY, "quantity must be a positive integer")

    if occurred_at > now + timedelta(seconds=future_tolerance_seconds):
        return Rejection(event_id, FUTURE_TIMESTAMP, f"occurred_at is more than {future_tolerance_seconds}s in the future")

    period = period_containing(customer.signup_date, customer.timezone, occurred_at)
    is_late = period.start_utc in customer.invoiced_period_starts
    if is_late:
        current = period_containing(customer.signup_date, customer.timezone, now)
        # Only the cycle just before the open one (or a force-closed open one) accepts corrections.
        if period.index < current.index - 1:
            return Rejection(event_id, LATE_EVENT_TOO_OLD, "period is already invoiced and older than the previous cycle")

    return ValidEvent(
        event_id=event_id,
        customer_id=customer.id,
        meter_id=meter_id,
        quantity=quantity,
        occurred_at=occurred_at,
        billing_period_start=period.start_utc,
        is_late=is_late,
    )


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)

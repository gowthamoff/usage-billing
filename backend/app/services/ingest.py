"""Batch ingestion: bulk lookups, pure per-event classification, bulk insert, counters, thresholds.

Everything for one batch happens in one transaction; the caller's session is committed here.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Customer, Invoice, PlanMeter, ThresholdNotification, UsageCounter, UsageEvent
from app.domain.thresholds import crossed_thresholds
from app.domain.validation import CustomerContext, Rejection, ValidEvent, classify_event

ACCEPTED = "accepted"
DUPLICATE = "duplicate"
REJECTED = "rejected"

# Keeps each multi-row INSERT well under psycopg's bound-parameter limit.
_INSERT_CHUNK = 1000

CounterKey = tuple[str, str, datetime]


@dataclass(frozen=True)
class EventError:
    """Rejection code and message for one event."""

    code: str
    message: str


@dataclass(frozen=True)
class EventResult:
    """Outcome for one event: accepted, duplicate or rejected."""

    event_id: str | None
    status: str
    is_late: bool | None = None
    error: EventError | None = None


@dataclass(frozen=True)
class BatchResult:
    """Batch totals plus one EventResult per input event, in input order."""

    received: int
    accepted: int
    duplicate: int
    rejected: int
    thresholds_fired: int
    results: list[EventResult]


def ingest_batch(db: Session, events: Sequence[Any], now: datetime | None = None) -> BatchResult:
    """Ingest one batch of raw events and commit; results are in input order."""
    now = now or datetime.now(timezone.utc)
    customers = _load_customer_contexts(db, events)

    results: dict[int, EventResult] = {}
    pending: list[tuple[int, ValidEvent]] = []
    seen: set[str] = set()
    for position, raw in enumerate(events):
        outcome = classify_event(raw, now, customers, settings.FUTURE_TOLERANCE_SECONDS)
        if isinstance(outcome, Rejection):
            results[position] = EventResult(outcome.event_id, REJECTED, error=EventError(outcome.code, outcome.message))
        elif outcome.event_id in seen:
            results[position] = EventResult(outcome.event_id, DUPLICATE)
        else:
            seen.add(outcome.event_id)
            pending.append((position, outcome))

    try:
        inserted = _insert_events(db, [event for _, event in pending], now)
        added: dict[CounterKey, int] = defaultdict(int)
        for position, event in pending:
            if event.event_id not in inserted:
                results[position] = EventResult(event.event_id, DUPLICATE)
                continue
            results[position] = EventResult(event.event_id, ACCEPTED, is_late=event.is_late or None)
            if not event.is_late:
                added[(event.customer_id, event.meter_id, event.billing_period_start)] += event.quantity
        fired = _bump_counters_and_record_thresholds(db, added, customers, now)
        db.commit()
    except Exception:
        db.rollback()
        raise

    ordered = [results[position] for position in range(len(events))]
    counts = Counter(result.status for result in ordered)
    return BatchResult(
        received=len(events),
        accepted=counts[ACCEPTED],
        duplicate=counts[DUPLICATE],
        rejected=counts[REJECTED],
        thresholds_fired=fired,
        results=ordered,
    )


def _load_customer_contexts(db: Session, events: Sequence[Any]) -> dict[str, CustomerContext]:
    ids = {
        raw.get("customer_id")
        for raw in events
        if isinstance(raw, Mapping) and isinstance(raw.get("customer_id"), str)
    }
    if not ids:
        return {}

    anchors: dict[str, tuple[str, date]] = {}
    plan_meters: dict[str, dict[str, int]] = defaultdict(dict)
    customer_rows = db.execute(
        select(Customer.id, Customer.timezone, Customer.signup_date, PlanMeter.meter_id, PlanMeter.allowance)
        .outerjoin(PlanMeter, PlanMeter.plan_id == Customer.plan_id)
        .where(Customer.id.in_(ids))
    ).all()
    for customer_id, tz, signup_date, meter_id, allowance in customer_rows:
        anchors[customer_id] = (tz, signup_date)
        if meter_id is not None:
            plan_meters[customer_id][meter_id] = allowance
    if not anchors:
        return {}

    invoiced: dict[str, set[datetime]] = defaultdict(set)
    invoice_rows = db.execute(
        select(Invoice.customer_id, Invoice.period_start).where(Invoice.customer_id.in_(list(anchors)))
    ).all()
    for customer_id, period_start in invoice_rows:
        invoiced[customer_id].add(period_start.astimezone(timezone.utc))

    return {
        customer_id: CustomerContext(
            id=customer_id,
            timezone=tz,
            signup_date=signup_date,
            plan_meters=dict(plan_meters[customer_id]),
            invoiced_period_starts=frozenset(invoiced[customer_id]),
        )
        for customer_id, (tz, signup_date) in anchors.items()
    }


def _insert_events(db: Session, events: Sequence[ValidEvent], now: datetime) -> set[str]:
    """First write wins: returns the ids actually inserted; the rest already existed."""
    inserted: set[str] = set()
    for start in range(0, len(events), _INSERT_CHUNK):
        chunk = events[start : start + _INSERT_CHUNK]
        stmt = (
            insert(UsageEvent)
            .values(
                [
                    {
                        "event_id": e.event_id,
                        "customer_id": e.customer_id,
                        "meter_id": e.meter_id,
                        "quantity": e.quantity,
                        "occurred_at": e.occurred_at,
                        "received_at": now,
                        "billing_period_start": e.billing_period_start,
                        "is_late": e.is_late,
                    }
                    for e in chunk
                ]
            )
            .on_conflict_do_nothing(index_elements=["event_id"])
            .returning(UsageEvent.event_id)
        )
        inserted.update(db.scalars(stmt).all())
    return inserted


def _bump_counters_and_record_thresholds(
    db: Session,
    added: Mapping[CounterKey, int],
    customers: Mapping[str, CustomerContext],
    now: datetime,
) -> int:
    if not added:
        return 0
    counters = insert(UsageCounter).values(
        [
            {"customer_id": customer_id, "meter_id": meter_id, "period_start": period_start, "quantity": quantity}
            for (customer_id, meter_id, period_start), quantity in added.items()
        ]
    )
    counters = counters.on_conflict_do_update(
        index_elements=["customer_id", "meter_id", "period_start"],
        set_={"quantity": UsageCounter.quantity + counters.excluded.quantity},
    ).returning(UsageCounter.customer_id, UsageCounter.meter_id, UsageCounter.period_start, UsageCounter.quantity)

    notifications: list[dict[str, Any]] = []
    for customer_id, meter_id, period_start, after in db.execute(counters).all():
        key = (customer_id, meter_id, period_start.astimezone(timezone.utc))
        before = after - added[key]
        allowance = customers[customer_id].plan_meters[meter_id]
        for threshold in crossed_thresholds(before, after, allowance, settings.THRESHOLDS):
            notifications.append(
                {
                    "customer_id": customer_id,
                    "meter_id": meter_id,
                    "period_start": key[2],
                    "threshold": threshold,
                    "usage_at_fire": after,
                    "allowance": allowance,
                    "created_at": now,
                    "next_attempt_at": now,
                }
            )
    if not notifications:
        return 0
    # Count via RETURNING: rowcount is -1 for this statement under psycopg 3.
    inserted = db.execute(
        insert(ThresholdNotification)
        .values(notifications)
        .on_conflict_do_nothing(index_elements=["customer_id", "meter_id", "period_start", "threshold"])
        .returning(ThresholdNotification.id)
    ).all()
    return len(inserted)

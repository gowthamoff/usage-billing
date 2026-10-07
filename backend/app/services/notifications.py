"""Threshold notification reads and the outbox delivery step used by the worker."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Customer, ThresholdNotification


@dataclass(frozen=True)
class DeliveryStats:
    """Outcome counts for one delivery pass."""

    sent: int
    failed: int


def list_notifications(db: Session, customer: Customer, period_start: datetime | None) -> list[ThresholdNotification]:
    """Return a customer's notifications newest first, optionally limited to one period."""
    stmt = select(ThresholdNotification).where(ThresholdNotification.customer_id == customer.id)
    if period_start is not None:
        stmt = stmt.where(ThresholdNotification.period_start == period_start)
    stmt = stmt.order_by(ThresholdNotification.created_at.desc(), ThresholdNotification.id.desc())
    return list(db.scalars(stmt).all())


def webhook_payload(notification: ThresholdNotification) -> dict[str, Any]:
    """Build the JSON body posted to the webhook for one notification."""
    return {
        "customer_id": notification.customer_id,
        "meter": notification.meter_id,
        "threshold": notification.threshold,
        "usage": notification.usage_at_fire,
        "allowance": notification.allowance,
        "period_start": notification.period_start.isoformat(),
        "fired_at": notification.created_at.isoformat(),
    }


def deliver_pending(
    db: Session,
    http: httpx.Client,
    webhook_url: str,
    now: datetime,
    max_attempts: int = 8,
    limit: int = 100,
) -> DeliveryStats:
    """POST unsent rows that are due; backoff 2^attempts seconds, give up after max_attempts."""
    pending = db.scalars(
        select(ThresholdNotification)
        .where(
            ThresholdNotification.sent_at.is_(None),
            ThresholdNotification.attempts < max_attempts,
            ThresholdNotification.next_attempt_at <= now,
        )
        .order_by(ThresholdNotification.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
    ).all()

    sent = failed = 0
    for notification in pending:
        try:
            response = http.post(webhook_url, json=webhook_payload(notification))
            response.raise_for_status()
            notification.sent_at = now
            notification.last_error = None
            sent += 1
        except Exception as exc:  # any delivery failure is recorded and retried, never raised
            notification.attempts += 1
            notification.last_error = f"{type(exc).__name__}: {exc}"[:500]
            notification.next_attempt_at = now + timedelta(seconds=2**notification.attempts)
            failed += 1
    db.commit()
    return DeliveryStats(sent=sent, failed=failed)

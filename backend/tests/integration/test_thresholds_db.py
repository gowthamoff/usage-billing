"""Proves threshold notifications fire exactly once per customer, meter, cycle and threshold."""

from datetime import datetime, timezone

from sqlalchemy import select

from app.db.models import ThresholdNotification
from app.services.ingest import ingest_batch
from tests.integration.conftest import events

NOW = datetime(2026, 3, 1, tzinfo=timezone.utc)


def fired(db) -> list[tuple[int, int]]:
    rows = db.scalars(select(ThresholdNotification).order_by(ThresholdNotification.threshold)).all()
    return [(n.threshold, n.usage_at_fire) for n in rows]


def test_80_and_100_fire_exactly_once_across_many_batches(db):
    # cus_asha / basic: api_calls allowance 10,000
    first = ingest_batch(db, events("b1", 30, quantity=100), NOW)  # 3,000
    assert first.thresholds_fired == 0 and fired(db) == []

    ingest_batch(db, events("b2", 30, quantity=100), NOW)  # 6,000 -> 50 %
    assert fired(db) == [(50, 6000)]

    ingest_batch(db, events("b3", 30, quantity=100), NOW)  # 9,000 -> 80 %
    assert fired(db) == [(50, 6000), (80, 9000)]

    ingest_batch(db, events("b4", 20, quantity=100), NOW)  # 11,000 -> 100 %
    assert fired(db) == [(50, 6000), (80, 9000), (100, 11000)]

    ingest_batch(db, events("b5", 10, quantity=100), NOW)  # 12,000: nothing new
    ingest_batch(db, events("b2", 30, quantity=100), NOW)  # replayed batch: duplicates, nothing new
    assert fired(db) == [(50, 6000), (80, 9000), (100, 11000)]

    rows = db.scalars(select(ThresholdNotification)).all()
    assert all(n.sent_at is None and n.attempts == 0 and n.allowance == 10000 for n in rows)


def test_thresholds_are_per_customer_meter_and_cycle(db):
    ingest_batch(db, events("asha_feb", 1, quantity=10000, occurred_at="2026-02-20T10:00:00Z"), NOW)
    ingest_batch(db, events("asha_jan", 1, quantity=10000, occurred_at="2026-01-20T10:00:00Z"), NOW)
    ingest_batch(db, events("asha_storage", 1, meter="storage_gb", quantity=6), NOW)
    ingest_batch(db, events("ravi", 1, customer_id="cus_ravi", quantity=50000), NOW)

    rows = db.scalars(select(ThresholdNotification)).all()
    keyed = sorted((n.customer_id, n.meter_id, n.period_start.astimezone(timezone.utc).date().isoformat(), n.threshold) for n in rows)
    assert keyed == [
        ("cus_asha", "api_calls", "2026-01-09", 50),
        ("cus_asha", "api_calls", "2026-01-09", 80),
        ("cus_asha", "api_calls", "2026-01-09", 100),
        ("cus_asha", "api_calls", "2026-02-09", 50),
        ("cus_asha", "api_calls", "2026-02-09", 80),
        ("cus_asha", "api_calls", "2026-02-09", 100),
        ("cus_asha", "storage_gb", "2026-02-09", 50),
        ("cus_ravi", "api_calls", "2026-01-30", 50),
    ]

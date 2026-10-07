"""Proves counters rebuilt from usage_events equal the live counters, with late events excluded."""

from datetime import datetime, timezone

from sqlalchemy import select

from app.db.models import Customer, UsageCounter
from app.domain.cycles import period_by_index
from app.services.counters import rebuild_counters
from app.services.ingest import ingest_batch
from app.services.invoicing import close_cycle
from tests.integration.conftest import event, events

UTC = timezone.utc
MARCH_15 = datetime(2026, 3, 15, tzinfo=UTC)


def snapshot(db) -> list[tuple]:
    rows = db.execute(
        select(UsageCounter.customer_id, UsageCounter.meter_id, UsageCounter.period_start, UsageCounter.quantity)
    ).all()
    return sorted((c, m, p.astimezone(UTC), int(q)) for c, m, p, q in rows)


def test_rebuild_counters_equals_live_counters(db):
    ingest_batch(db, events("asha_feb", 40, quantity=7, occurred_at="2026-02-20T10:00:00Z"), MARCH_15)
    ingest_batch(db, events("asha_jan", 10, quantity=3, occurred_at="2026-01-20T10:00:00Z"), MARCH_15)
    ingest_batch(db, events("asha_storage", 4, meter="storage_gb", quantity=2, occurred_at="2026-02-20T10:00:00Z"), MARCH_15)
    ingest_batch(db, events("ravi", 25, customer_id="cus_ravi", quantity=11, occurred_at="2026-02-20T10:00:00Z"), MARCH_15)
    ingest_batch(db, events("noor", 5, customer_id="cus_noor", quantity=1, occurred_at="2026-03-01T10:00:00Z"), MARCH_15)
    ingest_batch(db, events("asha_feb", 40, quantity=7, occurred_at="2026-02-20T10:00:00Z"), MARCH_15)  # replay

    # A late event for an invoiced cycle is stored but excluded from counters, live and rebuilt.
    asha = db.get(Customer, "cus_asha")
    close_cycle(db, asha, period_by_index(asha.signup_date, asha.timezone, 1), MARCH_15)
    late = ingest_batch(db, [event("evt_late", quantity=1000, occurred_at="2026-03-01T10:00:00Z")], datetime(2026, 3, 20, tzinfo=UTC))
    assert late.results[0].is_late is True

    live = snapshot(db)
    assert len(live) == 5
    assert ("cus_asha", "api_calls", period_by_index(asha.signup_date, asha.timezone, 1).start_utc, 280) in live

    rows = rebuild_counters(db)
    assert rows == 5
    assert snapshot(db) == live


def test_rebuild_route_reports_row_count(client, db):
    ingest_batch(db, events("x", 3, occurred_at="2026-02-20T10:00:00Z"), MARCH_15)
    response = client.post("/api/v1/admin/counters/rebuild")
    assert response.status_code == 200
    assert response.json() == {"rows": 1}

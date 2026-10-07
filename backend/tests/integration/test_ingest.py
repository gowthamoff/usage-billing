"""Proves batch ingest is idempotent, buckets by local cycle and maps outcomes to HTTP codes."""

from datetime import datetime, timezone

from sqlalchemy import func, select

from app.config import settings
from app.db.models import UsageCounter, UsageEvent
from app.services.ingest import ingest_batch
from tests.integration.conftest import event, events

UTC = timezone.utc
NOW = datetime(2026, 3, 1, tzinfo=UTC)


def counters(db) -> list[tuple]:
    rows = db.execute(
        select(UsageCounter.customer_id, UsageCounter.meter_id, UsageCounter.period_start, UsageCounter.quantity)
    ).all()
    return sorted((c, m, p.astimezone(UTC), q) for c, m, p, q in rows)


def event_sum(db) -> int:
    return int(db.scalar(select(func.coalesce(func.sum(UsageEvent.quantity), 0))))


def test_reingesting_the_same_batch_does_not_move_the_numbers(db):
    batch = events("a", 50, quantity=3)

    first = ingest_batch(db, batch, NOW)
    assert (first.accepted, first.duplicate, first.rejected) == (50, 0, 0)
    counters_after_first = counters(db)
    sum_after_first = event_sum(db)
    assert sum_after_first == 150

    second = ingest_batch(db, batch, NOW)
    assert (second.accepted, second.duplicate, second.rejected) == (0, 50, 0)
    assert all(result.status == "duplicate" for result in second.results)
    assert counters(db) == counters_after_first
    assert event_sum(db) == sum_after_first


def test_duplicate_with_a_different_payload_is_still_a_duplicate_and_first_write_wins(db):
    ingest_batch(db, [event("evt_x", quantity=2)], NOW)
    result = ingest_batch(db, [event("evt_x", quantity=99)], NOW)
    assert result.results[0].status == "duplicate"
    assert db.get(UsageEvent, "evt_x").quantity == 2


def test_in_batch_duplicate_is_counted_once(db):
    batch = [event("evt_dup", quantity=5), event("evt_dup", quantity=5), event("evt_other", quantity=1)]
    result = ingest_batch(db, batch, NOW)
    assert [r.status for r in result.results] == ["accepted", "duplicate", "accepted"]
    assert (result.accepted, result.duplicate) == (2, 1)
    assert event_sum(db) == 6
    assert counters(db)[0][3] == 6


def test_retry_after_partial_delivery_only_inserts_the_missing_events(db):
    ingest_batch(db, [event("evt_1"), event("evt_2")], NOW)
    retry = ingest_batch(db, [event("evt_1"), event("evt_2"), event("evt_3")], NOW)
    assert [r.status for r in retry.results] == ["duplicate", "duplicate", "accepted"]
    assert event_sum(db) == 3
    assert counters(db)[0][3] == 3


def test_kolkata_event_in_utc_evening_belongs_to_the_next_local_day_cycle(db):
    # cus_asha: Asia/Kolkata, signup day 10 -> cycle starts 10 Feb 00:00 IST = 09 Feb 18:30 UTC
    result = ingest_batch(db, [event("evt_boundary", occurred_at="2026-02-09T20:00:00Z")], NOW)
    assert result.results[0].status == "accepted"
    stored = db.get(UsageEvent, "evt_boundary")
    assert stored.billing_period_start.astimezone(UTC) == datetime(2026, 2, 9, 18, 30, tzinfo=UTC)

    ingest_batch(db, [event("evt_before", occurred_at="2026-02-09T18:00:00Z")], NOW)
    assert db.get(UsageEvent, "evt_before").billing_period_start.astimezone(UTC) == datetime(2026, 1, 9, 18, 30, tzinfo=UTC)
    assert [(c, m, p) for c, m, p, _ in counters(db)] == [
        ("cus_asha", "api_calls", datetime(2026, 1, 9, 18, 30, tzinfo=UTC)),
        ("cus_asha", "api_calls", datetime(2026, 2, 9, 18, 30, tzinfo=UTC)),
    ]


def test_mixed_batch_returns_207_with_per_event_errors(client, db):
    batch = [
        event("evt_ok"),
        event("evt_unknown_customer", customer_id="cus_nobody"),
        event("evt_unknown_meter", meter="emails"),
        event("evt_bad_qty", quantity=0),
        event("evt_future", occurred_at="2999-01-01T00:00:00Z"),
        {"customer_id": "cus_asha"},
        event("evt_ok"),
    ]
    response = client.post("/api/v1/events/batch", json={"events": batch})
    assert response.status_code == 207
    body = response.json()
    assert body["summary"] == {"received": 7, "accepted": 1, "duplicate": 1, "rejected": 5}
    statuses = [(r["status"], r.get("error", {}).get("code")) for r in body["results"]]
    assert statuses == [
        ("accepted", None),
        ("rejected", "unknown_customer"),
        ("rejected", "unknown_meter"),
        ("rejected", "invalid_quantity"),
        ("rejected", "future_timestamp"),
        ("rejected", "invalid_event"),
        ("duplicate", None),
    ]
    assert "is_late" not in body["results"][0] and "error" not in body["results"][0]
    assert body["results"][5]["event_id"] is None
    assert event_sum(db) == 1


def test_clean_batch_returns_200(client):
    response = client.post("/api/v1/events/batch", json={"events": events("clean", 3)})
    assert response.status_code == 200
    assert response.json()["summary"] == {"received": 3, "accepted": 3, "duplicate": 0, "rejected": 0}


def test_oversized_batch_returns_413(client):
    response = client.post("/api/v1/events/batch", json={"events": events("big", settings.MAX_BATCH_SIZE + 1)})
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "batch_too_large"


def test_malformed_envelope_returns_400(client):
    response = client.post("/api/v1/events/batch", json={"items": []})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"
    assert response.json()["error"]["details"]


def test_missing_api_key_returns_401(client):
    response = client.post("/api/v1/events/batch", json={"events": []}, headers={"X-API-Key": ""})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
    assert client.get("/health").status_code == 200

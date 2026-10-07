"""Proves cycle close issues one invoice per cycle and bills late usage as later adjustments."""

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from app.db.models import Customer, Invoice, InvoiceLine, UsageCounter
from app.domain.cycles import current_period, period_by_index
from app.services.ingest import ingest_batch
from app.services.invoicing import close_cycle, close_due
from tests.integration.conftest import event, events

UTC = timezone.utc
ASHA = (date(2026, 1, 10), "Asia/Kolkata")
PERIOD_1 = period_by_index(*ASHA, 1)  # 10 Feb - 10 Mar 2026 IST
PERIOD_2 = period_by_index(*ASHA, 2)  # 10 Mar - 10 Apr 2026 IST
PERIOD_3 = period_by_index(*ASHA, 3)  # 10 Apr - 10 May 2026 IST
IN_PERIOD_1 = "2026-02-20T10:00:00Z"
MARCH_15 = datetime(2026, 3, 15, tzinfo=UTC)
APRIL_15 = datetime(2026, 4, 15, tzinfo=UTC)
MAY_15 = datetime(2026, 5, 15, tzinfo=UTC)


def asha(db) -> Customer:
    return db.get(Customer, "cus_asha")


def lines_of(db, invoice_id: str) -> list[InvoiceLine]:
    return list(db.scalars(select(InvoiceLine).where(InvoiceLine.invoice_id == invoice_id).order_by(InvoiceLine.id)))


def test_closing_twice_yields_one_invoice_with_the_same_id(db):
    ingest_batch(db, events("p1", 12, quantity=1000, occurred_at=IN_PERIOD_1), MARCH_15)

    first, created = close_cycle(db, asha(db), PERIOD_1, MARCH_15)
    assert created is True
    second, created_again = close_cycle(db, asha(db), PERIOD_1, MARCH_15)
    assert created_again is False
    assert second.id == first.id
    assert first.id.startswith("inv_") and len(first.id) == 16
    assert db.scalar(select(Invoice.id).where(Invoice.customer_id == "cus_asha")) == first.id
    assert len(db.scalars(select(Invoice)).all()) == 1


def test_usage_lines_explain_the_amount_for_every_plan_meter(db):
    ingest_batch(db, events("p1", 12, quantity=1000, occurred_at=IN_PERIOD_1), MARCH_15)
    invoice, _ = close_cycle(db, asha(db), PERIOD_1, MARCH_15)

    lines = lines_of(db, invoice.id)
    assert [(l.line_type, l.meter_id) for l in lines] == [("usage", "api_calls"), ("usage", "storage_gb")]
    api = lines[0]
    assert (api.quantity, api.allowance, api.overage_units) == (12000, 10000, 2000)
    assert api.rate_minor == Decimal("50.000000")
    assert api.amount_minor == 100_000
    assert api.period_start.astimezone(UTC) == PERIOD_1.start_utc
    assert api.period_end.astimezone(UTC) == PERIOD_1.end_utc
    assert api.adjusts_invoice_id is None
    assert "12,000 call used, 10,000 included, 2,000 over allowance × ₹0.50 = ₹1,000.00" in api.description
    storage = lines[1]
    assert (storage.quantity, storage.allowance, storage.overage_units, storage.amount_minor) == (0, 10, 0, 0)
    assert invoice.total_minor == 100_000
    assert invoice.currency == "INR" and invoice.status == "issued"


def test_late_event_adds_an_adjustment_line_with_the_delta_on_the_next_invoice(db):
    ingest_batch(db, events("p1", 12, quantity=1000, occurred_at=IN_PERIOD_1), MARCH_15)
    first, _ = close_cycle(db, asha(db), PERIOD_1, MARCH_15)
    counters_before = db.execute(select(UsageCounter.quantity).where(UsageCounter.period_start == PERIOD_1.start_utc)).all()

    late = ingest_batch(db, [event("evt_late", quantity=500, occurred_at="2026-03-01T10:00:00Z")], datetime(2026, 3, 20, tzinfo=UTC))
    assert late.results[0].status == "accepted" and late.results[0].is_late is True
    assert late.thresholds_fired == 0
    counters_after = db.execute(select(UsageCounter.quantity).where(UsageCounter.period_start == PERIOD_1.start_utc)).all()
    assert counters_after == counters_before  # late events never touch the counters

    second, created = close_cycle(db, asha(db), PERIOD_2, APRIL_15)
    assert created is True
    lines = lines_of(db, second.id)
    assert [(l.line_type, l.meter_id) for l in lines] == [
        ("usage", "api_calls"),
        ("usage", "storage_gb"),
        ("adjustment", "api_calls"),
    ]
    adjustment = lines[2]
    assert adjustment.adjusts_invoice_id == first.id
    assert adjustment.quantity == 500
    assert adjustment.overage_units == 500
    assert adjustment.amount_minor == 25_000  # (12,500 - 10,000) x 50 - 100,000 already billed
    assert adjustment.period_start.astimezone(UTC) == PERIOD_1.start_utc
    assert adjustment.description == f"Late usage for 10 Feb – 09 Mar 2026 (received after invoice {first.id})"
    assert second.total_minor == 25_000

    # A later close re-rates period 1 again and finds nothing left to bill.
    third, _ = close_cycle(db, asha(db), PERIOD_3, MAY_15)
    assert [l.line_type for l in lines_of(db, third.id)] == ["usage", "usage"]
    assert third.total_minor == 0


def test_late_usage_that_stays_within_the_allowance_adds_no_adjustment(db):
    ingest_batch(db, events("p1", 5, quantity=1000, occurred_at=IN_PERIOD_1), MARCH_15)
    close_cycle(db, asha(db), PERIOD_1, MARCH_15)
    ingest_batch(db, [event("evt_late", quantity=500, occurred_at="2026-03-01T10:00:00Z")], datetime(2026, 3, 20, tzinfo=UTC))

    second, _ = close_cycle(db, asha(db), PERIOD_2, APRIL_15)
    assert [l.line_type for l in lines_of(db, second.id)] == ["usage", "usage"]
    assert second.total_minor == 0


def test_too_old_late_event_is_rejected(db):
    close_cycle(db, asha(db), PERIOD_1, MARCH_15)
    close_cycle(db, asha(db), PERIOD_2, APRIL_15)

    result = ingest_batch(
        db,
        [
            event("evt_too_old", occurred_at="2026-03-01T10:00:00Z"),  # period 1, two cycles back
            event("evt_still_ok", occurred_at="2026-03-15T10:00:00Z"),  # period 2, just before current
        ],
        APRIL_15,
    )
    assert result.results[0].status == "rejected"
    assert result.results[0].error.code == "late_event_too_old"
    assert result.results[1].status == "accepted" and result.results[1].is_late is True


def test_close_due_invoices_the_last_ended_cycle_of_every_customer_once(db):
    now = datetime(2026, 4, 15, tzinfo=UTC)
    closed = close_due(db, now)
    assert sorted(c.customer_id for c in closed) == ["cus_asha", "cus_kai", "cus_lee", "cus_noor", "cus_ravi"]
    for item in closed:
        customer = db.get(Customer, item.customer_id)
        previous = period_by_index(customer.signup_date, customer.timezone, current_period(customer, now).index - 1)
        assert item.period_start.astimezone(UTC) == previous.start_utc
    assert close_due(db, now) == []
    assert len(db.scalars(select(Invoice)).all()) == 5


def test_close_route_force_closes_current_cycle_then_returns_existing(client, db):
    created = client.post("/api/v1/customers/cus_asha/cycles/close", json={"force": True})
    assert created.status_code == 201
    body = created.json()
    assert body["currency"] == "INR" and body["period_start_local"].endswith("+05:30")

    again = client.post("/api/v1/customers/cus_asha/cycles/close", json={"force": True})
    assert again.status_code == 200
    assert again.json()["id"] == body["id"]

    detail = client.get(f"/api/v1/invoices/{body['id']}")
    assert detail.status_code == 200
    assert [line["meter"] for line in detail.json()["lines"]] == ["api_calls", "storage_gb"]
    assert detail.json()["lines"][0]["display_name"] == "API calls"

    listed = client.get("/api/v1/customers/cus_asha/invoices")
    assert [inv["id"] for inv in listed.json()] == [body["id"]]


def test_close_route_rejects_a_cycle_that_has_not_ended(client, db):
    current = current_period(asha(db), datetime.now(UTC))
    response = client.post(
        "/api/v1/customers/cus_asha/cycles/close", json={"period_start": current.start_utc.isoformat()}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "cycle_not_ended"

    misaligned = client.post("/api/v1/customers/cus_asha/cycles/close", json={"period_start": "2026-02-01T00:00:00Z"})
    assert misaligned.status_code == 400
    assert misaligned.json()["error"]["code"] == "invalid_period_start"


def test_close_route_default_closes_the_most_recently_ended_cycle(client, db):
    response = client.post("/api/v1/customers/cus_asha/cycles/close", json={})
    assert response.status_code == 201
    customer = asha(db)
    expected = period_by_index(customer.signup_date, customer.timezone, current_period(customer, datetime.now(UTC)).index - 1)
    assert datetime.fromisoformat(response.json()["period_start"]) == expected.start_utc

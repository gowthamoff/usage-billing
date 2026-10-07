"""Proves per-event classification: rejection codes, cycle assignment and late-event rules."""

from datetime import date, datetime, timedelta, timezone

import pytest

from app.domain.cycles import period_by_index
from app.domain.validation import (
    FUTURE_TIMESTAMP,
    INVALID_EVENT,
    INVALID_QUANTITY,
    LATE_EVENT_TOO_OLD,
    UNKNOWN_CUSTOMER,
    UNKNOWN_METER,
    CustomerContext,
    Rejection,
    ValidEvent,
    classify_event,
)

UTC = timezone.utc
SIGNUP = date(2026, 1, 10)
TZ = "Asia/Kolkata"
NOW = datetime(2026, 3, 20, 12, 0, tzinfo=UTC)  # inside cycle index 2 (10 Mar - 10 Apr IST)


def context(invoiced_indexes: tuple[int, ...] = ()) -> dict[str, CustomerContext]:
    return {
        "cus_asha": CustomerContext(
            id="cus_asha",
            timezone=TZ,
            signup_date=SIGNUP,
            plan_meters={"api_calls": 10000, "storage_gb": 10},
            invoiced_period_starts=frozenset(period_by_index(SIGNUP, TZ, n).start_utc for n in invoiced_indexes),
        )
    }


def event(**overrides):
    base = {
        "event_id": "evt_1",
        "customer_id": "cus_asha",
        "meter": "api_calls",
        "quantity": 3,
        "occurred_at": "2026-03-15T10:00:00Z",
    }
    return {**base, **overrides}


def test_valid_event_gets_its_billing_period():
    result = classify_event(event(), NOW, context())
    assert isinstance(result, ValidEvent)
    assert result.billing_period_start == period_by_index(SIGNUP, TZ, 2).start_utc
    assert result.is_late is False
    assert result.occurred_at == datetime(2026, 3, 15, 10, 0, tzinfo=UTC)


def test_unknown_customer():
    result = classify_event(event(customer_id="cus_nobody"), NOW, context())
    assert isinstance(result, Rejection) and result.code == UNKNOWN_CUSTOMER
    assert result.event_id == "evt_1"


def test_unknown_meter_includes_meters_not_priced_in_the_plan():
    result = classify_event(event(meter="emails_sent"), NOW, context())
    assert isinstance(result, Rejection) and result.code == UNKNOWN_METER


@pytest.mark.parametrize("quantity", [0, -1, 1.5, "3", True, None])
def test_invalid_quantity(quantity):
    result = classify_event(event(quantity=quantity), NOW, context())
    assert isinstance(result, Rejection)
    assert result.code in (INVALID_QUANTITY, INVALID_EVENT)


def test_future_timestamp_beyond_tolerance_is_rejected_but_within_tolerance_is_accepted():
    at_edge = (NOW + timedelta(seconds=300)).isoformat()
    assert isinstance(classify_event(event(occurred_at=at_edge), NOW, context(), 300), ValidEvent)
    just_over = (NOW + timedelta(seconds=301)).isoformat()
    result = classify_event(event(occurred_at=just_over), NOW, context(), 300)
    assert isinstance(result, Rejection) and result.code == FUTURE_TIMESTAMP
    assert isinstance(classify_event(event(occurred_at=just_over), NOW, context(), 600), ValidEvent)


@pytest.mark.parametrize(
    "raw",
    [
        "not an object",
        {},
        event(event_id=None),
        event(event_id=""),
        event(event_id=42),
        event(occurred_at="yesterday"),
        event(occurred_at="2026-03-15T10:00:00"),  # naive, no offset
        event(occurred_at=1700000000),
    ],
)
def test_shape_errors_are_invalid_event(raw):
    result = classify_event(raw, NOW, context())
    assert isinstance(result, Rejection) and result.code == INVALID_EVENT


def test_late_event_for_the_cycle_just_before_the_current_one_is_accepted_as_late():
    result = classify_event(event(occurred_at="2026-03-01T10:00:00Z"), NOW, context(invoiced_indexes=(1,)))
    assert isinstance(result, ValidEvent)
    assert result.is_late is True
    assert result.billing_period_start == period_by_index(SIGNUP, TZ, 1).start_utc


def test_late_event_for_an_older_invoiced_cycle_is_rejected():
    result = classify_event(event(occurred_at="2026-01-20T10:00:00Z"), NOW, context(invoiced_indexes=(0, 1)))
    assert isinstance(result, Rejection) and result.code == LATE_EVENT_TOO_OLD


def test_old_event_for_an_uninvoiced_cycle_is_a_normal_event():
    result = classify_event(event(occurred_at="2026-01-20T10:00:00Z"), NOW, context(invoiced_indexes=(1,)))
    assert isinstance(result, ValidEvent)
    assert result.is_late is False
    assert result.billing_period_start == period_by_index(SIGNUP, TZ, 0).start_utc


def test_event_for_a_force_closed_current_cycle_is_late_not_rejected():
    result = classify_event(event(), NOW, context(invoiced_indexes=(2,)))
    assert isinstance(result, ValidEvent) and result.is_late is True

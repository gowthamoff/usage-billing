"""Proves billing cycles anchor to local signup midnight with no drift across months or DST."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import pytest

from app.domain.cycles import (
    add_months_clamped,
    current_period,
    format_period_label,
    next_period,
    period_by_index,
    period_containing,
    period_index_at,
    previous_period,
    to_customer_time,
)

UTC = timezone.utc


@dataclass(frozen=True)
class Anchor:
    signup_date: date
    timezone: str


def test_add_months_clamped_to_last_day_without_drift():
    signup = date(2026, 1, 31)
    assert add_months_clamped(signup, 1) == date(2026, 2, 28)
    assert add_months_clamped(signup, 2) == date(2026, 3, 31)
    assert add_months_clamped(signup, 3) == date(2026, 4, 30)
    assert add_months_clamped(signup, 12) == date(2027, 1, 31)
    assert add_months_clamped(signup, 13) == date(2027, 2, 28)
    assert add_months_clamped(date(2026, 3, 15), -1) == date(2026, 2, 15)


def test_cycle_starts_never_drift_for_day_31_signup():
    starts = [period_by_index(date(2026, 1, 31), "UTC", n).start_utc.date() for n in range(4)]
    assert starts == [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)]


def test_kolkata_boundary_event_in_utc_evening_belongs_to_next_local_cycle():
    """10 Feb 00:00 IST is 09 Feb 18:30Z, so 20:00Z on 09 Feb is already in the next cycle."""
    signup, tz = date(2026, 1, 10), "Asia/Kolkata"
    period = period_containing(signup, tz, datetime(2026, 2, 9, 20, 0, tzinfo=UTC))
    assert period.index == 1
    assert period.start_utc == datetime(2026, 2, 9, 18, 30, tzinfo=UTC)
    assert period.end_utc == datetime(2026, 3, 9, 18, 30, tzinfo=UTC)

    before_midnight = period_containing(signup, tz, datetime(2026, 2, 9, 18, 0, tzinfo=UTC))
    assert before_midnight.index == 0
    assert before_midnight.end_utc == period.start_utc


def test_new_york_dst_cycles_are_23_or_25_hours_off_a_whole_number_of_days():
    signup, tz = date(2026, 2, 15), "America/New_York"
    spring = period_by_index(signup, tz, 0)  # contains 8 Mar 2026, clocks go forward
    assert spring.end_utc - spring.start_utc == timedelta(days=28) - timedelta(hours=1)
    autumn = period_by_index(signup, tz, 8)  # contains 1 Nov 2026, clocks go back
    assert autumn.end_utc - autumn.start_utc == timedelta(days=31) + timedelta(hours=1)
    assert to_customer_time(spring.start_utc, tz).hour == 0
    assert to_customer_time(spring.end_utc, tz).hour == 0


@pytest.mark.parametrize(
    "at",
    [
        datetime(2026, 1, 10, 0, 0, tzinfo=UTC),
        datetime(2026, 2, 9, 18, 29, 59, tzinfo=UTC),
        datetime(2026, 2, 9, 18, 30, tzinfo=UTC),
        datetime(2026, 7, 1, 12, 0, tzinfo=UTC),
        datetime(2025, 12, 1, 12, 0, tzinfo=UTC),
    ],
)
def test_period_containing_brackets_the_instant(at):
    period = period_containing(date(2026, 1, 10), "Asia/Kolkata", at)
    assert period.start_utc <= at < period.end_utc


def test_period_index_at_requires_aware_datetime():
    with pytest.raises(ValueError):
        period_index_at(date(2026, 1, 10), "UTC", datetime(2026, 2, 1))


def test_previous_next_and_current_period():
    anchor = Anchor(date(2026, 1, 10), "Asia/Kolkata")
    now = datetime(2026, 3, 20, tzinfo=UTC)
    current = current_period(anchor, now)
    assert current.index == 2
    assert previous_period(anchor.signup_date, anchor.timezone, current).index == 1
    assert previous_period(anchor.signup_date, anchor.timezone, current).end_utc == current.start_utc
    assert next_period(anchor.signup_date, anchor.timezone, current).start_utc == current.end_utc


def test_format_period_label_uses_inclusive_local_dates():
    period = period_by_index(date(2026, 1, 10), "Asia/Kolkata", 0)
    assert format_period_label(period.start_utc, period.end_utc, "Asia/Kolkata") == "10 Jan – 09 Feb 2026"
    december = period_by_index(date(2025, 12, 10), "Asia/Kolkata", 0)
    assert format_period_label(december.start_utc, december.end_utc, "Asia/Kolkata") == "10 Dec 2025 – 09 Jan 2026"

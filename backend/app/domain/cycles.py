"""Monthly billing cycles anchored to the signup day, bounded by the customer's local midnight."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Protocol
from zoneinfo import ZoneInfo

UTC = timezone.utc


class CycleAnchor(Protocol):
    """Anything with a signup date and timezone, such as a Customer row."""

    signup_date: date
    timezone: str


@dataclass(frozen=True)
class Period:
    """One billing cycle, half-open: [start_utc, end_utc)."""

    index: int
    start_utc: datetime
    end_utc: datetime


def add_months_clamped(day: date, months: int) -> date:
    """Add calendar months to `day`, clamping to the target month's last day.

    Always called with the original signup date, never with a previous (possibly clamped)
    boundary, so 31 Jan -> 28 Feb -> 31 Mar -> 30 Apr: clamping never accumulates.
    """
    total = day.year * 12 + (day.month - 1) + months
    year, month_zero = divmod(total, 12)
    month = month_zero + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def period_start_utc(signup_date: date, tz: str, index: int) -> datetime:
    """Return the UTC instant of local midnight on cycle `index`'s anchored start day."""
    local_midnight = datetime.combine(add_months_clamped(signup_date, index), time(0), tzinfo=ZoneInfo(tz))
    return local_midnight.astimezone(UTC)


def period_by_index(signup_date: date, tz: str, index: int) -> Period:
    """Build the period with the given cycle index."""
    return Period(
        index=index,
        start_utc=period_start_utc(signup_date, tz, index),
        end_utc=period_start_utc(signup_date, tz, index + 1),
    )


def period_index_at(signup_date: date, tz: str, at: datetime) -> int:
    """Return which cycle `at` falls in: 0 = first month after signup, 1 = second, ...

    The result N satisfies start_N <= at < start_{N+1}.
    """
    # A time without a timezone is ambiguous ("10:00 where?"), so refuse it.
    if at.tzinfo is None:
        raise ValueError("at must be timezone-aware")

    # Billing months follow the customer's calendar, so look at their local date.
    local = at.astimezone(ZoneInfo(tz))

    # First guess: months since signup. Signup 10 Jan, local 5 Mar -> 2.
    index = (local.year - signup_date.year) * 12 + (local.month - signup_date.month)

    # The guess ignores the day: 5 Mar is before the 10th, so it is still cycle 1.
    # Step back while the guessed cycle starts after `at` ...
    while period_start_utc(signup_date, tz, index) > at:
        index -= 1
    # ... and step forward while the next cycle has already started.
    while period_start_utc(signup_date, tz, index + 1) <= at:
        index += 1
    return index


def period_containing(signup_date: date, tz: str, at_utc: datetime) -> Period:
    """Return the period containing `at_utc`."""
    return period_by_index(signup_date, tz, period_index_at(signup_date, tz, at_utc))


def current_period(customer: CycleAnchor, now: datetime) -> Period:
    """Return the customer's period containing `now`."""
    return period_containing(customer.signup_date, customer.timezone, now)


def previous_period(signup_date: date, tz: str, period: Period) -> Period:
    """Return the period immediately before `period`."""
    return period_by_index(signup_date, tz, period.index - 1)


def next_period(signup_date: date, tz: str, period: Period) -> Period:
    """Return the period immediately after `period`."""
    return period_by_index(signup_date, tz, period.index + 1)


def to_customer_time(at: datetime, tz: str) -> datetime:
    """Convert an aware datetime to the given IANA timezone."""
    return at.astimezone(ZoneInfo(tz))


def format_period_label(start_utc: datetime, end_utc: datetime, tz: str) -> str:
    """Format a period as inclusive local dates, e.g. '10 Jan – 09 Feb 2026'."""
    first = to_customer_time(start_utc, tz).date()
    last = to_customer_time(end_utc, tz).date() - timedelta(days=1)
    if first.year == last.year:
        return f"{first:%d %b} – {last:%d %b %Y}"
    return f"{first:%d %b %Y} – {last:%d %b %Y}"

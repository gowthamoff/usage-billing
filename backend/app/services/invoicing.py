"""Cycle close: rate a period from raw events, add late-usage adjustments for earlier invoices,
issue once."""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Customer, Invoice, InvoiceLine, Meter
from app.domain.cycles import Period, current_period, format_period_label, previous_period
from app.domain.money import format_inr, format_inr_rate
from app.domain.rating import PlanMeterRate, RatedLine, rate_period
from app.services.usage import CURRENCY, load_plan_meters, usage_by_meter, usage_by_period_and_meter

USAGE = "usage"
ADJUSTMENT = "adjustment"
STATUS_ISSUED = "issued"


@dataclass(frozen=True)
class ClosedCycle:
    """Record of one newly issued invoice."""

    customer_id: str
    invoice_id: str
    period_start: datetime


def new_invoice_id() -> str:
    """Generate a random invoice id."""
    return "inv_" + uuid.uuid4().hex[:12]


def find_invoice(db: Session, customer_id: str, period_start: datetime) -> Invoice | None:
    """Return the invoice for a customer's period, if one has been issued."""
    return db.scalar(select(Invoice).where(Invoice.customer_id == customer_id, Invoice.period_start == period_start))


def close_cycle(db: Session, customer: Customer, period: Period, now: datetime) -> tuple[Invoice, bool]:
    """Issue the invoice for `period` and return (invoice, created). A second close returns the
    existing invoice."""
    existing = find_invoice(db, customer.id, period.start_utc)
    if existing is not None:
        return existing, False

    plan_meters = load_plan_meters(db, customer.plan_id)
    rates = [PlanMeterRate(pm.meter_id, pm.allowance, pm.overage_rate_minor) for pm, _ in plan_meters]
    meters = {meter.id: meter for _, meter in plan_meters}

    lines = [
        _usage_line(rated, period, meters[rated.meter_id])
        for rated in rate_period(usage_by_meter(db, customer.id, period.start_utc), rates)
    ]
    lines.extend(_adjustment_lines(db, customer, period, rates))

    invoice = Invoice(
        id=new_invoice_id(),
        customer_id=customer.id,
        period_start=period.start_utc,
        period_end=period.end_utc,
        currency=CURRENCY,
        total_minor=sum(line.amount_minor for line in lines),
        status=STATUS_ISSUED,
        issued_at=now,
    )
    invoice.lines = lines
    db.add(invoice)
    try:
        db.commit()
    except IntegrityError:
        # Lost a race on UNIQUE (customer_id, period_start): the other close's invoice counts.
        db.rollback()
        winner = find_invoice(db, customer.id, period.start_utc)
        if winner is None:
            raise
        return winner, False
    return invoice, True


def _usage_line(rated: RatedLine, period: Period, meter: Meter) -> InvoiceLine:
    description = (
        f"{meter.display_name}: {rated.quantity:,} {meter.unit} used, {rated.allowance:,} included, "
        f"{rated.overage_units:,} over allowance × {format_inr_rate(rated.rate_minor)} = {format_inr(rated.amount_minor)}"
    )
    return InvoiceLine(
        line_type=USAGE,
        meter_id=rated.meter_id,
        period_start=period.start_utc,
        period_end=period.end_utc,
        quantity=rated.quantity,
        allowance=rated.allowance,
        overage_units=rated.overage_units,
        rate_minor=rated.rate_minor,
        amount_minor=rated.amount_minor,
        description=description,
    )


def _adjustment_lines(db: Session, customer: Customer, period: Period, rates: list[PlanMeterRate]) -> list[InvoiceLine]:
    """Re-rate every earlier invoiced period from raw events (late ones included) and bill only
    the difference.

    `already billed` for a period = its usage lines + every adjustment line that targeted it, so
    late events are billed exactly once no matter how many closes happen afterwards.
    """
    prior = db.execute(
        select(Invoice.id, Invoice.period_start, Invoice.period_end)
        .where(Invoice.customer_id == customer.id, Invoice.period_start < period.start_utc)
        .order_by(Invoice.period_start)
    ).all()
    if not prior:
        return []
    starts = [row.period_start for row in prior]
    usage = usage_by_period_and_meter(db, customer.id, starts)
    late = usage_by_period_and_meter(db, customer.id, starts, late_only=True)
    billed = _billed_by_period_and_meter(db, customer.id, starts)

    lines: list[InvoiceLine] = []
    for invoice_id, start, end in prior:
        start = start.astimezone(timezone.utc)
        period_usage = {meter_id: qty for (ps, meter_id), qty in usage.items() if ps == start}
        for rated in rate_period(period_usage, rates):
            billed_amount, billed_overage = billed.get((start, rated.meter_id), (0, 0))
            delta = rated.amount_minor - billed_amount
            if delta == 0:
                continue
            lines.append(
                InvoiceLine(
                    line_type=ADJUSTMENT,
                    meter_id=rated.meter_id,
                    period_start=start,
                    period_end=end,
                    quantity=late.get((start, rated.meter_id), 0),
                    allowance=rated.allowance,
                    overage_units=rated.overage_units - billed_overage,
                    rate_minor=rated.rate_minor,
                    amount_minor=delta,
                    description=(
                        f"Late usage for {format_period_label(start, end, customer.timezone)} "
                        f"(received after invoice {invoice_id})"
                    ),
                    adjusts_invoice_id=invoice_id,
                )
            )
    return lines


def _billed_by_period_and_meter(
    db: Session, customer_id: str, period_starts: list[datetime]
) -> dict[tuple[datetime, str], tuple[int, int]]:
    """Sum (amount, overage_units) already billed per (period, meter). Usage lines and adjustments
    both carry the period they bill for in line.period_start."""
    rows = db.execute(
        select(InvoiceLine.period_start, InvoiceLine.meter_id, func.sum(InvoiceLine.amount_minor), func.sum(InvoiceLine.overage_units))
        .join(Invoice, Invoice.id == InvoiceLine.invoice_id)
        .where(Invoice.customer_id == customer_id, InvoiceLine.period_start.in_(period_starts))
        .group_by(InvoiceLine.period_start, InvoiceLine.meter_id)
    ).all()
    return {
        (period_start.astimezone(timezone.utc), meter_id): (int(amount), int(overage))
        for period_start, meter_id, amount, overage in rows
    }


def find_due(db: Session, now: datetime) -> list[tuple[Customer, Period]]:
    """Return customers whose most recently ended cycle has no invoice yet, in one query."""
    rows = db.execute(
        select(Customer, Invoice.period_start)
        .outerjoin(Invoice, Invoice.customer_id == Customer.id)
        .order_by(Customer.id)
    ).all()
    customers: dict[str, Customer] = {}
    invoiced: dict[str, set[datetime]] = defaultdict(set)
    for customer, period_start in rows:
        customers[customer.id] = customer
        if period_start is not None:
            invoiced[customer.id].add(period_start.astimezone(timezone.utc))

    due: list[tuple[Customer, Period]] = []
    for customer in customers.values():
        current = current_period(customer, now)
        if current.index <= 0:
            continue
        last_ended = previous_period(customer.signup_date, customer.timezone, current)
        if last_ended.start_utc not in invoiced[customer.id]:
            due.append((customer, last_ended))
    return due


def close_due(db: Session, now: datetime) -> list[ClosedCycle]:
    """Invoice every due cycle. Each close commits on its own, so one failure never rolls back
    another customer's invoice."""
    closed: list[ClosedCycle] = []
    for customer, period in find_due(db, now):
        invoice, created = close_cycle(db, customer, period, now)
        if created:
            closed.append(ClosedCycle(customer.id, invoice.id, invoice.period_start))
    return closed

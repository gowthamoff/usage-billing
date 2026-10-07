"""ORM models: plans, customers, usage events and counters, notifications and invoices."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base holding the metadata Alembic migrates."""


class Plan(Base):
    """A pricing plan: a named set of metered allowances and overage rates."""

    __tablename__ = "plans"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    plan_meters: Mapped[list[PlanMeter]] = relationship(back_populates="plan", order_by="PlanMeter.meter_id")


class Meter(Base):
    """A billable usage dimension (e.g. api_calls) and its display unit."""

    __tablename__ = "meters"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    unit: Mapped[str] = mapped_column(Text, nullable=False)


class PlanMeter(Base):
    """Per-cycle allowance and overage rate of one meter on one plan."""

    __tablename__ = "plan_meters"

    plan_id: Mapped[str] = mapped_column(Text, ForeignKey("plans.id"), primary_key=True)
    meter_id: Mapped[str] = mapped_column(Text, ForeignKey("meters.id"), primary_key=True)
    allowance: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # Minor units per unit as an exact decimal so sub-paisa rates work; rounded once per line.
    overage_rate_minor: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)

    plan: Mapped[Plan] = relationship(back_populates="plan_meters")
    meter: Mapped[Meter] = relationship()


class Customer(Base):
    """A billed account; signup_date and timezone anchor its monthly cycles."""

    __tablename__ = "customers"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    timezone: Mapped[str] = mapped_column(Text, nullable=False)
    signup_date: Mapped[date] = mapped_column(Date, nullable=False)
    plan_id: Mapped[str] = mapped_column(Text, ForeignKey("plans.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    plan: Mapped[Plan] = relationship(lazy="joined")


class UsageEvent(Base):
    """An immutable usage record, deduplicated on the client-supplied event_id."""

    __tablename__ = "usage_events"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_usage_events_quantity_positive"),
        Index("ix_usage_events_customer_meter_occurred", "customer_id", "meter_id", "occurred_at"),
        Index("ix_usage_events_customer_period", "customer_id", "billing_period_start"),
    )

    event_id: Mapped[str] = mapped_column(Text, primary_key=True)
    customer_id: Mapped[str] = mapped_column(Text, ForeignKey("customers.id"), nullable=False)
    meter_id: Mapped[str] = mapped_column(Text, ForeignKey("meters.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(BigInteger, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Server clock at ingest; billing uses occurred_at, this is kept only for audit and debugging.
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    # Cycle resolved once at ingest (customer tz) so counters and invoicing never redo tz math.
    billing_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Cycle already invoiced: kept out of counters, billed as an adjustment on the next invoice.
    is_late: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))


class UsageCounter(Base):
    """Running on-time usage per customer, meter and cycle; rebuildable from usage_events."""

    __tablename__ = "usage_counters"

    customer_id: Mapped[str] = mapped_column(Text, ForeignKey("customers.id"), primary_key=True)
    meter_id: Mapped[str] = mapped_column(Text, ForeignKey("meters.id"), primary_key=True)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    quantity: Mapped[int] = mapped_column(BigInteger, nullable=False)


class ThresholdNotification(Base):
    """Outbox row for a threshold crossing, unique per customer, meter, cycle and threshold."""

    __tablename__ = "threshold_notifications"
    __table_args__ = (
        UniqueConstraint(
            "customer_id", "meter_id", "period_start", "threshold", name="uq_threshold_notifications_once_per_cycle"
        ),
        CheckConstraint("threshold > 0", name="ck_threshold_notifications_threshold_positive"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    customer_id: Mapped[str] = mapped_column(Text, ForeignKey("customers.id"), nullable=False)
    meter_id: Mapped[str] = mapped_column(Text, ForeignKey("meters.id"), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    threshold: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    usage_at_fire: Mapped[int] = mapped_column(BigInteger, nullable=False)
    allowance: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class Invoice(Base):
    """An issued invoice; at most one per customer and cycle."""

    __tablename__ = "invoices"
    __table_args__ = (UniqueConstraint("customer_id", "period_start", name="uq_invoices_customer_period"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    customer_id: Mapped[str] = mapped_column(Text, ForeignKey("customers.id"), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'INR'"))
    total_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'issued'"))
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    customer: Mapped[Customer] = relationship()
    lines: Mapped[list[InvoiceLine]] = relationship(
        back_populates="invoice", foreign_keys="InvoiceLine.invoice_id", order_by="InvoiceLine.id"
    )


class InvoiceLine(Base):
    """A usage line, or an adjustment line billing late usage for an earlier cycle."""

    __tablename__ = "invoice_lines"
    __table_args__ = (
        CheckConstraint("line_type IN ('usage', 'adjustment')", name="ck_invoice_lines_line_type"),
        Index("ix_invoice_lines_invoice", "invoice_id"),
        Index("ix_invoice_lines_period_start", "period_start"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    invoice_id: Mapped[str] = mapped_column(Text, ForeignKey("invoices.id"), nullable=False)
    line_type: Mapped[str] = mapped_column(Text, nullable=False)
    meter_id: Mapped[str] = mapped_column(Text, ForeignKey("meters.id"), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    quantity: Mapped[int] = mapped_column(BigInteger, nullable=False)
    allowance: Mapped[int] = mapped_column(BigInteger, nullable=False)
    overage_units: Mapped[int] = mapped_column(BigInteger, nullable=False)
    rate_minor: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # Adjustment lines only: issued invoices are never edited, so corrections point back to them.
    adjusts_invoice_id: Mapped[str | None] = mapped_column(Text, ForeignKey("invoices.id"), nullable=True)

    invoice: Mapped[Invoice] = relationship(back_populates="lines", foreign_keys=[invoice_id])

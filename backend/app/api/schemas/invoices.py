"""Request/response schemas for invoices, their lines and billing-cycle close operations."""

from datetime import datetime
from decimal import Decimal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.db.models import Invoice, InvoiceLine
from app.domain.cycles import to_customer_time


class InvoiceOut(BaseModel):
    """Invoice header for one customer billing period; amounts in minor units (paise)."""

    id: str
    customer_id: str
    period_start: datetime
    period_end: datetime
    period_start_local: datetime = Field(description="`period_start` in the customer's timezone.")
    period_end_local: datetime = Field(description="`period_end` in the customer's timezone.")
    currency: str
    total_minor: int
    status: str
    issued_at: datetime

    @classmethod
    def from_invoice(cls, invoice: Invoice, tz: str) -> "InvoiceOut":
        return cls(**cls._fields(invoice, tz))

    @staticmethod
    def _fields(invoice: Invoice, tz: str) -> dict:
        return {
            "id": invoice.id,
            "customer_id": invoice.customer_id,
            "period_start": invoice.period_start,
            "period_end": invoice.period_end,
            "period_start_local": to_customer_time(invoice.period_start, tz),
            "period_end_local": to_customer_time(invoice.period_end, tz),
            "currency": invoice.currency,
            "total_minor": invoice.total_minor,
            "status": invoice.status,
            "issued_at": invoice.issued_at,
        }


class InvoiceLineOut(BaseModel):
    """One usage or late-usage adjustment line, carrying the inputs that explain its amount."""

    id: int
    line_type: str
    meter: str = Field(validation_alias="meter_id")
    display_name: str
    period_start: datetime
    period_end: datetime
    quantity: int
    allowance: int
    overage_units: int
    rate_minor: Decimal = Field(
        description="Overage price per unit in minor units; may be fractional (sub-paisa)."
    )
    amount_minor: int
    description: str
    adjusts_invoice_id: str | None

    @classmethod
    def from_line(cls, line: InvoiceLine, display_name: str) -> "InvoiceLineOut":
        return cls(
            id=line.id,
            line_type=line.line_type,
            meter_id=line.meter_id,
            display_name=display_name,
            period_start=line.period_start,
            period_end=line.period_end,
            quantity=line.quantity,
            allowance=line.allowance,
            overage_units=line.overage_units,
            rate_minor=line.rate_minor,
            amount_minor=line.amount_minor,
            description=line.description,
            adjusts_invoice_id=line.adjusts_invoice_id,
        )


class InvoiceDetailOut(InvoiceOut):
    """Invoice header plus its lines."""

    lines: list[InvoiceLineOut]

    @classmethod
    def from_invoice_with_lines(
        cls, invoice: Invoice, tz: str, lines: list[tuple[InvoiceLine, str]]
    ) -> "InvoiceDetailOut":
        return cls(
            **cls._fields(invoice, tz),
            lines=[InvoiceLineOut.from_line(line, display_name) for line, display_name in lines],
        )


class CloseCycleRequest(BaseModel):
    """Which cycle to close; defaults to the most recently ended one."""

    period_start: AwareDatetime | None = None
    force: bool = False  # demo-only: close the still-running cycle as of now


class ClosedCycleOut(BaseModel):
    """One cycle closed by a close-due run and the invoice it produced."""

    model_config = ConfigDict(from_attributes=True)

    customer_id: str
    invoice_id: str
    period_start: datetime


class CloseDueOut(BaseModel):
    """Cycles newly invoiced by a close-due run; empty when nothing was due."""

    closed: list[ClosedCycleOut]

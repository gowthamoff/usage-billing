"""Invoice read endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_customer_or_404
from app.api.schemas.invoices import InvoiceDetailOut, InvoiceOut
from app.db.models import Customer, Invoice, InvoiceLine, Meter
from app.db.session import get_db
from app.errors import NotFound

router = APIRouter(tags=["invoices"])


@router.get("/customers/{customer_id}/invoices", response_model=list[InvoiceOut])
def list_invoices(customer: Customer = Depends(get_customer_or_404), db: Session = Depends(get_db)) -> list[InvoiceOut]:
    """List the customer's invoices, most recent cycle first.
    404 when the customer does not exist."""
    invoices = db.scalars(
        select(Invoice).where(Invoice.customer_id == customer.id).order_by(Invoice.period_start.desc())
    ).all()
    return [InvoiceOut.from_invoice(invoice, customer.timezone) for invoice in invoices]


@router.get("/invoices/{invoice_id}", response_model=InvoiceDetailOut)
def get_invoice(invoice_id: str, db: Session = Depends(get_db)) -> InvoiceDetailOut:
    """Return an invoice with its usage and adjustment lines.
    404 when the invoice does not exist."""
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise NotFound(f"invoice {invoice_id!r} not found", code="invoice_not_found")
    lines = db.execute(
        select(InvoiceLine, Meter.display_name)
        .join(Meter, Meter.id == InvoiceLine.meter_id)
        .where(InvoiceLine.invoice_id == invoice.id)
        .order_by(InvoiceLine.id)
    ).all()
    return InvoiceDetailOut.from_invoice_with_lines(
        invoice, invoice.customer.timezone, [(line, display_name) for line, display_name in lines]
    )

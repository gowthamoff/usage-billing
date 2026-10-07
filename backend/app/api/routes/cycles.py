"""Billing cycle closing: one customer on demand, or every due cycle in a sweep."""

from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.deps import get_customer_or_404, utcnow
from app.api.schemas.common import ErrorResponse
from app.api.schemas.invoices import CloseCycleRequest, CloseDueOut, InvoiceOut
from app.db.models import Customer
from app.db.session import get_db
from app.domain.cycles import Period, current_period, period_containing, previous_period
from app.errors import Conflict, DomainError
from app.services.invoicing import close_cycle, close_due

router = APIRouter(tags=["cycles"])


@router.post(
    "/customers/{customer_id}/cycles/close",
    response_model=InvoiceOut,
    status_code=201,
    responses={
        200: {"model": InvoiceOut, "description": "The cycle was already invoiced"},
        409: {"model": ErrorResponse, "description": "cycle_not_ended"},
    },
)
def close_customer_cycle(
    body: CloseCycleRequest | None = None,
    customer: Customer = Depends(get_customer_or_404),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Close a billing cycle and issue its invoice; closing again returns the same invoice.
    201 when created, 200 when it already existed, 409 when the cycle has not ended,
    400 when period_start is not the exact start of one of the customer's cycles."""
    body = body or CloseCycleRequest()
    now = utcnow()
    period = _target_period(customer, body, now)
    if period.end_utc > now and not body.force:
        raise Conflict(
            f"cycle starting {period.start_utc.isoformat()} ends at {period.end_utc.isoformat()}; it has not ended yet",
            code="cycle_not_ended",
        )
    invoice, created = close_cycle(db, customer, period, now)
    return JSONResponse(
        status_code=201 if created else 200,
        content=InvoiceOut.from_invoice(invoice, customer.timezone).model_dump(mode="json"),
    )


def _target_period(customer: Customer, body: CloseCycleRequest, now: datetime) -> Period:
    """Pick the cycle to close: explicit period_start, else the current one when forced,
    else the most recently ended one."""
    current = current_period(customer, now)
    if body.period_start is not None:
        period = period_containing(customer.signup_date, customer.timezone, body.period_start)
        if period.start_utc != body.period_start or period.index < 0:
            raise DomainError(
                "period_start must be the exact UTC start of one of the customer's cycles",
                code="invalid_period_start",
            )
        if period.index > current.index:
            raise DomainError("period_start is in the future", code="invalid_period_start")
        return period
    if body.force:
        return current
    if current.index <= 0:
        raise Conflict("the customer's first cycle has not ended yet", code="cycle_not_ended")
    return previous_period(customer.signup_date, customer.timezone, current)


@router.post("/cycles/close-due", response_model=CloseDueOut)
def close_due_cycles(db: Session = Depends(get_db)) -> CloseDueOut:
    """Invoice the most recently ended cycle of every customer that does not have one yet.
    Idempotent, so it is safe to call on a schedule."""
    return CloseDueOut(closed=close_due(db, utcnow()))

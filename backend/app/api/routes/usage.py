"""Current-cycle usage endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_customer_or_404, utcnow
from app.api.schemas.customers import PeriodOut
from app.api.schemas.usage import MeterUsageOut, TimeseriesOut, UsageOut
from app.db.models import Customer
from app.db.session import get_db
from app.services.usage import current_usage, timeseries

router = APIRouter(tags=["usage"])


@router.get("/customers/{customer_id}/usage", response_model=UsageOut)
def get_usage(customer: Customer = Depends(get_customer_or_404), db: Session = Depends(get_db)) -> UsageOut:
    """Return usage, allowance, state and projected cost per plan meter for the current cycle.
    404 when the customer does not exist."""
    summary = current_usage(db, customer, utcnow())
    return UsageOut(
        period=PeriodOut.from_period(summary.period, summary.timezone),
        currency=summary.currency,
        meters=[MeterUsageOut.model_validate(m) for m in summary.meters],
        total_cost_minor=summary.total_cost_minor,
    )


@router.get("/customers/{customer_id}/usage/timeseries", response_model=TimeseriesOut)
def get_usage_timeseries(
    meter: str = Query(..., description="meter id, e.g. api_calls"),
    customer: Customer = Depends(get_customer_or_404),
    db: Session = Depends(get_db),
) -> TimeseriesOut:
    """Return daily usage of one meter over the current cycle, in the customer's local dates.
    404 when the customer does not exist."""
    return TimeseriesOut.model_validate(timeseries(db, customer, meter, utcnow()))

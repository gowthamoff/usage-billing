"""Customer read endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_customer_or_404, utcnow
from app.api.schemas.customers import CustomerDetailOut, CustomerOut, PeriodOut
from app.db.models import Customer
from app.db.session import get_db
from app.domain.cycles import current_period

router = APIRouter(tags=["customers"])


@router.get("/customers", response_model=list[CustomerOut])
def list_customers(db: Session = Depends(get_db)) -> list[Customer]:
    """List every customer with its plan, ordered by id."""
    return list(db.scalars(select(Customer).order_by(Customer.id)).all())


@router.get("/customers/{customer_id}", response_model=CustomerDetailOut)
def get_customer(customer: Customer = Depends(get_customer_or_404)) -> CustomerDetailOut:
    """Return a customer together with the billing cycle that contains the current instant.
    404 when the customer does not exist."""
    period = current_period(customer, utcnow())
    return CustomerDetailOut(
        **CustomerOut.model_validate(customer).model_dump(),
        current_period=PeriodOut.from_period(period, customer.timezone),
    )

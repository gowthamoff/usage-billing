"""Threshold notification history."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_customer_or_404, utcnow
from app.api.schemas.notifications import NotificationOut
from app.db.models import Customer
from app.db.session import get_db
from app.domain.cycles import current_period
from app.services.notifications import list_notifications

router = APIRouter(tags=["notifications"])


@router.get("/customers/{customer_id}/notifications", response_model=list[NotificationOut])
def get_notifications(
    all_cycles: bool = Query(False, alias="all", description="true returns every cycle, not just the current one"),
    customer: Customer = Depends(get_customer_or_404),
    db: Session = Depends(get_db),
) -> list[NotificationOut]:
    """List the threshold notifications fired for the customer, current cycle only by default.
    404 when the customer does not exist."""
    period_start = None if all_cycles else current_period(customer, utcnow()).start_utc
    return [NotificationOut.model_validate(n) for n in list_notifications(db, customer, period_start)]

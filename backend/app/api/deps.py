"""FastAPI dependencies shared by the routes: API-key auth, the clock and customer lookup."""

import secrets
from datetime import datetime, timezone

from fastapi import Depends, Security
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Customer
from app.db.session import get_db
from app.errors import NotFound, Unauthorized

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def utcnow() -> datetime:
    """Return the current instant as an aware UTC datetime."""
    return datetime.now(timezone.utc)


def require_api_key(api_key: str | None = Security(api_key_header)) -> None:
    """Reject the request with 401 unless X-API-Key matches the configured key."""
    if api_key is None or not secrets.compare_digest(api_key.encode(), settings.API_KEY.encode()):
        raise Unauthorized("missing or invalid X-API-Key header")


def get_customer_or_404(customer_id: str, db: Session = Depends(get_db)) -> Customer:
    """Load the customer named in the path or raise NotFound."""
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise NotFound(f"customer {customer_id!r} not found", code="customer_not_found")
    return customer

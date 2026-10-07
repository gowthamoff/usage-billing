"""Operator endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.counters import rebuild_counters

router = APIRouter(tags=["admin"])


@router.post("/admin/counters/rebuild")
def rebuild_usage_counters(db: Session = Depends(get_db)) -> dict[str, int]:
    """Rebuild the usage counters from the stored events and report how many rows were written.
    Recovery path for counter drift; usage reads never depend on it."""
    return {"rows": rebuild_counters(db)}

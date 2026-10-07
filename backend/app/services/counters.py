"""usage_counters: a derived cache for the threshold check, always rebuildable from raw events."""

from sqlalchemy import func, insert, select, text
from sqlalchemy.orm import Session

from app.db.models import UsageCounter, UsageEvent


def rebuild_counters(db: Session) -> int:
    """Rebuild usage_counters from non-late events and return the number of rows written."""
    db.execute(text("TRUNCATE TABLE usage_counters"))
    totals = (
        select(
            UsageEvent.customer_id,
            UsageEvent.meter_id,
            UsageEvent.billing_period_start,
            func.sum(UsageEvent.quantity),
        )
        .where(UsageEvent.is_late.is_(False))
        .group_by(UsageEvent.customer_id, UsageEvent.meter_id, UsageEvent.billing_period_start)
    )
    # Count via RETURNING: rowcount is -1 for INSERT ... SELECT under psycopg 3.
    written = db.execute(
        insert(UsageCounter)
        .from_select(
            [UsageCounter.customer_id, UsageCounter.meter_id, UsageCounter.period_start, UsageCounter.quantity],
            totals,
        )
        .returning(UsageCounter.customer_id)
    ).all()
    db.commit()
    return len(written)

"""Deterministic reference data: plans, meters and the five demo customers. Idempotent upserts."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import Customer, Meter, Plan, PlanMeter


@dataclass(frozen=True)
class SeedCustomer:
    """Definition of one demo customer."""

    id: str
    name: str
    timezone: str
    signup_date: date
    plan_id: str


SEED_METERS: tuple[tuple[str, str, str], ...] = (
    ("api_calls", "API calls", "call"),
    ("storage_gb", "Storage", "GB"),
)

SEED_PLANS: dict[str, str] = {"basic": "Basic", "pro": "Pro"}

# (plan_id, meter_id, allowance, overage rate in paise per unit)
SEED_PLAN_METERS: tuple[tuple[str, str, int, Decimal], ...] = (
    ("basic", "api_calls", 10_000, Decimal("50.000000")),
    ("basic", "storage_gb", 10, Decimal("300.000000")),
    ("pro", "api_calls", 100_000, Decimal("30.000000")),
    ("pro", "storage_gb", 100, Decimal("200.000000")),
)

SEED_CUSTOMERS: tuple[SeedCustomer, ...] = (
    SeedCustomer("cus_asha", "Asha Verma", "Asia/Kolkata", date(2026, 1, 10), "basic"),
    SeedCustomer("cus_ravi", "Ravi Menon", "Asia/Kolkata", date(2026, 1, 31), "pro"),
    SeedCustomer("cus_noor", "Noor Haddad", "America/New_York", date(2026, 2, 15), "basic"),
    SeedCustomer("cus_lee", "Lee Walker", "Europe/London", date(2026, 1, 5), "pro"),
    SeedCustomer("cus_kai", "Kai Tanaka", "Asia/Tokyo", date(2026, 2, 28), "basic"),
)


def seed(db: Session) -> dict[str, int]:
    """Upsert all reference data in one transaction; returns row counts per table."""
    plans = insert(Plan).values([{"id": pid, "name": name} for pid, name in SEED_PLANS.items()])
    db.execute(plans.on_conflict_do_update(index_elements=["id"], set_={"name": plans.excluded.name}))

    meters = insert(Meter).values(
        [{"id": mid, "display_name": display, "unit": unit} for mid, display, unit in SEED_METERS]
    )
    db.execute(
        meters.on_conflict_do_update(
            index_elements=["id"],
            set_={"display_name": meters.excluded.display_name, "unit": meters.excluded.unit},
        )
    )

    plan_meters = insert(PlanMeter).values(
        [
            {"plan_id": pid, "meter_id": mid, "allowance": allowance, "overage_rate_minor": rate}
            for pid, mid, allowance, rate in SEED_PLAN_METERS
        ]
    )
    db.execute(
        plan_meters.on_conflict_do_update(
            index_elements=["plan_id", "meter_id"],
            set_={
                "allowance": plan_meters.excluded.allowance,
                "overage_rate_minor": plan_meters.excluded.overage_rate_minor,
            },
        )
    )

    customers = insert(Customer).values(
        [
            {
                "id": c.id,
                "name": c.name,
                "timezone": c.timezone,
                "signup_date": c.signup_date,
                "plan_id": c.plan_id,
            }
            for c in SEED_CUSTOMERS
        ]
    )
    db.execute(
        customers.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "name": customers.excluded.name,
                "timezone": customers.excluded.timezone,
                "signup_date": customers.excluded.signup_date,
                "plan_id": customers.excluded.plan_id,
            },
        )
    )
    db.commit()
    return {
        "plans": len(SEED_PLANS),
        "meters": len(SEED_METERS),
        "plan_meters": len(SEED_PLAN_METERS),
        "customers": len(SEED_CUSTOMERS),
    }

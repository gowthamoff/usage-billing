"""Response schemas for current-cycle usage per meter and daily usage timeseries."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.api.schemas.customers import PeriodOut


class MeterUsageOut(BaseModel):
    """Usage, allowance and running overage cost for one meter in the current cycle."""

    model_config = ConfigDict(from_attributes=True)

    meter: str
    display_name: str
    unit: str
    used: int
    allowance: int
    remaining: int
    overage_units: int
    percent: float = Field(
        description="Share of allowance used, truncated to 2 dp; exceeds 100 when in overage."
    )
    state: str = Field(description="One of within_allowance, approaching_limit (>=80%), in_overage.")
    rate_minor: Decimal = Field(
        description="Overage price per unit in minor units; may be fractional (sub-paisa)."
    )
    cost_minor: int


class UsageOut(BaseModel):
    """Current-cycle usage for every meter on the customer's plan."""

    period: PeriodOut
    currency: str
    meters: list[MeterUsageOut]
    total_cost_minor: int


class TimeseriesPointOut(BaseModel):
    """Usage total for one bucket."""

    model_config = ConfigDict(from_attributes=True)

    date: date
    quantity: int


class TimeseriesOut(BaseModel):
    """Bucketed usage series for one meter."""

    model_config = ConfigDict(from_attributes=True)

    meter: str
    bucket: str
    points: list[TimeseriesPointOut]

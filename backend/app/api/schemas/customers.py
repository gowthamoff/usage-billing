"""Response schemas for customers, their plan and the billing period they are currently in."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.cycles import Period, to_customer_time


class PlanOut(BaseModel):
    """Plan summary embedded in a customer."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str


class PeriodOut(BaseModel):
    """A billing period as a half-open [start, end) interval in UTC and customer-local time."""

    start: datetime
    end: datetime
    start_local: datetime = Field(description="Same instant as `start`, in the customer's timezone.")
    end_local: datetime = Field(description="Same instant as `end`, in the customer's timezone.")

    @classmethod
    def from_period(cls, period: Period, tz: str) -> "PeriodOut":
        return cls(
            start=period.start_utc,
            end=period.end_utc,
            start_local=to_customer_time(period.start_utc, tz),
            end_local=to_customer_time(period.end_utc, tz),
        )


class CustomerOut(BaseModel):
    """Customer with the timezone and signup date that anchor its billing cycles."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    timezone: str
    signup_date: date
    plan: PlanOut


class CustomerDetailOut(CustomerOut):
    """Customer plus the billing period containing the current instant."""

    current_period: PeriodOut

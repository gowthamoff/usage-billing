"""Response schema for usage-threshold notifications and their delivery status."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NotificationOut(BaseModel):
    """A threshold crossing recorded once per customer, meter and cycle, with delivery state."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    meter: str = Field(validation_alias="meter_id")
    threshold: int
    period_start: datetime
    usage_at_fire: int
    allowance: int
    created_at: datetime
    sent_at: datetime | None
    attempts: int
    last_error: str | None

"""Request/response schemas for batch usage-event ingestion with per-event outcomes."""

from typing import Any, Literal

from pydantic import BaseModel, Field, SerializerFunctionWrapHandler, model_serializer

from app.services.ingest import BatchResult


class BatchRequest(BaseModel):
    """Envelope for a batch of raw usage events."""

    # Items are validated per event by the domain so one bad event never rejects the batch.
    events: list[Any]


class EventErrorOut(BaseModel):
    """Why a single event was rejected."""

    code: str
    message: str


class EventResultOut(BaseModel):
    """Outcome for one event, in the same position as the request item."""

    event_id: str | None
    status: Literal["accepted", "duplicate", "rejected"]
    is_late: bool | None = Field(
        default=None,
        description="True when the event's cycle is already invoiced; billed as an adjustment later.",
    )
    error: EventErrorOut | None = None

    @model_serializer(mode="wrap")
    def omit_unset_optionals(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        # event_id is always present (null for shape errors); is_late/error appear only when set.
        return {key: value for key, value in handler(self).items() if value is not None or key == "event_id"}


class BatchSummaryOut(BaseModel):
    """Counts of events per outcome; accepted + duplicate + rejected == received."""

    received: int
    accepted: int
    duplicate: int
    rejected: int


class BatchResponse(BaseModel):
    """Batch summary plus per-event results in request order."""

    summary: BatchSummaryOut
    results: list[EventResultOut]

    @classmethod
    def from_result(cls, result: BatchResult) -> "BatchResponse":
        return cls(
            summary=BatchSummaryOut(
                received=result.received,
                accepted=result.accepted,
                duplicate=result.duplicate,
                rejected=result.rejected,
            ),
            results=[
                EventResultOut(
                    event_id=r.event_id,
                    status=r.status,
                    is_late=r.is_late,
                    error=EventErrorOut(code=r.error.code, message=r.error.message) if r.error else None,
                )
                for r in result.results
            ],
        )

"""Usage event ingestion."""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.schemas.common import ErrorResponse
from app.api.schemas.events import BatchRequest, BatchResponse
from app.config import settings
from app.db.session import get_db
from app.errors import PayloadTooLarge
from app.services.ingest import ingest_batch

router = APIRouter(tags=["events"])


@router.post(
    "/events/batch",
    response_model=BatchResponse,
    responses={
        207: {"model": BatchResponse, "description": "At least one event was rejected"},
        400: {"model": ErrorResponse},
        413: {"model": ErrorResponse},
    },
)
def post_events_batch(body: BatchRequest, db: Session = Depends(get_db)) -> JSONResponse:
    """Ingest a batch of usage events; duplicates are reported, never re-counted.
    207 when any event is rejected, 413 when the batch exceeds MAX_BATCH_SIZE."""

    if len(body.events) > settings.MAX_BATCH_SIZE:
        raise PayloadTooLarge(f"batch has {len(body.events)} events; the maximum is {settings.MAX_BATCH_SIZE}")
    result = ingest_batch(db, body.events)
    response = BatchResponse.from_result(result)
    return JSONResponse(
        status_code=207 if result.rejected else 200,
        content=response.model_dump(mode="json"),
    )

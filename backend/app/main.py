"""FastAPI app: routers, API-key guard, error envelope, and the notifier worker's lifecycle."""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.deps import require_api_key
from app.api.routes import admin, customers, cycles, events, health, invoices, notifications, usage, webhook
from app.errors import DomainError
from app.workers.notifier import run_notifier

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Run the notifier worker alongside the app and stop it cleanly on shutdown."""
    stop = asyncio.Event()
    worker = asyncio.create_task(run_notifier(stop), name="notifier")
    try:
        yield
    finally:
        stop.set()
        await worker


app = FastAPI(title="Usage metering & billing", version="1.0.0", lifespan=lifespan)

# The webhook receiver stays public: the notifier POSTs to it without an API key.
app.include_router(health.router)
app.include_router(webhook.router, prefix=API_PREFIX)
for secured in (events, customers, usage, notifications, invoices, cycles, admin):
    app.include_router(secured.router, prefix=API_PREFIX, dependencies=[Depends(require_api_key)])


def _error_response(status: int, code: str, message: str, details: list | None = None) -> JSONResponse:
    body: dict = {"code": code, "message": message}
    if details is not None:
        body["details"] = details
    return JSONResponse(status_code=status, content={"error": body})


@app.exception_handler(RequestValidationError)
async def handle_request_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
    """Map request validation failures to a 400 error envelope instead of FastAPI's default 422."""
    details = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
    return _error_response(400, "validation_error", "malformed request", details)


@app.exception_handler(DomainError)
async def handle_domain_error(_: Request, exc: DomainError) -> JSONResponse:
    """Map a DomainError to the error envelope using its own status and code."""
    return _error_response(exc.status, exc.code, exc.message, exc.details)


@app.exception_handler(StarletteHTTPException)
async def handle_http_exception(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Wrap framework HTTP errors (404, 405, ...) in the error envelope, keeping their headers."""
    response = _error_response(exc.status_code, "http_error", str(exc.detail))
    if exc.headers:
        response.headers.update(exc.headers)
    return response

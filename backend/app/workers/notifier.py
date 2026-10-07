"""Outbox worker: delivers threshold notifications in the background of the API process."""

import asyncio
import logging
from datetime import datetime, timezone

import httpx

from app.config import settings
from app.db.session import SessionLocal
from app.services.notifications import deliver_pending

log = logging.getLogger(__name__)


def deliver_once() -> int:
    """One synchronous tick with its own session and client; runs in a worker thread."""
    with SessionLocal() as db, httpx.Client(timeout=5) as http:
        stats = deliver_pending(
            db,
            http,
            settings.WEBHOOK_URL,
            datetime.now(timezone.utc),
            max_attempts=settings.NOTIFIER_MAX_ATTEMPTS,
        )
    if stats.sent or stats.failed:
        log.info("notifier: sent=%d failed=%d", stats.sent, stats.failed)
    return stats.sent


async def run_notifier(stop: asyncio.Event) -> None:
    """Polls until `stop` is set. Errors are logged, never raised, so the task outlives any outage."""
    while not stop.is_set():
        try:
            await asyncio.to_thread(deliver_once)
        except Exception:
            log.exception("notifier tick failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.NOTIFIER_POLL_SECONDS)
        except asyncio.TimeoutError:
            pass

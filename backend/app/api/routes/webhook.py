"""Built-in webhook target so threshold deliveries can be observed without an external receiver."""

import logging
from typing import Any

from fastapi import APIRouter

log = logging.getLogger(__name__)

router = APIRouter(tags=["webhook"])


@router.post("/webhook-receiver")
def receive_webhook(payload: dict[str, Any]) -> dict[str, bool]:
    """Log the received payload and acknowledge it.
    Default WEBHOOK_URL target; unauthenticated because the notifier posts to it without a key."""
    log.info("webhook received %s", payload)
    return {"ok": True}

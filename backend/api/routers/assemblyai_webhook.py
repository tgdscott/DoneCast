from __future__ import annotations

import logging
from fastapi import APIRouter, Header, HTTPException, Request

from api.core.config import settings
from api.services.transcription.assemblyai_webhook import webhook_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assemblyai", tags=["assemblyai"])

_HEADER_NAME = (settings.ASSEMBLYAI_WEBHOOK_HEADER or "X-AssemblyAI-Signature").strip() or "X-AssemblyAI-Signature"


@router.post("/webhook", status_code=200)
async def assemblyai_webhook(
    request: Request,
    signature: str | None = Header(None, alias=_HEADER_NAME),
) -> None:
    secret = (settings.ASSEMBLYAI_WEBHOOK_SECRET or "").strip()
    if secret:
        expected = secret
        if signature != expected:
            logger.warning("[assemblyai] webhook signature mismatch: provided=%s", signature)
            raise HTTPException(status_code=401, detail="Invalid AssemblyAI webhook signature")

    payload = await request.json()
    delivered = webhook_manager.notify(payload)
    if not delivered:
        webhook_manager.prune()
    logger.info("[assemblyai] webhook received status=%s id=%s delivered=%s", payload.get("status"), payload.get("id"), delivered)

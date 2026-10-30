"""Fast, authenticated webhook acceptance; slow work stays in PostgreSQL."""

import hmac
import json

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


@router.post("/telegram/webhook", include_in_schema=False)
async def telegram_webhook(request: Request):
    settings = request.app.state.settings
    configured = settings.telegram_webhook_secret
    expected = configured.get_secret_value() if configured else ""
    received = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not expected or not hmac.compare_digest(expected.encode(), received.encode()):
        raise HTTPException(status_code=403, detail="Invalid webhook authentication")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 1024 * 1024:
            raise HTTPException(status_code=413, detail="Update too large")
    try:
        payload = json.loads(body)
        identifier = payload.get("update_id")
        if (
            not isinstance(identifier, int)
            or isinstance(identifier, bool)
            or not 0 <= identifier < 2**63
        ):
            raise ValueError
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid Telegram update") from None
    try:
        await request.app.state.telegram_inbox.accept(payload)
    except Exception:
        raise HTTPException(
            status_code=503, detail="Delivery could not be saved; retry later"
        ) from None
    runtime = getattr(request.app.state, "telegram_runtime", None)
    if runtime:
        runtime.wakeup.set()
    return {"ok": True}

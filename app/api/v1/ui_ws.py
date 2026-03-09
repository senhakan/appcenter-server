from __future__ import annotations

import logging
import time
import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket
from jose import JWTError, jwt
from starlette.websockets import WebSocketDisconnect

from app.config import get_settings
from app.database import get_db
from app.models import Setting, User
from app.services.ws_manager import ws_manager

router = APIRouter(tags=["ui"])
logger = logging.getLogger("appcenter.ws.ui")
settings = get_settings()
MAX_MESSAGE_BYTES = 64 * 1024


def _to_bool(value: str | None, default: bool = False) -> bool:
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _ui_ws_enabled(db) -> bool:
    # Canonical flag: ui_ws_enabled
    row = db.query(Setting).filter(Setting.key == "ui_ws_enabled").first()
    if row and row.value is not None and str(row.value).strip() != "":
        return _to_bool(row.value, default=False)
    # Backward compatibility with legacy key.
    legacy = db.query(Setting).filter(Setting.key == "ws_ui_enabled").first()
    return _to_bool((legacy.value if legacy else None), default=False)


@router.websocket("/ws")
async def ui_ws_endpoint(websocket: WebSocket):
    await websocket.accept()

    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="missing_token")
        return

    db = next(get_db())
    try:
        if not _ui_ws_enabled(db):
            await websocket.close(code=4000, reason="ui_ws_disabled")
            return

        try:
            payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
            username = payload.get("sub")
        except (JWTError, KeyError, TypeError, ValueError):
            await websocket.close(code=4001, reason="unauthorized")
            return

        if not username:
            await websocket.close(code=4001, reason="unauthorized")
            return

        user = db.query(User).filter(User.username == username, User.is_active.is_(True)).first()
        if not user:
            await websocket.close(code=4001, reason="unauthorized")
            return
    finally:
        db.close()
    await ws_manager.register_ui(websocket, user_id=user.id, role=user.role or "viewer")
    logger.info("ws ui connected user_id=%s", user.id)
    expiry_task: asyncio.Task | None = None

    exp = payload.get("exp")
    if isinstance(exp, (int, float)):
        delay = int(exp) - int(datetime.now(timezone.utc).timestamp())
        if delay <= 0:
            await websocket.close(code=4001, reason="token_expired")
            await ws_manager.unregister_ui(user.id, ws=websocket)
            return

        async def _close_on_expiry() -> None:
            await asyncio.sleep(delay)
            await websocket.close(code=4001, reason="token_expired")

        expiry_task = asyncio.create_task(_close_on_expiry())

    msg_count = 0
    msg_window_start = time.monotonic()
    MAX_MSGS_PER_MINUTE = 120

    try:
        while True:
            message = await websocket.receive()
            if "text" in message and isinstance(message["text"], str):
                if len(message["text"].encode("utf-8")) > MAX_MESSAGE_BYTES:
                    await websocket.close(code=1009, reason="message_too_large")
                    break
            msg_count += 1
            now = time.monotonic()
            if now - msg_window_start >= 60:
                msg_count = 1
                msg_window_start = now
            elif msg_count > MAX_MSGS_PER_MINUTE:
                logger.warning("ws ui rate limited user_id=%s", user.id)
                await websocket.close(code=4029, reason="rate_limited")
                break
            if message.get("type") == "websocket.disconnect":
                break
    except WebSocketDisconnect:
        pass
    finally:
        if expiry_task:
            expiry_task.cancel()
            try:
                await expiry_task
            except BaseException:
                pass
        await ws_manager.unregister_ui(user.id, ws=websocket)
        logger.info("ws ui disconnected user_id=%s", user.id)

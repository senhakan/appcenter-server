"""WebSocket connection manager for agents and UI clients."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

try:
    from websockets.exceptions import ConnectionClosed
except Exception:  # pragma: no cover - optional dependency path
    ConnectionClosed = Exception

logger = logging.getLogger("appcenter.ws")


def _msg_id() -> str:
    """Generate a unique message id like msg_a1b2c3d4."""
    return f"msg_{os.urandom(4).hex()}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_message(msg_type: str, payload: dict | None = None, ack: bool = False) -> dict:
    """Create a standard WS message envelope."""
    return {
        "id": _msg_id(),
        "type": msg_type,
        "ts": _now_iso(),
        "payload": payload or {},
        "ack": ack,
    }


class AgentConnection:
    """Represents a connected agent's WS session."""

    __slots__ = ("ws", "agent_uuid", "connected_at", "last_pong")

    def __init__(self, ws: WebSocket, agent_uuid: str):
        self.ws = ws
        self.agent_uuid = agent_uuid
        self.connected_at = time.monotonic()
        self.last_pong = time.monotonic()


class UIConnection:
    """Represents a connected UI user's WS session."""

    __slots__ = ("ws", "user_id", "role", "connected_at")

    def __init__(self, ws: WebSocket, user_id: int, role: str):
        self.ws = ws
        self.user_id = user_id
        self.role = role
        self.connected_at = time.monotonic()


class WSManager:
    def __init__(self):
        self._agents: dict[str, AgentConnection] = {}  # uuid -> conn
        self._ui_clients: dict[int, list[UIConnection]] = {}  # user_id -> conns
        self._lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Store the main event loop reference for sync-context push."""
        self._loop = loop

    def schedule_broadcast_to_ui(self, message: dict) -> None:
        """Schedule a UI broadcast from a sync context (e.g. heartbeat endpoint)."""
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        asyncio.run_coroutine_threadsafe(self.broadcast_to_ui(message), loop)

    def schedule_send_to_agent(self, agent_uuid: str, message: dict) -> None:
        """Schedule an agent push from a sync context."""
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        asyncio.run_coroutine_threadsafe(self.send_to_agent(agent_uuid, message), loop)

    # --- Agent ---
    async def register_agent(self, ws: WebSocket, agent_uuid: str) -> None:
        old_conn: AgentConnection | None = None
        async with self._lock:
            old_conn = self._agents.get(agent_uuid)
            self._agents[agent_uuid] = AgentConnection(ws=ws, agent_uuid=agent_uuid)
            logger.info(
                "ws agent registered uuid=%s agents=%s",
                agent_uuid,
                len(self._agents),
            )

        if old_conn and old_conn.ws is not ws:
            try:
                await old_conn.ws.close(code=1001, reason="replaced")
            except Exception:
                pass
            logger.warning("ws agent replaced old connection uuid=%s", agent_uuid)

    async def unregister_agent(self, agent_uuid: str, ws: WebSocket | None = None) -> None:
        removed = False
        async with self._lock:
            conn = self._agents.get(agent_uuid)
            if conn is not None and (ws is None or conn.ws is ws):
                del self._agents[agent_uuid]
                removed = True
                count = len(self._agents)
            else:
                count = len(self._agents)
        if removed:
            logger.info("ws agent unregistered uuid=%s agents=%s", agent_uuid, count)

    def get_agent(self, agent_uuid: str) -> Optional[AgentConnection]:
        # NOTE: read-only dict access here intentionally avoids asyncio.Lock.
        # This relies on CPython's GIL for safe concurrent reads from sync threads.
        return self._agents.get(agent_uuid)

    def is_agent_connected(self, agent_uuid: str) -> bool:
        # NOTE: lock-free read; relies on CPython GIL for concurrent dict reads.
        return agent_uuid in self._agents

    async def send_to_agent(self, agent_uuid: str, message: dict) -> bool:
        conn = self.get_agent(agent_uuid)
        if conn is None:
            return False

        try:
            await conn.ws.send_json(message)
            return True
        except (WebSocketDisconnect, ConnectionClosed, RuntimeError) as exc:
            logger.warning("ws send failed agent_uuid=%s err=%s", agent_uuid, exc)
        except Exception as exc:
            logger.warning("ws send unexpected failure agent_uuid=%s err=%s", agent_uuid, exc)

        await self.unregister_agent(agent_uuid, ws=conn.ws)
        return False

    @property
    def agent_count(self) -> int:
        # NOTE: lock-free read; relies on CPython GIL for concurrent dict reads.
        return len(self._agents)

    @property
    def agent_uuids(self) -> list[str]:
        # NOTE: lock-free read; relies on CPython GIL for concurrent dict reads.
        return list(self._agents.keys())

    # --- UI ---
    async def register_ui(self, ws: WebSocket, user_id: int, role: str) -> None:
        async with self._lock:
            bucket = self._ui_clients.setdefault(user_id, [])
            bucket.append(UIConnection(ws=ws, user_id=user_id, role=role))
            total = sum(len(conns) for conns in self._ui_clients.values())
            logger.info("ws ui registered user_id=%s role=%s ui_clients=%s", user_id, role, total)

    async def unregister_ui(self, user_id: int, ws: WebSocket | None = None) -> None:
        removed = False
        async with self._lock:
            conns = self._ui_clients.get(user_id) or []
            if conns:
                if ws is None:
                    removed = bool(conns)
                    self._ui_clients.pop(user_id, None)
                else:
                    kept = [conn for conn in conns if conn.ws is not ws]
                    removed = len(kept) != len(conns)
                    if kept:
                        self._ui_clients[user_id] = kept
                    else:
                        self._ui_clients.pop(user_id, None)
            count = sum(len(items) for items in self._ui_clients.values())
        if removed:
            logger.info("ws ui unregistered user_id=%s ui_clients=%s", user_id, count)

    async def broadcast_to_ui(self, message: dict) -> None:
        clients = [
            (user_id, conn)
            for user_id, conns in list(self._ui_clients.items())
            for conn in list(conns)
        ]
        dead_clients: list[tuple[int, WebSocket]] = []

        for user_id, conn in clients:
            try:
                await conn.ws.send_json(message)
            except (WebSocketDisconnect, ConnectionClosed, RuntimeError) as exc:
                logger.warning("ws ui send failed user_id=%s err=%s", user_id, exc)
                dead_clients.append((user_id, conn.ws))
            except Exception as exc:
                logger.warning("ws ui send unexpected failure user_id=%s err=%s", user_id, exc)
                dead_clients.append((user_id, conn.ws))

        for user_id, ws in dead_clients:
            await self.unregister_ui(user_id, ws=ws)

    @property
    def ui_count(self) -> int:
        # NOTE: lock-free read; relies on CPython GIL for concurrent dict reads.
        return sum(len(conns) for conns in self._ui_clients.values())

    # --- Cleanup ---
    async def close_all(self) -> None:
        async with self._lock:
            agents = list(self._agents.values())
            ui_clients = [conn for conns in self._ui_clients.values() for conn in conns]
            self._agents.clear()
            self._ui_clients.clear()

        for conn in agents:
            try:
                await conn.ws.close(code=1001, reason="server_shutdown")
            except Exception:
                pass

        for conn in ui_clients:
            try:
                await conn.ws.close(code=1001, reason="server_shutdown")
            except Exception:
                pass

        logger.info("ws manager closed all connections")


# Singleton
ws_manager = WSManager()

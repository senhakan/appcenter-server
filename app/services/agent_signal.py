"""In-memory signal registry for agent long-polling wake-up + WS push."""

from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime, timezone

from app.services.ws_manager import ws_manager, make_message

logger = logging.getLogger("appcenter.signal")

_agent_events: dict[str, asyncio.Event] = {}
_agent_loops: dict[str, asyncio.AbstractEventLoop] = {}
_active_listeners: dict[str, datetime] = {}
_state_lock = threading.Lock()


def get_or_create_event(agent_uuid: str) -> asyncio.Event:
    with _state_lock:
        ev = _agent_events.get(agent_uuid)
        if ev is None:
            ev = asyncio.Event()
            _agent_events[agent_uuid] = ev
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # Allow sync/unit-test callers; async endpoint path will register loop.
        pass
    else:
        with _state_lock:
            _agent_loops[agent_uuid] = loop
    return ev


def notify_agent(agent_uuid: str) -> None:
    # 1) Try WS push first via WS manager scheduler (thread-safe).
    if ws_manager.is_agent_connected(agent_uuid):
        ws_manager.schedule_send_to_agent(agent_uuid, make_message("server.signal", {"reason": "wake"}))

    # 2) Always also set the long-poll Event as fallback.
    with _state_lock:
        ev = _agent_events.get(agent_uuid)
        loop = _agent_loops.get(agent_uuid)
    if ev is None:
        return
    if loop is None or loop.is_closed():
        ev.set()
        return
    try:
        loop.call_soon_threadsafe(ev.set)
    except RuntimeError:
        with _state_lock:
            _agent_events.pop(agent_uuid, None)
            _agent_loops.pop(agent_uuid, None)
            _active_listeners.pop(agent_uuid, None)


def mark_listener_active(agent_uuid: str) -> None:
    with _state_lock:
        _active_listeners[agent_uuid] = datetime.now(timezone.utc)


def mark_listener_inactive(agent_uuid: str) -> None:
    with _state_lock:
        _active_listeners.pop(agent_uuid, None)


def is_agent_listening(agent_uuid: str) -> bool:
    with _state_lock:
        return agent_uuid in _active_listeners


def get_listening_agent_uuids() -> list[str]:
    with _state_lock:
        return list(_active_listeners.keys())


def active_listener_count() -> int:
    with _state_lock:
        return len(_active_listeners)


def clear_all() -> None:
    with _state_lock:
        events = list(_agent_events.items())
        loops = dict(_agent_loops)
        _agent_events.clear()
        _agent_loops.clear()
        _active_listeners.clear()

    for agent_uuid, ev in events:
        loop = loops.get(agent_uuid)
        if loop is not None:
            try:
                loop.call_soon_threadsafe(ev.set)
            except RuntimeError:
                pass

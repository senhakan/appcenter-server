"""In-memory signal registry for agent long-polling wake-up."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

_agent_events: dict[str, asyncio.Event] = {}
_agent_loops: dict[str, asyncio.AbstractEventLoop] = {}
_active_listeners: dict[str, datetime] = {}


def get_or_create_event(agent_uuid: str) -> asyncio.Event:
    ev = _agent_events.get(agent_uuid)
    if ev is None:
        ev = asyncio.Event()
        _agent_events[agent_uuid] = ev
    try:
        _agent_loops[agent_uuid] = asyncio.get_running_loop()
    except RuntimeError:
        # Allow sync/unit-test callers; async endpoint path will register loop.
        pass
    return ev


def notify_agent(agent_uuid: str) -> None:
    ev = _agent_events.get(agent_uuid)
    if ev is None:
        return
    loop = _agent_loops.get(agent_uuid)
    if loop is None:
        # Fallback for sync/test contexts.
        ev.set()
        return
    try:
        loop.call_soon_threadsafe(ev.set)
    except RuntimeError:
        # Event loop may be closed during shutdown/reload.
        _agent_events.pop(agent_uuid, None)
        _agent_loops.pop(agent_uuid, None)
        _active_listeners.pop(agent_uuid, None)


def mark_listener_active(agent_uuid: str) -> None:
    _active_listeners[agent_uuid] = datetime.now(timezone.utc)


def mark_listener_inactive(agent_uuid: str) -> None:
    _active_listeners.pop(agent_uuid, None)


def is_agent_listening(agent_uuid: str) -> bool:
    return agent_uuid in _active_listeners


def get_listening_agent_uuids() -> list[str]:
    return list(_active_listeners.keys())


def active_listener_count() -> int:
    return len(_active_listeners)


def clear_all() -> None:
    for agent_uuid, ev in list(_agent_events.items()):
        loop = _agent_loops.get(agent_uuid)
        if loop is not None:
            try:
                loop.call_soon_threadsafe(ev.set)
            except RuntimeError:
                pass
    _agent_events.clear()
    _agent_loops.clear()
    _active_listeners.clear()

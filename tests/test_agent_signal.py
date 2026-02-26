"""Tests for the agent signal (long-polling wake-up) service."""

import asyncio

import pytest

from app.services import agent_signal


@pytest.fixture(autouse=True)
def _clean():
    agent_signal.clear_all()
    yield
    agent_signal.clear_all()


def test_get_or_create_event_returns_same_instance():
    ev1 = agent_signal.get_or_create_event("aaa")
    ev2 = agent_signal.get_or_create_event("aaa")
    assert ev1 is ev2


def test_notify_sets_event():
    ev = agent_signal.get_or_create_event("bbb")
    assert not ev.is_set()
    agent_signal.notify_agent("bbb")
    assert ev.is_set()


def test_notify_nonexistent_agent_is_noop():
    agent_signal.notify_agent("no-such-agent")


def test_listener_tracking():
    assert not agent_signal.is_agent_listening("ccc")
    agent_signal.mark_listener_active("ccc")
    assert agent_signal.is_agent_listening("ccc")
    assert agent_signal.active_listener_count() == 1
    assert "ccc" in agent_signal.get_listening_agent_uuids()
    agent_signal.mark_listener_inactive("ccc")
    assert not agent_signal.is_agent_listening("ccc")
    assert agent_signal.active_listener_count() == 0


@pytest.mark.asyncio
async def test_signal_immediate_wake():
    ev = agent_signal.get_or_create_event("ddd")
    agent_signal.notify_agent("ddd")
    await asyncio.wait_for(ev.wait(), timeout=1)
    assert ev.is_set()


@pytest.mark.asyncio
async def test_signal_timeout():
    ev = agent_signal.get_or_create_event("eee")
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(ev.wait(), timeout=0.1)


def test_clear_all():
    agent_signal.get_or_create_event("f1")
    agent_signal.mark_listener_active("f1")
    agent_signal.get_or_create_event("f2")
    agent_signal.clear_all()
    assert agent_signal.active_listener_count() == 0
    assert agent_signal.get_listening_agent_uuids() == []

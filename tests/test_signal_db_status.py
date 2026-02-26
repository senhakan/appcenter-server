from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.api.v1.agent import _mark_agent_offline_if_signal_stale, _mark_agent_online_from_signal
from app.database import SessionLocal
from app.models import Agent


def _register_agent(client, uid: str) -> None:
    resp = client.post(
        "/api/v1/agent/register",
        json={
            "uuid": uid,
            "hostname": uid,
            "os_version": "Windows 11",
            "agent_version": "1.0.0",
        },
    )
    assert resp.status_code == 200


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def test_signal_connect_marks_agent_online_and_updates_last_seen(client):
    uid = "signal-db-online-1"
    _register_agent(client, uid)

    db = SessionLocal()
    try:
        agent = db.query(Agent).filter(Agent.uuid == uid).first()
        assert agent is not None
        agent.status = "offline"
        agent.last_seen = datetime.now(timezone.utc) - timedelta(minutes=10)
        db.add(agent)
        db.commit()
    finally:
        db.close()

    _mark_agent_online_from_signal(uid)

    db = SessionLocal()
    try:
        agent = db.query(Agent).filter(Agent.uuid == uid).first()
        assert agent is not None
        assert agent.status == "online"
        assert agent.last_seen is not None
        assert datetime.now(timezone.utc) - _as_utc(agent.last_seen) < timedelta(seconds=5)
    finally:
        db.close()


def test_stale_disconnect_marks_agent_offline(client):
    uid = "signal-db-offline-1"
    _register_agent(client, uid)
    _mark_agent_online_from_signal(uid)

    disconnected_at = datetime.now(timezone.utc)
    _mark_agent_offline_if_signal_stale(uid, disconnected_at)

    db = SessionLocal()
    try:
        agent = db.query(Agent).filter(Agent.uuid == uid).first()
        assert agent is not None
        assert agent.status == "offline"
    finally:
        db.close()


def test_reconnect_with_new_last_seen_keeps_agent_online(client):
    uid = "signal-db-race-1"
    _register_agent(client, uid)
    _mark_agent_online_from_signal(uid)
    disconnected_at = datetime.now(timezone.utc)

    db = SessionLocal()
    try:
        agent = db.query(Agent).filter(Agent.uuid == uid).first()
        assert agent is not None
        agent.status = "online"
        agent.last_seen = disconnected_at + timedelta(seconds=1)
        db.add(agent)
        db.commit()
    finally:
        db.close()

    _mark_agent_offline_if_signal_stale(uid, disconnected_at)

    db = SessionLocal()
    try:
        agent = db.query(Agent).filter(Agent.uuid == uid).first()
        assert agent is not None
        assert agent.status == "online"
    finally:
        db.close()

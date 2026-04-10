from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import RemoteSupportSession, User
from tests.test_phase5_api import _register_agent


def test_settings_accept_remote_support_helper_flags(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = client.put(
        "/api/v1/settings",
        headers=auth_headers,
        json={
            "values": {
                "remote_support_helper_connection_overlay_enabled": "true",
                "remote_support_helper_show_operator_name_enabled": "true",
            }
        },
    )
    assert resp.status_code == 200

    items = {item["key"]: item["value"] for item in resp.json()["items"]}
    assert items["remote_support_helper_connection_overlay_enabled"] == "true"
    assert items["remote_support_helper_show_operator_name_enabled"] == "true"


def test_agent_approve_returns_helper_flags_and_operator_name(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    settings_resp = client.put(
        "/api/v1/settings",
        headers=auth_headers,
        json={
            "values": {
                "remote_support_helper_connection_overlay_enabled": "true",
                "remote_support_helper_show_operator_name_enabled": "true",
            }
        },
    )
    assert settings_resp.status_code == 200

    agent_headers = _register_agent(client, uuid="agent-rs-helper-settings-1")

    with SessionLocal() as db:
        admin = db.query(User).filter(User.username == "admin").first()
        assert admin is not None
        session = RemoteSupportSession(
            agent_uuid="agent-rs-helper-settings-1",
            admin_user_id=admin.id,
            status="pending_approval",
            reason="Helper flags test",
            vnc_password="test-pass-123",
            requested_at=datetime.now(timezone.utc),
            approval_timeout_at=datetime.now(timezone.utc) + timedelta(seconds=60),
            max_duration_min=60,
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        session_id = session.id

    approve_resp = client.post(
        f"/api/v1/agent/remote-support/{session_id}/approve",
        headers=agent_headers,
        json={"approved": True, "monitor_count": 1},
    )
    assert approve_resp.status_code == 200
    body = approve_resp.json()
    assert body["status"] == "ok"
    assert body["helper_connection_overlay_enabled"] is True
    assert body["helper_user_display_name"] == "admin"
    assert body["vnc_password"] == "test-pass-123"

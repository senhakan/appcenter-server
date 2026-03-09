from __future__ import annotations

import uuid


def _ws_msg(msg_type: str, payload: dict) -> dict:
    return {"type": msg_type, "payload": payload}


def test_ws_inventory_hash_triggers_sync_required(client, auth_headers):
    agent_uuid = str(uuid.uuid4())
    reg = client.post(
        "/api/v1/agent/register",
        json={
            "uuid": agent_uuid,
            "hostname": "ws-test-pc",
            "os_version": "Windows 11",
            "agent_version": "1.0.0",
        },
    )
    assert reg.status_code == 200
    secret = reg.json()["secret_key"]

    updated = client.put(
        "/api/v1/settings",
        headers=auth_headers,
        json={"values": {"ws_agent_enabled": "true"}},
    )
    assert updated.status_code == 200

    with client.websocket_connect("/api/v1/agent/ws") as ws:
        ws.send_json(_ws_msg("agent.auth", {"uuid": agent_uuid, "secret": secret}))
        auth_ok = ws.receive_json()
        assert auth_ok["type"] == "server.auth.ok"

        ws.send_json(
            _ws_msg(
                "agent.hello",
                {
                    "hostname": "ws-test-pc",
                    "os_version": "Windows 11",
                    "version": "1.0.0",
                    "platform": "windows",
                    "arch": "amd64",
                    "ip_address": "10.1.1.1",
                },
            )
        )
        hello = ws.receive_json()
        assert hello["type"] == "server.hello"

        ws.send_json(_ws_msg("agent.inventory.hash", {"hash": "ws-inv-hash-1"}))
        sync_required = ws.receive_json()
        assert sync_required["type"] == "server.inventory.sync_required"

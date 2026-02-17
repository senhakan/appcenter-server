from __future__ import annotations

import uuid


def _register_agent(client, agent_uuid=None):
    uid = agent_uuid or str(uuid.uuid4())
    resp = client.post("/api/v1/agent/register", json={
        "uuid": uid,
        "hostname": "test-pc",
        "os_version": "Windows 11",
        "agent_version": "0.1.0",
    })
    assert resp.status_code == 200
    secret = resp.json()["secret_key"]
    headers = {"X-Agent-UUID": uid, "X-Agent-Secret": secret}
    return uid, headers


def _admin_headers(client):
    login = client.post('/api/v1/auth/login', json={'username': 'admin', 'password': 'admin123'})
    assert login.status_code == 200
    token = login.json()['access_token']
    return {'Authorization': f'Bearer {token}'}


def test_system_profile_persist_and_history(client):
    uid, headers = _register_agent(client)
    admin = _admin_headers(client)

    p1 = {
        "os_full_name": "Windows 11 Pro",
        "os_version": "10.0.22000",
        "build_number": "22000",
        "architecture": "64-bit",
        "manufacturer": "HP",
        "model": "EliteDesk",
        "cpu_model": "Intel(R) Core(TM) i7",
        "cpu_cores_physical": 4,
        "cpu_cores_logical": 8,
        "total_memory_gb": 16,
        "disk_count": 1,
        "disks": [{"index": 0, "size_gb": 512, "model": "NVMe", "bus_type": "NVMe"}],
        "virtualization": {"is_virtual": False, "vendor": None, "model": None},
    }

    hb1 = client.post("/api/v1/agent/heartbeat", json={
        "hostname": "test-pc",
        "system_profile": p1,
    }, headers=headers)
    assert hb1.status_code == 200

    detail = client.get(f"/api/v1/agents/{uid}", headers=admin)
    assert detail.status_code == 200
    body = detail.json()
    assert body["system_profile"]["os_full_name"] == "Windows 11 Pro"
    assert body["system_profile_updated_at"] is not None

    hist1 = client.get(f"/api/v1/agents/{uid}/system/history?limit=50&offset=0", headers=admin)
    assert hist1.status_code == 200
    j1 = hist1.json()
    assert j1["total"] == 1
    assert "initial" in (j1["items"][0]["changed_fields"] or [])

    # Second report with a change should create another history row.
    p2 = dict(p1)
    p2["cpu_model"] = "Intel(R) Core(TM) i9"
    hb2 = client.post("/api/v1/agent/heartbeat", json={
        "hostname": "test-pc",
        "system_profile": p2,
    }, headers=headers)
    assert hb2.status_code == 200

    hist2 = client.get(f"/api/v1/agents/{uid}/system/history?limit=50&offset=0", headers=admin)
    assert hist2.status_code == 200
    j2 = hist2.json()
    assert j2["total"] == 2
    assert "cpu_model" in (j2["items"][0]["changed_fields"] or [])
    diff = j2["items"][0].get("diff") or []
    assert any(d.get("field") == "cpu_model" and d.get("old") == p1["cpu_model"] and d.get("new") == p2["cpu_model"] for d in diff)

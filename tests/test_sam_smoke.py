from __future__ import annotations

import uuid


def _register_agent(client, agent_uuid: str | None = None) -> tuple[str, dict[str, str]]:
    uid = agent_uuid or str(uuid.uuid4())
    resp = client.post(
        "/api/v1/agent/register",
        json={
            "uuid": uid,
            "hostname": "sam-smoke-host",
            "os_version": "Ubuntu 24.04",
            "agent_version": "1.0.0",
            "platform": "linux",
        },
    )
    assert resp.status_code == 200
    secret = resp.json()["secret_key"]
    return uid, {"X-Agent-UUID": uid, "X-Agent-Secret": secret}


def test_sam_api_smoke(client, auth_headers):
    uid, agent_headers = _register_agent(client)
    inv = client.post(
        "/api/v1/agent/inventory",
        headers=agent_headers,
        json={
            "inventory_hash": "sam-smoke-1",
            "software_count": 2,
            "items": [
                {"name": "Smoke Tool 1", "version": "1.0.0", "publisher": "Microsoft Corporation"},
                {"name": "Smoke Tool 2", "version": "2.0.0", "publisher": "Google LLC"},
            ],
        },
    )
    assert inv.status_code == 200

    lic = client.post(
        "/api/v1/licenses",
        headers=auth_headers,
        json={
            "software_name_pattern": "Smoke Tool 1",
            "match_type": "exact",
            "total_licenses": 1,
            "license_type": "licensed",
        },
    )
    assert lic.status_code == 201

    dashboard = client.get("/api/v1/sam/dashboard", headers=auth_headers)
    assert dashboard.status_code == 200
    assert "platform_items" in dashboard.json()

    catalog = client.get("/api/v1/sam/catalog?platform=linux&page=1&per_page=20", headers=auth_headers)
    assert catalog.status_code == 200
    assert catalog.json()["page"] == 1

    trends = client.get("/api/v1/inventory/trends?days=30", headers=auth_headers)
    assert trends.status_code == 200
    assert trends.json()["summary"]["days"] == 30

    recs = client.get("/api/v1/licenses/recommendations?limit=20", headers=auth_headers)
    assert recs.status_code == 200
    assert "items" in recs.json()

    perf = client.get("/api/v1/sam/performance", headers=auth_headers)
    assert perf.status_code == 200
    pdata = perf.json()
    assert "checks" in pdata and len(pdata["checks"]) >= 4
    assert all("duration_ms" in c for c in pdata["checks"])

    inv_list = client.get(f"/api/v1/agents/{uid}/inventory", headers=auth_headers)
    assert inv_list.status_code == 200
    assert inv_list.json()["total"] >= 2


def test_sam_ui_routes_smoke(client):
    paths = [
        "/inventory/sam-dashboard",
        "/inventory/catalog",
        "/inventory/reports",
        "/inventory/risk",
        "/inventory/normalization",
        "/licenses",
    ]
    for path in paths:
        resp = client.get(path)
        assert resp.status_code == 200
        assert "<html" in resp.text.lower()

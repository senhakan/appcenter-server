"""Tests for the inventory & license management module."""
from __future__ import annotations

import uuid


def _register_agent(client, agent_uuid=None):
    """Register an agent and return (uuid, secret, headers)."""
    uid = agent_uuid or str(uuid.uuid4())
    resp = client.post("/api/v1/agent/register", json={
        "uuid": uid,
        "hostname": "test-pc",
        "os_version": "Windows 10",
        "agent_version": "1.0.0",
    })
    assert resp.status_code == 200
    secret = resp.json()["secret_key"]
    headers = {"X-Agent-UUID": uid, "X-Agent-Secret": secret}
    return uid, secret, headers


SAMPLE_ITEMS = [
    {"name": "Google Chrome", "version": "120.0.1", "publisher": "Google", "architecture": "x64"},
    {"name": "Mozilla Firefox", "version": "121.0", "publisher": "Mozilla"},
    {"name": "7-Zip", "version": "23.01", "publisher": "Igor Pavlov"},
]


# --- Test 1: Full inventory flow with heartbeat hash ---


def test_inventory_heartbeat_flow(client):
    uid, secret, headers = _register_agent(client)

    # Heartbeat with hash → sync_required=True (first time, no hash stored)
    hb = client.post("/api/v1/agent/heartbeat", json={
        "hostname": "test-pc",
        "inventory_hash": "abc123",
        "logged_in_sessions": [
            {"username": "TEST\\alice", "session_type": "rdp", "logon_id": "999"},
        ],
    }, headers=headers)
    assert hb.status_code == 200
    config = hb.json()["config"]
    assert config["inventory_sync_required"] is True

    # Verify sessions are persisted and exposed on agent detail endpoint
    # (requires admin auth; use default admin credentials seeded on startup).
    login = client.post('/api/v1/auth/login', json={'username': 'admin', 'password': 'admin123'})
    assert login.status_code == 200
    token = login.json()['access_token']
    auth_headers = {'Authorization': f'Bearer {token}'}
    detail = client.get(f"/api/v1/agents/{uid}", headers=auth_headers)
    assert detail.status_code == 200
    data = detail.json()
    assert data["logged_in_sessions"] == [{"username": "TEST\\alice", "session_type": "rdp", "logon_id": "999"}]
    assert data["logged_in_sessions_updated_at"] is not None

    # Submit inventory
    resp = client.post("/api/v1/agent/inventory", json={
        "inventory_hash": "abc123",
        "software_count": len(SAMPLE_ITEMS),
        "items": SAMPLE_ITEMS,
    }, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["changes"] == {"installed": 0, "removed": 0, "updated": 0}

    # Heartbeat with same hash → sync_required=False
    hb2 = client.post("/api/v1/agent/heartbeat", json={
        "hostname": "test-pc", "inventory_hash": "abc123",
    }, headers=headers)
    assert hb2.status_code == 200
    assert hb2.json()["config"]["inventory_sync_required"] is False

    # Heartbeat with different hash → sync_required=True
    hb3 = client.post("/api/v1/agent/heartbeat", json={
        "hostname": "test-pc", "inventory_hash": "def456",
    }, headers=headers)
    assert hb3.status_code == 200
    assert hb3.json()["config"]["inventory_sync_required"] is True


# --- Test 2: Diff/change history on second submission ---


def test_inventory_diff_change_history(client):
    uid, secret, headers = _register_agent(client)

    # First submission (no change history written)
    client.post("/api/v1/agent/inventory", json={
        "inventory_hash": "h1",
        "software_count": 2,
        "items": [
            {"name": "App A", "version": "1.0"},
            {"name": "App B", "version": "2.0"},
        ],
    }, headers=headers)

    # Second submission: App A updated, App B removed, App C installed
    resp = client.post("/api/v1/agent/inventory", json={
        "inventory_hash": "h2",
        "software_count": 2,
        "items": [
            {"name": "App A", "version": "1.1"},
            {"name": "App C", "version": "3.0"},
        ],
    }, headers=headers)
    assert resp.status_code == 200
    changes = resp.json()["changes"]
    assert changes["updated"] == 1
    assert changes["removed"] == 1
    assert changes["installed"] == 1


# --- Test 3: First inventory should NOT create change history ---


def test_first_inventory_no_change_history(client, auth_headers):
    uid, secret, headers = _register_agent(client)

    client.post("/api/v1/agent/inventory", json={
        "inventory_hash": "first",
        "software_count": 1,
        "items": [{"name": "Solo App", "version": "1.0"}],
    }, headers=headers)

    resp = client.get(f"/api/v1/agents/{uid}/inventory/changes", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


# --- Test 4: Normalization CRUD ---


def test_normalization_crud(client, auth_headers):
    # Create
    resp = client.post("/api/v1/inventory/normalization", json={
        "pattern": "Chrome",
        "normalized_name": "Google Chrome",
        "match_type": "contains",
    }, headers=auth_headers)
    assert resp.status_code == 201
    rule_id = resp.json()["id"]

    # List
    resp = client.get("/api/v1/inventory/normalization", headers=auth_headers)
    assert resp.status_code == 200
    assert any(r["id"] == rule_id for r in resp.json()["items"])

    # Update
    resp = client.put(f"/api/v1/inventory/normalization/{rule_id}", json={
        "normalized_name": "Chrome Browser",
    }, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["normalized_name"] == "Chrome Browser"

    # Delete
    resp = client.delete(f"/api/v1/inventory/normalization/{rule_id}", headers=auth_headers)
    assert resp.status_code == 200


# --- Test 5: License CRUD ---


def test_license_crud(client, auth_headers):
    # Create
    resp = client.post("/api/v1/licenses", json={
        "software_name_pattern": "Microsoft Office",
        "match_type": "contains",
        "total_licenses": 50,
        "license_type": "licensed",
        "description": "Office suite",
    }, headers=auth_headers)
    assert resp.status_code == 201
    lic_id = resp.json()["id"]

    # List
    resp = client.get("/api/v1/licenses", headers=auth_headers)
    assert resp.status_code == 200
    assert any(l["id"] == lic_id for l in resp.json()["items"])

    # Get
    resp = client.get(f"/api/v1/licenses/{lic_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["software_name_pattern"] == "Microsoft Office"

    # Update
    resp = client.put(f"/api/v1/licenses/{lic_id}", json={
        "total_licenses": 100,
    }, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["total_licenses"] == 100

    # Delete
    resp = client.delete(f"/api/v1/licenses/{lic_id}", headers=auth_headers)
    assert resp.status_code == 200


# --- Test 6: License usage report ---


def test_license_usage_report(client, auth_headers):
    uid, secret, headers = _register_agent(client)

    # Submit inventory with a known software
    client.post("/api/v1/agent/inventory", json={
        "inventory_hash": "lic-test",
        "software_count": 1,
        "items": [{"name": "Forbidden Tool", "version": "1.0"}],
    }, headers=headers)

    # Create prohibited license
    resp = client.post("/api/v1/licenses", json={
        "software_name_pattern": "Forbidden Tool",
        "match_type": "exact",
        "license_type": "prohibited",
    }, headers=auth_headers)
    assert resp.status_code == 201

    # Create licensed with insufficient count
    resp = client.post("/api/v1/licenses", json={
        "software_name_pattern": "Forbidden Tool",
        "match_type": "exact",
        "total_licenses": 0,
        "license_type": "licensed",
    }, headers=auth_headers)
    assert resp.status_code == 201

    # Check report
    resp = client.get("/api/v1/licenses/report", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    prohibited = [i for i in items if i["license_type"] == "prohibited" and i["pattern"] == "Forbidden Tool"]
    assert len(prohibited) >= 1
    assert prohibited[0]["is_violation"] is True


# --- Test 7: Dashboard stats ---


def test_inventory_dashboard_stats(client, auth_headers):
    resp = client.get("/api/v1/inventory/dashboard", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "total_unique_software" in data
    assert "license_violations" in data
    assert "prohibited_alerts" in data
    assert "agents_with_inventory" in data
    assert "added_today" in data
    assert "removed_today" in data


# --- Test 8: Agent inventory query + software summary ---


def test_agent_inventory_and_software_summary(client, auth_headers):
    uid, secret, headers = _register_agent(client)

    client.post("/api/v1/agent/inventory", json={
        "inventory_hash": "query-test",
        "software_count": 2,
        "items": [
            {"name": "QueryApp Alpha", "version": "1.0"},
            {"name": "QueryApp Beta", "version": "2.0"},
        ],
    }, headers=headers)

    # Agent inventory
    resp = client.get(f"/api/v1/agents/{uid}/inventory", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["total"] == 2

    # Software summary
    resp = client.get("/api/v1/inventory/software?search=QueryApp", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["total"] >= 2

    # Software agents
    resp = client.get("/api/v1/inventory/software/QueryApp Alpha/agents", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


# --- Test 9: Cleanup old change history ---


def test_cleanup_old_change_history(client):
    from datetime import datetime, timedelta, timezone
    from app.database import SessionLocal
    from app.models import SoftwareChangeHistory
    from app.services.inventory_service import cleanup_old_change_history

    uid, secret, headers = _register_agent(client)

    # First + second inventory to generate change history
    client.post("/api/v1/agent/inventory", json={
        "inventory_hash": "c1", "software_count": 1,
        "items": [{"name": "OldApp", "version": "1.0"}],
    }, headers=headers)
    client.post("/api/v1/agent/inventory", json={
        "inventory_hash": "c2", "software_count": 0, "items": [],
    }, headers=headers)

    db = SessionLocal()
    try:
        # Backdate the change history record
        records = db.query(SoftwareChangeHistory).filter(
            SoftwareChangeHistory.agent_uuid == uid
        ).all()
        assert len(records) > 0
        for r in records:
            r.detected_at = datetime.now(timezone.utc) - timedelta(days=100)
        db.commit()

        deleted = cleanup_old_change_history(db, 90)
        assert deleted >= 1
    finally:
        db.close()

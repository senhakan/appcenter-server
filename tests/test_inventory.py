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
    assert len(data["logged_in_sessions"]) == 1
    session = data["logged_in_sessions"][0]
    assert session["username"] == "TEST\\alice"
    assert session["session_type"] == "rdp"
    assert session["logon_id"] == "999"
    assert session.get("session_state") in {None, "active", "disconnected"}
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


def test_sam_risk_overview_and_policy_crud(client, auth_headers):
    uid, _secret, headers = _register_agent(client)
    client.post("/api/v1/agent/inventory", json={
        "inventory_hash": "risk-1",
        "software_count": 1,
        "items": [{"name": "Legacy Suite", "version": "5.2"}],
    }, headers=headers)

    p = client.post("/api/v1/sam/lifecycle-policies", json={
        "software_name_pattern": "Legacy Suite",
        "match_type": "exact",
        "platform": "windows",
        "eol_date": "2026-01-01T00:00:00Z",
        "eos_date": "2026-02-01T00:00:00Z",
        "is_active": True,
    }, headers=auth_headers)
    assert p.status_code == 201

    c = client.post("/api/v1/sam/cost-profiles", json={
        "software_name_pattern": "Legacy Suite",
        "match_type": "exact",
        "platform": "windows",
        "monthly_cost_cents": 12345,
        "currency": "USD",
        "is_active": True,
    }, headers=auth_headers)
    assert c.status_code == 201

    risk = client.get("/api/v1/sam/risk-overview?platform=windows&search=Legacy", headers=auth_headers)
    assert risk.status_code == 200
    payload = risk.json()
    assert payload["total"] >= 1
    first = payload["items"][0]
    assert first["software_name"] == "Legacy Suite"
    assert first["platform"] == "windows"
    assert first["estimated_monthly_cost_cents"] >= 12345
    assert first["lifecycle_status"] in {"eol", "eos"}

    del_policy = client.delete(f"/api/v1/sam/lifecycle-policies/{p.json()['id']}", headers=auth_headers)
    del_cost = client.delete(f"/api/v1/sam/cost-profiles/{c.json()['id']}", headers=auth_headers)
    assert del_policy.status_code == 200
    assert del_cost.status_code == 200


def test_sam_schedule_runner_generates_files(client, auth_headers):
    from datetime import datetime, timedelta, timezone

    from app.database import SessionLocal
    from app.models import SamReportSchedule
    from app.tasks.scheduler import run_due_sam_report_schedules

    uid, _secret, headers = _register_agent(client)
    client.post("/api/v1/agent/inventory", json={
        "inventory_hash": "sched-1",
        "software_count": 1,
        "items": [{"name": "Sched App", "version": "1.0"}],
    }, headers=headers)

    create = client.post("/api/v1/sam/report-schedules", json={
        "name": "test minute",
        "report_type": "sam_catalog",
        "format": "csv",
        "cron_expr": "* * * * *",
        "recipients": None,
        "is_active": True,
    }, headers=auth_headers)
    assert create.status_code == 201
    sched_id = create.json()["id"]
    assert create.json()["next_run_at"] is not None

    db = SessionLocal()
    try:
        item = db.query(SamReportSchedule).filter(SamReportSchedule.id == sched_id).first()
        assert item is not None
        item.next_run_at = datetime.now(timezone.utc) - timedelta(minutes=2)
        db.add(item)
        db.commit()
    finally:
        db.close()

    run_due_sam_report_schedules()

    files = client.get("/api/v1/sam/reports/generated?limit=20", headers=auth_headers)
    assert files.status_code == 200
    payload = files.json()
    assert payload["total"] >= 1
    assert any(str(x.get("filename", "")).startswith("sam_catalog_schedule_") for x in payload["items"])


def test_inventory_trends_endpoint(client, auth_headers):
    uid, _secret, headers = _register_agent(client)
    client.post("/api/v1/agent/inventory", json={
        "inventory_hash": "trend-1",
        "software_count": 1,
        "items": [{"name": "Trend App", "version": "1.0"}],
    }, headers=headers)
    client.post("/api/v1/agent/inventory", json={
        "inventory_hash": "trend-2",
        "software_count": 1,
        "items": [{"name": "Trend App", "version": "1.1"}],
    }, headers=headers)
    resp = client.get("/api/v1/inventory/trends?days=14", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "points" in data and isinstance(data["points"], list)
    assert "alerts" in data and isinstance(data["alerts"], list)
    assert "summary" in data and isinstance(data["summary"], dict)
    assert data["summary"]["days"] == 14


def test_license_recommendations_endpoint(client, auth_headers):
    uid, _secret, headers = _register_agent(client)
    client.post("/api/v1/agent/inventory", json={
        "inventory_hash": "rec-1",
        "software_count": 1,
        "items": [{"name": "Forbidden Rec Tool", "version": "1.0"}],
    }, headers=headers)
    create = client.post("/api/v1/licenses", json={
        "software_name_pattern": "Forbidden Rec Tool",
        "match_type": "exact",
        "license_type": "prohibited",
    }, headers=auth_headers)
    assert create.status_code == 201
    rec = client.get("/api/v1/licenses/recommendations?limit=20", headers=auth_headers)
    assert rec.status_code == 200
    payload = rec.json()
    assert payload["total"] >= 1
    assert any(i["pattern"] == "Forbidden Rec Tool" for i in payload["items"])


def test_publisher_normalization_on_inventory(client, auth_headers):
    uid, _secret, headers = _register_agent(client)
    client.post("/api/v1/agent/inventory", json={
        "inventory_hash": "pub-1",
        "software_count": 1,
        "items": [{"name": "Publisher App", "version": "1.0", "publisher": "Microsoft Corporation"}],
    }, headers=headers)
    inv = client.get(f"/api/v1/agents/{uid}/inventory", headers=auth_headers)
    assert inv.status_code == 200
    assert inv.json()["total"] == 1
    first = inv.json()["items"][0]
    assert first["publisher"] == "Microsoft"
    assert first["normalized_publisher"] == "Microsoft"

from __future__ import annotations

from app.database import SessionLocal
from app.models import Agent, TaskHistory


def test_dashboard_timeline_includes_task(client, auth_headers):
    uid = "dash-tl-agent"
    # Insert agent + task directly.
    db = SessionLocal()
    try:
        if not db.query(Agent).filter(Agent.uuid == uid).first():
            db.add(Agent(uuid=uid, hostname="dash-host", status="online"))
            db.commit()
        db.add(TaskHistory(agent_uuid=uid, action="install", status="success", message="dash-test"))
        db.commit()
    finally:
        db.close()

    resp = client.get("/api/v1/dashboard/timeline", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json().get("items") or []
    assert any(i.get("event_type") == "task" for i in items)


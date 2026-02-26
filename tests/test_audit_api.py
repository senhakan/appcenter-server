from __future__ import annotations

import uuid

from fastapi.testclient import TestClient


def _create_user(client: TestClient, auth_headers: dict[str, str], role: str) -> str:
    username = f"audit_{role}_{uuid.uuid4().hex[:8]}"
    res = client.post(
        "/api/v1/users",
        headers=auth_headers,
        json={
            "username": username,
            "password": "pass1234",
            "role": role,
            "is_active": True,
        },
    )
    assert res.status_code == 201
    return username


def _login_headers(client: TestClient, username: str, password: str = "pass1234") -> dict[str, str]:
    login = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_audit_logs_admin_only_and_filter(client: TestClient, auth_headers: dict[str, str]) -> None:
    username = _create_user(client, auth_headers, "operator")
    operator_headers = _login_headers(client, username)

    denied = client.get("/api/v1/audit/logs", headers=operator_headers)
    assert denied.status_code == 403

    ok = client.get("/api/v1/audit/logs", headers=auth_headers)
    assert ok.status_code == 200
    assert isinstance(ok.json().get("items"), list)

    filtered = client.get("/api/v1/audit/logs", headers=auth_headers, params={"action": "user.create"})
    assert filtered.status_code == 200
    assert filtered.json()["total"] >= 1

    future = client.get("/api/v1/audit/logs", headers=auth_headers, params={"created_from": "2999-01-01"})
    assert future.status_code == 200
    assert future.json()["total"] == 0

    invalid = client.get("/api/v1/audit/logs", headers=auth_headers, params={"created_from": "bad-date"})
    assert invalid.status_code == 400

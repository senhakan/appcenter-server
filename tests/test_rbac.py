from __future__ import annotations

import uuid

from fastapi.testclient import TestClient


def _unique_username(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _create_user(client: TestClient, admin_headers: dict[str, str], role: str) -> str:
    username = _unique_username(role)
    res = client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "username": username,
            "password": "pass1234",
            "full_name": f"{role.title()} User",
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


def test_rbac_access_matrix(client: TestClient, auth_headers: dict[str, str]) -> None:
    viewer_username = _create_user(client, auth_headers, "viewer")
    operator_username = _create_user(client, auth_headers, "operator")

    viewer_headers = _login_headers(client, viewer_username)
    operator_headers = _login_headers(client, operator_username)

    viewer_agents = client.get("/api/v1/agents", headers=viewer_headers)
    assert viewer_agents.status_code == 200

    viewer_groups_create = client.post("/api/v1/groups", headers=viewer_headers, json={"name": _unique_username("grp")})
    assert viewer_groups_create.status_code == 403

    operator_groups_create = client.post(
        "/api/v1/groups",
        headers=operator_headers,
        json={"name": _unique_username("grp")},
    )
    assert operator_groups_create.status_code == 200

    viewer_settings = client.get("/api/v1/settings", headers=viewer_headers)
    assert viewer_settings.status_code == 403

    operator_settings = client.put(
        "/api/v1/settings",
        headers=operator_headers,
        json={"values": {"heartbeat_interval_sec": "55"}},
    )
    assert operator_settings.status_code == 403

    me = client.get("/api/v1/auth/me", headers=operator_headers)
    assert me.status_code == 200
    assert me.json()["role"] == "operator"


def test_user_management_admin_only_and_last_admin_protection(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    operator_username = _create_user(client, auth_headers, "operator")
    operator_headers = _login_headers(client, operator_username)

    operator_users_list = client.get("/api/v1/users", headers=operator_headers)
    assert operator_users_list.status_code == 403

    users_list = client.get("/api/v1/users", headers=auth_headers)
    assert users_list.status_code == 200
    admin_user = next((u for u in users_list.json()["items"] if u["username"] == "admin"), None)
    assert admin_user is not None

    delete_admin = client.delete(f"/api/v1/users/{admin_user['id']}", headers=auth_headers)
    assert delete_admin.status_code == 400

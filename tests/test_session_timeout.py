from __future__ import annotations


def test_settings_session_timeout_validation(client, auth_headers):
    ok = client.put(
        "/api/v1/settings",
        headers=auth_headers,
        json={"values": {"session_timeout_minutes": "45"}},
    )
    assert ok.status_code == 200, ok.text

    bad = client.put(
        "/api/v1/settings",
        headers=auth_headers,
        json={"values": {"session_timeout_minutes": "0"}},
    )
    assert bad.status_code == 400, bad.text


def test_login_and_extend_respect_session_timeout_setting(client, auth_headers):
    save = client.put(
        "/api/v1/settings",
        headers=auth_headers,
        json={"values": {"session_timeout_minutes": "2"}},
    )
    assert save.status_code == 200, save.text

    login = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    assert login.status_code == 200, login.text
    body = login.json()
    assert body["expires_in_sec"] == 120
    assert body["expires_at"]

    token = body["access_token"]
    ext = client.post("/api/v1/auth/extend", headers={"Authorization": f"Bearer {token}"})
    assert ext.status_code == 200, ext.text
    ext_body = ext.json()
    assert ext_body["expires_in_sec"] == 120
    assert ext_body["expires_at"]

from __future__ import annotations

from app.services import ldap_service


def _set_auth_settings(client, auth_headers, **values):
    payload = {"values": {k: str(v).lower() if isinstance(v, bool) else str(v) for k, v in values.items()}}
    res = client.put("/api/v1/settings", headers=auth_headers, json=payload)
    assert res.status_code == 200, res.text


def test_ldap_login_and_jit_create(client, auth_headers, monkeypatch):
    monkeypatch.setattr(ldap_service.settings, "ldap_server_uri", "ldap://127.0.0.1:1389")
    monkeypatch.setattr(ldap_service.settings, "ldap_use_ssl", False)
    monkeypatch.setattr(ldap_service.settings, "ldap_start_tls", False)
    monkeypatch.setattr(ldap_service.settings, "ldap_bind_dn", "cn=admin,dc=appcenter,dc=local")
    monkeypatch.setattr(ldap_service.settings, "ldap_bind_password", "admin123")
    monkeypatch.setattr(ldap_service.settings, "ldap_user_base_dn", "ou=people,dc=appcenter,dc=local")
    monkeypatch.setattr(ldap_service.settings, "ldap_user_filter", "(uid={username})")
    monkeypatch.setattr(ldap_service.settings, "ldap_group_base_dn", "ou=groups,dc=appcenter,dc=local")
    monkeypatch.setattr(
        ldap_service.settings,
        "ldap_group_filter",
        "(|(member={user_dn})(uniqueMember={user_dn})(memberUid={username}))",
    )
    monkeypatch.setattr(ldap_service.settings, "ldap_timeout_sec", 10)

    _set_auth_settings(
        client,
        auth_headers,
        auth_ldap_enabled=True,
        auth_ldap_allow_local_fallback=True,
        auth_ldap_jit_create_users=True,
        auth_ldap_directory_type="openldap",
        auth_ldap_default_role_profile_key="viewer",
        auth_ldap_group_admin="appcenter-admins",
        auth_ldap_group_operator="appcenter-operators",
        auth_ldap_group_viewer="appcenter-viewers",
    )

    login = client.post("/api/v1/auth/login", json={"username": "operator.user", "password": "OperatorPass123!"})
    assert login.status_code == 200, login.text
    body = login.json()
    assert body["auth_source"] == "ldap"

    token = body["access_token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200, me.text
    user = me.json()
    assert user["username"] == "operator.user"
    assert user["auth_source"] == "ldap"
    assert user["role_profile_key"] == "operator"


def test_local_admin_fallback_when_ldap_enabled(client, auth_headers, monkeypatch):
    monkeypatch.setattr(ldap_service.settings, "ldap_server_uri", "ldap://127.0.0.1:1389")
    monkeypatch.setattr(ldap_service.settings, "ldap_use_ssl", False)
    monkeypatch.setattr(ldap_service.settings, "ldap_start_tls", False)
    monkeypatch.setattr(ldap_service.settings, "ldap_bind_dn", "cn=admin,dc=appcenter,dc=local")
    monkeypatch.setattr(ldap_service.settings, "ldap_bind_password", "admin123")
    monkeypatch.setattr(ldap_service.settings, "ldap_user_base_dn", "ou=people,dc=appcenter,dc=local")
    monkeypatch.setattr(ldap_service.settings, "ldap_user_filter", "(uid={username})")

    _set_auth_settings(
        client,
        auth_headers,
        auth_ldap_enabled=True,
        auth_ldap_allow_local_fallback=True,
        auth_ldap_jit_create_users=True,
        auth_ldap_directory_type="openldap",
        auth_ldap_default_role_profile_key="viewer",
    )

    login = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    assert login.status_code == 200, login.text
    assert login.json()["auth_source"] == "local"

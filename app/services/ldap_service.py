from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import os
import secrets
from typing import Optional
from urllib.parse import urlparse

from ldap3 import ALL, SUBTREE, Connection, Server, Tls
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_password_hash
from app.config import get_settings
from app.models import RoleProfile, Setting, User

logger = logging.getLogger("appcenter.ldap")
settings = get_settings()


class LdapError(RuntimeError):
    """Base LDAP auth error."""


class LdapConfigurationError(LdapError):
    """LDAP is enabled but required configuration is missing."""


@dataclass
class LdapIdentity:
    username: str
    dn: str
    full_name: str | None = None
    email: str | None = None
    groups: list[str] | None = None


def _get_setting(db: Session, key: str, default: str) -> str:
    item = db.query(Setting).filter(Setting.key == key).first()
    return (item.value or default) if item else default


def _truthy(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def ldap_enabled(db: Session) -> bool:
    return _truthy(_get_setting(db, "auth_ldap_enabled", "false"))


def allow_local_fallback(db: Session) -> bool:
    return _truthy(_get_setting(db, "auth_ldap_allow_local_fallback", "true"), default=True)


def jit_create_users(db: Session) -> bool:
    return _truthy(_get_setting(db, "auth_ldap_jit_create_users", "false"))


def directory_type(db: Session) -> str:
    value = (_get_setting(db, "auth_ldap_directory_type", "openldap") or "openldap").strip().lower()
    return value if value in {"openldap", "ad"} else "openldap"


def default_role_profile_key(db: Session) -> str:
    value = (_get_setting(db, "auth_ldap_default_role_profile_key", "viewer") or "viewer").strip().lower()
    return value or "viewer"


def _configured_user_filter(db: Session) -> str:
    raw = (settings.ldap_user_filter or "").strip()
    if raw:
        return raw
    return "(sAMAccountName={username})" if directory_type(db) == "ad" else "(uid={username})"


def _build_tls() -> Tls | None:
    cert_file = (settings.ldap_ca_cert_file or "").strip()
    if not cert_file:
        return None
    if not os.path.exists(cert_file):
        raise LdapConfigurationError(f"LDAP CA cert file not found: {cert_file}")
    return Tls(ca_certs_file=cert_file)


def _build_server() -> Server:
    server_uri = (settings.ldap_server_uri or "").strip()
    if not server_uri:
        raise LdapConfigurationError("LDAP server URI is not configured")
    parsed = urlparse(server_uri)
    host = parsed.hostname or parsed.path or server_uri
    port = parsed.port
    use_ssl = bool(settings.ldap_use_ssl)
    if parsed.scheme.lower() == "ldaps":
        use_ssl = True
    if not host:
        raise LdapConfigurationError("LDAP server URI host is invalid")
    return Server(
        host=host,
        port=port,
        use_ssl=use_ssl,
        connect_timeout=int(settings.ldap_timeout_sec or 10),
        tls=_build_tls(),
        get_info=ALL,
    )


def _service_bind_connection() -> Connection:
    bind_dn = (settings.ldap_bind_dn or "").strip()
    bind_password = settings.ldap_bind_password or ""
    if not bind_dn:
        raise LdapConfigurationError("LDAP bind DN is not configured")
    server = _build_server()
    conn = Connection(
        server,
        user=bind_dn,
        password=bind_password,
        auto_bind=False,
        raise_exceptions=True,
        receive_timeout=int(settings.ldap_timeout_sec or 10),
    )
    if settings.ldap_start_tls:
        conn.start_tls()
    conn.bind()
    return conn


def _user_search_base() -> str:
    base_dn = (settings.ldap_user_base_dn or "").strip()
    if not base_dn:
        raise LdapConfigurationError("LDAP user base DN is not configured")
    return base_dn


def _group_search_base() -> str:
    return (settings.ldap_group_base_dn or settings.ldap_user_base_dn or "").strip()


def _normalize_attr(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        for item in value:
            text = str(item).strip()
            if text:
                return text
        return None
    text = str(value).strip()
    return text or None


def _extract_entry_attr(entry, *names: str) -> str | None:
    attrs = getattr(entry, "entry_attributes_as_dict", {}) or {}
    for name in names:
        if name in attrs:
            value = _normalize_attr(attrs.get(name))
            if value:
                return value
    return None


def _extract_group_names(entry) -> list[str]:
    attrs = getattr(entry, "entry_attributes_as_dict", {}) or {}
    groups: list[str] = []
    for raw in attrs.get("memberOf", []) or []:
        text = str(raw).strip()
        if not text:
            continue
        first = text.split(",", 1)[0]
        if first.lower().startswith("cn="):
            groups.append(first[3:])
        groups.append(text)
    return groups


def _user_search_attributes(db: Session) -> list[str]:
    if directory_type(db) == "ad":
        return ["cn", "displayName", "mail", "userPrincipalName", "sAMAccountName", "memberOf"]
    return ["cn", "displayName", "mail", "uid", "memberOf"]


def _search_group_names(conn: Connection, username: str, user_dn: str) -> list[str]:
    base = _group_search_base()
    group_filter = (settings.ldap_group_filter or "").strip()
    if not base or not group_filter:
        return []
    rendered = group_filter.format(username=username, user_dn=user_dn)
    conn.search(
        search_base=base,
        search_filter=rendered,
        search_scope=SUBTREE,
        attributes=["cn"],
    )
    groups: list[str] = []
    for entry in conn.entries:
        cn = _extract_entry_attr(entry, "cn")
        if cn:
            groups.append(cn)
        dn = str(getattr(entry, "entry_dn", "")).strip()
        if dn:
            groups.append(dn)
    return groups


def authenticate_directory_user(username: str, password: str, db: Session) -> LdapIdentity:
    login_name = (username or "").strip()
    if not login_name:
        raise LdapError("Username is required")
    if not password:
        raise LdapError("Password is required")

    conn = _service_bind_connection()
    try:
        search_filter = _configured_user_filter(db).format(username=login_name)
        conn.search(
            search_base=_user_search_base(),
            search_filter=search_filter,
            search_scope=SUBTREE,
            attributes=_user_search_attributes(db),
            size_limit=2,
        )
        if len(conn.entries) != 1:
            raise LdapError("LDAP user not found or not unique")
        entry = conn.entries[0]
        user_dn = str(getattr(entry, "entry_dn", "")).strip()
        if not user_dn:
            raise LdapError("LDAP user DN is empty")

        user_conn = Connection(
            _build_server(),
            user=user_dn,
            password=password,
            auto_bind=False,
            raise_exceptions=True,
            receive_timeout=int(settings.ldap_timeout_sec or 10),
        )
        if settings.ldap_start_tls:
            user_conn.start_tls()
        user_conn.bind()
        user_conn.unbind()

        groups = _extract_group_names(entry)
        groups.extend(_search_group_names(conn, login_name, user_dn))
        normalized_groups = sorted({g.strip() for g in groups if str(g).strip()})
        return LdapIdentity(
            username=login_name,
            dn=user_dn,
            full_name=_extract_entry_attr(entry, "displayName", "cn", "name"),
            email=_extract_entry_attr(entry, "mail", "userPrincipalName"),
            groups=normalized_groups,
        )
    finally:
        conn.unbind()


def _parse_group_list(value: str) -> set[str]:
    items = set()
    for item in (value or "").split(","):
        text = item.strip()
        if text:
            items.add(text.casefold())
    return items


def _role_profile_from_groups(db: Session, groups: list[str]) -> RoleProfile | None:
    lookup = {g.casefold() for g in groups if g and str(g).strip()}
    for setting_key, fallback_key in (
        ("auth_ldap_group_admin", "admin"),
        ("auth_ldap_group_operator", "operator"),
        ("auth_ldap_group_viewer", "viewer"),
    ):
        configured = _parse_group_list(_get_setting(db, setting_key, ""))
        if configured and lookup.intersection(configured):
            return db.query(RoleProfile).filter(func.lower(RoleProfile.key) == fallback_key).first()
    return None


def _default_role_profile(db: Session) -> RoleProfile:
    role_key = default_role_profile_key(db)
    role_profile = db.query(RoleProfile).filter(func.lower(RoleProfile.key) == role_key).first()
    if not role_profile or not role_profile.is_active:
        raise LdapConfigurationError(f"LDAP default role profile is invalid: {role_key}")
    return role_profile


def _find_user(db: Session, username: str) -> User | None:
    return db.query(User).filter(func.lower(User.username) == username.strip().lower()).first()


def sync_authenticated_user(db: Session, identity: LdapIdentity) -> User | None:
    user = _find_user(db, identity.username)
    if user and not user.is_active:
        return None

    role_profile = _role_profile_from_groups(db, identity.groups or [])
    if role_profile is None and user and user.role_profile_id:
        role_profile = db.query(RoleProfile).filter(RoleProfile.id == user.role_profile_id).first()
    if role_profile is None:
        role_profile = _default_role_profile(db)

    now = datetime.now(timezone.utc)
    if not user:
        if not jit_create_users(db):
            return None
        role_key = (role_profile.key or "viewer").strip().lower()
        legacy_role = role_key if role_key in {"admin", "operator", "viewer"} else "viewer"
        user = User(
            username=identity.username,
            password_hash=get_password_hash(secrets.token_urlsafe(32)),
            full_name=identity.full_name,
            email=identity.email,
            auth_source="ldap",
            ldap_dn=identity.dn,
            last_directory_sync=now,
            last_login=now,
            role=legacy_role,
            role_profile_id=role_profile.id,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    user.auth_source = "ldap"
    user.ldap_dn = identity.dn
    user.last_directory_sync = now
    user.last_login = now
    if identity.full_name:
        user.full_name = identity.full_name
    if identity.email:
        user.email = identity.email
    if role_profile and role_profile.is_active:
        role_key = (role_profile.key or "viewer").strip().lower()
        user.role_profile_id = role_profile.id
        user.role = role_key if role_key in {"admin", "operator", "viewer"} else "viewer"
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

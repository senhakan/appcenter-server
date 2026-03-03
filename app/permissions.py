from __future__ import annotations

from typing import Any


PERMISSION_CATALOG: list[dict[str, Any]] = [
    {
        "group": "Special",
        "permissions": [
            ("*", "Tum izinler (full access)"),
        ],
    },
    {
        "group": "UI Menu",
        "permissions": [
            ("ui.menu.dashboard", "Dashboard menusu"),
            ("ui.menu.agents", "Ajanlar menusu"),
            ("ui.menu.remote_support", "Destek Merkezi menusu"),
            ("ui.menu.groups", "Gruplar menusu"),
            ("ui.menu.applications", "Uygulamalar menusu"),
            ("ui.menu.deployments", "Dagitimlar menusu"),
            ("ui.menu.inventory", "Envanter menusu"),
            ("ui.menu.licenses", "Lisanslar menusu"),
            ("ui.menu.management", "Yonetim menusu"),
            ("ui.menu.settings", "Ayarlar menusu"),
            ("ui.menu.users", "Kullanicilar menusu"),
            ("ui.menu.roles", "Roller menusu"),
            ("ui.menu.audit", "Audit Log menusu"),
            ("ui.menu.infra_recordings", "Session Recordings menusu"),
        ],
    },
    {
        "group": "UI Pages",
        "permissions": [
            ("ui.page.dashboard", "Dashboard sayfasi"),
            ("ui.page.agents", "Ajanlar sayfasi"),
            ("ui.page.remote_support", "Destek Merkezi sayfasi"),
            ("ui.page.groups", "Gruplar sayfasi"),
            ("ui.page.applications", "Uygulamalar sayfasi"),
            ("ui.page.deployments", "Dagitimlar sayfasi"),
            ("ui.page.inventory", "Envanter sayfasi"),
            ("ui.page.licenses", "Lisanslar sayfasi"),
            ("ui.page.settings", "Ayarlar sayfasi"),
            ("ui.page.users", "Kullanicilar sayfasi"),
            ("ui.page.roles", "Roller sayfasi"),
            ("ui.page.audit", "Audit sayfasi"),
            ("ui.page.infra_recordings", "Session Recordings sayfasi"),
        ],
    },
    {
        "group": "API Permissions",
        "permissions": [
            ("dashboard.view", "Dashboard verileri goruntuleme"),
            ("agents.view", "Ajanlari goruntuleme"),
            ("agents.manage", "Ajanlari yonetme"),
            ("groups.view", "Gruplari goruntuleme"),
            ("groups.manage", "Gruplari yonetme"),
            ("applications.view", "Uygulamalari goruntuleme"),
            ("applications.manage", "Uygulamalari yonetme"),
            ("deployments.view", "Dagitimlari goruntuleme"),
            ("deployments.manage", "Dagitimlari yonetme"),
            ("inventory.view", "Envanter verilerini goruntuleme"),
            ("inventory.manage", "Envanter kurallarini yonetme"),
            ("licenses.view", "Lisanslari goruntuleme"),
            ("licenses.manage", "Lisanslari yonetme"),
            ("remote_support.view", "Destek Merkezi liste erisimi"),
            ("remote_support.session.view", "Uzak destek oturumlarini goruntuleme"),
            ("remote_support.session.manage", "Uzak destek oturumlarini yonetme"),
            ("remote_support.recordings.view", "Uzak destek kayitlarini goruntuleme"),
            ("remote_support.recordings.manage", "Uzak destek kayitlarini yonetme"),
            ("settings.manage", "Ayarlari yonetme"),
            ("users.manage", "Kullanicilari yonetme"),
            ("roles.manage", "Rol profillerini yonetme"),
            ("audit.view", "Audit log goruntuleme"),
        ],
    },
]


def all_permissions() -> set[str]:
    out: set[str] = set()
    for group in PERMISSION_CATALOG:
        for permission, _label in group.get("permissions") or []:
            p = (permission or "").strip()
            if p:
                out.add(p)
    return out


ALL_PERMISSIONS: set[str] = all_permissions()

VIEWER_DEFAULT_PERMISSIONS: set[str] = {
    "ui.menu.dashboard",
    "ui.menu.agents",
    "ui.menu.remote_support",
    "ui.menu.groups",
    "ui.menu.applications",
    "ui.menu.deployments",
    "ui.menu.inventory",
    "ui.menu.licenses",
    "ui.page.dashboard",
    "ui.page.agents",
    "ui.page.remote_support",
    "ui.page.groups",
    "ui.page.applications",
    "ui.page.deployments",
    "ui.page.inventory",
    "ui.page.licenses",
    "dashboard.view",
    "agents.view",
    "groups.view",
    "applications.view",
    "deployments.view",
    "inventory.view",
    "licenses.view",
    "remote_support.view",
    "remote_support.session.view",
    "remote_support.recordings.view",
}

OPERATOR_DEFAULT_PERMISSIONS: set[str] = set(VIEWER_DEFAULT_PERMISSIONS) | {
    "agents.manage",
    "groups.manage",
    "applications.manage",
    "deployments.manage",
    "inventory.manage",
    "licenses.manage",
    "remote_support.session.manage",
    "remote_support.recordings.manage",
}

ADMIN_DEFAULT_PERMISSIONS: set[str] = {"*"}

SYSTEM_ROLE_DEFAULTS: dict[str, set[str]] = {
    "viewer": VIEWER_DEFAULT_PERMISSIONS,
    "operator": OPERATOR_DEFAULT_PERMISSIONS,
    "admin": ADMIN_DEFAULT_PERMISSIONS,
}

SUPPORT_CENTER_ONLY_PERMISSIONS: set[str] = {
    "ui.menu.remote_support",
    "ui.page.remote_support",
    "agents.view",
    "remote_support.view",
    "remote_support.session.view",
    "remote_support.session.manage",
}

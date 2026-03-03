from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.config import get_settings
from app.permissions import (
    ADMIN_DEFAULT_PERMISSIONS,
    OPERATOR_DEFAULT_PERMISSIONS,
    SUPPORT_CENTER_ONLY_PERMISSIONS,
    VIEWER_DEFAULT_PERMISSIONS,
)

settings = get_settings()

is_sqlite = settings.database_url.startswith("sqlite")
connect_args = {"check_same_thread": False} if is_sqlite else {}

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    pool_pre_ping=True,
)


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record) -> None:
    if not is_sqlite:
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
Base = declarative_base()


DEFAULT_SETTINGS = {
    "bandwidth_limit_kbps": ("1024", "Agent download bandwidth limit (KB/s)"),
    "heartbeat_interval_sec": ("60", "Agent heartbeat interval (seconds)"),
    "agent_timeout_sec": ("300", "Agent offline threshold (5 minutes)"),
    "download_timeout_sec": ("1800", "Max download timeout (30 minutes)"),
    "install_timeout_sec": ("1800", "Max install timeout (30 minutes)"),
    "max_retry_count": ("3", "Failed task max retry count"),
    "log_retention_days": ("30", "Keep logs for X days"),
    "enable_auto_cleanup": ("true", "Delete installers after successful install"),
    "agent_latest_version": ("1.0.0", "Latest available agent version"),
    "agent_download_url": ("", "Agent self-update download URL"),
    "agent_hash": ("", "Agent installer SHA256 hash"),
    "agent_latest_version_windows": ("1.0.0", "Latest available Windows agent version"),
    "agent_download_url_windows": ("", "Windows agent self-update download URL"),
    "agent_hash_windows": ("", "Windows agent installer SHA256 hash"),
    "agent_latest_version_linux": ("", "Latest available Linux agent version"),
    "agent_download_url_linux": ("", "Linux agent self-update download URL"),
    "agent_hash_linux": ("", "Linux agent installer SHA256 hash"),
    "server_timezone": ("UTC", "Server timezone (always UTC)"),
    "ui_timezone": ("Europe/Istanbul", "UI timezone (IANA, ex: Europe/Istanbul)"),
    "session_timeout_minutes": ("60", "Web session timeout (minutes)"),
    "inventory_scan_interval_min": ("10", "Agent envanter tarama araligi (dakika)"),
    "inventory_history_retention_days": ("90", "Yazilim degisim gecmisi saklama suresi (gun)"),
    "system_history_retention_days": ("360", "Sistem profili degisim gecmisi saklama suresi (gun)"),
    "runtime_update_interval_min": ("60", "Agent runtime update kontrol araligi (dakika)"),
    "runtime_update_jitter_sec": ("300", "Agent runtime update jitter (saniye)"),
    "dynamic_group_sync_interval_sec": ("120", "Dinamik grup uyeliklerinin otomatik kontrol araligi (saniye)"),
    "session_recording_enabled": ("false", "Remote support session recording auto-start"),
    "session_recording_fps": ("10", "Remote support session recording target FPS"),
    "session_recording_watermark_enabled": ("false", "Remote support session recording watermark"),
}

DEFAULT_ROLE_PROFILES = [
    {
        "key": "viewer",
        "name": "Viewer",
        "description": "Salt okuma erisimi",
        "base_role": "viewer",
        "permissions": sorted(list(VIEWER_DEFAULT_PERMISSIONS)),
        "is_system": True,
    },
    {
        "key": "operator",
        "name": "Operator",
        "description": "Operasyonel degisiklik yapabilir",
        "base_role": "operator",
        "permissions": sorted(list(OPERATOR_DEFAULT_PERMISSIONS)),
        "is_system": True,
    },
    {
        "key": "admin",
        "name": "Admin",
        "description": "Tam yonetim erisimi",
        "base_role": "admin",
        "permissions": sorted(list(ADMIN_DEFAULT_PERMISSIONS)),
        "is_system": True,
    },
    {
        "key": "support_center_only",
        "name": "Destek Merkezi Operatoru",
        "description": "Yalnizca Destek Merkezi ve baglanti akislarina erisim",
        "base_role": "operator",
        "permissions": sorted(list(SUPPORT_CENTER_ONLY_PERMISSIONS)),
        "is_system": False,
    },
]

DEFAULT_GROUPS = {
    "Store": "AppCenter Store tray uygulamasinin zorunlu oldugu ajanlar",
    "Remote Support": "Uzak destek baglantisina izin verilen ajanlar",
    "Genel": "Tum bilgisayarlar",
    "IT": "Bilgi Islem",
    "Muhasebe": "Muhasebe departmani",
    "Satis": "Satis departmani",
}

DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD_HASH = "$2b$12$KGitLdPDMejjrOvs7C4H2utSydHbNH75jwmelpwpJ5ezfkh.QEd3u"


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app import models  # pylint: disable=import-outside-toplevel

    Base.metadata.create_all(bind=engine)
    _run_startup_migrations()


def _run_startup_migrations() -> None:
    _migrate_role_profiles_table()
    _migrate_role_profiles_permissions_column()
    _migrate_users_role_profile_column()
    _migrate_users_avatar_column()
    _migrate_users_profile_columns()
    _migrate_groups_dynamic_columns()
    _migrate_agent_platform_columns()
    _migrate_application_platform_columns()
    _migrate_agent_update_platform_settings()
    if is_sqlite:
        _migrate_sqlite_groups_table()
        _migrate_sqlite_applications_table()
        _migrate_sqlite_agent_groups_table()
        _migrate_sqlite_agents_inventory_columns()
        _migrate_sqlite_agents_session_columns()
        _migrate_sqlite_agents_system_profile_columns()
        _migrate_sqlite_agents_remote_support_columns()
        _migrate_sqlite_system_profile_history_columns()
        _migrate_sqlite_agent_identity_history_table()
        _migrate_sqlite_agent_status_history_table()
        _migrate_sqlite_remote_support_table()
        _migrate_sqlite_remote_support_recordings_table()
        _migrate_sqlite_audit_logs_table()


def _migrate_role_profiles_table() -> None:
    with engine.begin() as conn:
        if is_sqlite:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS role_profiles (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        key VARCHAR NOT NULL UNIQUE,
                        name VARCHAR NOT NULL UNIQUE,
                        description TEXT,
                        base_role VARCHAR NOT NULL DEFAULT 'viewer',
                        is_system INTEGER NOT NULL DEFAULT 0,
                        is_active INTEGER NOT NULL DEFAULT 1,
                        created_at DATETIME,
                        updated_at DATETIME,
                        CONSTRAINT ck_role_profile_base_role CHECK (base_role IN ('admin','operator','viewer'))
                    )
                    """
                )
            )
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_role_profile_key ON role_profiles(key)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_role_profile_active ON role_profiles(is_active)"))
            return

        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS role_profiles (
                    id SERIAL PRIMARY KEY,
                    key VARCHAR NOT NULL UNIQUE,
                    name VARCHAR NOT NULL UNIQUE,
                    description TEXT NULL,
                    base_role VARCHAR NOT NULL DEFAULT 'viewer',
                    is_system BOOLEAN NOT NULL DEFAULT FALSE,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMPTZ,
                    updated_at TIMESTAMPTZ,
                    CONSTRAINT ck_role_profile_base_role CHECK (base_role IN ('admin','operator','viewer'))
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_role_profile_key ON role_profiles(key)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_role_profile_active ON role_profiles(is_active)"))


def _migrate_users_role_profile_column() -> None:
    with engine.begin() as conn:
        if is_sqlite:
            table_exists = conn.execute(
                text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='users' LIMIT 1")
            ).first()
            if not table_exists:
                return
            rows = conn.execute(text("PRAGMA table_info(users)")).mappings().all()
            existing = {row["name"] for row in rows}
            if "role_profile_id" not in existing:
                conn.execute(text("ALTER TABLE users ADD COLUMN role_profile_id INTEGER"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_user_role_profile ON users(role_profile_id)"))
            return

        table_exists = conn.execute(
            text("SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='users' LIMIT 1")
        ).first()
        if not table_exists:
            return
        rows = conn.execute(
            text("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='users'")
        ).all()
        existing = {row[0] for row in rows}
        if "role_profile_id" not in existing:
            conn.execute(text("ALTER TABLE users ADD COLUMN role_profile_id INTEGER NULL"))
        # best-effort FK and index, idempotent guards
        fk_exists = conn.execute(
            text(
                """
                SELECT 1
                FROM information_schema.table_constraints tc
                WHERE tc.table_schema='public'
                  AND tc.table_name='users'
                  AND tc.constraint_type='FOREIGN KEY'
                  AND tc.constraint_name='fk_users_role_profile_id'
                LIMIT 1
                """
            )
        ).first()
        if not fk_exists:
            conn.execute(
                text(
                    """
                    ALTER TABLE users
                    ADD CONSTRAINT fk_users_role_profile_id
                    FOREIGN KEY (role_profile_id) REFERENCES role_profiles(id) ON DELETE SET NULL
                    """
                )
            )
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_user_role_profile ON users(role_profile_id)"))


def _migrate_role_profiles_permissions_column() -> None:
    with engine.begin() as conn:
        if is_sqlite:
            table_exists = conn.execute(
                text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='role_profiles' LIMIT 1")
            ).first()
            if not table_exists:
                return
            rows = conn.execute(text("PRAGMA table_info(role_profiles)")).mappings().all()
            existing = {row["name"] for row in rows}
            if "permissions_json" not in existing:
                conn.execute(text("ALTER TABLE role_profiles ADD COLUMN permissions_json TEXT"))
            return

        table_exists = conn.execute(
            text("SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='role_profiles' LIMIT 1")
        ).first()
        if not table_exists:
            return
        rows = conn.execute(
            text("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='role_profiles'")
        ).all()
        existing = {row[0] for row in rows}
        if "permissions_json" not in existing:
            conn.execute(text("ALTER TABLE role_profiles ADD COLUMN permissions_json TEXT"))


def _migrate_users_avatar_column() -> None:
    with engine.begin() as conn:
        if is_sqlite:
            table_exists = conn.execute(
                text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='users' LIMIT 1")
            ).first()
            if not table_exists:
                return
            rows = conn.execute(text("PRAGMA table_info(users)")).mappings().all()
            existing = {row["name"] for row in rows}
            if "avatar_url" not in existing:
                conn.execute(text("ALTER TABLE users ADD COLUMN avatar_url VARCHAR"))
            return

        table_exists = conn.execute(
            text("SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='users' LIMIT 1")
        ).first()
        if not table_exists:
            return
        rows = conn.execute(
            text("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='users'")
        ).all()
        existing = {row[0] for row in rows}
        if "avatar_url" not in existing:
            conn.execute(text("ALTER TABLE users ADD COLUMN avatar_url VARCHAR NULL"))


def _migrate_users_profile_columns() -> None:
    with engine.begin() as conn:
        expected = {
            "phone": "VARCHAR",
            "phone_ext": "VARCHAR",
            "organization": "VARCHAR",
            "department": "VARCHAR",
        }
        if is_sqlite:
            table_exists = conn.execute(
                text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='users' LIMIT 1")
            ).first()
            if not table_exists:
                return
            rows = conn.execute(text("PRAGMA table_info(users)")).mappings().all()
            existing = {row["name"] for row in rows}
            for col, sql_type in expected.items():
                if col not in existing:
                    conn.execute(text(f"ALTER TABLE users ADD COLUMN {col} {sql_type}"))
            return

        table_exists = conn.execute(
            text("SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='users' LIMIT 1")
        ).first()
        if not table_exists:
            return
        rows = conn.execute(
            text("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='users'")
        ).all()
        existing = {row[0] for row in rows}
        for col, sql_type in expected.items():
            if col not in existing:
                conn.execute(text(f"ALTER TABLE users ADD COLUMN {col} {sql_type} NULL"))


def _migrate_groups_dynamic_columns() -> None:
    with engine.begin() as conn:
        if is_sqlite:
            table_exists = conn.execute(
                text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='groups' LIMIT 1")
            ).first()
            if not table_exists:
                return
            rows = conn.execute(text("PRAGMA table_info(groups)")).mappings().all()
            existing = {row["name"] for row in rows}
            if "is_dynamic" not in existing:
                conn.execute(text("ALTER TABLE groups ADD COLUMN is_dynamic INTEGER NOT NULL DEFAULT 0"))
            if "dynamic_rules_json" not in existing:
                conn.execute(text("ALTER TABLE groups ADD COLUMN dynamic_rules_json TEXT"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_group_is_dynamic ON groups(is_dynamic)"))
            return

        table_exists = conn.execute(
            text("SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='groups' LIMIT 1")
        ).first()
        if not table_exists:
            return
        rows = conn.execute(
            text("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='groups'")
        ).all()
        existing = {row[0] for row in rows}
        if "is_dynamic" not in existing:
            conn.execute(text("ALTER TABLE groups ADD COLUMN is_dynamic BOOLEAN NOT NULL DEFAULT FALSE"))
        if "dynamic_rules_json" not in existing:
            conn.execute(text("ALTER TABLE groups ADD COLUMN dynamic_rules_json TEXT"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_group_is_dynamic ON groups(is_dynamic)"))


def _migrate_sqlite_groups_table() -> None:
    """Add group lifecycle/dynamic columns to groups table."""
    with engine.begin() as conn:
        table_exists = conn.execute(
            text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='groups' LIMIT 1")
        ).first()
        if not table_exists:
            return

        rows = conn.execute(text("PRAGMA table_info(groups)")).mappings().all()
        existing_columns = {row["name"] for row in rows}
        if "is_active" not in existing_columns:
            conn.execute(text("ALTER TABLE groups ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1"))
        if "is_dynamic" not in existing_columns:
            conn.execute(text("ALTER TABLE groups ADD COLUMN is_dynamic INTEGER NOT NULL DEFAULT 0"))
        if "dynamic_rules_json" not in existing_columns:
            conn.execute(text("ALTER TABLE groups ADD COLUMN dynamic_rules_json TEXT"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_group_is_dynamic ON groups(is_dynamic)"))


def _migrate_sqlite_applications_table() -> None:
    # Lightweight, idempotent migration for instances created before v1.1 schema additions.
    expected_columns = {
        "install_args": "TEXT",
        "uninstall_args": "TEXT",
        "icon_url": "VARCHAR",
        "category": "VARCHAR",
        "dependencies": "TEXT",
        "min_os_version": "VARCHAR",
        "target_platform": "VARCHAR NOT NULL DEFAULT 'windows'",
    }

    with engine.begin() as conn:
        table_exists = conn.execute(
            text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='applications' LIMIT 1")
        ).first()
        if not table_exists:
            return

        rows = conn.execute(text("PRAGMA table_info(applications)")).mappings().all()
        existing_columns = {row["name"] for row in rows}

        for column_name, column_type in expected_columns.items():
            if column_name in existing_columns:
                continue
            conn.execute(text(f"ALTER TABLE applications ADD COLUMN {column_name} {column_type}"))


def _migrate_agent_platform_columns() -> None:
    expected = {
        "platform": "VARCHAR NOT NULL DEFAULT 'windows'",
        "arch": "VARCHAR",
        "distro": "VARCHAR",
        "distro_version": "VARCHAR",
    }
    with engine.begin() as conn:
        if is_sqlite:
            table_exists = conn.execute(
                text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='agents' LIMIT 1")
            ).first()
            if not table_exists:
                return
            rows = conn.execute(text("PRAGMA table_info(agents)")).mappings().all()
            existing = {row["name"] for row in rows}
            for col, sql_type in expected.items():
                if col not in existing:
                    conn.execute(text(f"ALTER TABLE agents ADD COLUMN {col} {sql_type}"))
            return

        table_exists = conn.execute(
            text("SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='agents' LIMIT 1")
        ).first()
        if not table_exists:
            return
        rows = conn.execute(
            text("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='agents'")
        ).all()
        existing = {row[0] for row in rows}
        for col, sql_type in expected.items():
            if col not in existing:
                conn.execute(text(f"ALTER TABLE agents ADD COLUMN {col} {sql_type}"))


def _migrate_application_platform_columns() -> None:
    with engine.begin() as conn:
        if is_sqlite:
            table_exists = conn.execute(
                text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='applications' LIMIT 1")
            ).first()
            if not table_exists:
                return
            rows = conn.execute(text("PRAGMA table_info(applications)")).mappings().all()
            existing = {row["name"] for row in rows}
            if "target_platform" not in existing:
                conn.execute(text("ALTER TABLE applications ADD COLUMN target_platform VARCHAR NOT NULL DEFAULT 'windows'"))
            return

        table_exists = conn.execute(
            text("SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='applications' LIMIT 1")
        ).first()
        if not table_exists:
            return
        rows = conn.execute(
            text("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='applications'")
        ).all()
        existing = {row[0] for row in rows}
        if "target_platform" not in existing:
            conn.execute(text("ALTER TABLE applications ADD COLUMN target_platform VARCHAR NOT NULL DEFAULT 'windows'"))


def _migrate_agent_update_platform_settings() -> None:
    setting_pairs = [
        ("agent_latest_version_windows", "agent_latest_version"),
        ("agent_download_url_windows", "agent_download_url"),
        ("agent_hash_windows", "agent_hash"),
    ]
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        for new_key, old_key in setting_pairs:
            exists = conn.execute(text("SELECT value FROM settings WHERE key = :k LIMIT 1"), {"k": new_key}).first()
            if exists:
                continue
            old = conn.execute(text("SELECT value FROM settings WHERE key = :k LIMIT 1"), {"k": old_key}).first()
            value = str(old[0]) if old and old[0] is not None else (DEFAULT_SETTINGS.get(new_key) or ("", ""))[0]
            desc = (DEFAULT_SETTINGS.get(new_key) or ("", ""))[1]
            conn.execute(
                text("INSERT INTO settings (key, value, description, updated_at) VALUES (:k, :v, :d, :u)"),
                {"k": new_key, "v": value, "d": desc, "u": now},
            )


def _migrate_sqlite_agent_groups_table() -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS agent_groups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_uuid VARCHAR NOT NULL,
                    group_id INTEGER NOT NULL,
                    created_at DATETIME,
                    UNIQUE(agent_uuid, group_id),
                    FOREIGN KEY(agent_uuid) REFERENCES agents(uuid) ON DELETE CASCADE,
                    FOREIGN KEY(group_id) REFERENCES groups(id) ON DELETE CASCADE
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_agent_groups_agent ON agent_groups(agent_uuid)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_agent_groups_group ON agent_groups(group_id)"))

        # Backfill from legacy single-group mapping.
        conn.execute(
            text(
                """
                INSERT OR IGNORE INTO agent_groups (agent_uuid, group_id, created_at)
                SELECT uuid, group_id, :now_utc
                FROM agents
                WHERE group_id IS NOT NULL
                """
            ),
            {"now_utc": datetime.now(timezone.utc).isoformat()},
        )


def _migrate_sqlite_agents_inventory_columns() -> None:
    """Add inventory_hash, inventory_updated_at, software_count to agents table."""
    expected_columns = {
        "inventory_hash": "VARCHAR",
        "inventory_updated_at": "DATETIME",
        "software_count": "INTEGER DEFAULT 0",
    }

    with engine.begin() as conn:
        table_exists = conn.execute(
            text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='agents' LIMIT 1")
        ).first()
        if not table_exists:
            return

        rows = conn.execute(text("PRAGMA table_info(agents)")).mappings().all()
        existing_columns = {row["name"] for row in rows}

        for column_name, column_type in expected_columns.items():
            if column_name in existing_columns:
                continue
            conn.execute(text(f"ALTER TABLE agents ADD COLUMN {column_name} {column_type}"))


def _migrate_sqlite_agents_session_columns() -> None:
    """Add logged_in_sessions_json, logged_in_sessions_updated_at to agents table."""
    expected_columns = {
        "logged_in_sessions_json": "TEXT",
        "logged_in_sessions_updated_at": "DATETIME",
    }

    with engine.begin() as conn:
        table_exists = conn.execute(
            text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='agents' LIMIT 1")
        ).first()
        if not table_exists:
            return

        rows = conn.execute(text("PRAGMA table_info(agents)")).mappings().all()
        existing_columns = {row["name"] for row in rows}

        for column_name, column_type in expected_columns.items():
            if column_name in existing_columns:
                continue
            conn.execute(text(f"ALTER TABLE agents ADD COLUMN {column_name} {column_type}"))


def _migrate_sqlite_agents_system_profile_columns() -> None:
    """Add system profile snapshot columns to agents table."""
    expected_columns = {
        "system_profile_json": "TEXT",
        "system_profile_hash": "VARCHAR",
        "system_profile_updated_at": "DATETIME",
    }

    with engine.begin() as conn:
        table_exists = conn.execute(
            text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='agents' LIMIT 1")
        ).first()
        if not table_exists:
            return

        rows = conn.execute(text("PRAGMA table_info(agents)")).mappings().all()
        existing_columns = {row["name"] for row in rows}

        for column_name, column_type in expected_columns.items():
            if column_name in existing_columns:
                continue
            conn.execute(text(f"ALTER TABLE agents ADD COLUMN {column_name} {column_type}"))


def _migrate_sqlite_agents_remote_support_columns() -> None:
    """Add remote support runtime status columns to agents table."""
    expected_columns = {
        "remote_support_state": "VARCHAR",
        "remote_support_session_id": "INTEGER",
        "remote_support_helper_running": "INTEGER DEFAULT 0",
        "remote_support_helper_pid": "INTEGER",
        "remote_support_updated_at": "DATETIME",
    }

    with engine.begin() as conn:
        table_exists = conn.execute(
            text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='agents' LIMIT 1")
        ).first()
        if not table_exists:
            return

        rows = conn.execute(text("PRAGMA table_info(agents)")).mappings().all()
        existing_columns = {row["name"] for row in rows}

        for column_name, column_type in expected_columns.items():
            if column_name in existing_columns:
                continue
            conn.execute(text(f"ALTER TABLE agents ADD COLUMN {column_name} {column_type}"))


def _migrate_sqlite_system_profile_history_columns() -> None:
    """Add diff_json to agent_system_profile_history table."""
    expected_columns = {
        "diff_json": "TEXT",
    }

    with engine.begin() as conn:
        table_exists = conn.execute(
            text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='agent_system_profile_history' LIMIT 1")
        ).first()
        if not table_exists:
            return

        rows = conn.execute(text("PRAGMA table_info(agent_system_profile_history)")).mappings().all()
        existing_columns = {row["name"] for row in rows}

        for column_name, column_type in expected_columns.items():
            if column_name in existing_columns:
                continue
            conn.execute(
                text(f"ALTER TABLE agent_system_profile_history ADD COLUMN {column_name} {column_type}")
            )


def _migrate_sqlite_agent_identity_history_table() -> None:
    """Create agent_identity_history table for hostname/ip changes."""
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS agent_identity_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_uuid VARCHAR NOT NULL,
                    detected_at DATETIME,
                    old_hostname VARCHAR,
                    new_hostname VARCHAR,
                    old_ip_address VARCHAR,
                    new_ip_address VARCHAR,
                    FOREIGN KEY(agent_uuid) REFERENCES agents(uuid) ON DELETE CASCADE
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_identityhist_agent ON agent_identity_history(agent_uuid)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_identityhist_detected ON agent_identity_history(detected_at)"))


def _migrate_sqlite_agent_status_history_table() -> None:
    """Create agent_status_history table for online/offline transitions."""
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS agent_status_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_uuid VARCHAR NOT NULL,
                    detected_at DATETIME,
                    old_status VARCHAR,
                    new_status VARCHAR,
                    reason VARCHAR,
                    FOREIGN KEY(agent_uuid) REFERENCES agents(uuid) ON DELETE CASCADE
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_statushist_agent ON agent_status_history(agent_uuid)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_statushist_detected ON agent_status_history(detected_at)"))


def _migrate_sqlite_remote_support_table() -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS remote_support_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_uuid TEXT NOT NULL REFERENCES agents(uuid) ON DELETE CASCADE,
                    admin_user_id INTEGER NOT NULL REFERENCES users(id),
                    status TEXT NOT NULL DEFAULT 'pending_approval',
                    reason TEXT,
                    vnc_password TEXT,
                    requested_at TEXT NOT NULL,
                    approval_timeout_at TEXT NOT NULL,
                    approved_at TEXT,
                    monitor_count INTEGER,
                    connected_at TEXT,
                    ended_at TEXT,
                    ended_by TEXT,
                    max_duration_min INTEGER NOT NULL DEFAULT 60,
                    end_signal_pending INTEGER NOT NULL DEFAULT 0,
                    admin_notes TEXT,
                    CONSTRAINT ck_rs_status CHECK (
                        status IN ('pending_approval','approved','rejected','connecting','active','ended','timeout','error')
                    )
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_rs_agent ON remote_support_sessions(agent_uuid)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_rs_status ON remote_support_sessions(status)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_rs_requested ON remote_support_sessions(requested_at)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_rs_admin ON remote_support_sessions(admin_user_id)"))

        # Older installs may have table without end_signal_pending.
        rows = conn.execute(text("PRAGMA table_info(remote_support_sessions)")).mappings().all()
        existing_columns = {row["name"] for row in rows}
        if "end_signal_pending" not in existing_columns:
            conn.execute(text("ALTER TABLE remote_support_sessions ADD COLUMN end_signal_pending INTEGER NOT NULL DEFAULT 0"))
        if "monitor_count" not in existing_columns:
            conn.execute(text("ALTER TABLE remote_support_sessions ADD COLUMN monitor_count INTEGER"))


def _migrate_sqlite_audit_logs_table() -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    action VARCHAR NOT NULL,
                    resource_type VARCHAR NOT NULL,
                    resource_id VARCHAR,
                    details_json TEXT,
                    created_at DATETIME,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_logs(user_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs(action)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_audit_resource ON audit_logs(resource_type, resource_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs(created_at)"))


def _migrate_sqlite_remote_support_recordings_table() -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS remote_support_recordings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL REFERENCES remote_support_sessions(id) ON DELETE CASCADE,
                    agent_uuid TEXT NOT NULL REFERENCES agents(uuid) ON DELETE CASCADE,
                    monitor_index INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'recording',
                    target_fps INTEGER,
                    trigger_source TEXT,
                    file_path TEXT,
                    log_path TEXT,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    duration_sec INTEGER,
                    file_size_bytes INTEGER,
                    error_message TEXT,
                    CONSTRAINT ck_rsr_status CHECK (
                        status IN ('recording','completed','stopped','failed')
                    )
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_rsr_session ON remote_support_recordings(session_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_rsr_agent ON remote_support_recordings(agent_uuid)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_rsr_status ON remote_support_recordings(status)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_rsr_started ON remote_support_recordings(started_at)"))
        cols = conn.execute(text("PRAGMA table_info(remote_support_recordings)")).mappings().all()
        names = {c["name"] for c in cols}
        if "target_fps" not in names:
            conn.execute(text("ALTER TABLE remote_support_recordings ADD COLUMN target_fps INTEGER"))
        if "monitor_index" not in names:
            conn.execute(text("ALTER TABLE remote_support_recordings ADD COLUMN monitor_index INTEGER NOT NULL DEFAULT 1"))


def seed_initial_data() -> None:
    from app import models  # pylint: disable=import-outside-toplevel

    db = SessionLocal()
    try:
        for key, (value, description) in DEFAULT_SETTINGS.items():
            exists = db.query(models.Setting).filter(models.Setting.key == key).first()
            if not exists:
                db.add(
                    models.Setting(
                        key=key,
                        value=value,
                        description=description,
                        updated_at=datetime.now(timezone.utc),
                    )
                )

        role_key_to_id: dict[str, int] = {}
        for item in DEFAULT_ROLE_PROFILES:
            existing = db.query(models.RoleProfile).filter(models.RoleProfile.key == item["key"]).first()
            if not existing:
                existing = models.RoleProfile(
                    key=item["key"],
                    name=item["name"],
                    description=item["description"],
                    base_role=item["base_role"],
                    permissions_json=json.dumps(item.get("permissions") or [], ensure_ascii=True),
                    is_system=bool(item["is_system"]),
                    is_active=True,
                )
                db.add(existing)
                db.flush()
            else:
                existing.base_role = item["base_role"]
                existing.permissions_json = json.dumps(item.get("permissions") or [], ensure_ascii=True)
                existing.is_system = bool(item["is_system"])
                existing.is_active = True
                db.add(existing)
            role_key_to_id[item["key"]] = int(existing.id)

        for group_name, description in DEFAULT_GROUPS.items():
            exists = db.query(models.Group).filter(models.Group.name == group_name).first()
            if not exists:
                db.add(models.Group(name=group_name, description=description))

        admin_exists = db.query(models.User).filter(models.User.username == DEFAULT_ADMIN_USERNAME).first()
        if not admin_exists:
            db.add(
                models.User(
                    username=DEFAULT_ADMIN_USERNAME,
                    password_hash=DEFAULT_ADMIN_PASSWORD_HASH,
                    full_name="Sistem Yoneticisi",
                    role="admin",
                    role_profile_id=role_key_to_id.get("admin"),
                    is_active=True,
                )
            )

        # Backfill system role profile links for legacy users.
        users_without_profile = db.query(models.User).filter(models.User.role_profile_id.is_(None)).all()
        for user in users_without_profile:
            role_key = (user.role or "").strip().lower()
            if role_key in role_key_to_id:
                user.role_profile_id = role_key_to_id[role_key]
                db.add(user)

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

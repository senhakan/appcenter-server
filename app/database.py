from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.config import get_settings
from app.permissions import (
    ADMIN_DEFAULT_PERMISSIONS,
    OPERATOR_DEFAULT_PERMISSIONS,
    SUPPORT_CENTER_ONLY_PERMISSIONS,
    VIEWER_DEFAULT_PERMISSIONS,
)

settings = get_settings()

if settings.database_url.startswith("sqlite"):
    raise RuntimeError("SQLite is no longer supported. Configure DATABASE_URL for PostgreSQL.")

engine = create_engine(
    settings.database_url,
    connect_args={},
    pool_pre_ping=True,
)


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
    "service_monitoring_enabled": ("true", "Ajan servis izleme (Windows+Linux) global ac/kapat"),
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
    _migrate_agent_runtime_network_columns()
    _migrate_application_platform_columns()
    _migrate_agent_update_platform_settings()
    _migrate_sam_advanced_tables()
    _migrate_inventory_perf_indexes()


def _migrate_role_profiles_table() -> None:
    with engine.begin() as conn:
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


def _migrate_agent_platform_columns() -> None:
    expected = {
        "platform": "VARCHAR NOT NULL DEFAULT 'windows'",
        "arch": "VARCHAR",
        "distro": "VARCHAR",
        "distro_version": "VARCHAR",
    }
    with engine.begin() as conn:
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
        constraint_row = conn.execute(
            text(
                """
                SELECT pg_get_constraintdef(oid)
                FROM pg_constraint
                WHERE conrelid = 'applications'::regclass
                  AND conname = 'ck_application_file_type'
                """
            )
        ).first()
        if constraint_row:
            definition = str(constraint_row[0] or "").lower()
            expected_tokens = ("deb", "tar.gz", "sh", "ps1")
            required_types_present = all(token in definition for token in expected_tokens)
            if not required_types_present:
                conn.execute(text("ALTER TABLE applications DROP CONSTRAINT ck_application_file_type"))
                conn.execute(
                    text(
                        "ALTER TABLE applications "
                        "ADD CONSTRAINT ck_application_file_type "
                        "CHECK (file_type IN ('msi', 'exe', 'ps1', 'deb', 'tar.gz', 'sh'))"
                    )
                )


def _migrate_agent_runtime_network_columns() -> None:
    expected = {
        "full_ip": "TEXT",
        "uptime_sec": "INTEGER",
        "services_json": "TEXT",
        "services_hash": "VARCHAR",
        "services_updated_at": "TIMESTAMPTZ",
        "service_monitoring_enabled": "BOOLEAN",
    }
    with engine.begin() as conn:
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


def _migrate_inventory_perf_indexes() -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_agent_platform ON agents(platform)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_agent_status ON agents(status)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_agent_last_seen ON agents(last_seen DESC)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_agent_platform_status ON agents(platform, status)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_inv_agent_uuid ON agent_software_inventory(agent_uuid)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_inv_normalized_name ON agent_software_inventory(normalized_name)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_inv_agent_norm_name ON agent_software_inventory(agent_uuid, normalized_name)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_inv_publisher ON agent_software_inventory(publisher)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_inv_norm_name_agent ON agent_software_inventory(normalized_name, agent_uuid)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_chg_agent_detected ON software_change_history(agent_uuid, detected_at DESC)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_chg_detected ON software_change_history(detected_at DESC)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_chg_type_detected ON software_change_history(change_type, detected_at DESC)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_license_active_type ON software_licenses(is_active, license_type)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_license_pattern ON software_licenses(software_name_pattern)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_sam_find_platform_status ON sam_compliance_findings(platform, status)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_sam_find_last_seen ON sam_compliance_findings(last_seen_at DESC)"))


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


def _migrate_sam_advanced_tables() -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS sam_lifecycle_policies (
                    id SERIAL PRIMARY KEY,
                    software_name_pattern VARCHAR NOT NULL,
                    match_type VARCHAR NOT NULL DEFAULT 'contains',
                    platform VARCHAR NOT NULL DEFAULT 'all',
                    eol_date TIMESTAMPTZ NULL,
                    eos_date TIMESTAMPTZ NULL,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    notes TEXT NULL,
                    created_at TIMESTAMPTZ NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL,
                    CONSTRAINT ck_sam_lifecycle_match_type CHECK (match_type IN ('exact','contains','starts_with')),
                    CONSTRAINT ck_sam_lifecycle_platform CHECK (platform IN ('all','windows','linux'))
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS sam_cost_profiles (
                    id SERIAL PRIMARY KEY,
                    software_name_pattern VARCHAR NOT NULL,
                    match_type VARCHAR NOT NULL DEFAULT 'contains',
                    platform VARCHAR NOT NULL DEFAULT 'all',
                    monthly_cost_cents INTEGER NOT NULL DEFAULT 0,
                    currency VARCHAR NOT NULL DEFAULT 'USD',
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    notes TEXT NULL,
                    created_at TIMESTAMPTZ NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL,
                    CONSTRAINT ck_sam_cost_match_type CHECK (match_type IN ('exact','contains','starts_with')),
                    CONSTRAINT ck_sam_cost_platform CHECK (platform IN ('all','windows','linux'))
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_sam_finding_status ON sam_compliance_findings(status)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_sam_finding_platform ON sam_compliance_findings(platform)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_sam_finding_software ON sam_compliance_findings(software_name)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_sam_schedule_active ON sam_report_schedules(is_active)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_sam_lifecycle_active ON sam_lifecycle_policies(is_active)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_sam_lifecycle_pattern ON sam_lifecycle_policies(software_name_pattern)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_sam_lifecycle_platform ON sam_lifecycle_policies(platform)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_sam_cost_active ON sam_cost_profiles(is_active)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_sam_cost_pattern ON sam_cost_profiles(software_name_pattern)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_sam_cost_platform ON sam_cost_profiles(platform)"))


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

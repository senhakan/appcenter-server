from __future__ import annotations

from datetime import datetime, timezone
from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.config import get_settings

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
    "work_hour_start": ("09:00", "Work hours start time (HH:MM) - UTC"),
    "work_hour_end": ("18:00", "Work hours end time (HH:MM) - UTC"),
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
    "server_timezone": ("UTC", "Server timezone (always UTC)"),
}

DEFAULT_GROUPS = {
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
    if is_sqlite:
        _migrate_sqlite_applications_table()


def _migrate_sqlite_applications_table() -> None:
    # Lightweight, idempotent migration for instances created before v1.1 schema additions.
    expected_columns = {
        "install_args": "TEXT",
        "uninstall_args": "TEXT",
        "icon_url": "VARCHAR",
        "category": "VARCHAR",
        "dependencies": "TEXT",
        "min_os_version": "VARCHAR",
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
                    is_active=True,
                )
            )

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

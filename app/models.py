from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.group_policy import is_system_group_name


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_dynamic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    dynamic_rules_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    agents: Mapped[list["Agent"]] = relationship(back_populates="group")
    agent_groups: Mapped[list["AgentGroup"]] = relationship(back_populates="group", cascade="all, delete-orphan")

    @property
    def is_system(self) -> bool:
        return is_system_group_name(self.name)

    @property
    def dynamic_rules(self) -> Optional[dict]:
        if not self.dynamic_rules_json:
            return None
        try:
            data = json.loads(self.dynamic_rules_json)
            return data if isinstance(data, dict) else None
        except Exception:
            return None


class Agent(Base):
    __tablename__ = "agents"
    __table_args__ = (
        CheckConstraint("status IN ('online', 'offline')", name="ck_agent_status"),
    )

    uuid: Mapped[str] = mapped_column(String, primary_key=True)
    hostname: Mapped[str] = mapped_column(String, nullable=False)
    ip_address: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # JSON array text of all non-loopback IP addresses reported by agent.
    full_ip: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Agent-reported host uptime in seconds.
    uptime_sec: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    os_user: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    os_version: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    platform: Mapped[str] = mapped_column(String, default="windows", nullable=False)
    arch: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    distro: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    distro_version: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    version: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String, default="offline", nullable=False)
    group_id: Mapped[Optional[int]] = mapped_column(ForeignKey("groups.id", ondelete="SET NULL"), nullable=True)
    secret_key: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    cpu_model: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    ram_gb: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    disk_free_gb: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    group: Mapped[Optional[Group]] = relationship(back_populates="agents")
    inventory_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    inventory_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    software_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Stored as JSON text to keep SQLite migration lightweight.
    logged_in_sessions_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    logged_in_sessions_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # System profile snapshot (static-ish info) + last update.
    system_profile_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    system_profile_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    system_profile_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Remote support runtime status snapshot from heartbeat.
    remote_support_state: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    remote_support_session_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    remote_support_helper_running: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    remote_support_helper_pid: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    remote_support_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Service snapshot (JSON text) + hash for low-traffic sync.
    services_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    services_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    services_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Null -> inherit global setting. True/False -> per-agent override.
    service_monitoring_enabled: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    agent_applications: Mapped[list["AgentApplication"]] = relationship(back_populates="agent")
    agent_groups: Mapped[list["AgentGroup"]] = relationship(back_populates="agent", cascade="all, delete-orphan")

    @property
    def group_ids(self) -> list[int]:
        return sorted({item.group_id for item in self.agent_groups})

    @property
    def logged_in_sessions(self) -> list[dict]:
        """Parsed logged-in session list from logged_in_sessions_json (best-effort)."""
        if not self.logged_in_sessions_json:
            return []
        try:
            data = json.loads(self.logged_in_sessions_json)
            if isinstance(data, list):
                return [x for x in data if isinstance(x, dict)]
            return []
        except Exception:
            return []

    @property
    def system_profile(self) -> Optional[dict]:
        """Parsed system profile snapshot from system_profile_json (best-effort)."""
        if not self.system_profile_json:
            return None
        try:
            data = json.loads(self.system_profile_json)
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    @property
    def full_ip_list(self) -> list[str]:
        """Parsed all-IP list from full_ip JSON text (best-effort)."""
        if not self.full_ip:
            return []
        try:
            data = json.loads(self.full_ip)
            if isinstance(data, list):
                return [str(x).strip() for x in data if str(x).strip()]
            return []
        except Exception:
            return []

    @property
    def services(self) -> list[dict]:
        """Parsed service snapshot from services_json (best-effort)."""
        if not self.services_json:
            return []
        try:
            data = json.loads(self.services_json)
            return data if isinstance(data, list) else []
        except Exception:
            return []


class AgentGroup(Base):
    __tablename__ = "agent_groups"
    __table_args__ = (
        UniqueConstraint("agent_uuid", "group_id", name="uq_agent_group_agent_uuid_group_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_uuid: Mapped[str] = mapped_column(ForeignKey("agents.uuid", ondelete="CASCADE"), nullable=False)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    agent: Mapped[Agent] = relationship(back_populates="agent_groups")
    group: Mapped[Group] = relationship(back_populates="agent_groups")


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (
        CheckConstraint("file_type IN ('msi', 'exe', 'ps1', 'deb', 'tar.gz', 'sh')", name="ck_application_file_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    original_filename: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    version: Mapped[str] = mapped_column(String, nullable=False)
    file_hash: Mapped[str] = mapped_column(String, nullable=False)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    file_type: Mapped[str] = mapped_column(String, default="msi", nullable=False)
    target_platform: Mapped[str] = mapped_column(String, default="windows", nullable=False)
    install_args: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    uninstall_args: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_visible_in_store: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    icon_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    dependencies: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    min_os_version: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    deployments: Mapped[list["Deployment"]] = relationship(back_populates="application")


class Deployment(Base):
    __tablename__ = "deployments"
    __table_args__ = (
        CheckConstraint("target_type IN ('All', 'Group', 'Agent')", name="ck_deployment_target_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    app_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), nullable=False)
    target_type: Mapped[str] = mapped_column(String, nullable=False)
    target_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    force_update: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    application: Mapped[Application] = relationship(back_populates="deployments")


class AgentApplication(Base):
    __tablename__ = "agent_applications"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'downloading', 'installing', 'installed', 'failed', 'uninstalling', 'removed')",
            name="ck_agent_application_status",
        ),
        UniqueConstraint("agent_uuid", "app_id", name="uq_agent_application_agent_uuid_app_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_uuid: Mapped[str] = mapped_column(ForeignKey("agents.uuid", ondelete="CASCADE"), nullable=False)
    app_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), nullable=False)
    deployment_id: Mapped[Optional[int]] = mapped_column(ForeignKey("deployments.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String, default="pending", nullable=False)
    installed_version: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_attempt: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    agent: Mapped[Agent] = relationship(back_populates="agent_applications")


class TaskHistory(Base):
    __tablename__ = "task_history"
    __table_args__ = (
        CheckConstraint("action IN ('install', 'uninstall', 'update', 'self_update')", name="ck_task_history_action"),
        CheckConstraint(
            "status IN ('pending', 'downloading', 'success', 'failed', 'timeout')",
            name="ck_task_history_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_uuid: Mapped[Optional[str]] = mapped_column(ForeignKey("agents.uuid", ondelete="SET NULL"), nullable=True)
    app_id: Mapped[Optional[int]] = mapped_column(ForeignKey("applications.id", ondelete="SET NULL"), nullable=True)
    deployment_id: Mapped[Optional[int]] = mapped_column(ForeignKey("deployments.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    exit_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    download_duration_sec: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    install_duration_sec: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('admin', 'operator', 'viewer')", name="ck_user_role"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    phone_ext: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    organization: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    department: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    role: Mapped[str] = mapped_column(String, default="viewer", nullable=False)
    role_profile_id: Mapped[Optional[int]] = mapped_column(ForeignKey("role_profiles.id", ondelete="SET NULL"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    role_profile: Mapped[Optional["RoleProfile"]] = relationship()


class RoleProfile(Base):
    __tablename__ = "role_profiles"
    __table_args__ = (
        CheckConstraint("base_role IN ('admin', 'operator', 'viewer')", name="ck_role_profile_base_role"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    base_role: Mapped[str] = mapped_column(String, nullable=False, default="viewer")
    permissions_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    @property
    def permissions(self) -> list[str]:
        if not self.permissions_json:
            return []
        try:
            data = json.loads(self.permissions_json)
            if isinstance(data, list):
                return [str(x).strip() for x in data if str(x).strip()]
            return []
        except Exception:
            return []


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String, nullable=False)
    resource_type: Mapped[str] = mapped_column(String, nullable=False)
    resource_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    details_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class RemoteSupportSession(Base):
    __tablename__ = "remote_support_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending_approval','approved','rejected','connecting','active','ended','timeout','error')",
            name="ck_rs_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_uuid: Mapped[str] = mapped_column(ForeignKey("agents.uuid", ondelete="CASCADE"), nullable=False)
    admin_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String, default="pending_approval", nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    vnc_password: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    approval_timeout_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    monitor_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    connected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    max_duration_min: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    end_signal_pending: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    admin_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class RemoteSupportRecording(Base):
    __tablename__ = "remote_support_recordings"
    __table_args__ = (
        CheckConstraint(
            "status IN ('recording','completed','stopped','failed')",
            name="ck_rsr_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("remote_support_sessions.id", ondelete="CASCADE"), nullable=False)
    agent_uuid: Mapped[str] = mapped_column(ForeignKey("agents.uuid", ondelete="CASCADE"), nullable=False)
    monitor_index: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String, default="recording", nullable=False)
    target_fps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    trigger_source: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    log_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_sec: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


Index("idx_settings_key", Setting.key)
Index("idx_group_name", Group.name)
Index("idx_group_is_dynamic", Group.is_dynamic)
Index("idx_agent_status", Agent.status)
Index("idx_agent_last_seen", Agent.last_seen)
Index("idx_agent_group", Agent.group_id)
Index("idx_agent_groups_agent", AgentGroup.agent_uuid)
Index("idx_agent_groups_group", AgentGroup.group_id)
Index("idx_app_name", Application.display_name)
Index("idx_app_visible", Application.is_visible_in_store)
Index("idx_app_active", Application.is_active)
Index("idx_deployment_app", Deployment.app_id)
Index("idx_deployment_target", Deployment.target_type, Deployment.target_id)
Index("idx_deployment_active", Deployment.is_active)
Index("idx_agent_app_status", AgentApplication.status)
Index("idx_agent_app_agent", AgentApplication.agent_uuid)
Index("idx_agent_app_app", AgentApplication.app_id)
Index("idx_task_agent", TaskHistory.agent_uuid)
Index("idx_task_app", TaskHistory.app_id)
Index("idx_task_status", TaskHistory.status)
Index("idx_task_created", TaskHistory.created_at)
Index("idx_user_username", User.username)
Index("idx_user_role_profile", User.role_profile_id)
Index("idx_role_profile_key", RoleProfile.key)
Index("idx_role_profile_active", RoleProfile.is_active)
Index("idx_audit_user", AuditLog.user_id)
Index("idx_audit_action", AuditLog.action)
Index("idx_audit_resource", AuditLog.resource_type, AuditLog.resource_id)
Index("idx_audit_created", AuditLog.created_at)
Index("idx_rs_agent", RemoteSupportSession.agent_uuid)
Index("idx_rs_status", RemoteSupportSession.status)
Index("idx_rs_requested", RemoteSupportSession.requested_at)
Index("idx_rs_admin", RemoteSupportSession.admin_user_id)
Index("idx_rsr_session", RemoteSupportRecording.session_id)
Index("idx_rsr_agent", RemoteSupportRecording.agent_uuid)
Index("idx_rsr_status", RemoteSupportRecording.status)
Index("idx_rsr_started", RemoteSupportRecording.started_at)


class AgentSoftwareInventory(Base):
    __tablename__ = "agent_software_inventory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_uuid: Mapped[str] = mapped_column(ForeignKey("agents.uuid", ondelete="CASCADE"), nullable=False)
    software_name: Mapped[str] = mapped_column(String, nullable=False)
    software_version: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    publisher: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    install_date: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    estimated_size_kb: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    architecture: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    normalized_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SoftwareChangeHistory(Base):
    __tablename__ = "software_change_history"
    __table_args__ = (
        CheckConstraint("change_type IN ('installed', 'removed', 'updated')", name="ck_change_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_uuid: Mapped[str] = mapped_column(ForeignKey("agents.uuid", ondelete="CASCADE"), nullable=False)
    software_name: Mapped[str] = mapped_column(String, nullable=False)
    software_version: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    publisher: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    previous_version: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    change_type: Mapped[str] = mapped_column(String, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SoftwareNormalizationRule(Base):
    __tablename__ = "software_normalization_rules"
    __table_args__ = (
        CheckConstraint("match_type IN ('exact', 'contains', 'starts_with')", name="ck_norm_match_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pattern: Mapped[str] = mapped_column(String, nullable=False)
    normalized_name: Mapped[str] = mapped_column(String, nullable=False)
    match_type: Mapped[str] = mapped_column(String, nullable=False, default="contains")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class SoftwareLicense(Base):
    __tablename__ = "software_licenses"
    __table_args__ = (
        CheckConstraint("match_type IN ('exact', 'contains', 'starts_with')", name="ck_license_match_type"),
        CheckConstraint("license_type IN ('licensed', 'prohibited')", name="ck_license_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    software_name_pattern: Mapped[str] = mapped_column(String, nullable=False)
    match_type: Mapped[str] = mapped_column(String, nullable=False, default="contains")
    total_licenses: Mapped[int] = mapped_column(Integer, default=0)
    license_type: Mapped[str] = mapped_column(String, nullable=False, default="licensed")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class SamComplianceFinding(Base):
    __tablename__ = "sam_compliance_findings"
    __table_args__ = (
        CheckConstraint(
            "finding_type IN ('overuse','prohibited','unsupported_version','unlicensed')",
            name="ck_sam_finding_type",
        ),
        CheckConstraint(
            "severity IN ('low','medium','high','critical')",
            name="ck_sam_finding_severity",
        ),
        CheckConstraint(
            "status IN ('new','triaged','accepted_risk','remediated','closed')",
            name="ck_sam_finding_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    software_name: Mapped[str] = mapped_column(String, nullable=False)
    platform: Mapped[str] = mapped_column(String, default="all", nullable=False)
    finding_type: Mapped[str] = mapped_column(String, nullable=False)
    severity: Mapped[str] = mapped_column(String, default="medium", nullable=False)
    status: Mapped[str] = mapped_column(String, default="new", nullable=False)
    affected_agents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    details_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class SamReportSchedule(Base):
    __tablename__ = "sam_report_schedules"
    __table_args__ = (
        CheckConstraint(
            "report_type IN ('sam_prevalence','sam_compliance','sam_catalog')",
            name="ck_sam_report_type",
        ),
        CheckConstraint(
            "format IN ('csv')",
            name="ck_sam_report_format",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    report_type: Mapped[str] = mapped_column(String, nullable=False)
    format: Mapped[str] = mapped_column(String, default="csv", nullable=False)
    cron_expr: Mapped[str] = mapped_column(String, nullable=False)
    recipients: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class SamLifecyclePolicy(Base):
    __tablename__ = "sam_lifecycle_policies"
    __table_args__ = (
        CheckConstraint("match_type IN ('exact','contains','starts_with')", name="ck_sam_lifecycle_match_type"),
        CheckConstraint("platform IN ('all','windows','linux')", name="ck_sam_lifecycle_platform"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    software_name_pattern: Mapped[str] = mapped_column(String, nullable=False)
    match_type: Mapped[str] = mapped_column(String, default="contains", nullable=False)
    platform: Mapped[str] = mapped_column(String, default="all", nullable=False)
    eol_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    eos_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class SamCostProfile(Base):
    __tablename__ = "sam_cost_profiles"
    __table_args__ = (
        CheckConstraint("match_type IN ('exact','contains','starts_with')", name="ck_sam_cost_match_type"),
        CheckConstraint("platform IN ('all','windows','linux')", name="ck_sam_cost_platform"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    software_name_pattern: Mapped[str] = mapped_column(String, nullable=False)
    match_type: Mapped[str] = mapped_column(String, default="contains", nullable=False)
    platform: Mapped[str] = mapped_column(String, default="all", nullable=False)
    monthly_cost_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String, default="USD", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


Index("idx_inv_agent", AgentSoftwareInventory.agent_uuid)
Index("idx_inv_software_name", AgentSoftwareInventory.software_name)
Index("idx_inv_normalized_name", AgentSoftwareInventory.normalized_name)
Index("idx_sam_finding_status", SamComplianceFinding.status)
Index("idx_sam_finding_platform", SamComplianceFinding.platform)
Index("idx_sam_finding_software", SamComplianceFinding.software_name)
Index("idx_sam_schedule_active", SamReportSchedule.is_active)
Index("idx_sam_lifecycle_active", SamLifecyclePolicy.is_active)
Index("idx_sam_lifecycle_pattern", SamLifecyclePolicy.software_name_pattern)
Index("idx_sam_lifecycle_platform", SamLifecyclePolicy.platform)
Index("idx_sam_cost_active", SamCostProfile.is_active)
Index("idx_sam_cost_pattern", SamCostProfile.software_name_pattern)
Index("idx_sam_cost_platform", SamCostProfile.platform)
Index("idx_change_agent", SoftwareChangeHistory.agent_uuid)
Index("idx_change_detected", SoftwareChangeHistory.detected_at)
Index("idx_change_type", SoftwareChangeHistory.change_type)


class AgentSystemProfileHistory(Base):
    __tablename__ = "agent_system_profile_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_uuid: Mapped[str] = mapped_column(ForeignKey("agents.uuid", ondelete="CASCADE"), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    profile_hash: Mapped[str] = mapped_column(String, nullable=False)
    profile_json: Mapped[str] = mapped_column(Text, nullable=False)
    changed_fields_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    diff_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    @property
    def system_profile(self) -> dict:
        try:
            data = json.loads(self.profile_json or "{}")
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    @property
    def changed_fields(self) -> list[str]:
        if not self.changed_fields_json:
            return []
        try:
            data = json.loads(self.changed_fields_json)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    @property
    def diff(self) -> list[dict]:
        if not self.diff_json:
            return []
        try:
            data = json.loads(self.diff_json)
            return data if isinstance(data, list) else []
        except Exception:
            return []


Index("idx_systemhist_agent", AgentSystemProfileHistory.agent_uuid)
Index("idx_systemhist_detected", AgentSystemProfileHistory.detected_at)


class AgentIdentityHistory(Base):
    __tablename__ = "agent_identity_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_uuid: Mapped[str] = mapped_column(ForeignKey("agents.uuid", ondelete="CASCADE"), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    old_hostname: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    new_hostname: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    old_ip_address: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    new_ip_address: Mapped[Optional[str]] = mapped_column(String, nullable=True)


Index("idx_identityhist_agent", AgentIdentityHistory.agent_uuid)
Index("idx_identityhist_detected", AgentIdentityHistory.detected_at)


class AgentStatusHistory(Base):
    __tablename__ = "agent_status_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_uuid: Mapped[str] = mapped_column(ForeignKey("agents.uuid", ondelete="CASCADE"), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    old_status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    new_status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)


Index("idx_statushist_agent", AgentStatusHistory.agent_uuid)
Index("idx_statushist_detected", AgentStatusHistory.detected_at)


class AgentServiceHistory(Base):
    __tablename__ = "agent_service_history"
    __table_args__ = (
        CheckConstraint(
            "change_type IN ('added', 'removed', 'status_changed', 'startup_changed', 'updated')",
            name="ck_agent_service_history_change_type",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_uuid: Mapped[str] = mapped_column(ForeignKey("agents.uuid", ondelete="CASCADE"), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    service_name: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    change_type: Mapped[str] = mapped_column(String, nullable=False)
    old_status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    new_status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    old_startup_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    new_startup_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    old_payload_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_payload_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


Index("idx_servicehist_agent", AgentServiceHistory.agent_uuid)
Index("idx_servicehist_detected", AgentServiceHistory.detected_at)
Index("idx_servicehist_name", AgentServiceHistory.service_name)
Index("idx_norm_pattern", SoftwareNormalizationRule.pattern)
Index("idx_license_pattern", SoftwareLicense.software_name_pattern)
Index("idx_license_type", SoftwareLicense.license_type)
Index("idx_sam_finding_status", SamComplianceFinding.status)
Index("idx_sam_finding_platform", SamComplianceFinding.platform)
Index("idx_sam_finding_type", SamComplianceFinding.finding_type)
Index("idx_sam_finding_last_seen", SamComplianceFinding.last_seen_at)
Index("idx_sam_schedule_active", SamReportSchedule.is_active)
Index("idx_sam_schedule_next_run", SamReportSchedule.next_run_at)

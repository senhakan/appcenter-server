from __future__ import annotations

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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    agents: Mapped[list["Agent"]] = relationship(back_populates="group")
    agent_groups: Mapped[list["AgentGroup"]] = relationship(back_populates="group", cascade="all, delete-orphan")


class Agent(Base):
    __tablename__ = "agents"
    __table_args__ = (
        CheckConstraint("status IN ('online', 'offline')", name="ck_agent_status"),
    )

    uuid: Mapped[str] = mapped_column(String, primary_key=True)
    hostname: Mapped[str] = mapped_column(String, nullable=False)
    ip_address: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    os_user: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    os_version: Mapped[Optional[str]] = mapped_column(String, nullable=True)
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

    agent_applications: Mapped[list["AgentApplication"]] = relationship(back_populates="agent")
    agent_groups: Mapped[list["AgentGroup"]] = relationship(back_populates="agent", cascade="all, delete-orphan")

    @property
    def group_ids(self) -> list[int]:
        return sorted({item.group_id for item in self.agent_groups})


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
        CheckConstraint("file_type IN ('msi', 'exe')", name="ck_application_file_type"),
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
    role: Mapped[str] = mapped_column(String, default="viewer", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


Index("idx_settings_key", Setting.key)
Index("idx_group_name", Group.name)
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


Index("idx_inv_agent", AgentSoftwareInventory.agent_uuid)
Index("idx_inv_software_name", AgentSoftwareInventory.software_name)
Index("idx_inv_normalized_name", AgentSoftwareInventory.normalized_name)
Index("idx_change_agent", SoftwareChangeHistory.agent_uuid)
Index("idx_change_detected", SoftwareChangeHistory.detected_at)
Index("idx_change_type", SoftwareChangeHistory.change_type)
Index("idx_norm_pattern", SoftwareNormalizationRule.pattern)
Index("idx_license_pattern", SoftwareLicense.software_name_pattern)
Index("idx_license_type", SoftwareLicense.license_type)

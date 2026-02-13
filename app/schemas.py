from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    username: str
    password: str


class MessageResponse(BaseModel):
    status: str
    message: str


class AgentRegisterRequest(BaseModel):
    uuid: str
    hostname: str
    os_version: Optional[str] = None
    agent_version: Optional[str] = None
    cpu_model: Optional[str] = None
    ram_gb: Optional[int] = None
    disk_free_gb: Optional[int] = None


class AgentConfig(BaseModel):
    heartbeat_interval_sec: int = 60
    bandwidth_limit_kbps: int = 1024
    work_hour_start: str = "09:00"
    work_hour_end: str = "18:00"


class AgentRegisterResponse(BaseModel):
    status: str = "success"
    message: str = "Agent registered successfully"
    secret_key: str
    config: AgentConfig


class InstalledAppItem(BaseModel):
    app_id: int
    version: str


class HeartbeatRequest(BaseModel):
    hostname: str
    ip_address: Optional[str] = None
    os_user: Optional[str] = None
    agent_version: Optional[str] = None
    disk_free_gb: Optional[int] = None
    cpu_usage: Optional[float] = None
    ram_usage: Optional[float] = None
    current_status: Optional[str] = None
    apps_changed: bool = False
    installed_apps: list[InstalledAppItem] = Field(default_factory=list)


class CommandItem(BaseModel):
    task_id: int
    action: str
    app_id: Optional[int] = None
    app_name: Optional[str] = None
    app_version: Optional[str] = None
    download_url: Optional[str] = None
    file_hash: Optional[str] = None
    file_size_bytes: Optional[int] = None
    install_args: Optional[str] = None
    force_update: bool = False
    priority: int = 5


class HeartbeatConfig(BaseModel):
    bandwidth_limit_kbps: int = 1024
    work_hour_start: str = "09:00"
    work_hour_end: str = "18:00"
    latest_agent_version: str = "1.0.0"
    agent_download_url: Optional[str] = None
    agent_hash: Optional[str] = None


class HeartbeatResponse(BaseModel):
    status: str = "ok"
    server_time: datetime
    config: HeartbeatConfig
    commands: list[CommandItem] = Field(default_factory=list)


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: Optional[str] = None
    email: Optional[str] = None
    role: str
    is_active: bool


class ApplicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    display_name: str
    description: Optional[str] = None
    filename: str
    original_filename: Optional[str] = None
    version: str
    file_hash: str
    file_size_bytes: Optional[int] = None
    file_type: str
    install_args: Optional[str] = None
    uninstall_args: Optional[str] = None
    is_visible_in_store: bool
    category: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ApplicationListResponse(BaseModel):
    items: list[ApplicationResponse]
    total: int


class DeploymentCreateRequest(BaseModel):
    app_id: int
    target_type: str
    target_id: Optional[str] = None
    is_mandatory: bool = False
    force_update: bool = False
    priority: int = 5
    is_active: bool = True


class DeploymentUpdateRequest(BaseModel):
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    is_mandatory: Optional[bool] = None
    force_update: Optional[bool] = None
    priority: Optional[int] = None
    is_active: Optional[bool] = None


class DeploymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    app_id: int
    target_type: str
    target_id: Optional[str] = None
    is_mandatory: bool
    force_update: bool
    priority: int
    is_active: bool
    created_at: datetime
    created_by: Optional[str] = None


class DeploymentListResponse(BaseModel):
    items: list[DeploymentResponse]
    total: int


class TaskStatusRequest(BaseModel):
    status: str
    progress: Optional[int] = None
    message: Optional[str] = None
    exit_code: Optional[int] = None
    installed_version: Optional[str] = None
    download_duration_sec: Optional[int] = None
    install_duration_sec: Optional[int] = None
    error: Optional[str] = None


class AgentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uuid: str
    hostname: str
    ip_address: Optional[str] = None
    os_user: Optional[str] = None
    os_version: Optional[str] = None
    version: Optional[str] = None
    last_seen: Optional[datetime] = None
    status: str
    group_id: Optional[int] = None
    cpu_model: Optional[str] = None
    ram_gb: Optional[int] = None
    disk_free_gb: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class AgentListResponse(BaseModel):
    items: list[AgentResponse]
    total: int


class DashboardStatsResponse(BaseModel):
    total_agents: int
    online_agents: int
    offline_agents: int
    total_applications: int
    pending_tasks: int
    failed_tasks: int
    active_deployments: int


class SettingItem(BaseModel):
    key: str
    value: str
    description: Optional[str] = None
    updated_at: Optional[datetime] = None


class SettingsListResponse(BaseModel):
    items: list[SettingItem]
    total: int


class SettingsUpdateRequest(BaseModel):
    values: dict[str, str]


class StoreAppItem(BaseModel):
    id: int
    display_name: str
    version: str
    description: Optional[str] = None
    icon_url: Optional[str] = None
    file_size_mb: int
    category: Optional[str] = None
    installed: bool
    installed_version: Optional[str] = None
    can_uninstall: bool


class StoreResponse(BaseModel):
    apps: list[StoreAppItem]


class AgentUpdateUploadResponse(BaseModel):
    status: str
    message: str
    version: str
    file_hash: str
    filename: str
    download_url: str

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


class LoggedInSession(BaseModel):
    username: str
    # Keep this as a string so older/newer agents can extend without breaking,
    # but we currently expect "local" or "rdp".
    session_type: str
    logon_id: Optional[str] = None


class SystemDisk(BaseModel):
    index: int
    size_gb: Optional[int] = None
    model: Optional[str] = None
    bus_type: Optional[str] = None


class VirtualizationInfo(BaseModel):
    is_virtual: bool = False
    vendor: Optional[str] = None
    model: Optional[str] = None


class SystemProfile(BaseModel):
    os_full_name: Optional[str] = None
    os_version: Optional[str] = None
    build_number: Optional[str] = None
    architecture: Optional[str] = None

    manufacturer: Optional[str] = None
    model: Optional[str] = None

    cpu_model: Optional[str] = None
    cpu_cores_physical: Optional[int] = None
    cpu_cores_logical: Optional[int] = None

    total_memory_gb: Optional[int] = None

    disk_count: Optional[int] = None
    disks: list[SystemDisk] = Field(default_factory=list)

    virtualization: Optional[VirtualizationInfo] = None


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
    inventory_hash: Optional[str] = None
    logged_in_sessions: Optional[list[LoggedInSession]] = None
    system_profile: Optional[SystemProfile] = None


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
    inventory_sync_required: bool = False
    inventory_scan_interval_min: int = 10


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
    icon_url: Optional[str] = None
    category: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ApplicationListResponse(BaseModel):
    items: list[ApplicationResponse]
    total: int


class ApplicationUpdateRequest(BaseModel):
    display_name: Optional[str] = None
    version: Optional[str] = None
    description: Optional[str] = None
    install_args: Optional[str] = None
    uninstall_args: Optional[str] = None
    is_visible_in_store: Optional[bool] = None
    category: Optional[str] = None
    is_active: Optional[bool] = None


class DeploymentCreateRequest(BaseModel):
    app_id: int
    target_type: str
    target_id: Optional[str] = None
    is_mandatory: bool = False
    force_update: bool = False
    priority: int = 5
    is_active: bool = True


class DeploymentUpdateRequest(BaseModel):
    app_id: Optional[int] = None
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
    group_ids: list[int] = Field(default_factory=list)
    cpu_model: Optional[str] = None
    ram_gb: Optional[int] = None
    disk_free_gb: Optional[int] = None
    logged_in_sessions: list[LoggedInSession] = Field(default_factory=list)
    logged_in_sessions_updated_at: Optional[datetime] = None
    system_profile: Optional[SystemProfile] = None
    system_profile_updated_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class SystemProfileHistoryItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    detected_at: datetime
    changed_fields: list[str] = Field(default_factory=list)
    diff: list[dict] = Field(default_factory=list)
    system_profile: SystemProfile


class AgentSystemHistoryListResponse(BaseModel):
    items: list[SystemProfileHistoryItemResponse]
    total: int


class AgentTimelineItemResponse(BaseModel):
    event_type: str
    detected_at: datetime

    # system_profile event
    changed_fields: list[str] = Field(default_factory=list)
    diff: list[dict] = Field(default_factory=list)
    system_profile: Optional[SystemProfile] = None

    # identity event
    old_hostname: Optional[str] = None
    new_hostname: Optional[str] = None
    old_ip_address: Optional[str] = None
    new_ip_address: Optional[str] = None


class AgentTimelineListResponse(BaseModel):
    items: list[AgentTimelineItemResponse]
    total: int


class AgentListResponse(BaseModel):
    items: list[AgentResponse]
    total: int


class GroupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str] = None
    created_at: datetime


class GroupListResponse(BaseModel):
    items: list[GroupResponse]
    total: int


class GroupCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None


class GroupUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class GroupAssignAgentsRequest(BaseModel):
    agent_uuids: list[str] = Field(default_factory=list)


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


# --- Inventory schemas ---


class SoftwareItem(BaseModel):
    name: str
    version: Optional[str] = None
    publisher: Optional[str] = None
    install_date: Optional[str] = None
    estimated_size_kb: Optional[int] = None
    architecture: Optional[str] = None


class AgentInventoryRequest(BaseModel):
    inventory_hash: str
    software_count: int
    items: list[SoftwareItem]


class AgentInventoryResponse(BaseModel):
    status: str = "ok"
    message: str
    changes: dict


class InventoryItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    software_name: str
    software_version: Optional[str] = None
    publisher: Optional[str] = None
    install_date: Optional[str] = None
    estimated_size_kb: Optional[int] = None
    architecture: Optional[str] = None
    normalized_name: Optional[str] = None


class AgentInventoryListResponse(BaseModel):
    items: list[InventoryItemResponse]
    total: int


class ChangeHistoryItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    software_name: str
    software_version: Optional[str] = None
    publisher: Optional[str] = None
    previous_version: Optional[str] = None
    change_type: str
    detected_at: datetime


class AgentChangeHistoryListResponse(BaseModel):
    items: list[ChangeHistoryItemResponse]
    total: int


class SoftwareSummaryItem(BaseModel):
    name: str
    agent_count: int
    versions: list[str]


class SoftwareSummaryListResponse(BaseModel):
    items: list[SoftwareSummaryItem]
    total: int


class SoftwareAgentItem(BaseModel):
    agent_uuid: str
    hostname: str
    software_version: Optional[str] = None
    status: str


class SoftwareAgentListResponse(BaseModel):
    items: list[SoftwareAgentItem]
    total: int


class InventoryDashboardResponse(BaseModel):
    total_unique_software: int
    license_violations: int
    prohibited_alerts: int
    agents_with_inventory: int
    added_today: int
    removed_today: int


# --- Normalization rule schemas ---


class NormalizationRuleCreateRequest(BaseModel):
    pattern: str
    normalized_name: str
    match_type: str = "contains"


class NormalizationRuleUpdateRequest(BaseModel):
    pattern: Optional[str] = None
    normalized_name: Optional[str] = None
    match_type: Optional[str] = None
    is_active: Optional[bool] = None


class NormalizationRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pattern: str
    normalized_name: str
    match_type: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class NormalizationRuleListResponse(BaseModel):
    items: list[NormalizationRuleResponse]
    total: int


# --- License schemas ---


class LicenseCreateRequest(BaseModel):
    software_name_pattern: str
    match_type: str = "contains"
    total_licenses: int = 0
    license_type: str = "licensed"
    description: Optional[str] = None


class LicenseUpdateRequest(BaseModel):
    software_name_pattern: Optional[str] = None
    match_type: Optional[str] = None
    total_licenses: Optional[int] = None
    license_type: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class LicenseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    software_name_pattern: str
    match_type: str
    total_licenses: int
    license_type: str
    description: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class LicenseListResponse(BaseModel):
    items: list[LicenseResponse]
    total: int


class LicenseUsageReportItem(BaseModel):
    license_id: int
    pattern: str
    license_type: str
    total_licenses: int
    usage: int
    surplus: int
    is_violation: bool


class LicenseUsageReportResponse(BaseModel):
    items: list[LicenseUsageReportItem]
    total: int

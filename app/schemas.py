from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: Optional[datetime] = None
    expires_in_sec: Optional[int] = None
    auth_source: Optional[str] = None


class LoginRequest(BaseModel):
    username: str
    password: str


class ProfileUpdateRequest(BaseModel):
    full_name: Optional[str] = Field(default=None, max_length=200)
    email: Optional[str] = Field(default=None, max_length=200)
    phone: Optional[str] = Field(default=None, max_length=50)
    phone_ext: Optional[str] = Field(default=None, max_length=20)
    organization: Optional[str] = Field(default=None, max_length=200)
    department: Optional[str] = Field(default=None, max_length=200)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=6, max_length=256)


class MessageResponse(BaseModel):
    status: str
    message: str


class AgentRegisterRequest(BaseModel):
    uuid: str
    hostname: str
    os_version: Optional[str] = None
    platform: Optional[str] = None
    arch: Optional[str] = None
    distro: Optional[str] = None
    distro_version: Optional[str] = None
    agent_version: Optional[str] = None
    cpu_model: Optional[str] = None
    ram_gb: Optional[int] = None
    disk_free_gb: Optional[int] = None


class AgentConfig(BaseModel):
    heartbeat_interval_sec: int = 60
    bandwidth_limit_kbps: int = 1024


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
    session_state: Optional[str] = None
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


class RemoteSupportHeartbeat(BaseModel):
    state: Optional[str] = None
    session_id: Optional[int] = None
    helper_running: bool = False
    helper_pid: Optional[int] = None


class ServiceItem(BaseModel):
    name: str
    display_name: Optional[str] = None
    status: str = "unknown"
    startup_type: str = "unknown"
    pid: Optional[int] = None
    run_as: Optional[str] = None
    description: Optional[str] = None


class HeartbeatRequest(BaseModel):
    hostname: str
    ip_address: Optional[str] = None
    full_ip: Optional[list[str]] = None
    uptime_sec: Optional[int] = None
    os_user: Optional[str] = None
    os_version: Optional[str] = None
    arch: Optional[str] = None
    distro: Optional[str] = None
    distro_version: Optional[str] = None
    agent_version: Optional[str] = None
    cpu_model: Optional[str] = None
    ram_gb: Optional[int] = None
    disk_free_gb: Optional[int] = None
    cpu_usage: Optional[float] = None
    ram_usage: Optional[float] = None
    current_status: Optional[str] = None
    apps_changed: bool = False
    installed_apps: list[InstalledAppItem] = Field(default_factory=list)
    inventory_hash: Optional[str] = None
    services_hash: Optional[str] = None
    services: Optional[list[ServiceItem]] = None
    platform: Optional[str] = None
    logged_in_sessions: Optional[list[LoggedInSession]] = None
    system_profile: Optional[SystemProfile] = None
    remote_support: Optional[RemoteSupportHeartbeat] = None


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
    latest_agent_version: str = "1.0.0"
    agent_download_url: Optional[str] = None
    agent_hash: Optional[str] = None
    inventory_sync_required: bool = False
    services_sync_required: bool = False
    service_monitoring_enabled: bool = False
    inventory_scan_interval_min: int = 10
    store_tray_enabled: bool = False
    remote_support_enabled: bool = False
    websocket_enabled: bool = False
    runtime_update_interval_min: int = 60
    runtime_update_jitter_sec: int = 300


class RemoteSupportRequest(BaseModel):
    session_id: int
    admin_name: str
    reason: str = ""
    requested_at: datetime
    timeout_at: datetime
    requires_approval: bool = True


class RemoteSupportEnd(BaseModel):
    session_id: int


class PendingAnnouncementItem(BaseModel):
    announcement_id: int
    title: str
    message: str
    priority: str


class HeartbeatResponse(BaseModel):
    status: str = "ok"
    server_time: datetime
    config: HeartbeatConfig
    commands: list[CommandItem] = Field(default_factory=list)
    remote_support_request: Optional[RemoteSupportRequest] = None
    remote_support_end: Optional[RemoteSupportEnd] = None
    pending_announcements: list[PendingAnnouncementItem] = Field(default_factory=list)


class RemoteSessionCreateRequest(BaseModel):
    agent_uuid: str
    reason: str = Field(min_length=3, max_length=500)
    max_duration_min: Optional[int] = Field(default=None, ge=1, le=480)


class RemoteSessionAgentApproveRequest(BaseModel):
    approved: bool
    monitor_count: Optional[int] = Field(default=None, ge=1, le=16)


class RemoteSessionReadyRequest(BaseModel):
    vnc_ready: bool = True
    local_vnc_port: int = 20010


class RemoteSessionEndedRequest(BaseModel):
    ended_by: str = "agent"
    reason: str = ""


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    phone_ext: Optional[str] = None
    organization: Optional[str] = None
    department: Optional[str] = None
    avatar_url: Optional[str] = None
    auth_source: str = "local"
    role: str
    role_profile_id: Optional[int] = None
    role_profile_key: Optional[str] = None
    role_profile_name: Optional[str] = None
    permissions: list[str] = Field(default_factory=list)
    is_active: bool


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=6, max_length=256)
    full_name: Optional[str] = Field(default=None, max_length=200)
    email: Optional[str] = Field(default=None, max_length=200)
    role: Optional[str] = None
    role_profile_id: Optional[int] = None
    is_active: bool = True


class UserUpdateRequest(BaseModel):
    username: Optional[str] = Field(default=None, min_length=3, max_length=120)
    password: Optional[str] = Field(default=None, min_length=6, max_length=256)
    full_name: Optional[str] = Field(default=None, max_length=200)
    email: Optional[str] = Field(default=None, max_length=200)
    role: Optional[str] = None
    role_profile_id: Optional[int] = None
    is_active: Optional[bool] = None


class UserListResponse(BaseModel):
    items: list[UserPublic]
    total: int


class RoleProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    key: str
    name: str
    description: Optional[str] = None
    permissions: list[str] = Field(default_factory=list)
    is_system: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class RoleProfileListResponse(BaseModel):
    items: list[RoleProfileResponse]
    total: int


class RoleProfileCreateRequest(BaseModel):
    key: str = Field(min_length=2, max_length=80)
    name: str = Field(min_length=2, max_length=120)
    description: Optional[str] = Field(default=None, max_length=500)
    permissions: list[str] = Field(default_factory=list)
    is_active: bool = True


class RoleProfileUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    description: Optional[str] = Field(default=None, max_length=500)
    permissions: Optional[list[str]] = None
    is_active: Optional[bool] = None


class AuditLogItemResponse(BaseModel):
    id: int
    user_id: Optional[int] = None
    username: Optional[str] = None
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    details_json: Optional[str] = None
    created_at: datetime


class AuditLogListResponse(BaseModel):
    items: list[AuditLogItemResponse]
    total: int


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
    target_platform: str = "windows"
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


class ApplicationScriptPreviewResponse(BaseModel):
    app_id: int
    filename: str
    file_type: str
    content: str
    truncated: bool = False


class ApplicationUpdateRequest(BaseModel):
    display_name: Optional[str] = None
    version: Optional[str] = None
    description: Optional[str] = None
    install_args: Optional[str] = None
    uninstall_args: Optional[str] = None
    is_visible_in_store: Optional[bool] = None
    category: Optional[str] = None
    target_platform: Optional[str] = None
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


class DeploymentClientLogItemResponse(BaseModel):
    agent_uuid: str
    agent_hostname: str
    agent_platform: str
    agent_status: str
    app_status: str
    installed_version: Optional[str] = None
    agent_error: Optional[str] = None
    task_id: Optional[int] = None
    task_status: Optional[str] = None
    task_message: Optional[str] = None
    exit_code: Optional[int] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    task_created_at: Optional[datetime] = None
    download_duration_sec: Optional[int] = None
    install_duration_sec: Optional[int] = None
    updated_at: Optional[datetime] = None


class DeploymentClientLogListResponse(BaseModel):
    items: list[DeploymentClientLogItemResponse]
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
    full_ip: Optional[str] = None
    uptime_sec: Optional[int] = None
    services_updated_at: Optional[datetime] = None
    services_hash: Optional[str] = None
    service_monitoring_enabled: Optional[bool] = None
    remote_support_approval_required: Optional[bool] = None
    os_user: Optional[str] = None
    os_version: Optional[str] = None
    platform: str = "windows"
    arch: Optional[str] = None
    distro: Optional[str] = None
    distro_version: Optional[str] = None
    version: Optional[str] = None
    last_seen: Optional[datetime] = None
    status: str
    group_id: Optional[int] = None
    group_ids: list[int] = Field(default_factory=list)
    cpu_model: Optional[str] = None
    ram_gb: Optional[int] = None
    disk_free_gb: Optional[int] = None
    notes: Optional[str] = None
    logged_in_sessions: list[LoggedInSession] = Field(default_factory=list)
    logged_in_sessions_updated_at: Optional[datetime] = None
    system_profile: Optional[SystemProfile] = None
    system_profile_updated_at: Optional[datetime] = None
    remote_support_state: Optional[str] = None
    remote_support_session_id: Optional[int] = None
    remote_support_helper_running: bool = False
    remote_support_helper_pid: Optional[int] = None
    remote_support_updated_at: Optional[datetime] = None
    remote_support_allowed: bool = False
    last_remote_connected_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class AgentNotesUpdateRequest(BaseModel):
    notes: Optional[str] = None


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

    # status event
    old_status: Optional[str] = None
    new_status: Optional[str] = None
    reason: Optional[str] = None

    # task event
    task_action: Optional[str] = None
    task_status: Optional[str] = None
    app_name: Optional[str] = None
    message: Optional[str] = None
    exit_code: Optional[int] = None

    # service event
    service_name: Optional[str] = None
    service_display_name: Optional[str] = None
    service_change_type: Optional[str] = None
    old_startup_type: Optional[str] = None
    new_startup_type: Optional[str] = None


class AgentTimelineListResponse(BaseModel):
    items: list[AgentTimelineItemResponse]
    total: int


class DashboardTimelineItemResponse(BaseModel):
    event_type: str
    detected_at: datetime
    agent_uuid: str
    hostname: Optional[str] = None
    summary: str
    severity: Optional[str] = None


class DashboardTimelineListResponse(BaseModel):
    items: list[DashboardTimelineItemResponse]


class AgentListResponse(BaseModel):
    items: list[AgentResponse]
    total: int


class GroupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str] = None
    is_active: bool
    is_dynamic: bool = False
    dynamic_rules: Optional[dict] = None
    created_at: datetime
    is_system: bool = False


class GroupListResponse(BaseModel):
    items: list[GroupResponse]
    total: int


class GroupCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    is_dynamic: bool = False
    dynamic_rules: Optional[dict] = None


class GroupUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    is_dynamic: Optional[bool] = None
    dynamic_rules: Optional[dict] = None


class GroupAssignAgentsRequest(BaseModel):
    agent_uuids: list[str] = Field(default_factory=list)


class GroupDynamicPreviewRequest(BaseModel):
    hostname_patterns: list[str] = Field(default_factory=list)
    ip_patterns: list[str] = Field(default_factory=list)
    sample_limit: int = Field(default=5, ge=1, le=20)


class GroupDynamicPreviewItem(BaseModel):
    uuid: str
    hostname: str
    ip_address: Optional[str] = None
    status: str


class GroupDynamicPreviewResponse(BaseModel):
    total: int
    items: list[GroupDynamicPreviewItem]


class DashboardStatsResponse(BaseModel):
    total_agents: int
    online_agents: int
    offline_agents: int
    total_applications: int
    pending_tasks: int
    failed_tasks: int
    active_deployments: int
    active_remote_sessions: int


class DashboardTopClientItemResponse(BaseModel):
    agent_uuid: str
    hostname: str
    status: str
    installed_app_count: int
    last_seen: Optional[datetime] = None


class DashboardTopClientListResponse(BaseModel):
    items: list[DashboardTopClientItemResponse]


class DashboardTrendsResponse(BaseModel):
    labels: list[str]
    online_transitions: list[int]
    offline_transitions: list[int]
    task_success: list[int]
    task_failed: list[int]
    task_pending: list[int]


class DashboardComplianceClientItemResponse(BaseModel):
    agent_uuid: str
    hostname: str
    status: str
    licensed_violations: int
    prohibited_hits: int
    risk_score: int


class DashboardComplianceBreakdownResponse(BaseModel):
    violation_licensed_rules: int
    violation_prohibited_rules: int
    at_risk_agents: int
    items: list[DashboardComplianceClientItemResponse]


class DashboardRemoteMetricsResponse(BaseModel):
    active_sessions: int
    sessions_last_7d: int
    rejected_last_7d: int
    timeout_last_7d: int
    error_last_7d: int
    avg_approval_delay_sec: int
    avg_session_duration_sec: int


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


class SettingsAgentBroadcastRequest(BaseModel):
    action: Literal["self_update"]
    mode: Literal["normal", "force"] = "normal"


class SettingsAgentBroadcastResponse(BaseModel):
    status: str = "success"
    message: str
    action: str
    targeted: int
    skipped: int
    targeted_agents: list[str] = Field(default_factory=list)
    skipped_agents: list[str] = Field(default_factory=list)


class AgentServiceMonitoringUpdateRequest(BaseModel):
    # null means "inherit global setting"
    enabled: Optional[bool] = None


class AgentRemoteSupportApprovalUpdateRequest(BaseModel):
    # null means "inherit global setting"
    enabled: Optional[bool] = None


class StoreAppItem(BaseModel):
    id: int
    display_name: str
    version: str
    description: Optional[str] = None
    icon_url: Optional[str] = None
    file_size_mb: int
    category: Optional[str] = None
    installed: bool
    install_state: Optional[str] = None
    error_message: Optional[str] = None
    conflict_detected: bool = False
    conflict_confidence: Optional[str] = None
    conflict_message: Optional[str] = None
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
    normalized_publisher: Optional[str] = None
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
    normalized_publisher: Optional[str] = None
    previous_version: Optional[str] = None
    change_type: str
    detected_at: datetime


class AgentChangeHistoryListResponse(BaseModel):
    items: list[ChangeHistoryItemResponse]
    total: int


class AgentServiceItemResponse(BaseModel):
    name: str
    display_name: Optional[str] = None
    status: str
    startup_type: str
    pid: Optional[int] = None
    run_as: Optional[str] = None
    description: Optional[str] = None


class AgentServiceListResponse(BaseModel):
    items: list[AgentServiceItemResponse]
    total: int


class AgentServiceHistoryItemResponse(BaseModel):
    id: int
    detected_at: datetime
    service_name: str
    display_name: Optional[str] = None
    change_type: str
    old_status: Optional[str] = None
    new_status: Optional[str] = None
    old_startup_type: Optional[str] = None
    new_startup_type: Optional[str] = None


class AgentServiceHistoryListResponse(BaseModel):
    items: list[AgentServiceHistoryItemResponse]
    total: int


class SoftwareSummaryItem(BaseModel):
    name: str
    publisher: Optional[str] = None
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


class SamPlatformKpi(BaseModel):
    platform: str
    total_agents: int
    agents_with_inventory: int
    unique_software: int
    install_rows: int
    added_24h: int
    removed_24h: int
    updated_24h: int


class SamTopSoftwareItem(BaseModel):
    name: str
    platform: str
    agent_count: int


class SamDashboardResponse(BaseModel):
    total_agents: int
    agents_with_inventory: int
    unique_software: int
    normalized_unique_software: int
    normalized_rows: int
    platform_items: list[SamPlatformKpi]
    top_software: list[SamTopSoftwareItem]


class SamCatalogItem(BaseModel):
    name: str
    total_agents: int
    windows_agents: int
    linux_agents: int
    install_rows: int
    versions: list[str]


class SamCatalogListResponse(BaseModel):
    items: list[SamCatalogItem]
    total: int
    page: int
    per_page: int


class SamComplianceFindingItem(BaseModel):
    id: int
    software_name: str
    platform: str
    finding_type: str
    severity: str
    status: str
    affected_agents: int
    details_json: Optional[str] = None
    first_seen_at: datetime
    last_seen_at: datetime
    resolved_at: Optional[datetime] = None


class SamComplianceFindingListResponse(BaseModel):
    items: list[SamComplianceFindingItem]
    total: int


class SamComplianceStatusUpdateRequest(BaseModel):
    status: str


class SamReportScheduleCreateRequest(BaseModel):
    name: str
    report_type: str
    format: str = "csv"
    cron_expr: str
    recipients: Optional[str] = None
    is_active: bool = True


class SamReportScheduleUpdateRequest(BaseModel):
    name: Optional[str] = None
    report_type: Optional[str] = None
    format: Optional[str] = None
    cron_expr: Optional[str] = None
    recipients: Optional[str] = None
    is_active: Optional[bool] = None


class SamReportScheduleItem(BaseModel):
    id: int
    name: str
    report_type: str
    format: str
    cron_expr: str
    recipients: Optional[str] = None
    is_active: bool
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class SamReportScheduleListResponse(BaseModel):
    items: list[SamReportScheduleItem]
    total: int


class SamLifecyclePolicyCreateRequest(BaseModel):
    software_name_pattern: str
    match_type: str = "contains"
    platform: str = "all"
    eol_date: Optional[datetime] = None
    eos_date: Optional[datetime] = None
    is_active: bool = True
    notes: Optional[str] = None


class SamLifecyclePolicyUpdateRequest(BaseModel):
    software_name_pattern: Optional[str] = None
    match_type: Optional[str] = None
    platform: Optional[str] = None
    eol_date: Optional[datetime] = None
    eos_date: Optional[datetime] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None


class SamLifecyclePolicyItem(BaseModel):
    id: int
    software_name_pattern: str
    match_type: str
    platform: str
    eol_date: Optional[datetime] = None
    eos_date: Optional[datetime] = None
    is_active: bool
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class SamLifecyclePolicyListResponse(BaseModel):
    items: list[SamLifecyclePolicyItem]
    total: int


class SamCostProfileCreateRequest(BaseModel):
    software_name_pattern: str
    match_type: str = "contains"
    platform: str = "all"
    monthly_cost_cents: int = 0
    currency: str = "USD"
    is_active: bool = True
    notes: Optional[str] = None


class SamCostProfileUpdateRequest(BaseModel):
    software_name_pattern: Optional[str] = None
    match_type: Optional[str] = None
    platform: Optional[str] = None
    monthly_cost_cents: Optional[int] = None
    currency: Optional[str] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None


class SamCostProfileItem(BaseModel):
    id: int
    software_name_pattern: str
    match_type: str
    platform: str
    monthly_cost_cents: int
    currency: str
    is_active: bool
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class SamCostProfileListResponse(BaseModel):
    items: list[SamCostProfileItem]
    total: int


class SamRiskOverviewItem(BaseModel):
    software_name: str
    platform: str
    agent_count: int
    lifecycle_status: str
    days_to_eol: Optional[int] = None
    days_to_eos: Optional[int] = None
    estimated_monthly_cost_cents: int = 0
    currency: str = "USD"


class SamRiskOverviewResponse(BaseModel):
    items: list[SamRiskOverviewItem]
    total: int
    critical_count: int
    warning_count: int
    monthly_cost_cents_total: int


class SamGeneratedReportItem(BaseModel):
    filename: str
    report_type: str
    created_at: datetime
    size_bytes: int
    download_url: str


class SamGeneratedReportListResponse(BaseModel):
    items: list[SamGeneratedReportItem]
    total: int


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


class LicenseRecommendationItem(BaseModel):
    pattern: str
    severity: str
    action: str
    reason: str
    affected: int
    delta: int


class LicenseRecommendationResponse(BaseModel):
    items: list[LicenseRecommendationItem]
    total: int


class InventoryTrendPoint(BaseModel):
    date: str
    installed: int
    removed: int
    updated: int
    total: int
    alert_level: str = "normal"
    alert_reason: Optional[str] = None


class InventoryTrendAlert(BaseModel):
    date: str
    level: str
    total: int
    baseline: float


class InventoryTrendSummary(BaseModel):
    days: int
    total_events: int
    avg_daily_events: float
    last_day_events: int
    max_daily_events: int


class InventoryTrendResponse(BaseModel):
    points: list[InventoryTrendPoint]
    alerts: list[InventoryTrendAlert]
    summary: InventoryTrendSummary


class SamPerformanceCheck(BaseModel):
    query: str
    duration_ms: float
    target_ms: float
    within_target: bool


class SamPerformanceResponse(BaseModel):
    target_ms: float
    max_duration_ms: float
    within_target: bool
    checks: list[SamPerformanceCheck]


# --- Announcement schemas ---


class AnnouncementCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=5000)
    priority: Literal["normal", "important", "critical"] = "normal"
    target_type: Literal["All", "Group", "Agent"]
    target_id: Optional[str] = None
    delivery_mode: Literal["online_only", "include_offline"] = "online_only"
    scheduled_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None


class AnnouncementUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    message: Optional[str] = Field(default=None, min_length=1, max_length=5000)
    priority: Optional[Literal["normal", "important", "critical"]] = None
    target_type: Optional[Literal["All", "Group", "Agent"]] = None
    target_id: Optional[str] = None
    delivery_mode: Optional[Literal["online_only", "include_offline"]] = None
    scheduled_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None


class AnnouncementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    message: str
    priority: str
    target_type: str
    target_id: Optional[str] = None
    target_name: Optional[str] = None
    delivery_mode: str
    status: str
    scheduled_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    created_by: Optional[int] = None
    created_by_username: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    total_targets: int
    delivered_count: int
    acknowledged_count: int
    failed_count: int
    pending_count: int = 0


class AnnouncementListResponse(BaseModel):
    items: list[AnnouncementResponse]
    total: int


class AnnouncementDeliveryItemResponse(BaseModel):
    id: int
    agent_uuid: str
    agent_hostname: Optional[str] = None
    agent_status: Optional[str] = None
    status: str
    delivered_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None
    failure_reason: Optional[str] = None
    retry_count: int


class AnnouncementDeliveryListResponse(BaseModel):
    items: list[AnnouncementDeliveryItemResponse]
    total: int


class AnnouncementAckRequest(BaseModel):
    announcement_id: int


class AssetNodeTypeLabelResponse(BaseModel):
    code: str
    display_name: str
    sort_order: int = 0
    is_active: bool = True


class AssetDictionaryResponse(BaseModel):
    organization_node_types: list[AssetNodeTypeLabelResponse]
    location_node_types: list[AssetNodeTypeLabelResponse]
    device_types: list[str]
    usage_types: list[str]
    ownership_types: list[str]
    lifecycle_statuses: list[str]


class AssetOrganizationNodeBase(BaseModel):
    node_type: str = Field(min_length=1, max_length=64)
    parent_id: Optional[int] = None
    name: str = Field(min_length=1, max_length=200)
    code: Optional[str] = Field(default=None, max_length=120)
    is_active: bool = True
    sort_order: int = 0
    notes: Optional[str] = None


class AssetOrganizationNodeUpdateRequest(BaseModel):
    node_type: Optional[str] = Field(default=None, min_length=1, max_length=64)
    parent_id: Optional[int] = None
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    code: Optional[str] = Field(default=None, max_length=120)
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None
    notes: Optional[str] = None


class AssetOrganizationNodeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    parent_id: Optional[int] = None
    node_type: str
    name: str
    code: Optional[str] = None
    is_active: bool
    sort_order: int
    notes: Optional[str] = None
    path: str = ""
    asset_count: int = 0
    created_at: datetime
    updated_at: datetime


class AssetOrganizationNodeListResponse(BaseModel):
    items: list[AssetOrganizationNodeResponse]
    total: int


class AssetLocationNodeBase(BaseModel):
    location_type: str = Field(min_length=1, max_length=64)
    parent_id: Optional[int] = None
    org_node_id: Optional[int] = None
    name: str = Field(min_length=1, max_length=200)
    code: Optional[str] = Field(default=None, max_length=120)
    address_text: Optional[str] = None
    is_active: bool = True
    notes: Optional[str] = None


class AssetLocationNodeUpdateRequest(BaseModel):
    location_type: Optional[str] = Field(default=None, min_length=1, max_length=64)
    parent_id: Optional[int] = None
    org_node_id: Optional[int] = None
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    code: Optional[str] = Field(default=None, max_length=120)
    address_text: Optional[str] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None


class AssetLocationNodeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    parent_id: Optional[int] = None
    org_node_id: Optional[int] = None
    location_type: str
    name: str
    code: Optional[str] = None
    address_text: Optional[str] = None
    is_active: bool
    notes: Optional[str] = None
    path: str = ""
    asset_count: int = 0
    created_at: datetime
    updated_at: datetime


class AssetLocationNodeListResponse(BaseModel):
    items: list[AssetLocationNodeResponse]
    total: int


class AssetPersonCreateRequest(BaseModel):
    person_code: Optional[str] = Field(default=None, max_length=120)
    username: Optional[str] = Field(default=None, max_length=120)
    full_name: str = Field(min_length=1, max_length=200)
    email: Optional[str] = Field(default=None, max_length=200)
    phone: Optional[str] = Field(default=None, max_length=50)
    title: Optional[str] = Field(default=None, max_length=200)
    org_node_id: Optional[int] = None
    cost_center_id: Optional[int] = None
    source_type: str = Field(default="manual", max_length=30)
    is_active: bool = True


class AssetPersonUpdateRequest(BaseModel):
    person_code: Optional[str] = Field(default=None, max_length=120)
    username: Optional[str] = Field(default=None, max_length=120)
    full_name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    email: Optional[str] = Field(default=None, max_length=200)
    phone: Optional[str] = Field(default=None, max_length=50)
    title: Optional[str] = Field(default=None, max_length=200)
    org_node_id: Optional[int] = None
    cost_center_id: Optional[int] = None
    source_type: Optional[str] = Field(default=None, max_length=30)
    is_active: Optional[bool] = None


class AssetPersonResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    person_code: Optional[str] = None
    username: Optional[str] = None
    full_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    title: Optional[str] = None
    org_node_id: Optional[int] = None
    org_path: Optional[str] = None
    cost_center_id: Optional[int] = None
    cost_center_name: Optional[str] = None
    source_type: str
    is_active: bool
    asset_count: int = 0
    created_at: datetime
    updated_at: datetime


class AssetPersonListResponse(BaseModel):
    items: list[AssetPersonResponse]
    total: int


class AssetPersonLinkedAssetResponse(BaseModel):
    id: int
    asset_tag: str
    device_type: str
    lifecycle_status: str


class AssetPersonDetailResponse(AssetPersonResponse):
    linked_assets: list[AssetPersonLinkedAssetResponse] = Field(default_factory=list)


class AssetCostCenterCreateRequest(BaseModel):
    parent_id: Optional[int] = None
    code: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    org_node_id: Optional[int] = None
    is_active: bool = True


class AssetCostCenterUpdateRequest(BaseModel):
    parent_id: Optional[int] = None
    code: Optional[str] = Field(default=None, min_length=1, max_length=120)
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    org_node_id: Optional[int] = None
    is_active: Optional[bool] = None


class AssetCostCenterResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    parent_id: Optional[int] = None
    code: str
    name: str
    org_node_id: Optional[int] = None
    org_path: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AssetCostCenterListResponse(BaseModel):
    items: list[AssetCostCenterResponse]
    total: int


class AssetRecordCreateRequest(BaseModel):
    asset_tag: str = Field(min_length=1, max_length=120)
    serial_number: Optional[str] = Field(default=None, max_length=200)
    inventory_number: Optional[str] = Field(default=None, max_length=200)
    device_type: str = Field(min_length=1, max_length=64)
    usage_type: str = Field(min_length=1, max_length=64)
    ownership_type: str = Field(min_length=1, max_length=64)
    lifecycle_status: str = Field(min_length=1, max_length=64)
    criticality: Optional[str] = Field(default=None, max_length=64)
    manufacturer: Optional[str] = Field(default=None, max_length=200)
    model: Optional[str] = Field(default=None, max_length=200)
    purchase_date: Optional[str] = Field(default=None, max_length=32)
    warranty_end_date: Optional[str] = Field(default=None, max_length=32)
    org_node_id: int
    location_node_id: int
    cost_center_id: Optional[int] = None
    primary_person_id: Optional[int] = None
    owner_person_id: Optional[int] = None
    support_team: Optional[str] = Field(default=None, max_length=200)
    is_active: bool = True
    notes: Optional[str] = None


class AssetRecordUpdateRequest(BaseModel):
    asset_tag: Optional[str] = Field(default=None, min_length=1, max_length=120)
    serial_number: Optional[str] = Field(default=None, max_length=200)
    inventory_number: Optional[str] = Field(default=None, max_length=200)
    device_type: Optional[str] = Field(default=None, min_length=1, max_length=64)
    usage_type: Optional[str] = Field(default=None, min_length=1, max_length=64)
    ownership_type: Optional[str] = Field(default=None, min_length=1, max_length=64)
    lifecycle_status: Optional[str] = Field(default=None, min_length=1, max_length=64)
    criticality: Optional[str] = Field(default=None, max_length=64)
    manufacturer: Optional[str] = Field(default=None, max_length=200)
    model: Optional[str] = Field(default=None, max_length=200)
    purchase_date: Optional[str] = Field(default=None, max_length=32)
    warranty_end_date: Optional[str] = Field(default=None, max_length=32)
    org_node_id: Optional[int] = None
    location_node_id: Optional[int] = None
    cost_center_id: Optional[int] = None
    primary_person_id: Optional[int] = None
    owner_person_id: Optional[int] = None
    support_team: Optional[str] = Field(default=None, max_length=200)
    is_active: Optional[bool] = None
    notes: Optional[str] = None


class AssetRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_tag: str
    serial_number: Optional[str] = None
    inventory_number: Optional[str] = None
    device_type: str
    usage_type: str
    ownership_type: str
    lifecycle_status: str
    criticality: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    purchase_date: Optional[str] = None
    warranty_end_date: Optional[str] = None
    org_node_id: int
    org_path: Optional[str] = None
    location_node_id: int
    location_path: Optional[str] = None
    cost_center_id: Optional[int] = None
    cost_center_name: Optional[str] = None
    primary_person_id: Optional[int] = None
    primary_person_name: Optional[str] = None
    owner_person_id: Optional[int] = None
    owner_person_name: Optional[str] = None
    support_team: Optional[str] = None
    is_active: bool
    notes: Optional[str] = None
    last_verified_at: Optional[datetime] = None
    last_verified_by: Optional[int] = None
    linked_agent_uuid: Optional[str] = None
    linked_agent_hostname: Optional[str] = None
    linked_agent_status: Optional[str] = None
    linked_agent_ip: Optional[str] = None
    linked_agent_last_seen: Optional[datetime] = None
    match_source: Optional[str] = None
    confidence_score: Optional[int] = None
    linked_at: Optional[datetime] = None
    data_quality_score: int = 100
    issue_count: int = 0
    created_at: datetime
    updated_at: datetime


class AssetRecordListResponse(BaseModel):
    items: list[AssetRecordResponse]
    total: int


class AssetAgentLinkRequest(BaseModel):
    asset_id: int
    agent_uuid: str
    match_source: Optional[str] = Field(default="manual", max_length=64)
    confidence_score: Optional[int] = Field(default=None, ge=0, le=100)
    is_primary: bool = True
    unlink_reason: Optional[str] = None


class AssetMatchingCandidateResponse(BaseModel):
    asset_id: Optional[int] = None
    asset_tag: Optional[str] = None
    agent_uuid: Optional[str] = None
    hostname: Optional[str] = None
    serial_hint: Optional[str] = None
    org_hint: Optional[str] = None
    location_hint: Optional[str] = None
    confidence: int = 0
    reasons: list[str] = Field(default_factory=list)
    candidate_type: str
    candidate_key: Optional[str] = None


class AssetMatchingCandidateListResponse(BaseModel):
    items: list[AssetMatchingCandidateResponse]
    total: int


class AssetDataQualityIssueResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_id: int
    asset_tag: Optional[str] = None
    issue_type: str
    severity: str
    status: str
    summary: str
    details_json: Optional[str] = None
    detected_at: datetime
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[int] = None


class AssetDataQualityIssueListResponse(BaseModel):
    items: list[AssetDataQualityIssueResponse]
    total: int


class AssetDataQualityBulkUpdateRequest(BaseModel):
    asset_ids: list[int] = Field(default_factory=list)
    owner_person_id: Optional[int] = None
    primary_person_id: Optional[int] = None
    org_node_id: Optional[int] = None
    location_node_id: Optional[int] = None
    cost_center_id: Optional[int] = None
    support_team: Optional[str] = Field(default=None, max_length=200)
    recompute_only: bool = False


class AssetDictionaryUpdateRequest(BaseModel):
    device_types: Optional[list[str]] = None
    usage_types: Optional[list[str]] = None
    ownership_types: Optional[list[str]] = None
    lifecycle_statuses: Optional[list[str]] = None


class AssetNodeTypeLabelUpdateItem(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=120)


class AssetNodeLabelUpdateRequest(BaseModel):
    organization_node_types: list[AssetNodeTypeLabelUpdateItem] = Field(default_factory=list)
    location_node_types: list[AssetNodeTypeLabelUpdateItem] = Field(default_factory=list)


class AssetMatchingDecisionRequest(BaseModel):
    candidate_key: str = Field(min_length=1, max_length=255)
    decision: Literal["rejected", "suppressed"] = "rejected"
    asset_id: Optional[int] = None
    agent_uuid: Optional[str] = Field(default=None, max_length=255)
    reason: Optional[str] = None


class AssetChangeLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_id: int
    change_type: str
    field_name: Optional[str] = None
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    changed_by: Optional[int] = None
    changed_at: datetime


class AssetChangeLogListResponse(BaseModel):
    items: list[AssetChangeLogResponse]
    total: int


class AssetRecordDetailResponse(AssetRecordResponse):
    issues: list[AssetDataQualityIssueResponse] = Field(default_factory=list)
    history: list[AssetChangeLogResponse] = Field(default_factory=list)


class AssetAgentSummaryResponse(BaseModel):
    asset_id: int
    asset_tag: str
    device_type: str
    lifecycle_status: str
    org_path: Optional[str] = None
    location_path: Optional[str] = None
    primary_person_name: Optional[str] = None
    owner_person_name: Optional[str] = None
    support_team: Optional[str] = None
    data_quality_score: int = 100
    issue_count: int = 0
    match_source: Optional[str] = None
    confidence_score: Optional[int] = None
    linked_at: Optional[datetime] = None
    last_verified_at: Optional[datetime] = None
    notes: Optional[str] = None


class AssetOverviewResponse(BaseModel):
    total_assets: int
    matched_assets: int
    unmatched_assets: int
    unmatched_agents: int
    owner_missing_count: int
    location_missing_count: int
    organization_distribution: list[dict]
    location_distribution: list[dict]
    asset_created_trend: list[dict] = Field(default_factory=list)
    match_created_trend: list[dict] = Field(default_factory=list)
    issue_detected_trend: list[dict] = Field(default_factory=list)
    organization_risk: list[dict] = Field(default_factory=list)
    location_risk: list[dict] = Field(default_factory=list)


class AssetReportBucketResponse(BaseModel):
    label: str
    value: int


class AssetReportListResponse(BaseModel):
    items: list[AssetReportBucketResponse]
    total: int

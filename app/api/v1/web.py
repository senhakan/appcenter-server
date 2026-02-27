from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from zoneinfo import ZoneInfo
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.auth import require_role
from app.config import get_settings
from app.database import get_db
from app.group_policy import is_system_group_name
from app.models import (
    Agent,
    AgentApplication,
    AgentGroup,
    AgentIdentityHistory,
    AgentSoftwareInventory,
    AgentStatusHistory,
    AgentSystemProfileHistory,
    Application,
    Deployment,
    Group,
    RemoteSupportSession,
    Setting,
    SoftwareLicense,
    SoftwareChangeHistory,
    TaskHistory,
    User,
)
from app.schemas import (
    AgentListResponse,
    AgentNotesUpdateRequest,
    AgentResponse,
    AgentUpdateUploadResponse,
    ApplicationListResponse,
    ApplicationResponse,
    ApplicationUpdateRequest,
    DashboardStatsResponse,
    DashboardTopClientItemResponse,
    DashboardTopClientListResponse,
    DashboardTimelineItemResponse,
    DashboardTimelineListResponse,
    DashboardTrendsResponse,
    DashboardComplianceBreakdownResponse,
    DashboardComplianceClientItemResponse,
    DashboardRemoteMetricsResponse,
    DeploymentCreateRequest,
    DeploymentListResponse,
    DeploymentResponse,
    DeploymentUpdateRequest,
    GroupAssignAgentsRequest,
    GroupCreateRequest,
    GroupListResponse,
    GroupResponse,
    GroupUpdateRequest,
    MessageResponse,
    SettingItem,
    SettingsListResponse,
    SettingsUpdateRequest,
)
from app.services.application_service import (
    create_application,
    delete_application,
    get_application,
    list_applications,
    remove_application_icon,
    update_application,
    update_application_icon,
)
from app.services import audit_service as audit
from app.services.deployment_service import (
    create_deployment,
    delete_deployment,
    get_deployment,
    list_deployments,
    update_deployment,
)
from app.utils.file_handler import move_temp_to_final, save_upload_to_temp

router = APIRouter(tags=["web"])
settings = get_settings()
MIN_SESSION_TIMEOUT_MINUTES = 1
MAX_SESSION_TIMEOUT_MINUTES = 1440


@router.get("/agents", response_model=AgentListResponse)
def agents_list(
    db: Session = Depends(get_db),
    _: User = Depends(require_role("viewer", "operator", "admin")),
) -> AgentListResponse:
    items = db.query(Agent).order_by(Agent.created_at.desc()).all()
    return AgentListResponse(items=items, total=len(items))


@router.get("/agents/{agent_uuid}", response_model=AgentResponse)
def agents_detail(
    agent_uuid: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_role("viewer", "operator", "admin")),
) -> AgentResponse:
    agent = db.query(Agent).filter(Agent.uuid == agent_uuid).first()
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return AgentResponse.model_validate(agent)


@router.put("/agents/{agent_uuid}/group", response_model=AgentResponse)
def agents_update_group(
    agent_uuid: str,
    group_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_role("operator", "admin")),
) -> AgentResponse:
    agent = db.query(Agent).filter(Agent.uuid == agent_uuid).first()
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    if group_id is not None:
        exists = db.query(Group.id).filter(Group.id == group_id).first()
        if not exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    agent.group_id = group_id
    db.add(agent)
    db.commit()
    db.refresh(agent)
    audit.record_audit(
        db,
        user_id=user.id,
        action="agent.update_group",
        resource_type="agent",
        resource_id=agent_uuid,
        details={"group_id": group_id},
    )
    return AgentResponse.model_validate(agent)


@router.put("/agents/{agent_uuid}/notes", response_model=AgentResponse)
def agents_update_notes(
    agent_uuid: str,
    payload: AgentNotesUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("operator", "admin")),
) -> AgentResponse:
    agent = db.query(Agent).filter(Agent.uuid == agent_uuid).first()
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    raw_notes = (payload.notes or "").strip()
    if len(raw_notes) > 2000:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Note is too long (max 2000 chars)")

    agent.notes = raw_notes or None
    db.add(agent)
    db.commit()
    db.refresh(agent)
    audit.record_audit(
        db,
        user_id=user.id,
        action="agent.update_notes",
        resource_type="agent",
        resource_id=agent_uuid,
        details={"notes_len": len(raw_notes)},
    )
    return AgentResponse.model_validate(agent)


@router.delete("/agents/{agent_uuid}", response_model=MessageResponse)
def agents_delete(
    agent_uuid: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("operator", "admin")),
) -> MessageResponse:
    agent = db.query(Agent).filter(Agent.uuid == agent_uuid).first()
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    # Explicit cleanup keeps delete stable across SQLite/ORM cascade differences.
    db.query(AgentApplication).filter(AgentApplication.agent_uuid == agent_uuid).delete(synchronize_session=False)
    db.query(AgentGroup).filter(AgentGroup.agent_uuid == agent_uuid).delete(synchronize_session=False)
    db.query(AgentSoftwareInventory).filter(AgentSoftwareInventory.agent_uuid == agent_uuid).delete(
        synchronize_session=False
    )
    db.query(SoftwareChangeHistory).filter(SoftwareChangeHistory.agent_uuid == agent_uuid).delete(
        synchronize_session=False
    )
    db.query(AgentSystemProfileHistory).filter(AgentSystemProfileHistory.agent_uuid == agent_uuid).delete(
        synchronize_session=False
    )
    db.query(AgentIdentityHistory).filter(AgentIdentityHistory.agent_uuid == agent_uuid).delete(
        synchronize_session=False
    )
    db.query(AgentStatusHistory).filter(AgentStatusHistory.agent_uuid == agent_uuid).delete(
        synchronize_session=False
    )
    db.query(TaskHistory).filter(TaskHistory.agent_uuid == agent_uuid).update(
        {TaskHistory.agent_uuid: None},
        synchronize_session=False,
    )
    db.query(Deployment).filter(
        Deployment.target_type == "Agent",
        Deployment.target_id == agent_uuid,
    ).delete(synchronize_session=False)

    db.delete(agent)
    db.commit()
    audit.record_audit(
        db,
        user_id=user.id,
        action="agent.delete",
        resource_type="agent",
        resource_id=agent_uuid,
    )
    return MessageResponse(status="success", message="Agent deleted")


@router.get("/groups", response_model=GroupListResponse)
def groups_list(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(require_role("viewer", "operator", "admin")),
) -> GroupListResponse:
    q = db.query(Group)
    if not include_inactive:
        q = q.filter(Group.is_active.is_(True))
    items = q.order_by(Group.name.asc()).all()
    return GroupListResponse(items=items, total=len(items))


@router.get("/groups/{group_id}", response_model=GroupResponse)
def groups_detail(
    group_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_role("viewer", "operator", "admin")),
) -> GroupResponse:
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    return GroupResponse.model_validate(group)


@router.post("/groups", response_model=GroupResponse)
def groups_create(
    payload: GroupCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("operator", "admin")),
) -> GroupResponse:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Group name is required")
    exists = db.query(Group.id).filter(func.lower(Group.name) == name.lower()).first()
    if exists:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Group name already exists")
    group = Group(name=name, description=(payload.description or "").strip() or None)
    db.add(group)
    db.commit()
    db.refresh(group)
    audit.record_audit(
        db,
        user_id=user.id,
        action="group.create",
        resource_type="group",
        resource_id=str(group.id),
        details={"name": group.name},
    )
    return GroupResponse.model_validate(group)


@router.put("/groups/{group_id}", response_model=GroupResponse)
def groups_update(
    group_id: int,
    payload: GroupUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("operator", "admin")),
) -> GroupResponse:
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    if group.is_system and (payload.name is not None or payload.description is not None or payload.is_active is False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="System group cannot be modified",
        )

    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Group name is required")
        exists = (
            db.query(Group.id)
            .filter(Group.id != group.id, func.lower(Group.name) == name.lower())
            .first()
        )
        if exists:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Group name already exists")
        group.name = name
    if payload.description is not None:
        group.description = payload.description.strip() or None
    if payload.is_active is not None:
        group.is_active = bool(payload.is_active)
    db.add(group)
    db.commit()
    db.refresh(group)
    audit.record_audit(
        db,
        user_id=user.id,
        action="group.update",
        resource_type="group",
        resource_id=str(group.id),
        details={"name": group.name, "is_active": bool(group.is_active)},
    )
    return GroupResponse.model_validate(group)


@router.put("/groups/{group_id}/agents", response_model=MessageResponse)
def groups_assign_agents(
    group_id: int,
    payload: GroupAssignAgentsRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("operator", "admin")),
) -> MessageResponse:
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    if not group.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Group is inactive")

    target_uuids = {uuid.strip() for uuid in payload.agent_uuids if uuid and uuid.strip()}
    if target_uuids:
        existing_count = db.query(func.count(Agent.uuid)).filter(Agent.uuid.in_(target_uuids)).scalar() or 0
        if existing_count != len(target_uuids):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="One or more agents not found")

    current_rows = db.query(AgentGroup).filter(AgentGroup.group_id == group_id).all()
    current_uuids = {row.agent_uuid for row in current_rows}

    remove_uuids = current_uuids - target_uuids
    add_uuids = target_uuids - current_uuids

    if remove_uuids:
        db.query(AgentGroup).filter(
            AgentGroup.group_id == group_id,
            AgentGroup.agent_uuid.in_(remove_uuids),
        ).delete(synchronize_session=False)

    for agent_uuid in add_uuids:
        db.add(AgentGroup(agent_uuid=agent_uuid, group_id=group_id))

    # Keep legacy single-group field populated with one membership for backward compatibility.
    touched_uuids = remove_uuids.union(add_uuids)
    if touched_uuids:
        touched_agents = db.query(Agent).filter(Agent.uuid.in_(touched_uuids)).all()
        for agent in touched_agents:
            group_ids = sorted(
                {
                    row.group_id
                    for row in db.query(AgentGroup)
                    .filter(AgentGroup.agent_uuid == agent.uuid)
                    .all()
                }
            )
            agent.group_id = group_ids[0] if group_ids else None
            db.add(agent)

    db.commit()
    audit.record_audit(
        db,
        user_id=user.id,
        action="group.assign_agents",
        resource_type="group",
        resource_id=str(group_id),
        details={"target_count": len(target_uuids)},
    )
    return MessageResponse(status="success", message="Group agents updated")


@router.delete("/groups/{group_id}", response_model=MessageResponse)
def groups_delete(
    group_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("operator", "admin")),
) -> MessageResponse:
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    if is_system_group_name(group.name):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="System group cannot be deleted")
    if not group.is_active:
        return MessageResponse(status="success", message="Group already inactive")

    # Remove memberships first; keep legacy single-group column consistent.
    db.query(AgentGroup).filter(AgentGroup.group_id == group_id).delete(synchronize_session=False)
    db.query(Agent).filter(Agent.group_id == group_id).update({Agent.group_id: None}, synchronize_session=False)

    group.is_active = False
    db.add(group)
    db.commit()
    audit.record_audit(
        db,
        user_id=user.id,
        action="group.deactivate",
        resource_type="group",
        resource_id=str(group_id),
        details={"name": group.name},
    )
    return MessageResponse(status="success", message="Group set to inactive")


@router.get("/dashboard/stats", response_model=DashboardStatsResponse)
def dashboard_stats(
    db: Session = Depends(get_db),
    _: User = Depends(require_role("viewer", "operator", "admin")),
) -> DashboardStatsResponse:
    total_agents = db.query(func.count(Agent.uuid)).scalar() or 0
    online_agents = db.query(func.count(Agent.uuid)).filter(Agent.status == "online").scalar() or 0
    total_apps = db.query(func.count(Application.id)).scalar() or 0
    pending_tasks = db.query(func.count(TaskHistory.id)).filter(TaskHistory.status == "pending").scalar() or 0
    failed_tasks = db.query(func.count(TaskHistory.id)).filter(TaskHistory.status == "failed").scalar() or 0
    active_deployments = db.query(func.count(Deployment.id)).filter(Deployment.is_active.is_(True)).scalar() or 0
    active_remote_sessions = (
        db.query(func.count(RemoteSupportSession.id))
        .filter(RemoteSupportSession.status.in_(("pending_approval", "approved", "connecting", "active")))
        .scalar()
        or 0
    )
    return DashboardStatsResponse(
        total_agents=total_agents,
        online_agents=online_agents,
        offline_agents=max(total_agents - online_agents, 0),
        total_applications=total_apps,
        pending_tasks=pending_tasks,
        failed_tasks=failed_tasks,
        active_deployments=active_deployments,
        active_remote_sessions=active_remote_sessions,
    )


@router.get("/dashboard/timeline", response_model=DashboardTimelineListResponse)
def dashboard_timeline(
    db: Session = Depends(get_db),
    _: User = Depends(require_role("viewer", "operator", "admin")),
) -> DashboardTimelineListResponse:
    def _as_utc(dt_value):
        # sqlite raw queries can return strings and/or naive datetimes.
        if dt_value is None:
            return None
        if isinstance(dt_value, str):
            s = dt_value.strip()
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            if " " in s and "T" not in s:
                s = s.replace(" ", "T", 1)
            try:
                dt_value = datetime.fromisoformat(s)
            except Exception:
                return None
        if isinstance(dt_value, datetime):
            if dt_value.tzinfo is None:
                return dt_value.replace(tzinfo=timezone.utc)
            return dt_value.astimezone(timezone.utc)
        return None

    rows = db.execute(
        text(
            """
            SELECT event_type, detected_at, agent_uuid, hostname,
                   old_status, new_status, reason,
                   old_hostname, new_hostname, old_ip_address, new_ip_address,
                   changed_fields_json,
                   task_action, task_status, app_name, message, exit_code
            FROM (
              SELECT 'status' AS event_type,
                     h.detected_at AS detected_at,
                     h.agent_uuid AS agent_uuid,
                     a.hostname AS hostname,
                     h.old_status AS old_status,
                     h.new_status AS new_status,
                     h.reason AS reason,
                     NULL AS old_hostname,
                     NULL AS new_hostname,
                     NULL AS old_ip_address,
                     NULL AS new_ip_address,
                     NULL AS changed_fields_json,
                     NULL AS task_action,
                     NULL AS task_status,
                     NULL AS app_name,
                     NULL AS message,
                     NULL AS exit_code
              FROM agent_status_history h
              JOIN agents a ON a.uuid = h.agent_uuid
              UNION ALL
              SELECT 'identity' AS event_type,
                     h.detected_at AS detected_at,
                     h.agent_uuid AS agent_uuid,
                     a.hostname AS hostname,
                     NULL AS old_status,
                     NULL AS new_status,
                     NULL AS reason,
                     h.old_hostname AS old_hostname,
                     h.new_hostname AS new_hostname,
                     h.old_ip_address AS old_ip_address,
                     h.new_ip_address AS new_ip_address,
                     NULL AS changed_fields_json,
                     NULL AS task_action,
                     NULL AS task_status,
                     NULL AS app_name,
                     NULL AS message,
                     NULL AS exit_code
              FROM agent_identity_history h
              JOIN agents a ON a.uuid = h.agent_uuid
              UNION ALL
              SELECT 'system_profile' AS event_type,
                     h.detected_at AS detected_at,
                     h.agent_uuid AS agent_uuid,
                     a.hostname AS hostname,
                     NULL AS old_status,
                     NULL AS new_status,
                     NULL AS reason,
                     NULL AS old_hostname,
                     NULL AS new_hostname,
                     NULL AS old_ip_address,
                     NULL AS new_ip_address,
                     h.changed_fields_json AS changed_fields_json,
                     NULL AS task_action,
                     NULL AS task_status,
                     NULL AS app_name,
                     NULL AS message,
                     NULL AS exit_code
              FROM agent_system_profile_history h
              JOIN agents a ON a.uuid = h.agent_uuid
              UNION ALL
              SELECT 'task' AS event_type,
                     COALESCE(t.completed_at, t.started_at, t.created_at) AS detected_at,
                     t.agent_uuid AS agent_uuid,
                     a.hostname AS hostname,
                     NULL AS old_status,
                     NULL AS new_status,
                     NULL AS reason,
                     NULL AS old_hostname,
                     NULL AS new_hostname,
                     NULL AS old_ip_address,
                     NULL AS new_ip_address,
                     NULL AS changed_fields_json,
                     t.action AS task_action,
                     t.status AS task_status,
                     app.display_name AS app_name,
                     t.message AS message,
                     t.exit_code AS exit_code
              FROM task_history t
              JOIN agents a ON a.uuid = t.agent_uuid
              LEFT JOIN applications app ON app.id = t.app_id
            )
            ORDER BY detected_at DESC
            LIMIT 10
            """
        )
    ).mappings().all()

    items: list[DashboardTimelineItemResponse] = []
    for r in rows:
        et = r["event_type"]
        summary = ""
        severity = None
        if et == "status":
            summary = f"Status: {r['old_status'] or '-'} → {r['new_status'] or '-'}"
            if r.get("reason"):
                summary += f" ({r['reason']})"
            if (r.get("new_status") or "").lower() == "online":
                severity = "ok"
            elif (r.get("new_status") or "").lower() == "offline":
                severity = "danger"
        elif et == "identity":
            hn = ""
            ip = ""
            if (r.get("old_hostname") or "") != (r.get("new_hostname") or ""):
                hn = f"hostname {r.get('old_hostname') or '-'} → {r.get('new_hostname') or '-'}"
            if (r.get("old_ip_address") or "") != (r.get("new_ip_address") or ""):
                ip = f"ip {r.get('old_ip_address') or '-'} → {r.get('new_ip_address') or '-'}"
            summary = "Identity: " + " | ".join([x for x in [hn, ip] if x]) if (hn or ip) else "Identity change"
            severity = "info"
        elif et == "task":
            app_name = r.get("app_name") or "-"
            summary = f"Task: {r.get('task_action') or '-'} {app_name} -> {r.get('task_status') or '-'}"
            if r.get("exit_code") is not None:
                summary += f" (exit={r.get('exit_code')})"
            if r.get("message"):
                summary += f" | {r.get('message')}"
            st = (r.get("task_status") or "").lower()
            if st == "success":
                severity = "ok"
            elif st in {"failed", "timeout"}:
                severity = "danger"
            else:
                severity = "warn"
        else:
            summary = "System profile updated"
            severity = "info"
        items.append(
            DashboardTimelineItemResponse(
                event_type=et,
                detected_at=_as_utc(r["detected_at"]),
                agent_uuid=r["agent_uuid"],
                hostname=r.get("hostname"),
                summary=summary,
                severity=severity,
            )
        )

    return DashboardTimelineListResponse(items=items)


@router.get("/dashboard/top-clients", response_model=DashboardTopClientListResponse)
def dashboard_top_clients(
    db: Session = Depends(get_db),
    _: User = Depends(require_role("viewer", "operator", "admin")),
) -> DashboardTopClientListResponse:
    rows = (
        db.query(
            Agent.uuid.label("agent_uuid"),
            Agent.hostname.label("hostname"),
            Agent.status.label("status"),
            Agent.last_seen.label("last_seen"),
            func.count(AgentSoftwareInventory.id).label("installed_app_count"),
        )
        .outerjoin(AgentSoftwareInventory, AgentSoftwareInventory.agent_uuid == Agent.uuid)
        .group_by(Agent.uuid, Agent.hostname, Agent.status, Agent.last_seen)
        .order_by(
            func.count(AgentSoftwareInventory.id).desc(),
            func.coalesce(Agent.last_seen, datetime(1970, 1, 1, tzinfo=timezone.utc)).desc(),
            Agent.hostname.asc(),
        )
        .limit(10)
        .all()
    )

    items = [
        DashboardTopClientItemResponse(
            agent_uuid=str(r.agent_uuid),
            hostname=r.hostname or "-",
            status=(r.status or "offline"),
            installed_app_count=int(r.installed_app_count or 0),
            last_seen=r.last_seen,
        )
        for r in rows
    ]
    return DashboardTopClientListResponse(items=items)


@router.get("/dashboard/trends", response_model=DashboardTrendsResponse)
def dashboard_trends(
    db: Session = Depends(get_db),
    _: User = Depends(require_role("viewer", "operator", "admin")),
) -> DashboardTrendsResponse:
    today = datetime.now(timezone.utc).date()
    days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    labels = [d.strftime("%d.%m") for d in days]

    def _bucket_map():
        return {d.isoformat(): 0 for d in days}

    status_online = _bucket_map()
    status_offline = _bucket_map()
    task_success = _bucket_map()
    task_failed = _bucket_map()
    task_pending = _bucket_map()

    start_dt = datetime.combine(days[0], datetime.min.time(), tzinfo=timezone.utc)

    status_rows = (
        db.query(
            func.date(AgentStatusHistory.detected_at).label("day"),
            AgentStatusHistory.new_status.label("new_status"),
            func.count(AgentStatusHistory.id).label("cnt"),
        )
        .filter(AgentStatusHistory.detected_at >= start_dt)
        .group_by(func.date(AgentStatusHistory.detected_at), AgentStatusHistory.new_status)
        .all()
    )
    for r in status_rows:
        day = str(r.day or "")
        status = (r.new_status or "").lower()
        cnt = int(r.cnt or 0)
        if day not in status_online:
            continue
        if status == "online":
            status_online[day] += cnt
        elif status == "offline":
            status_offline[day] += cnt

    task_rows = (
        db.query(
            func.date(func.coalesce(TaskHistory.completed_at, TaskHistory.created_at)).label("day"),
            TaskHistory.status.label("status"),
            func.count(TaskHistory.id).label("cnt"),
        )
        .filter(func.coalesce(TaskHistory.completed_at, TaskHistory.created_at) >= start_dt)
        .group_by(func.date(func.coalesce(TaskHistory.completed_at, TaskHistory.created_at)), TaskHistory.status)
        .all()
    )
    for r in task_rows:
        day = str(r.day or "")
        status = (r.status or "").lower()
        cnt = int(r.cnt or 0)
        if day not in task_success:
            continue
        if status == "success":
            task_success[day] += cnt
        elif status in {"failed", "timeout"}:
            task_failed[day] += cnt
        elif status == "pending":
            task_pending[day] += cnt

    keys = [d.isoformat() for d in days]
    return DashboardTrendsResponse(
        labels=labels,
        online_transitions=[status_online[k] for k in keys],
        offline_transitions=[status_offline[k] for k in keys],
        task_success=[task_success[k] for k in keys],
        task_failed=[task_failed[k] for k in keys],
        task_pending=[task_pending[k] for k in keys],
    )


@router.get("/dashboard/compliance-breakdown", response_model=DashboardComplianceBreakdownResponse)
def dashboard_compliance_breakdown(
    db: Session = Depends(get_db),
    _: User = Depends(require_role("viewer", "operator", "admin")),
) -> DashboardComplianceBreakdownResponse:
    licenses = db.query(SoftwareLicense).filter(SoftwareLicense.is_active.is_(True)).all()
    agents = db.query(Agent.uuid, Agent.hostname, Agent.status).all()
    risk_map: dict[str, dict] = {
        str(a.uuid): {
            "agent_uuid": str(a.uuid),
            "hostname": a.hostname or "-",
            "status": (a.status or "offline"),
            "licensed_violations": 0,
            "prohibited_hits": 0,
            "risk_score": 0,
        }
        for a in agents
    }

    name_col = func.coalesce(AgentSoftwareInventory.normalized_name, AgentSoftwareInventory.software_name)
    violation_licensed_rules = 0
    violation_prohibited_rules = 0

    for lic in licenses:
        pattern = (lic.software_name_pattern or "").strip()
        if not pattern:
            continue
        q = db.query(func.distinct(AgentSoftwareInventory.agent_uuid))
        if lic.match_type == "exact":
            q = q.filter(name_col == pattern)
        elif lic.match_type == "starts_with":
            q = q.filter(name_col.ilike(f"{pattern}%"))
        else:
            q = q.filter(name_col.ilike(f"%{pattern}%"))
        matched = [str(x[0]) for x in q.all() if x and x[0]]
        usage = len(matched)

        if lic.license_type == "prohibited" and usage > 0:
            violation_prohibited_rules += 1
            for agent_uuid in matched:
                row = risk_map.get(agent_uuid)
                if not row:
                    continue
                row["prohibited_hits"] += 1
                row["risk_score"] += 3
            continue

        if lic.license_type == "licensed" and usage > int(lic.total_licenses or 0):
            violation_licensed_rules += 1
            for agent_uuid in matched:
                row = risk_map.get(agent_uuid)
                if not row:
                    continue
                row["licensed_violations"] += 1
                row["risk_score"] += 1

    at_risk = [v for v in risk_map.values() if int(v["risk_score"]) > 0]
    at_risk.sort(key=lambda x: (-int(x["risk_score"]), -int(x["prohibited_hits"]), x["hostname"]))
    items = [
        DashboardComplianceClientItemResponse(
            agent_uuid=row["agent_uuid"],
            hostname=row["hostname"],
            status=row["status"],
            licensed_violations=int(row["licensed_violations"]),
            prohibited_hits=int(row["prohibited_hits"]),
            risk_score=int(row["risk_score"]),
        )
        for row in at_risk[:10]
    ]
    return DashboardComplianceBreakdownResponse(
        violation_licensed_rules=violation_licensed_rules,
        violation_prohibited_rules=violation_prohibited_rules,
        at_risk_agents=len(at_risk),
        items=items,
    )


@router.get("/dashboard/remote-metrics", response_model=DashboardRemoteMetricsResponse)
def dashboard_remote_metrics(
    db: Session = Depends(get_db),
    _: User = Depends(require_role("viewer", "operator", "admin")),
) -> DashboardRemoteMetricsResponse:
    now = datetime.now(timezone.utc)
    start_dt = now - timedelta(days=7)
    active_sessions = (
        db.query(func.count(RemoteSupportSession.id))
        .filter(RemoteSupportSession.status.in_(("pending_approval", "approved", "connecting", "active")))
        .scalar()
        or 0
    )
    sessions = db.query(RemoteSupportSession).filter(RemoteSupportSession.requested_at >= start_dt).all()
    sessions_last_7d = len(sessions)
    rejected_last_7d = sum(1 for s in sessions if (s.status or "").lower() == "rejected")
    timeout_last_7d = sum(1 for s in sessions if (s.status or "").lower() == "timeout")
    error_last_7d = sum(1 for s in sessions if (s.status or "").lower() == "error")

    approval_delays = []
    durations = []
    for s in sessions:
        if s.approved_at and s.requested_at:
            approval_delays.append(max(0, int((_as_utc(s.approved_at) - _as_utc(s.requested_at)).total_seconds())))
        if s.connected_at and s.ended_at:
            durations.append(max(0, int((_as_utc(s.ended_at) - _as_utc(s.connected_at)).total_seconds())))

    avg_approval_delay_sec = int(sum(approval_delays) / len(approval_delays)) if approval_delays else 0
    avg_session_duration_sec = int(sum(durations) / len(durations)) if durations else 0

    return DashboardRemoteMetricsResponse(
        active_sessions=int(active_sessions),
        sessions_last_7d=sessions_last_7d,
        rejected_last_7d=rejected_last_7d,
        timeout_last_7d=timeout_last_7d,
        error_last_7d=error_last_7d,
        avg_approval_delay_sec=avg_approval_delay_sec,
        avg_session_duration_sec=avg_session_duration_sec,
    )


@router.get("/applications", response_model=ApplicationListResponse)
def applications_list(
    only_active: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(require_role("viewer", "operator", "admin")),
) -> ApplicationListResponse:
    items = list_applications(db, only_active=only_active)
    return ApplicationListResponse(items=items, total=len(items))


@router.get("/applications/{app_id}", response_model=ApplicationResponse)
def applications_detail(
    app_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_role("viewer", "operator", "admin")),
) -> ApplicationResponse:
    app = get_application(db, app_id)
    return ApplicationResponse.model_validate(app)


@router.post("/applications", response_model=ApplicationResponse)
async def applications_upload(
    display_name: str = Form(...),
    version: str = Form(...),
    file: UploadFile = File(...),
    description: Optional[str] = Form(None),
    install_args: Optional[str] = Form(None),
    uninstall_args: Optional[str] = Form(None),
    is_visible_in_store: bool = Form(True),
    category: Optional[str] = Form(None),
    icon: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_role("operator", "admin")),
) -> ApplicationResponse:
    app = await create_application(
        db=db,
        display_name=display_name,
        version=version,
        upload_file=file,
        description=description,
        install_args=install_args,
        uninstall_args=uninstall_args,
        is_visible_in_store=is_visible_in_store,
        category=category,
        icon_file=icon,
    )
    audit.record_audit(
        db,
        user_id=user.id,
        action="application.create",
        resource_type="application",
        resource_id=str(app.id),
        details={"display_name": app.display_name, "version": app.version},
    )
    return ApplicationResponse.model_validate(app)


@router.put("/applications/{app_id}", response_model=ApplicationResponse)
def applications_update(
    app_id: int,
    payload: ApplicationUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("operator", "admin")),
) -> ApplicationResponse:
    app = update_application(
        db=db,
        app_id=app_id,
        display_name=payload.display_name,
        version=payload.version,
        description=payload.description,
        install_args=payload.install_args,
        uninstall_args=payload.uninstall_args,
        is_visible_in_store=payload.is_visible_in_store,
        category=payload.category,
        is_active=payload.is_active,
    )
    audit.record_audit(
        db,
        user_id=user.id,
        action="application.update",
        resource_type="application",
        resource_id=str(app.id),
        details={"display_name": app.display_name, "version": app.version, "is_active": bool(app.is_active)},
    )
    return ApplicationResponse.model_validate(app)


@router.put("/applications/{app_id}/icon", response_model=ApplicationResponse)
async def applications_update_icon(
    app_id: int,
    icon: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_role("operator", "admin")),
) -> ApplicationResponse:
    app = await update_application_icon(db=db, app_id=app_id, icon_file=icon)
    audit.record_audit(
        db,
        user_id=user.id,
        action="application.update_icon",
        resource_type="application",
        resource_id=str(app.id),
    )
    return ApplicationResponse.model_validate(app)


@router.delete("/applications/{app_id}/icon", response_model=ApplicationResponse)
def applications_delete_icon(
    app_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("operator", "admin")),
) -> ApplicationResponse:
    app = remove_application_icon(db=db, app_id=app_id)
    audit.record_audit(
        db,
        user_id=user.id,
        action="application.delete_icon",
        resource_type="application",
        resource_id=str(app.id),
    )
    return ApplicationResponse.model_validate(app)


@router.delete("/applications/{app_id}", response_model=MessageResponse)
def applications_delete(
    app_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("operator", "admin")),
) -> MessageResponse:
    delete_application(db, app_id)
    audit.record_audit(
        db,
        user_id=user.id,
        action="application.delete",
        resource_type="application",
        resource_id=str(app_id),
    )
    return MessageResponse(status="success", message="Application deleted")


@router.get("/deployments", response_model=DeploymentListResponse)
def deployments_list(
    db: Session = Depends(get_db),
    _: User = Depends(require_role("viewer", "operator", "admin")),
) -> DeploymentListResponse:
    items = list_deployments(db)
    return DeploymentListResponse(items=items, total=len(items))


@router.get("/deployments/{deployment_id}", response_model=DeploymentResponse)
def deployments_detail(
    deployment_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_role("viewer", "operator", "admin")),
) -> DeploymentResponse:
    item = get_deployment(db, deployment_id)
    return DeploymentResponse.model_validate(item)


@router.post("/deployments", response_model=DeploymentResponse)
def deployments_create(
    payload: DeploymentCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("operator", "admin")),
) -> DeploymentResponse:
    item = create_deployment(db, payload, created_by=user.username)
    audit.record_audit(
        db,
        user_id=user.id,
        action="deployment.create",
        resource_type="deployment",
        resource_id=str(item.id),
        details={"app_id": item.app_id, "target_type": item.target_type, "target_id": item.target_id},
    )
    return DeploymentResponse.model_validate(item)


@router.put("/deployments/{deployment_id}", response_model=DeploymentResponse)
def deployments_update(
    deployment_id: int,
    payload: DeploymentUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("operator", "admin")),
) -> DeploymentResponse:
    item = update_deployment(db, deployment_id, payload)
    audit.record_audit(
        db,
        user_id=user.id,
        action="deployment.update",
        resource_type="deployment",
        resource_id=str(item.id),
        details={"app_id": item.app_id, "target_type": item.target_type, "target_id": item.target_id},
    )
    return DeploymentResponse.model_validate(item)


@router.delete("/deployments/{deployment_id}", response_model=MessageResponse)
def deployments_delete(
    deployment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("operator", "admin")),
) -> MessageResponse:
    delete_deployment(db, deployment_id)
    audit.record_audit(
        db,
        user_id=user.id,
        action="deployment.delete",
        resource_type="deployment",
        resource_id=str(deployment_id),
    )
    return MessageResponse(status="success", message="Deployment deleted")


@router.get("/settings", response_model=SettingsListResponse)
def settings_list(
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
) -> SettingsListResponse:
    items = db.query(Setting).order_by(Setting.key.asc()).all()
    mapped = [SettingItem(key=s.key, value=s.value, description=s.description, updated_at=s.updated_at) for s in items]
    return SettingsListResponse(items=mapped, total=len(mapped))


@router.put("/settings", response_model=SettingsListResponse)
def settings_update(
    payload: SettingsUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin")),
) -> SettingsListResponse:
    now = datetime.now(timezone.utc)
    for key, value in payload.values.items():
        if key == "ui_timezone":
            try:
                ZoneInfo((value or "").strip())
            except Exception:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ui_timezone")
        if key == "session_timeout_minutes":
            try:
                minutes = int((value or "").strip())
            except Exception:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid session_timeout_minutes",
                )
            if minutes < MIN_SESSION_TIMEOUT_MINUTES or minutes > MAX_SESSION_TIMEOUT_MINUTES:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"session_timeout_minutes must be between "
                        f"{MIN_SESSION_TIMEOUT_MINUTES} and {MAX_SESSION_TIMEOUT_MINUTES}"
                    ),
                )
        if key in {"runtime_update_interval_min", "runtime_update_jitter_sec"}:
            try:
                num = int((value or "").strip())
            except Exception:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid {key}",
                )
            if num < 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"{key} must be >= 0",
                )
        item = db.query(Setting).filter(Setting.key == key).first()
        if not item:
            item = Setting(key=key, value=value, description="Updated via API", updated_at=now)
        else:
            item.value = value
            item.updated_at = now
        db.add(item)
    db.commit()
    audit.record_audit(
        db,
        user_id=user.id,
        action="settings.update",
        resource_type="settings",
        details={"keys": sorted(list(payload.values.keys()))},
    )
    return settings_list(db)


@router.post("/agent-update/upload", response_model=AgentUpdateUploadResponse)
async def upload_agent_update(
    version: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin")),
) -> AgentUpdateUploadResponse:
    updates_dir = str(Path(settings.upload_dir) / "agent_updates")
    temp_path, digest_hex, _, file_type = await save_upload_to_temp(
        upload_file=file,
        upload_dir=updates_dir,
        max_upload_size=settings.max_upload_size,
    )
    filename = f"agent_{version}_{digest_hex[:8]}.{file_type}"
    final_path = Path(updates_dir) / filename
    move_temp_to_final(temp_path, final_path)

    now = datetime.now(timezone.utc)
    download_url = f"/api/v1/agent/update/download/{filename}"
    pairs = {
        "agent_latest_version": version,
        "agent_download_url": download_url,
        "agent_hash": f"sha256:{digest_hex}",
        "agent_update_filename": filename,
    }
    for key, value in pairs.items():
        item = db.query(Setting).filter(Setting.key == key).first()
        if not item:
            item = Setting(key=key, value=value, description="Agent update metadata", updated_at=now)
        else:
            item.value = value
            item.updated_at = now
        db.add(item)
    db.commit()
    audit.record_audit(
        db,
        user_id=user.id,
        action="agent_update.upload",
        resource_type="agent_update",
        resource_id=filename,
        details={"version": version},
    )

    return AgentUpdateUploadResponse(
        status="success",
        message="Agent update uploaded",
        version=version,
        file_hash=f"sha256:{digest_hex}",
        filename=filename,
        download_url=download_url,
    )

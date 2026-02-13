from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import get_settings
from app.database import get_db
from app.models import Agent, AgentApplication, AgentGroup, Application, Deployment, Group, Setting, TaskHistory, User
from app.schemas import (
    AgentListResponse,
    AgentResponse,
    AgentUpdateUploadResponse,
    ApplicationListResponse,
    ApplicationResponse,
    ApplicationUpdateRequest,
    DashboardStatsResponse,
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
    update_application,
)
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


@router.get("/agents", response_model=AgentListResponse)
def agents_list(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> AgentListResponse:
    items = db.query(Agent).order_by(Agent.created_at.desc()).all()
    return AgentListResponse(items=items, total=len(items))


@router.get("/agents/{agent_uuid}", response_model=AgentResponse)
def agents_detail(
    agent_uuid: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
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
    _: User = Depends(get_current_user),
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
    return AgentResponse.model_validate(agent)


@router.get("/groups", response_model=GroupListResponse)
def groups_list(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> GroupListResponse:
    items = db.query(Group).order_by(Group.name.asc()).all()
    return GroupListResponse(items=items, total=len(items))


@router.get("/groups/{group_id}", response_model=GroupResponse)
def groups_detail(
    group_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> GroupResponse:
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    return GroupResponse.model_validate(group)


@router.post("/groups", response_model=GroupResponse)
def groups_create(
    payload: GroupCreateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
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
    return GroupResponse.model_validate(group)


@router.put("/groups/{group_id}", response_model=GroupResponse)
def groups_update(
    group_id: int,
    payload: GroupUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> GroupResponse:
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")

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
    db.add(group)
    db.commit()
    db.refresh(group)
    return GroupResponse.model_validate(group)


@router.put("/groups/{group_id}/agents", response_model=MessageResponse)
def groups_assign_agents(
    group_id: int,
    payload: GroupAssignAgentsRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> MessageResponse:
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")

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
    return MessageResponse(status="success", message="Group agents updated")


@router.get("/dashboard/stats", response_model=DashboardStatsResponse)
def dashboard_stats(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> DashboardStatsResponse:
    total_agents = db.query(func.count(Agent.uuid)).scalar() or 0
    online_agents = db.query(func.count(Agent.uuid)).filter(Agent.status == "online").scalar() or 0
    total_apps = db.query(func.count(Application.id)).scalar() or 0
    pending_tasks = db.query(func.count(TaskHistory.id)).filter(TaskHistory.status == "pending").scalar() or 0
    failed_tasks = db.query(func.count(TaskHistory.id)).filter(TaskHistory.status == "failed").scalar() or 0
    active_deployments = db.query(func.count(Deployment.id)).filter(Deployment.is_active.is_(True)).scalar() or 0
    return DashboardStatsResponse(
        total_agents=total_agents,
        online_agents=online_agents,
        offline_agents=max(total_agents - online_agents, 0),
        total_applications=total_apps,
        pending_tasks=pending_tasks,
        failed_tasks=failed_tasks,
        active_deployments=active_deployments,
    )


@router.get("/applications", response_model=ApplicationListResponse)
def applications_list(
    only_active: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> ApplicationListResponse:
    items = list_applications(db, only_active=only_active)
    return ApplicationListResponse(items=items, total=len(items))


@router.get("/applications/{app_id}", response_model=ApplicationResponse)
def applications_detail(
    app_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
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
    _: User = Depends(get_current_user),
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
    return ApplicationResponse.model_validate(app)


@router.put("/applications/{app_id}", response_model=ApplicationResponse)
def applications_update(
    app_id: int,
    payload: ApplicationUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
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
    return ApplicationResponse.model_validate(app)


@router.delete("/applications/{app_id}", response_model=MessageResponse)
def applications_delete(
    app_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> MessageResponse:
    delete_application(db, app_id)
    return MessageResponse(status="success", message="Application deleted")


@router.get("/deployments", response_model=DeploymentListResponse)
def deployments_list(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> DeploymentListResponse:
    items = list_deployments(db)
    return DeploymentListResponse(items=items, total=len(items))


@router.get("/deployments/{deployment_id}", response_model=DeploymentResponse)
def deployments_detail(
    deployment_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> DeploymentResponse:
    item = get_deployment(db, deployment_id)
    return DeploymentResponse.model_validate(item)


@router.post("/deployments", response_model=DeploymentResponse)
def deployments_create(
    payload: DeploymentCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DeploymentResponse:
    item = create_deployment(db, payload, created_by=user.username)
    return DeploymentResponse.model_validate(item)


@router.put("/deployments/{deployment_id}", response_model=DeploymentResponse)
def deployments_update(
    deployment_id: int,
    payload: DeploymentUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> DeploymentResponse:
    item = update_deployment(db, deployment_id, payload)
    return DeploymentResponse.model_validate(item)


@router.delete("/deployments/{deployment_id}", response_model=MessageResponse)
def deployments_delete(
    deployment_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> MessageResponse:
    delete_deployment(db, deployment_id)
    return MessageResponse(status="success", message="Deployment deleted")


@router.get("/settings", response_model=SettingsListResponse)
def settings_list(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> SettingsListResponse:
    items = db.query(Setting).order_by(Setting.key.asc()).all()
    mapped = [SettingItem(key=s.key, value=s.value, description=s.description, updated_at=s.updated_at) for s in items]
    return SettingsListResponse(items=mapped, total=len(mapped))


@router.put("/settings", response_model=SettingsListResponse)
def settings_update(
    payload: SettingsUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> SettingsListResponse:
    now = datetime.now(timezone.utc)
    for key, value in payload.values.items():
        item = db.query(Setting).filter(Setting.key == key).first()
        if not item:
            item = Setting(key=key, value=value, description="Updated via API", updated_at=now)
        else:
            item.value = value
            item.updated_at = now
        db.add(item)
    db.commit()
    return settings_list(db)


@router.post("/agent-update/upload", response_model=AgentUpdateUploadResponse)
async def upload_agent_update(
    version: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
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

    return AgentUpdateUploadResponse(
        status="success",
        message="Agent update uploaded",
        version=version,
        file_hash=f"sha256:{digest_hex}",
        filename=filename,
        download_url=download_url,
    )

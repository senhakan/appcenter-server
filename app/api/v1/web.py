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
from app.models import Agent, AgentApplication, Application, Deployment, Setting, TaskHistory, User
from app.schemas import (
    AgentListResponse,
    AgentResponse,
    AgentUpdateUploadResponse,
    ApplicationListResponse,
    ApplicationResponse,
    DashboardStatsResponse,
    DeploymentCreateRequest,
    DeploymentListResponse,
    DeploymentResponse,
    DeploymentUpdateRequest,
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

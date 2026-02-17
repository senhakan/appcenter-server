from __future__ import annotations

import secrets
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import Agent, AgentApplication, Application, Setting, TaskHistory
from app.services.heartbeat_service import process_heartbeat
from app.schemas import (
    AgentConfig,
    AgentInventoryRequest,
    AgentInventoryResponse,
    AgentRegisterRequest,
    AgentRegisterResponse,
    HeartbeatRequest,
    HeartbeatResponse,
    MessageResponse,
    StoreAppItem,
    StoreResponse,
    TaskStatusRequest,
)
from app.services import inventory_service
from app.utils.file_handler import parse_range_header

router = APIRouter(prefix="/agent", tags=["agent"])
settings = get_settings()


def _get_setting(db: Session, key: str, default: str) -> str:
    setting = db.query(Setting).filter(Setting.key == key).first()
    if not setting:
        return default
    return setting.value


def _agent_config(db: Session) -> AgentConfig:
    return AgentConfig(
        heartbeat_interval_sec=int(_get_setting(db, "heartbeat_interval_sec", "60")),
        bandwidth_limit_kbps=int(_get_setting(db, "bandwidth_limit_kbps", "1024")),
        work_hour_start=_get_setting(db, "work_hour_start", "09:00"),
        work_hour_end=_get_setting(db, "work_hour_end", "18:00"),
    )


def _authenticate_agent(db: Session, agent_uuid: str, agent_secret: str) -> Agent:
    agent = db.query(Agent).filter(Agent.uuid == agent_uuid).first()
    if not agent or not agent.secret_key or agent.secret_key != agent_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid agent credentials")
    return agent


@router.post("/register", response_model=AgentRegisterResponse)
def register_agent(payload: AgentRegisterRequest, db: Session = Depends(get_db)) -> AgentRegisterResponse:
    now = datetime.now(timezone.utc)
    agent = db.query(Agent).filter(Agent.uuid == payload.uuid).first()
    if agent:
        agent.hostname = payload.hostname
        agent.os_version = payload.os_version
        agent.version = payload.agent_version
        agent.cpu_model = payload.cpu_model
        agent.ram_gb = payload.ram_gb
        agent.disk_free_gb = payload.disk_free_gb
        agent.status = "online"
        agent.last_seen = now
        agent.updated_at = now
        if not agent.secret_key:
            agent.secret_key = f"sk_{secrets.token_urlsafe(24)}"
    else:
        agent = Agent(
            uuid=payload.uuid,
            hostname=payload.hostname,
            os_version=payload.os_version,
            version=payload.agent_version,
            cpu_model=payload.cpu_model,
            ram_gb=payload.ram_gb,
            disk_free_gb=payload.disk_free_gb,
            status="online",
            last_seen=now,
            secret_key=f"sk_{secrets.token_urlsafe(24)}",
        )
        db.add(agent)

    db.commit()
    db.refresh(agent)

    return AgentRegisterResponse(secret_key=agent.secret_key, config=_agent_config(db))


@router.post("/heartbeat", response_model=HeartbeatResponse)
def heartbeat(
    payload: HeartbeatRequest,
    x_agent_uuid: str = Header(..., alias="X-Agent-UUID"),
    x_agent_secret: str = Header(..., alias="X-Agent-Secret"),
    db: Session = Depends(get_db),
) -> HeartbeatResponse:
    agent = _authenticate_agent(db, x_agent_uuid, x_agent_secret)
    now, config, commands, _inv_sync = process_heartbeat(db, agent, payload)
    return HeartbeatResponse(server_time=now, config=config, commands=commands)


@router.get("/download/{app_id}")
def download_application(
    app_id: int,
    x_agent_uuid: str = Header(..., alias="X-Agent-UUID"),
    x_agent_secret: str = Header(..., alias="X-Agent-Secret"),
    range_header: str = Header(None, alias="Range"),
    db: Session = Depends(get_db),
):
    _authenticate_agent(db, x_agent_uuid, x_agent_secret)

    app = db.query(Application).filter(Application.id == app_id, Application.is_active.is_(True)).first()
    if not app:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    file_path = (Path(settings.upload_dir) / Path(app.filename).name).resolve()
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Installer file not found")

    file_size = file_path.stat().st_size
    byte_range = parse_range_header(range_header, file_size)

    if byte_range:
        start, end = byte_range
        content_length = end - start + 1
        headers = {
            "Accept-Ranges": "bytes",
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Content-Length": str(content_length),
            "Content-Disposition": f'attachment; filename="{app.original_filename or app.filename}"',
        }

        def iter_partial():
            with open(file_path, "rb") as f:
                f.seek(start)
                remaining = content_length
                chunk_size = 1024 * 1024
                while remaining > 0:
                    chunk = f.read(min(chunk_size, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        return StreamingResponse(
            iter_partial(),
            status_code=status.HTTP_206_PARTIAL_CONTENT,
            media_type="application/octet-stream",
            headers=headers,
        )

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(file_size),
        "Content-Disposition": f'attachment; filename="{app.original_filename or app.filename}"',
    }

    def iter_full():
        with open(file_path, "rb") as f:
            chunk_size = 1024 * 1024
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                yield chunk

    return StreamingResponse(iter_full(), media_type="application/octet-stream", headers=headers)


@router.post("/task/{task_id}/status", response_model=MessageResponse)
def report_task_status(
    task_id: int,
    payload: TaskStatusRequest,
    x_agent_uuid: str = Header(..., alias="X-Agent-UUID"),
    x_agent_secret: str = Header(..., alias="X-Agent-Secret"),
    db: Session = Depends(get_db),
) -> MessageResponse:
    _authenticate_agent(db, x_agent_uuid, x_agent_secret)

    task = db.query(TaskHistory).filter(TaskHistory.id == task_id).first()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    now = datetime.now(timezone.utc)
    task.status = payload.status
    task.message = payload.error or payload.message
    task.exit_code = payload.exit_code
    task.download_duration_sec = payload.download_duration_sec
    task.install_duration_sec = payload.install_duration_sec
    if payload.status in {"success", "failed", "timeout"}:
        task.completed_at = now
    db.add(task)

    if task.app_id:
        agent_app = (
            db.query(AgentApplication)
            .filter(AgentApplication.agent_uuid == x_agent_uuid, AgentApplication.app_id == task.app_id)
            .first()
        )
        if agent_app:
            if payload.status == "success":
                agent_app.status = "installed"
                agent_app.installed_version = payload.installed_version or agent_app.installed_version
            elif payload.status in {"failed", "timeout"}:
                agent_app.status = "failed"
                agent_app.retry_count += 1
                agent_app.error_message = payload.error or payload.message
            elif payload.status == "downloading":
                agent_app.status = "downloading"
            agent_app.last_attempt = now
            db.add(agent_app)

    db.commit()
    return MessageResponse(status="ok", message="Task status updated")


@router.post("/inventory", response_model=AgentInventoryResponse)
def submit_inventory(
    payload: AgentInventoryRequest,
    x_agent_uuid: str = Header(..., alias="X-Agent-UUID"),
    x_agent_secret: str = Header(..., alias="X-Agent-Secret"),
    db: Session = Depends(get_db),
) -> AgentInventoryResponse:
    _authenticate_agent(db, x_agent_uuid, x_agent_secret)
    changes = inventory_service.submit_inventory(db, x_agent_uuid, payload.inventory_hash, payload.items)
    return AgentInventoryResponse(message="Inventory updated", changes=changes)


@router.get("/store", response_model=StoreResponse)
def get_store_applications(
    x_agent_uuid: str = Header(..., alias="X-Agent-UUID"),
    x_agent_secret: str = Header(..., alias="X-Agent-Secret"),
    db: Session = Depends(get_db),
) -> StoreResponse:
    _authenticate_agent(db, x_agent_uuid, x_agent_secret)

    rows = (
        db.query(Application, AgentApplication)
        .outerjoin(
            AgentApplication,
            (AgentApplication.app_id == Application.id) & (AgentApplication.agent_uuid == x_agent_uuid),
        )
        .filter(Application.is_visible_in_store.is_(True), Application.is_active.is_(True))
        .order_by(Application.display_name.asc())
        .all()
    )

    apps: list[StoreAppItem] = []
    for app, agent_app in rows:
        size_mb = int(((app.file_size_bytes or 0) + (1024 * 1024 - 1)) / (1024 * 1024))
        installed = bool(agent_app and agent_app.status in {"installed", "installing", "downloading"})
        installed_version = agent_app.installed_version if agent_app else None
        can_uninstall = bool(agent_app and agent_app.status == "installed")
        apps.append(
            StoreAppItem(
                id=app.id,
                display_name=app.display_name,
                version=app.version,
                description=app.description,
                icon_url=app.icon_url,
                file_size_mb=size_mb,
                category=app.category,
                installed=installed,
                installed_version=installed_version,
                can_uninstall=can_uninstall,
            )
        )
    return StoreResponse(apps=apps)


@router.get("/update/download/{filename}")
def download_agent_update(
    filename: str,
    x_agent_uuid: str = Header(..., alias="X-Agent-UUID"),
    x_agent_secret: str = Header(..., alias="X-Agent-Secret"),
    db: Session = Depends(get_db),
):
    _authenticate_agent(db, x_agent_uuid, x_agent_secret)

    safe_name = Path(filename).name
    file_path = (Path(settings.upload_dir) / "agent_updates" / safe_name).resolve()
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Update file not found")

    headers = {
        "Content-Length": str(file_path.stat().st_size),
        "Content-Disposition": f'attachment; filename="{safe_name}"',
    }

    def iter_file():
        with open(file_path, "rb") as f:
            chunk_size = 1024 * 1024
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                yield chunk

    return StreamingResponse(iter_file(), media_type="application/octet-stream", headers=headers)

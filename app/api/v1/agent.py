from __future__ import annotations

import asyncio
import secrets
from datetime import datetime, timezone
from pathlib import Path
import re

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal, get_db
from app.services import agent_signal
from app.models import Agent, AgentApplication, AgentSoftwareInventory, AgentStatusHistory, Application, Setting, TaskHistory
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
    RemoteSupportEnd,
    RemoteSupportRequest,
    StoreAppItem,
    StoreResponse,
    TaskStatusRequest,
)
from app.services.deployment_service import queue_store_install_for_agent
from app.services import inventory_service
from app.services import remote_support_service as rs
from app.utils.file_handler import parse_range_header

router = APIRouter(prefix="/agent", tags=["agent"])
SIGNAL_OFFLINE_GRACE_SEC = 3
SIGNAL_MAX_HOLD_SEC = 10
VALID_PLATFORMS = {"windows", "linux"}


def _clean_error_message(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.replace("\x00", "").strip()
    if not cleaned:
        return None
    # Keep store cards compact.
    if len(cleaned) > 500:
        return cleaned[:500] + "..."
    return cleaned


def _canon_name(value: str | None) -> str:
    if not value:
        return ""
    value = value.casefold()
    value = re.sub(r"[^a-z0-9]+", "", value)
    return value


def _detect_store_conflict(
    app: Application,
    inventory_rows: list[AgentSoftwareInventory],
) -> tuple[bool, str | None, str | None]:
    app_key = _canon_name(app.display_name)
    if len(app_key) < 3:
        return False, None, None

    matches: list[AgentSoftwareInventory] = []
    for row in inventory_rows:
        inv_name = row.normalized_name or row.software_name
        inv_key = _canon_name(inv_name)
        if len(inv_key) < 3:
            continue
        if app_key in inv_key or inv_key in app_key:
            matches.append(row)

    if not matches:
        return False, None, None

    versions = sorted({(m.software_version or "").strip() for m in matches if (m.software_version or "").strip()})
    has_same_version = app.version.strip() in versions if app.version else False
    confidence = "high" if has_same_version else "medium"
    if has_same_version:
        msg = "Bu uygulamanin ayni surumu sisteminizde olabilir. Kurulumdan once mevcut kurulumu kontrol etmeniz onerilir."
    else:
        joined = ", ".join(versions[:3]) if versions else "bilinmiyor"
        msg = (
            "Bu uygulamanin farkli bir surumu sisteminizde olabilir "
            f"(tespit edilen: {joined}). Kurulumdan once mevcut surumu kaldirmaniz onerilir."
        )
    return True, confidence, msg

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
    )


def _authenticate_agent(db: Session, agent_uuid: str, agent_secret: str) -> Agent:
    agent = db.query(Agent).filter(Agent.uuid == agent_uuid).first()
    if not agent or not agent.secret_key or agent.secret_key != agent_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid agent credentials")
    return agent


def _normalize_platform(value: str | None) -> str:
    platform = (value or "windows").strip().lower()
    if platform not in VALID_PLATFORMS:
        return "windows"
    return platform


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _mark_agent_online_from_signal(agent_uuid: str) -> None:
    db = SessionLocal()
    now = datetime.now(timezone.utc)
    try:
        agent = db.query(Agent).filter(Agent.uuid == agent_uuid).first()
        if not agent:
            return
        old_status = agent.status
        agent.status = "online"
        agent.last_seen = now
        agent.updated_at = now
        db.add(agent)
        if old_status != "online":
            db.add(
                AgentStatusHistory(
                    agent_uuid=agent.uuid,
                    detected_at=now,
                    old_status=old_status,
                    new_status="online",
                    reason="signal_connect",
                )
            )
        db.commit()
    finally:
        db.close()


def _mark_agent_offline_if_signal_stale(agent_uuid: str, disconnected_at: datetime) -> None:
    db = SessionLocal()
    now = datetime.now(timezone.utc)
    try:
        agent = db.query(Agent).filter(Agent.uuid == agent_uuid).first()
        if not agent:
            return

        last_seen = _as_utc(agent.last_seen)
        if last_seen and last_seen > disconnected_at:
            return
        if agent.status == "offline":
            return

        old_status = agent.status
        agent.status = "offline"
        agent.updated_at = now
        db.add(agent)
        db.add(
            AgentStatusHistory(
                agent_uuid=agent.uuid,
                detected_at=now,
                old_status=old_status,
                new_status="offline",
                reason="signal_disconnect",
            )
        )
        db.commit()
        rs.end_sessions_for_offline_agents(db, [agent_uuid])
    finally:
        db.close()


async def _schedule_signal_disconnect_offline(agent_uuid: str, disconnected_at: datetime) -> None:
    await asyncio.sleep(SIGNAL_OFFLINE_GRACE_SEC)
    _mark_agent_offline_if_signal_stale(agent_uuid, disconnected_at)


@router.post("/register", response_model=AgentRegisterResponse)
def register_agent(payload: AgentRegisterRequest, db: Session = Depends(get_db)) -> AgentRegisterResponse:
    now = datetime.now(timezone.utc)
    platform = _normalize_platform(payload.platform)
    agent = db.query(Agent).filter(Agent.uuid == payload.uuid).first()
    if agent:
        agent.hostname = payload.hostname
        agent.os_version = payload.os_version
        agent.platform = platform
        agent.arch = payload.arch
        agent.distro = payload.distro
        agent.distro_version = payload.distro_version
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
            platform=platform,
            arch=payload.arch,
            distro=payload.distro,
            distro_version=payload.distro_version,
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
    if payload.platform is not None:
        agent.platform = _normalize_platform(payload.platform)
    now, config, commands, _inv_sync = process_heartbeat(db, agent, payload)

    remote_req: RemoteSupportRequest | None = None
    remote_end: RemoteSupportEnd | None = None
    remote_support_allowed = settings.remote_support_enabled and bool(getattr(config, "remote_support_enabled", False))
    if remote_support_allowed:
        pending = rs.get_pending_for_agent(db, x_agent_uuid)
        if pending:
            remote_req = RemoteSupportRequest(
                session_id=pending.id,
                admin_name=rs.admin_name_for_session(db, pending),
                reason=pending.reason or "",
                requested_at=pending.requested_at,
                timeout_at=pending.approval_timeout_at,
            )
        else:
            end_sig = rs.get_end_signal_for_agent(db, x_agent_uuid)
            if end_sig:
                remote_end = RemoteSupportEnd(session_id=end_sig.id)
                rs.mark_end_signal_delivered(db, end_sig.id, x_agent_uuid)

    return HeartbeatResponse(
        server_time=now,
        config=config,
        commands=commands,
        remote_support_request=remote_req,
        remote_support_end=remote_end,
    )


@router.get("/signal")
async def wait_for_signal(
    timeout: int = Query(default=55, ge=5, le=55),
    x_agent_uuid: str = Header(..., alias="X-Agent-UUID"),
    x_agent_secret: str = Header(..., alias="X-Agent-Secret"),
):
    db = next(get_db())
    try:
        _authenticate_agent(db, x_agent_uuid, x_agent_secret)
    finally:
        db.close()
    _mark_agent_online_from_signal(x_agent_uuid)

    event = agent_signal.get_or_create_event(x_agent_uuid)
    agent_signal.mark_listener_active(x_agent_uuid)
    hold_timeout = min(timeout, SIGNAL_MAX_HOLD_SEC)
    try:
        await asyncio.wait_for(event.wait(), timeout=hold_timeout)
        return {"status": "signal", "reason": "wake"}
    except asyncio.TimeoutError:
        return {"status": "timeout"}
    finally:
        disconnected_at = datetime.now(timezone.utc)
        event.clear()
        agent_signal.mark_listener_inactive(x_agent_uuid)
        asyncio.create_task(_schedule_signal_disconnect_offline(x_agent_uuid, disconnected_at))


@router.get("/download/{app_id}")
def download_application(
    app_id: int,
    x_agent_uuid: str = Header(..., alias="X-Agent-UUID"),
    x_agent_secret: str = Header(..., alias="X-Agent-Secret"),
    range_header: str = Header(None, alias="Range"),
    db: Session = Depends(get_db),
):
    agent = _authenticate_agent(db, x_agent_uuid, x_agent_secret)

    app = db.query(Application).filter(Application.id == app_id, Application.is_active.is_(True)).first()
    if not app:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    agent_platform = _normalize_platform(getattr(agent, "platform", None))
    app_platform = _normalize_platform(getattr(app, "target_platform", None))
    if agent_platform != app_platform:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Application is not available for this platform")

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
            def _to_utc(dt: datetime | None) -> datetime | None:
                if dt is None:
                    return None
                if dt.tzinfo is None:
                    return dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)

            task_started = _to_utc(task.started_at)
            last_attempt = _to_utc(agent_app.last_attempt)
            stale_for_agent_state = (
                task_started is not None
                and last_attempt is not None
                and task_started < last_attempt
            )

            if payload.status == "success":
                agent_app.status = "installed"
                agent_app.installed_version = payload.installed_version or agent_app.installed_version
            elif payload.status in {"failed", "timeout"}:
                # Do not let stale failures overwrite a newer successful state.
                if not (stale_for_agent_state and agent_app.status == "installed"):
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
    agent = _authenticate_agent(db, x_agent_uuid, x_agent_secret)
    agent_platform = _normalize_platform(getattr(agent, "platform", None))

    rows = (
        db.query(Application, AgentApplication)
        .outerjoin(
            AgentApplication,
            (AgentApplication.app_id == Application.id) & (AgentApplication.agent_uuid == x_agent_uuid),
        )
        .filter(
            Application.is_visible_in_store.is_(True),
            Application.is_active.is_(True),
            Application.target_platform == agent_platform,
        )
        .order_by(Application.display_name.asc())
        .all()
    )
    inventory_rows = (
        db.query(AgentSoftwareInventory)
        .filter(AgentSoftwareInventory.agent_uuid == x_agent_uuid)
        .all()
    )

    apps: list[StoreAppItem] = []
    for app, agent_app in rows:
        size_mb = int(((app.file_size_bytes or 0) + (1024 * 1024 - 1)) / (1024 * 1024))
        # Only treat as installed when installation is actually complete.
        installed = bool(agent_app and agent_app.status == "installed")
        install_state = agent_app.status if agent_app else "not_installed"
        error_message = _clean_error_message(agent_app.error_message if agent_app else None)
        conflict_detected, conflict_confidence, conflict_message = _detect_store_conflict(app, inventory_rows)
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
                install_state=install_state,
                error_message=error_message,
                conflict_detected=conflict_detected,
                conflict_confidence=conflict_confidence,
                conflict_message=conflict_message,
                installed_version=installed_version,
                can_uninstall=can_uninstall,
            )
        )
    return StoreResponse(apps=apps)


@router.post("/store/{app_id}/install", response_model=MessageResponse)
def install_from_store(
    app_id: int,
    x_agent_uuid: str = Header(..., alias="X-Agent-UUID"),
    x_agent_secret: str = Header(..., alias="X-Agent-Secret"),
    db: Session = Depends(get_db),
) -> MessageResponse:
    _authenticate_agent(db, x_agent_uuid, x_agent_secret)
    status_key, message = queue_store_install_for_agent(db, x_agent_uuid, app_id)
    return MessageResponse(status=status_key, message=message)


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

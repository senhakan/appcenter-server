from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.auth import require_permission
from app.database import get_db
from app.models import Agent, RemoteSupportRecording, RemoteSupportSession, User
from app.schemas import (
    MessageResponse,
    RemoteSessionAgentApproveRequest,
    RemoteSessionCreateRequest,
    RemoteSessionEndedRequest,
    RemoteSessionReadyRequest,
)
from app.services import novnc_service as novnc
from app.services import remote_support_service as rs
from app.services import runtime_config_service as runtime_config
from app.services import session_recording_service as recording
from app.services import audit_service as audit
from app.api.v1.agent import _authenticate_agent

router = APIRouter(tags=["remote-support"])


def _duration_sec(started_at, ended_at) -> Optional[int]:
    if not started_at:
        return None
    end_value = ended_at
    if not end_value:
        return None
    try:
        delta = end_value - started_at
        return max(int(delta.total_seconds()), 0)
    except Exception:
        return None


@router.get("/remote-support/recording/service-status")
def get_recording_service_status(
    user: User = Depends(require_permission("remote_support.recordings.manage")),
    db: Session = Depends(get_db),
):
    _ = user
    return {"status": "ok", "service": recording.get_service_status(db)}


@router.post("/remote-support/sessions/{session_id}/recording/start")
def start_session_recording(
    session_id: int,
    trigger: str = Query(default="manual"),
    monitor: int = Query(default=1, ge=1, le=2),
    user: User = Depends(require_permission("remote_support.recordings.manage")),
    db: Session = Depends(get_db),
):
    rec, started = recording.start_recording(db, session_id, trigger_source=trigger, monitor_index=monitor)
    if started:
        audit.record_audit(
            db,
            user_id=user.id,
            action="remote_support.recording_start",
            resource_type="remote_support_recording",
            resource_id=str(rec.id),
            details={"session_id": session_id, "monitor": monitor, "trigger": trigger},
        )
    return {
        "status": "ok",
        "started": started,
        "recording": {
            "id": rec.id,
            "session_id": rec.session_id,
            "monitor_index": rec.monitor_index,
            "status": rec.status,
            "target_fps": rec.target_fps,
            "file_path": rec.file_path,
            "started_at": rec.started_at,
        },
    }


@router.post("/remote-support/sessions/{session_id}/recording/stop", response_model=MessageResponse)
def stop_session_recording(
    session_id: int,
    user: User = Depends(require_permission("remote_support.recordings.manage")),
    db: Session = Depends(get_db),
):
    stopped = recording.stop_recording(db, session_id, reason="manual_stop")
    if stopped:
        audit.record_audit(
            db,
            user_id=user.id,
            action="remote_support.recording_stop",
            resource_type="remote_support_session",
            resource_id=str(session_id),
            details={"reason": "manual_stop"},
        )
        return MessageResponse(status="ok", message="Recording stop signal sent")
    return MessageResponse(status="ok", message="No running recording for this session")


@router.get("/remote-support/recordings")
def list_remote_recordings(
    session_id: Optional[int] = None,
    agent_uuid: Optional[str] = None,
    monitor: Optional[int] = Query(default=None, ge=1, le=2),
    limit: int = 100,
    user: User = Depends(require_permission("remote_support.recordings.view")),
    db: Session = Depends(get_db),
):
    _ = user
    q = db.query(RemoteSupportRecording)
    if session_id is not None:
        q = q.filter(RemoteSupportRecording.session_id == session_id)
    if agent_uuid:
        q = q.filter(RemoteSupportRecording.agent_uuid == agent_uuid)
    if monitor is not None:
        q = q.filter(RemoteSupportRecording.monitor_index == monitor)
    items = q.order_by(RemoteSupportRecording.id.desc()).limit(max(1, min(limit, 500))).all()
    agent_map = {
        a.uuid: a.hostname
        for a in db.query(Agent).filter(Agent.uuid.in_({r.agent_uuid for r in items})).all()
    } if items else {}
    return {
        "status": "ok",
        "items": [
            {
                "id": r.id,
                "session_id": r.session_id,
                "agent_uuid": r.agent_uuid,
                "agent_hostname": agent_map.get(r.agent_uuid),
                "monitor_index": r.monitor_index,
                "status": r.status,
                "target_fps": r.target_fps,
                "trigger_source": r.trigger_source,
                "file_path": r.file_path,
                "started_at": r.started_at,
                "ended_at": r.ended_at,
                "duration_sec": r.duration_sec,
                "file_size_bytes": r.file_size_bytes,
                "error_message": r.error_message,
            }
            for r in items
        ],
        "total": len(items),
    }


@router.get("/remote-support/recordings/{recording_id}/stream")
def stream_remote_recording(
    recording_id: int,
    user: User = Depends(require_permission("remote_support.recordings.view")),
    db: Session = Depends(get_db),
):
    _ = user
    rec = db.query(RemoteSupportRecording).filter(RemoteSupportRecording.id == recording_id).first()
    if not rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recording not found")
    raw_path = (rec.file_path or "").strip()
    if not raw_path:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Recording file path is empty")
    root = recording.get_recordings_root()
    path = Path(raw_path).expanduser().resolve()
    if root not in path.parents:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Recording path is outside allowed directory")
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recording file not found")
    return FileResponse(str(path), media_type="video/mp4", filename=path.name)


@router.get("/remote-support/recordings/{recording_id}/play-token")
def create_recording_play_token(
    recording_id: int,
    user: User = Depends(require_permission("remote_support.recordings.view")),
    db: Session = Depends(get_db),
):
    _ = user
    rec = db.query(RemoteSupportRecording).filter(RemoteSupportRecording.id == recording_id).first()
    if not rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recording not found")
    token, exp = recording.create_playback_token(recording_id, expires_sec=900)
    return {"status": "ok", "play_token": token, "expires_at": exp}


@router.get("/remote-support/recordings/{recording_id}/public-stream")
def stream_remote_recording_public(
    recording_id: int,
    play_token: str = Query(default=""),
    db: Session = Depends(get_db),
):
    if not recording.verify_playback_token(play_token, recording_id):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid playback token")
    rec = db.query(RemoteSupportRecording).filter(RemoteSupportRecording.id == recording_id).first()
    if not rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recording not found")
    raw_path = (rec.file_path or "").strip()
    if not raw_path:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Recording file path is empty")
    root = recording.get_recordings_root()
    path = Path(raw_path).expanduser().resolve()
    if root not in path.parents:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Recording path is outside allowed directory")
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recording file not found")
    return FileResponse(str(path), media_type="video/mp4", filename=path.name)


@router.post("/remote-support/sessions")
def create_remote_session(
    body: RemoteSessionCreateRequest,
    user: User = Depends(require_permission("remote_support.session.manage")),
    db: Session = Depends(get_db),
):
    session = rs.create_session(db, body.agent_uuid, user.id, body.reason, body.max_duration_min)
    audit.record_audit(
        db,
        user_id=user.id,
        action="remote_support.session_create",
        resource_type="remote_support_session",
        resource_id=str(session.id),
        details={"agent_uuid": body.agent_uuid, "reason": body.reason},
    )
    return {
        "status": "ok",
        "session": {
            "id": session.id,
            "agent_uuid": session.agent_uuid,
            "admin_name": rs.admin_name_for_session(db, session),
            "status": session.status,
            "reason": session.reason,
            "monitor_count": session.monitor_count,
            "requested_at": session.requested_at,
            "approval_timeout_at": session.approval_timeout_at,
            "max_duration_min": session.max_duration_min,
        },
    }


@router.get("/remote-support/sessions")
def list_remote_sessions(
    status: Optional[str] = None,
    agent_uuid: Optional[str] = None,
    limit: int = 50,
    user: User = Depends(require_permission("remote_support.session.view")),
    db: Session = Depends(get_db),
):
    _ = user
    rs.ensure_enabled(db)
    sessions = rs.list_sessions(db, status_filter=status, agent_uuid=agent_uuid, limit=limit)
    return {
        "status": "ok",
        "items": [
            {
                "id": s.id,
                "agent_uuid": s.agent_uuid,
                "admin_name": rs.admin_name_for_session(db, s),
                "status": s.status,
                "reason": s.reason,
                "monitor_count": s.monitor_count,
                "requested_at": s.requested_at,
                "approved_at": s.approved_at,
                "connected_at": s.connected_at,
                "ended_at": s.ended_at,
                "ended_by": s.ended_by,
                "max_duration_min": s.max_duration_min,
            }
            for s in sessions
        ],
    }


@router.get("/remote-support/history")
def list_remote_history(
    q: Optional[str] = None,
    outcome: Optional[str] = None,
    limit: int = 100,
    user: User = Depends(require_permission("remote_support.session.view")),
    db: Session = Depends(get_db),
):
    _ = user
    rs.ensure_enabled(db)
    sessions = rs.list_sessions(db, limit=max(1, min(limit, 300)))
    agent_map = {
        item.uuid: item.hostname
        for item in db.query(Agent).filter(Agent.uuid.in_({s.agent_uuid for s in sessions})).all()
    } if sessions else {}
    query_text = (q or "").strip().lower()
    items = []
    for s in sessions:
        hostname = (agent_map.get(s.agent_uuid) or "").strip()
        admin_name = rs.admin_name_for_session(db, s)
        duration_sec = _duration_sec(s.connected_at, s.ended_at)
        derived_outcome = "connected" if s.connected_at else ("failed" if s.ended_at or s.status in {"rejected", "timeout", "error"} else "pending")
        record = {
            "id": s.id,
            "agent_uuid": s.agent_uuid,
            "agent_hostname": hostname or None,
            "admin_name": admin_name,
            "status": s.status,
            "outcome": derived_outcome,
            "reason": s.reason,
            "requested_at": s.requested_at,
            "approved_at": s.approved_at,
            "connected_at": s.connected_at,
            "ended_at": s.ended_at,
            "ended_by": s.ended_by,
            "duration_sec": duration_sec,
            "max_duration_min": s.max_duration_min,
        }
        if query_text:
            haystack = " ".join([
                str(record["id"]),
                record["agent_uuid"] or "",
                record["agent_hostname"] or "",
                record["admin_name"] or "",
                record["reason"] or "",
                record["status"] or "",
                record["ended_by"] or "",
            ]).lower()
            if query_text not in haystack:
                continue
        if outcome and outcome not in {"all", derived_outcome}:
            continue
        items.append(record)

    return {"status": "ok", "items": items, "total": len(items)}


@router.get("/remote-support/sessions/{session_id}")
def get_remote_session(
    session_id: int,
    user: User = Depends(require_permission("remote_support.session.view")),
    db: Session = Depends(get_db),
):
    _ = user
    rs.ensure_enabled(db)
    s = rs.get_session(db, session_id)
    return {
        "status": "ok",
        "session": {
            "id": s.id,
            "agent_uuid": s.agent_uuid,
            "admin_name": rs.admin_name_for_session(db, s),
            "status": s.status,
            "reason": s.reason,
            "monitor_count": s.monitor_count,
            "requested_at": s.requested_at,
            "approval_timeout_at": s.approval_timeout_at,
            "approved_at": s.approved_at,
            "connected_at": s.connected_at,
            "ended_at": s.ended_at,
            "ended_by": s.ended_by,
            "max_duration_min": s.max_duration_min,
        },
    }


@router.post("/remote-support/sessions/{session_id}/end", response_model=MessageResponse)
def end_remote_session(
    session_id: int,
    user: User = Depends(require_permission("remote_support.session.manage")),
    db: Session = Depends(get_db),
):
    _ = user
    rs.end_session(db, session_id, ended_by="admin")
    audit.record_audit(
        db,
        user_id=user.id,
        action="remote_support.session_end",
        resource_type="remote_support_session",
        resource_id=str(session_id),
        details={"ended_by": "admin"},
    )
    return MessageResponse(status="ok", message="Session ended")


@router.post("/remote-support/sessions/{session_id}/cancel", response_model=MessageResponse)
def cancel_remote_session(
    session_id: int,
    user: User = Depends(require_permission("remote_support.session.manage")),
    db: Session = Depends(get_db),
):
    rs.cancel_pending_session(db, session_id, admin_user_id=user.id)
    audit.record_audit(
        db,
        user_id=user.id,
        action="remote_support.session_cancel",
        resource_type="remote_support_session",
        resource_id=str(session_id),
    )
    return MessageResponse(status="ok", message="Pending approval cancelled")


@router.get("/remote-support/sessions/{session_id}/novnc-ticket")
def get_remote_session_novnc_ticket(
    session_id: int,
    monitor: int = Query(default=1, ge=1, le=2),
    user: User = Depends(require_permission("remote_support.session.manage")),
    db: Session = Depends(get_db),
):
    _ = user
    rs.ensure_enabled(db)
    s = rs.get_session(db, session_id)
    allowed_states = {"approved", "connecting", "active"}
    if (s.status or "").lower() not in allowed_states:
        return {"status": "ok", "viewer": {"enabled": False, "reason": f"viewer_not_available_in_state:{s.status}"}}
    if not s.vnc_password:
        return {"status": "ok", "viewer": {"enabled": False, "reason": "missing_vnc_password"}}
    if monitor == 2 and int(s.monitor_count or 0) < 2:
        return {"status": "ok", "viewer": {"enabled": False, "reason": "monitor_not_available"}}

    agent = db.query(Agent).filter(Agent.uuid == s.agent_uuid).first()
    agent_ip = (agent.ip_address or "").strip() if agent else ""
    if not agent_ip:
        return {"status": "ok", "viewer": {"enabled": False, "reason": "missing_agent_ip"}}
    vnc_port = 20011 if monitor == 2 else 20010

    try:
        token, ws_path = novnc.build_ticket(agent_ip=agent_ip, vnc_port=vnc_port)
        novnc.cleanup_old_tokens()
    except OSError as exc:
        return {"status": "ok", "viewer": {"enabled": False, "reason": f"novnc_token_error:{exc}"}}

    return {
        "status": "ok",
        "viewer": {
            "enabled": True,
            "token": token,
            "ws_path": ws_path,
            "password": s.vnc_password,
            "session_id": s.id,
            "agent_ip": agent_ip,
            "monitor": monitor,
            "vnc_port": vnc_port,
        },
    }


@router.post("/agent/remote-support/{session_id}/approve")
def approve_remote_session(
    session_id: int,
    body: RemoteSessionAgentApproveRequest,
    x_agent_uuid: str = Header(..., alias="X-Agent-UUID"),
    x_agent_secret: str = Header(..., alias="X-Agent-Secret"),
    db: Session = Depends(get_db),
):
    _authenticate_agent(db, x_agent_uuid, x_agent_secret)
    session = rs.approve_from_agent(db, session_id, x_agent_uuid, body.approved, body.monitor_count)
    if body.approved and session.status == "approved":
        runtime = runtime_config.get_remote_support_runtime(db)
        return {
            "status": "ok",
            "vnc_password": session.vnc_password,
            "guacd_host": rs.settings.guac_reverse_vnc_host,
            "guacd_reverse_port": rs.settings.guac_reverse_vnc_port,
            "novnc_mode": runtime.novnc_mode,
            "ws_mode": runtime.ws_mode,
        }
    return {"status": "ok", "message": "Session rejected"}


@router.post("/agent/remote-support/{session_id}/ready", response_model=MessageResponse)
def ready_remote_session(
    session_id: int,
    body: RemoteSessionReadyRequest,
    x_agent_uuid: str = Header(..., alias="X-Agent-UUID"),
    x_agent_secret: str = Header(..., alias="X-Agent-Secret"),
    db: Session = Depends(get_db),
):
    _authenticate_agent(db, x_agent_uuid, x_agent_secret)
    if body.vnc_ready:
        rs.mark_ready_from_agent(db, session_id, x_agent_uuid)
    return MessageResponse(status="ok", message="ready")


@router.post("/agent/remote-support/{session_id}/ended", response_model=MessageResponse)
def ended_remote_session(
    session_id: int,
    body: RemoteSessionEndedRequest,
    x_agent_uuid: str = Header(..., alias="X-Agent-UUID"),
    x_agent_secret: str = Header(..., alias="X-Agent-Secret"),
    db: Session = Depends(get_db),
):
    _authenticate_agent(db, x_agent_uuid, x_agent_secret)
    rs.end_session_from_agent(db, session_id, x_agent_uuid, body.ended_by)
    return MessageResponse(status="ok", message="ended")

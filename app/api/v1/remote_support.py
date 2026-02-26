from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from app.auth import require_role
from app.database import get_db
from app.models import Agent, User
from app.schemas import (
    MessageResponse,
    RemoteSessionAgentApproveRequest,
    RemoteSessionCreateRequest,
    RemoteSessionEndedRequest,
    RemoteSessionReadyRequest,
)
from app.services import novnc_service as novnc
from app.services import remote_support_service as rs
from app.services import audit_service as audit
from app.api.v1.agent import _authenticate_agent

router = APIRouter(tags=["remote-support"])


@router.post("/remote-support/sessions")
def create_remote_session(
    body: RemoteSessionCreateRequest,
    user: User = Depends(require_role("operator", "admin")),
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
    user: User = Depends(require_role("viewer", "operator", "admin")),
    db: Session = Depends(get_db),
):
    _ = user
    rs.ensure_enabled()
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


@router.get("/remote-support/sessions/{session_id}")
def get_remote_session(
    session_id: int,
    user: User = Depends(require_role("viewer", "operator", "admin")),
    db: Session = Depends(get_db),
):
    _ = user
    rs.ensure_enabled()
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
    user: User = Depends(require_role("operator", "admin")),
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
    user: User = Depends(require_role("operator", "admin")),
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
    user: User = Depends(require_role("operator", "admin")),
    db: Session = Depends(get_db),
):
    _ = user
    rs.ensure_enabled()
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
        return {
            "status": "ok",
            "vnc_password": session.vnc_password,
            "guacd_host": rs.settings.guac_reverse_vnc_host,
            "guacd_reverse_port": rs.settings.guac_reverse_vnc_port,
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

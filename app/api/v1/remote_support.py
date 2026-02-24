from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.auth import get_current_user
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
from app.api.v1.agent import _authenticate_agent

router = APIRouter(tags=["remote-support"])


@router.post("/remote-support/sessions")
def create_remote_session(
    body: RemoteSessionCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = rs.create_session(db, body.agent_uuid, user.id, body.reason, body.max_duration_min)
    return {
        "status": "ok",
        "session": {
            "id": session.id,
            "agent_uuid": session.agent_uuid,
            "status": session.status,
            "reason": session.reason,
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
    user: User = Depends(get_current_user),
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
                "status": s.status,
                "reason": s.reason,
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
    user: User = Depends(get_current_user),
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
            "status": s.status,
            "reason": s.reason,
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
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ = user
    rs.end_session(db, session_id, ended_by="admin")
    return MessageResponse(status="ok", message="Session ended")


@router.get("/remote-support/sessions/{session_id}/novnc-ticket")
def get_remote_session_novnc_ticket(
    session_id: int,
    user: User = Depends(get_current_user),
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

    agent = db.query(Agent).filter(Agent.uuid == s.agent_uuid).first()
    agent_ip = (agent.ip_address or "").strip() if agent else ""
    if not agent_ip:
        return {"status": "ok", "viewer": {"enabled": False, "reason": "missing_agent_ip"}}

    try:
        token, ws_path = novnc.build_ticket(agent_ip=agent_ip, vnc_port=20010)
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
    session = rs.approve_from_agent(db, session_id, x_agent_uuid, body.approved)
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

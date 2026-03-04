from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
import string

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Agent, AgentGroup, Group, RemoteSupportSession, User
from app.services import agent_signal

settings = get_settings()

_ACTIVE_STATES = {"pending_approval", "approved", "connecting", "active"}
_OFFLINE_END_STATES = {"approved", "connecting", "active"}
_VNC_PASS_ALPHABET = string.ascii_letters + string.digits


def _generate_vnc_password(length: int = 8) -> str:
    # UltraVNC helper expects short password format; keep deterministic length/alphabet.
    return "".join(secrets.choice(_VNC_PASS_ALPHABET) for _ in range(max(1, length)))


def ensure_enabled() -> None:
    if not settings.remote_support_enabled:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Remote support is disabled")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _set_agent_remote_state(
    db: Session,
    agent_uuid: str,
    state: Optional[str],
    session_id: Optional[int],
    helper_running: Optional[bool] = None,
) -> None:
    agent = db.query(Agent).filter(Agent.uuid == agent_uuid).first()
    if not agent:
        return
    agent.remote_support_state = state
    agent.remote_support_session_id = session_id
    if helper_running is not None:
        agent.remote_support_helper_running = bool(helper_running)
        if not helper_running:
            agent.remote_support_helper_pid = None
    agent.remote_support_updated_at = _utcnow()
    db.add(agent)


def _stop_recording_best_effort(db: Session, session_id: int, reason: str) -> None:
    try:
        from app.services import session_recording_service

        session_recording_service.stop_recording(db, session_id, reason=reason)
    except Exception:
        # Recording stop failures should never block session state updates.
        pass


def _ensure_agent_online(db: Session, agent_uuid: str) -> Agent:
    agent = db.query(Agent).filter(Agent.uuid == agent_uuid).first()
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    if agent.status != "online":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Agent is offline")
    return agent


def is_agent_allowed(db: Session, agent_uuid: str) -> bool:
    row = (
        db.query(AgentGroup.agent_uuid)
        .join(Group, Group.id == AgentGroup.group_id)
        .filter(
            AgentGroup.agent_uuid == agent_uuid,
            func.lower(Group.name) == "remote support",
        )
        .first()
    )
    return row is not None


def _ensure_no_active_session(db: Session, agent_uuid: str) -> None:
    existing = (
        db.query(RemoteSupportSession)
        .filter(RemoteSupportSession.agent_uuid == agent_uuid, RemoteSupportSession.status.in_(_ACTIVE_STATES))
        .first()
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent already has an active remote support session")


def create_session(db: Session, agent_uuid: str, admin_user_id: int, reason: str, max_duration_min: int) -> RemoteSupportSession:
    ensure_enabled()
    clean_reason = (reason or "").strip()
    if len(clean_reason) < 3:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Connection reason is required")
    if len(clean_reason) > 500:
        clean_reason = clean_reason[:500]
    if not is_agent_allowed(db, agent_uuid):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Agent is not in Remote Support group",
        )
    _ensure_agent_online(db, agent_uuid)
    _ensure_no_active_session(db, agent_uuid)

    max_allowed = max(1, settings.remote_support_max_duration_min)
    requested = max(1, min(max_duration_min, max_allowed))
    static_vnc_password = (settings.remote_support_vnc_password or "").strip()
    vnc_password = static_vnc_password if static_vnc_password else _generate_vnc_password(8)

    now = _utcnow()
    timeout_sec = max(30, settings.remote_support_approval_timeout_sec)
    session = RemoteSupportSession(
        agent_uuid=agent_uuid,
        admin_user_id=admin_user_id,
        status="pending_approval",
        reason=clean_reason,
        vnc_password=vnc_password,
        requested_at=now,
        approval_timeout_at=now + timedelta(seconds=timeout_sec),
        max_duration_min=requested,
    )
    db.add(session)
    db.flush()
    _set_agent_remote_state(db, agent_uuid, "pending_approval", session.id, helper_running=False)
    db.commit()
    db.refresh(session)
    agent_signal.notify_agent(agent_uuid)
    return session


def list_sessions(
    db: Session,
    status_filter: Optional[str] = None,
    agent_uuid: Optional[str] = None,
    limit: int = 50,
) -> list[RemoteSupportSession]:
    now = _utcnow()
    q = db.query(RemoteSupportSession)
    if status_filter:
        q = q.filter(RemoteSupportSession.status == status_filter)
    if agent_uuid:
        q = q.filter(RemoteSupportSession.agent_uuid == agent_uuid)
    rows = q.order_by(RemoteSupportSession.id.desc()).limit(max(1, min(limit, 200))).all()
    changed = False
    for s in rows:
        if s.status != "pending_approval":
            continue
        timeout_at = _as_utc(s.approval_timeout_at)
        if not timeout_at or now <= timeout_at:
            continue
        s.status = "timeout"
        s.ended_at = now
        s.ended_by = "timeout"
        s.vnc_password = None
        s.end_signal_pending = False
        _set_agent_remote_state(db, s.agent_uuid, "idle", None, helper_running=False)
        db.add(s)
        changed = True
    if changed:
        db.commit()
    return rows


def get_session(db: Session, session_id: int) -> RemoteSupportSession:
    session = db.query(RemoteSupportSession).filter(RemoteSupportSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if session.status == "pending_approval":
        now = _utcnow()
        timeout_at = _as_utc(session.approval_timeout_at)
        if timeout_at and now > timeout_at:
            session.status = "timeout"
            session.ended_at = now
            session.ended_by = "timeout"
            session.vnc_password = None
            session.end_signal_pending = False
            _set_agent_remote_state(db, session.agent_uuid, "idle", None, helper_running=False)
            db.add(session)
            db.commit()
            db.refresh(session)
    return session


def get_pending_for_agent(db: Session, agent_uuid: str) -> Optional[RemoteSupportSession]:
    ensure_enabled()
    now = _utcnow()
    return (
        db.query(RemoteSupportSession)
        .filter(
            RemoteSupportSession.agent_uuid == agent_uuid,
            RemoteSupportSession.status == "pending_approval",
            RemoteSupportSession.approval_timeout_at > now,
        )
        .order_by(RemoteSupportSession.id.asc())
        .first()
    )


def get_end_signal_for_agent(db: Session, agent_uuid: str) -> Optional[RemoteSupportSession]:
    ensure_enabled()
    return (
        db.query(RemoteSupportSession)
        .filter(
            RemoteSupportSession.agent_uuid == agent_uuid,
            RemoteSupportSession.end_signal_pending.is_(True),
            RemoteSupportSession.status == "ended",
        )
        .order_by(RemoteSupportSession.ended_at.desc(), RemoteSupportSession.id.desc())
        .first()
    )


def mark_end_signal_delivered(db: Session, session_id: int, agent_uuid: str) -> None:
    s = (
        db.query(RemoteSupportSession)
        .filter(RemoteSupportSession.id == session_id, RemoteSupportSession.agent_uuid == agent_uuid)
        .first()
    )
    if not s:
        return
    if s.end_signal_pending:
        s.end_signal_pending = False
        db.add(s)
        db.commit()


def approve_from_agent(
    db: Session,
    session_id: int,
    agent_uuid: str,
    approved: bool,
    monitor_count: int | None = None,
) -> RemoteSupportSession:
    ensure_enabled()
    session = get_session(db, session_id)
    if session.agent_uuid != agent_uuid:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Session does not belong to agent")
    if session.status != "pending_approval":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Session is not waiting approval")

    now = _utcnow()
    timeout_at = _as_utc(session.approval_timeout_at)
    if timeout_at and now > timeout_at:
        session.status = "timeout"
        session.ended_at = now
        session.ended_by = "timeout"
        session.vnc_password = None
        _set_agent_remote_state(db, agent_uuid, "idle", None, helper_running=False)
    elif approved:
        session.status = "approved"
        session.approved_at = now
        if monitor_count is not None and monitor_count > 0:
            session.monitor_count = int(monitor_count)
        _set_agent_remote_state(db, agent_uuid, "approved", session.id, helper_running=False)
    else:
        session.status = "rejected"
        session.ended_at = now
        session.ended_by = "user"
        session.vnc_password = None
        _set_agent_remote_state(db, agent_uuid, "idle", None, helper_running=False)

    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def mark_ready_from_agent(db: Session, session_id: int, agent_uuid: str) -> RemoteSupportSession:
    ensure_enabled()
    session = get_session(db, session_id)
    if session.agent_uuid != agent_uuid:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Session does not belong to agent")
    if session.status not in {"approved", "connecting"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Session not in approvable state")

    now = _utcnow()
    if not session.connected_at:
        session.connected_at = now
    session.status = "active"
    _set_agent_remote_state(db, agent_uuid, "active", session.id, helper_running=True)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def end_session(db: Session, session_id: int, ended_by: str) -> RemoteSupportSession:
    ensure_enabled()
    session = get_session(db, session_id)
    if session.status in {"ended", "rejected", "timeout"}:
        return session

    session.status = "ended"
    session.ended_at = _utcnow()
    session.ended_by = ended_by
    session.vnc_password = None
    # If admin ends the session, agent must be signaled via heartbeat.
    session.end_signal_pending = ended_by == "admin"
    _set_agent_remote_state(db, session.agent_uuid, "idle", None, helper_running=False)
    db.add(session)
    db.commit()
    db.refresh(session)
    _stop_recording_best_effort(db, session.id, reason=f"session_end:{ended_by}")
    agent_signal.notify_agent(session.agent_uuid)
    return session


def end_session_from_agent(db: Session, session_id: int, agent_uuid: str, ended_by: str) -> RemoteSupportSession:
    ensure_enabled()
    session = get_session(db, session_id)
    if session.agent_uuid != agent_uuid:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Session does not belong to agent")
    if session.status in {"ended", "rejected", "timeout"}:
        return session

    session.status = "ended"
    session.ended_at = _utcnow()
    session.ended_by = ended_by or "agent"
    session.vnc_password = None
    session.end_signal_pending = False
    _set_agent_remote_state(db, agent_uuid, "idle", None, helper_running=False)
    db.add(session)
    db.commit()
    db.refresh(session)
    _stop_recording_best_effort(db, session.id, reason=f"agent_end:{ended_by or 'agent'}")
    return session


def cancel_pending_session(db: Session, session_id: int, admin_user_id: int | None = None) -> RemoteSupportSession:
    ensure_enabled()
    session = get_session(db, session_id)
    if admin_user_id and int(session.admin_user_id) != int(admin_user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Session does not belong to user")
    if session.status != "pending_approval":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Session is not waiting approval")

    session.status = "ended"
    session.ended_at = _utcnow()
    session.ended_by = "admin_cancel_on_close"
    session.vnc_password = None
    # Notify agent to tear down any pre-started helper and pending consent flow.
    session.end_signal_pending = True
    _set_agent_remote_state(db, session.agent_uuid, "idle", None, helper_running=False)
    db.add(session)
    db.commit()
    db.refresh(session)
    _stop_recording_best_effort(db, session.id, reason="pending_cancel")
    agent_signal.notify_agent(session.agent_uuid)
    return session


def check_approval_timeouts(db: Session) -> int:
    now = _utcnow()
    sessions = (
        db.query(RemoteSupportSession)
        .filter(RemoteSupportSession.status == "pending_approval", RemoteSupportSession.approval_timeout_at < now)
        .all()
    )
    for s in sessions:
        s.status = "timeout"
        s.ended_at = now
        s.ended_by = "timeout"
        s.vnc_password = None
        _set_agent_remote_state(db, s.agent_uuid, "idle", None, helper_running=False)
        db.add(s)
    if sessions:
        db.commit()
    return len(sessions)


def check_max_durations(db: Session) -> int:
    now = _utcnow()
    sessions = db.query(RemoteSupportSession).filter(RemoteSupportSession.status == "active").all()
    hit = 0
    for s in sessions:
        if not s.connected_at:
            continue
        connected_at = _as_utc(s.connected_at)
        if not connected_at:
            continue
        elapsed_min = (now - connected_at).total_seconds() / 60.0
        if elapsed_min >= max(1, s.max_duration_min):
            s.status = "ended"
            s.ended_at = now
            s.ended_by = "timeout"
            s.vnc_password = None
            s.end_signal_pending = True
            _set_agent_remote_state(db, s.agent_uuid, "idle", None, helper_running=False)
            db.add(s)
            _stop_recording_best_effort(db, s.id, reason="session_end:timeout")
            hit += 1
    if hit:
        db.commit()
    return hit


def end_sessions_for_offline_agents(db: Session, agent_uuids: list[str]) -> int:
    if not agent_uuids:
        return 0
    sessions = (
        db.query(RemoteSupportSession)
        .filter(RemoteSupportSession.agent_uuid.in_(agent_uuids), RemoteSupportSession.status.in_(_OFFLINE_END_STATES))
        .all()
    )
    now = _utcnow()
    for s in sessions:
        s.status = "ended"
        s.ended_at = now
        s.ended_by = "agent_offline"
        s.vnc_password = None
        # Keep end signal pending so agent can self-heal stale local state after reconnect.
        s.end_signal_pending = True
        _set_agent_remote_state(db, s.agent_uuid, "idle", None, helper_running=False)
        db.add(s)
        _stop_recording_best_effort(db, s.id, reason="session_end:agent_offline")
    if sessions:
        db.commit()
    return len(sessions)


def admin_name_for_session(db: Session, session: RemoteSupportSession) -> str:
    user = db.query(User).filter(User.id == session.admin_user_id).first()
    if not user:
        return "AppCenter Admin"
    # Remote support consent message must reflect the actual login account.
    return (user.username or "").strip() or "AppCenter Admin"

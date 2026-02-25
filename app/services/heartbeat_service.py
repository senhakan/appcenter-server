from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import (
    Agent,
    AgentApplication,
    AgentGroup,
    AgentIdentityHistory,
    AgentStatusHistory,
    AgentSystemProfileHistory,
    Application,
    Deployment,
    Group,
    RemoteSupportSession,
    TaskHistory,
)
from app.schemas import CommandItem, HeartbeatConfig, HeartbeatRequest


def _get_setting(db: Session, key: str, default: str) -> str:
    from app.models import Setting

    setting = db.query(Setting).filter(Setting.key == key).first()
    return setting.value if setting else default


def get_heartbeat_config(db: Session) -> HeartbeatConfig:
    download_url = _get_setting(db, "agent_download_url", "")
    agent_hash = _get_setting(db, "agent_hash", "")
    runtime_base_url = (_get_setting(db, "runtime_update_base_url", "") or "").strip()
    return HeartbeatConfig(
        bandwidth_limit_kbps=int(_get_setting(db, "bandwidth_limit_kbps", "1024")),
        work_hour_start=_get_setting(db, "work_hour_start", "09:00"),
        work_hour_end=_get_setting(db, "work_hour_end", "18:00"),
        latest_agent_version=_get_setting(db, "agent_latest_version", "1.0.0"),
        agent_download_url=download_url or None,
        agent_hash=agent_hash or None,
        runtime_update_base_url=runtime_base_url or None,
        runtime_update_interval_min=int(_get_setting(db, "runtime_update_interval_min", "60")),
        runtime_update_jitter_sec=int(_get_setting(db, "runtime_update_jitter_sec", "300")),
    )


def _is_store_tray_enabled_for_agent(db: Session, agent_uuid: str) -> bool:
    row = (
        db.query(AgentGroup.agent_uuid)
        .join(Group, Group.id == AgentGroup.group_id)
        .filter(
            AgentGroup.agent_uuid == agent_uuid,
            func.lower(Group.name) == "store",
        )
        .first()
    )
    return row is not None


def _sync_installed_apps(db: Session, agent: Agent, payload: HeartbeatRequest, now: datetime) -> None:
    if not payload.apps_changed:
        return
    for installed in payload.installed_apps:
        agent_app = (
            db.query(AgentApplication)
            .filter(
                AgentApplication.agent_uuid == agent.uuid,
                AgentApplication.app_id == installed.app_id,
            )
            .first()
        )
        if not agent_app:
            agent_app = AgentApplication(
                agent_uuid=agent.uuid,
                app_id=installed.app_id,
                status="installed",
                installed_version=installed.version,
                last_attempt=now,
            )
        else:
            agent_app.status = "installed"
            agent_app.installed_version = installed.version
            agent_app.last_attempt = now
        db.add(agent_app)


def _pending_commands(db: Session, agent: Agent, now: datetime) -> list[CommandItem]:
    rows = (
        db.query(AgentApplication, Application, Deployment)
        .join(Application, Application.id == AgentApplication.app_id)
        .outerjoin(Deployment, Deployment.id == AgentApplication.deployment_id)
        .filter(
            AgentApplication.agent_uuid == agent.uuid,
            AgentApplication.status == "pending",
            Application.is_active.is_(True),
        )
        .order_by(Deployment.priority.desc().nullslast(), AgentApplication.created_at.asc())
        .all()
    )

    commands: list[CommandItem] = []
    for agent_app, app, deployment in rows:
        task = TaskHistory(
            agent_uuid=agent.uuid,
            app_id=app.id,
            deployment_id=deployment.id if deployment else None,
            action="install",
            status="pending",
            message="Queued from heartbeat",
            started_at=now,
        )
        db.add(task)
        db.flush()

        agent_app.status = "downloading"
        agent_app.last_attempt = now
        db.add(agent_app)

        commands.append(
            CommandItem(
                task_id=task.id,
                action="install",
                app_id=app.id,
                app_name=app.display_name,
                app_version=app.version,
                download_url=f"/api/v1/agent/download/{app.id}",
                file_hash=app.file_hash,
                file_size_bytes=app.file_size_bytes,
                install_args=app.install_args,
                # Store-origin installs (no deployment row) should run immediately:
                # skip work-hours/jitter gating on the agent side.
                force_update=deployment.force_update if deployment else True,
                priority=deployment.priority if deployment else 5,
            )
        )
    return commands


def _resolve_active_remote_session_id(db: Session, agent_uuid: str) -> int | None:
    s = (
        db.query(RemoteSupportSession)
        .filter(
            RemoteSupportSession.agent_uuid == agent_uuid,
            RemoteSupportSession.status.in_(["pending_approval", "approved", "connecting", "active"]),
        )
        .order_by(RemoteSupportSession.id.desc())
        .first()
    )
    return int(s.id) if s else None


def _hash_json_dict(data: dict) -> str:
    # Deterministic, order-independent hashing for change detection.
    b = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(b).hexdigest()


def _diff_system_profile(old: dict | None, new: dict) -> list[str]:
    if not old:
        return ["initial"]

    changed: list[str] = []
    keys = [
        "os_full_name",
        "os_version",
        "build_number",
        "architecture",
        "manufacturer",
        "model",
        "cpu_model",
        "cpu_cores_physical",
        "cpu_cores_logical",
        "total_memory_gb",
    ]
    for k in keys:
        if old.get(k) != new.get(k):
            changed.append(k)

    # Disks: compare by index.
    def disk_map(d: dict | None) -> dict[int, dict]:
        out: dict[int, dict] = {}
        if not d:
            return out
        for item in d.get("disks") or []:
            if not isinstance(item, dict):
                continue
            idx = item.get("index")
            if isinstance(idx, int):
                out[idx] = {
                    "size_gb": item.get("size_gb"),
                    "model": item.get("model"),
                    "bus_type": item.get("bus_type"),
                }
        return out

    if disk_map(old) != disk_map(new) or old.get("disk_count") != new.get("disk_count"):
        changed.append("disks")

    if old.get("virtualization") != new.get("virtualization"):
        changed.append("virtualization")

    return changed


def _diff_system_profile_pairs(old: dict | None, new: dict) -> list[dict]:
    if not old:
        return []

    out: list[dict] = []

    def add(field: str, old_v, new_v) -> None:
        if old_v != new_v:
            out.append({"field": field, "old": old_v, "new": new_v})

    for k in [
        "os_full_name",
        "os_version",
        "build_number",
        "architecture",
        "manufacturer",
        "model",
        "cpu_model",
        "cpu_cores_physical",
        "cpu_cores_logical",
        "total_memory_gb",
    ]:
        add(k, old.get(k), new.get(k))

    add("disk_count", old.get("disk_count"), new.get("disk_count"))
    add("disks", old.get("disks"), new.get("disks"))
    add("virtualization", old.get("virtualization"), new.get("virtualization"))
    return out


def process_heartbeat(db: Session, agent: Agent, payload: HeartbeatRequest) -> tuple[datetime, HeartbeatConfig, list[CommandItem], bool]:
    now = datetime.now(timezone.utc)

    # Track identity changes (UUID remains stable).
    old_hostname = agent.hostname
    old_ip = agent.ip_address
    new_hostname = payload.hostname
    new_ip = payload.ip_address

    if (old_hostname and new_hostname and old_hostname != new_hostname) or ((old_ip or "") != (new_ip or "")):
        db.add(
            AgentIdentityHistory(
                agent_uuid=agent.uuid,
                detected_at=now,
                old_hostname=old_hostname,
                new_hostname=new_hostname,
                old_ip_address=old_ip,
                new_ip_address=new_ip,
            )
        )

    # Track status transitions (e.g. offline -> online when heartbeat resumes).
    old_status = agent.status

    agent.hostname = payload.hostname
    agent.ip_address = payload.ip_address
    agent.os_user = payload.os_user
    if payload.agent_version:
        agent.version = payload.agent_version
    if payload.disk_free_gb is not None:
        agent.disk_free_gb = payload.disk_free_gb

    # Logged-in sessions (local/RDP) - optional for backward compatibility.
    if payload.logged_in_sessions is not None:
        agent.logged_in_sessions_json = json.dumps([s.model_dump() for s in payload.logged_in_sessions])
        agent.logged_in_sessions_updated_at = now

    # System profile snapshot - sent periodically (not on every heartbeat).
    if payload.system_profile is not None:
        profile_dict = payload.system_profile.model_dump()
        profile_hash = _hash_json_dict(profile_dict)
        if agent.system_profile_hash != profile_hash:
            changed_fields = _diff_system_profile(agent.system_profile, profile_dict)
            diff = _diff_system_profile_pairs(agent.system_profile, profile_dict)
            db.add(
                AgentSystemProfileHistory(
                    agent_uuid=agent.uuid,
                    detected_at=now,
                    profile_hash=profile_hash,
                    profile_json=json.dumps(profile_dict),
                    changed_fields_json=json.dumps(changed_fields),
                    diff_json=json.dumps(diff),
                )
            )
            agent.system_profile_json = json.dumps(profile_dict)
            agent.system_profile_hash = profile_hash
            agent.system_profile_updated_at = now

    # Remote support runtime status (live session/helper visibility).
    # Guard against stale heartbeats reviving an already-ended session in UI.
    if payload.remote_support is not None:
        incoming_state = (payload.remote_support.state or "").strip().lower()
        incoming_sid = int(payload.remote_support.session_id or 0)
        active_sid = _resolve_active_remote_session_id(db, agent.uuid)

        accept = False
        if active_sid is None:
            # No active server-side session: only accept terminal/idle snapshots.
            accept = incoming_state in {"idle", "ended", "none", ""}
        else:
            # Active session exists: accept if heartbeat matches active session id
            # or if agent doesn't provide id but state is active-ish.
            accept = (incoming_sid == active_sid) or (incoming_sid == 0 and incoming_state in {"approved", "connecting", "active"})

        if accept:
            agent.remote_support_state = payload.remote_support.state
            agent.remote_support_session_id = payload.remote_support.session_id
            agent.remote_support_helper_running = bool(payload.remote_support.helper_running)
            agent.remote_support_helper_pid = payload.remote_support.helper_pid
            agent.remote_support_updated_at = now

    agent.last_seen = now
    agent.status = "online"
    agent.updated_at = now
    db.add(agent)

    if old_status != agent.status:
        db.add(
            AgentStatusHistory(
                agent_uuid=agent.uuid,
                detected_at=now,
                old_status=old_status,
                new_status=agent.status,
                reason="heartbeat",
            )
        )

    _sync_installed_apps(db, agent, payload, now)
    commands = _pending_commands(db, agent, now)

    inventory_sync_required = False
    if payload.inventory_hash is not None:
        if agent.inventory_hash is None or agent.inventory_hash != payload.inventory_hash:
            inventory_sync_required = True

    config = get_heartbeat_config(db)
    config.inventory_scan_interval_min = int(_get_setting(db, "inventory_scan_interval_min", "10"))
    config.inventory_sync_required = inventory_sync_required
    config.store_tray_enabled = _is_store_tray_enabled_for_agent(db, agent.uuid)

    db.commit()
    return now, config, commands, inventory_sync_required

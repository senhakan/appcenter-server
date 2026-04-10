from __future__ import annotations

import asyncio
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
    Announcement,
    AnnouncementDelivery,
    AgentServiceHistory,
    AgentStatusHistory,
    AgentSystemProfileHistory,
    Application,
    Deployment,
    Group,
    RemoteSupportSession,
    TaskHistory,
)
from app.schemas import CommandItem, HeartbeatConfig, HeartbeatRequest, PendingAnnouncementItem, ServiceItem
from app.services.announcement_service import deliver_pending_to_agent
from app.services import runtime_config_service as runtime_config
from app.services.ws_manager import make_message, ws_manager


def _get_setting(db: Session, key: str, default: str) -> str:
    from app.models import Setting

    setting = db.query(Setting).filter(Setting.key == key).first()
    return setting.value if setting else default


def get_heartbeat_config(db: Session, agent_platform: str) -> HeartbeatConfig:
    platform = (agent_platform or "windows").strip().lower()
    if platform not in {"windows", "linux"}:
        platform = "windows"
    latest_version = _get_setting(db, f"agent_latest_version_{platform}", "") or _get_setting(db, "agent_latest_version", "1.0.0")
    download_url = _get_setting(db, f"agent_download_url_{platform}", "") or _get_setting(db, "agent_download_url", "")
    agent_hash = _get_setting(db, f"agent_hash_{platform}", "") or _get_setting(db, "agent_hash", "")
    return HeartbeatConfig(
        bandwidth_limit_kbps=int(_get_setting(db, "bandwidth_limit_kbps", "1024")),
        latest_agent_version=latest_version or "1.0.0",
        agent_download_url=download_url or None,
        agent_hash=agent_hash or None,
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


def _is_remote_support_enabled_for_agent(db: Session, agent_uuid: str) -> bool:
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


def _hash_json_list(data: list[dict]) -> str:
    b = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(b).hexdigest()


def _normalize_service_status(value: str | None) -> str:
    v = (value or "").strip().lower()
    if v in {"running", "run", "active"}:
        return "running"
    if v in {"stopped", "stop", "inactive"}:
        return "stopped"
    if v in {"paused", "pause"}:
        return "paused"
    if v in {"failed", "error"}:
        return "failed"
    return "unknown"


def _normalize_startup_type(value: str | None) -> str:
    v = (value or "").strip().lower()
    if v in {"auto", "automatic", "enabled"}:
        return "auto"
    if v in {"manual", "demand"}:
        return "manual"
    if v in {"disabled", "masked"}:
        return "disabled"
    if v in {"delayed", "auto-delayed", "automatic (delayed start)"}:
        return "delayed"
    return "unknown"


def _normalize_services(items: list[ServiceItem] | None) -> list[dict]:
    if not items:
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for item in items:
        name = (item.name or "").strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "name": name,
                "display_name": (item.display_name or "").strip() or None,
                "status": _normalize_service_status(item.status),
                "startup_type": _normalize_startup_type(item.startup_type),
                "pid": int(item.pid) if item.pid and int(item.pid) > 0 else None,
                "run_as": (item.run_as or "").strip() or None,
                "description": (item.description or "").strip() or None,
            }
        )
    out.sort(key=lambda x: (x.get("name") or "").lower())
    return out


def _diff_services(old_items: list[dict], new_items: list[dict]) -> list[dict]:
    old_map = {(x.get("name") or "").lower(): x for x in old_items if (x.get("name") or "").strip()}
    new_map = {(x.get("name") or "").lower(): x for x in new_items if (x.get("name") or "").strip()}
    keys = sorted(set(old_map.keys()) | set(new_map.keys()))
    changes: list[dict] = []
    for key in keys:
        old = old_map.get(key)
        new = new_map.get(key)
        if old is None and new is not None:
            changes.append({"type": "added", "old": None, "new": new})
            continue
        if old is not None and new is None:
            changes.append({"type": "removed", "old": old, "new": None})
            continue
        assert old is not None and new is not None
        status_changed = (old.get("status") or "unknown") != (new.get("status") or "unknown")
        startup_changed = (old.get("startup_type") or "unknown") != (new.get("startup_type") or "unknown")
        if status_changed and startup_changed:
            change_type = "updated"
        elif status_changed:
            change_type = "status_changed"
        elif startup_changed:
            change_type = "startup_changed"
        else:
            continue
        changes.append({"type": change_type, "old": old, "new": new})
    return changes


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


def _mark_pending_announcements_delivered(
    db: Session,
    agent_uuid: str,
    pending_announcements: list[PendingAnnouncementItem],
    delivered_at: datetime,
) -> None:
    announcement_ids: list[int] = []
    seen: set[int] = set()
    for item in pending_announcements:
        if item.announcement_id in seen:
            continue
        seen.add(item.announcement_id)
        announcement_ids.append(item.announcement_id)
    if not announcement_ids:
        return

    rows = (
        db.query(AnnouncementDelivery, Announcement)
        .join(Announcement, Announcement.id == AnnouncementDelivery.announcement_id)
        .filter(
            AnnouncementDelivery.agent_uuid == agent_uuid,
            AnnouncementDelivery.announcement_id.in_(announcement_ids),
            AnnouncementDelivery.status == "pending",
        )
        .all()
    )
    for delivery, announcement in rows:
        delivery.status = "delivered"
        delivery.delivered_at = delivered_at
        announcement.delivered_count += 1
        db.add(delivery)
        db.add(announcement)


def process_heartbeat(
    db: Session,
    agent: Agent,
    payload: HeartbeatRequest,
) -> tuple[datetime, HeartbeatConfig, list[CommandItem], bool, list[PendingAnnouncementItem]]:
    now = datetime.now(timezone.utc)
    full_ip_list: list[str] = []
    if payload.full_ip is not None:
        seen: set[str] = set()
        for raw in payload.full_ip:
            ip = (raw or "").strip()
            if not ip or ip in seen:
                continue
            seen.add(ip)
            full_ip_list.append(ip)
    payload_ip = (payload.ip_address or "").strip() or None
    persisted_ip = (agent.ip_address or "").strip() or None
    persisted_full_ip_first: str | None = None
    if not payload_ip and not full_ip_list and agent.full_ip:
        try:
            existing_full = json.loads(agent.full_ip)
            if isinstance(existing_full, list):
                for raw in existing_full:
                    ip = (str(raw) if raw is not None else "").strip()
                    if ip:
                        persisted_full_ip_first = ip
                        break
        except Exception:
            persisted_full_ip_first = None
    # Preserve/derive IP if heartbeat omits ip_address/full_ip fields.
    effective_ip = payload_ip or (full_ip_list[0] if full_ip_list else None) or persisted_ip or persisted_full_ip_first

    # Track identity changes (UUID remains stable).
    old_hostname = agent.hostname
    old_ip = agent.ip_address
    new_hostname = payload.hostname
    new_ip = effective_ip

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
    agent.ip_address = effective_ip
    if payload.full_ip is not None:
        agent.full_ip = json.dumps(full_ip_list)
    if payload.uptime_sec is not None:
        try:
            uptime = int(payload.uptime_sec)
            if uptime >= 0:
                agent.uptime_sec = uptime
        except Exception:
            pass
    agent.os_user = payload.os_user
    if payload.os_version is not None:
        agent.os_version = payload.os_version
    if payload.arch is not None:
        agent.arch = payload.arch
    if payload.distro is not None:
        agent.distro = payload.distro
    if payload.distro_version is not None:
        agent.distro_version = payload.distro_version
    if payload.agent_version:
        agent.version = payload.agent_version
    if payload.cpu_model is not None:
        agent.cpu_model = payload.cpu_model
    if payload.ram_gb is not None:
        agent.ram_gb = payload.ram_gb
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
        passive_states = {"idle", "ended", "none", "", "rejected"}
        terminal_states = passive_states | {"error"}

        accept = False
        if active_sid is None:
            # No active server-side session: only accept terminal/idle snapshots.
            accept = incoming_state in passive_states
        else:
            if incoming_sid == active_sid and incoming_state in terminal_states:
                # Agent reports the active session as terminal/error. Reconcile the
                # server-side session immediately so stale sessions do not block
                # the next remote support attempt.
                from app.services import remote_support_service as rs

                ended_by = "agent_error" if incoming_state == "error" else "agent"
                rs.end_session_from_agent(db, active_sid, agent.uuid, ended_by)
                active_sid = None
                accept = incoming_state in passive_states
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

    config = get_heartbeat_config(db, agent.platform or "windows")
    config.inventory_scan_interval_min = int(_get_setting(db, "inventory_scan_interval_min", "10"))
    config.inventory_sync_required = inventory_sync_required
    config.store_tray_enabled = _is_store_tray_enabled_for_agent(db, agent.uuid)
    config.remote_support_enabled = runtime_config.is_remote_support_enabled(db) and _is_remote_support_enabled_for_agent(db, agent.uuid)
    # WS agent-level enable: DB'de ws_agent_enabled=true ise tüm agentlara enable et
    ws_agent_flag = _get_setting(db, "ws_agent_enabled", "false")
    config.websocket_enabled = ws_agent_flag.strip().lower() in ("true", "1", "yes")
    global_service_enabled = str(_get_setting(db, "service_monitoring_enabled", "false")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    effective_service_enabled = (
        bool(agent.service_monitoring_enabled)
        if agent.service_monitoring_enabled is not None
        else global_service_enabled
    )
    config.service_monitoring_enabled = effective_service_enabled
    services_sync_required = False
    if effective_service_enabled:
        if payload.services_hash is not None:
            services_sync_required = (
                agent.services_hash is None
                or (payload.services_hash or "").strip() == ""
                or agent.services_hash != (payload.services_hash or "").strip()
            )
        if payload.services is not None:
            normalized = _normalize_services(payload.services)
            incoming_hash = (payload.services_hash or "").strip() or _hash_json_list(normalized)
            existing = agent.services or []
            if agent.services_hash != incoming_hash or existing != normalized:
                # Do not create noisy "initial" events when service monitoring is first enabled.
                has_baseline = bool(existing) and bool((agent.services_hash or "").strip())
                if has_baseline:
                    for ch in _diff_services(existing, normalized):
                        old = ch.get("old")
                        new = ch.get("new")
                        ref = new or old or {}
                        db.add(
                            AgentServiceHistory(
                                agent_uuid=agent.uuid,
                                detected_at=now,
                                service_name=(ref.get("name") or "").strip() or "unknown",
                                display_name=(ref.get("display_name") or "").strip() or None,
                                change_type=ch["type"],
                                old_status=(old or {}).get("status"),
                                new_status=(new or {}).get("status"),
                                old_startup_type=(old or {}).get("startup_type"),
                                new_startup_type=(new or {}).get("startup_type"),
                                old_payload_json=json.dumps(old) if old else None,
                                new_payload_json=json.dumps(new) if new else None,
                            )
                        )
                agent.services_json = json.dumps(normalized)
                agent.services_hash = incoming_hash
                agent.services_updated_at = now
                db.add(agent)
            services_sync_required = False
    else:
        services_sync_required = False
    config.services_sync_required = services_sync_required

    pending_announcements: list[PendingAnnouncementItem] = []
    pending_payloads = deliver_pending_to_agent(db, agent.uuid)
    if pending_payloads:
        for item in pending_payloads:
            try:
                pending_announcements.append(PendingAnnouncementItem.model_validate(item))
            except Exception:
                continue
        if pending_announcements:
            _mark_pending_announcements_delivered(db, agent.uuid, pending_announcements, now)

    db.commit()
    if ws_manager.ui_count > 0:
        ws_manager.schedule_broadcast_to_ui(
            make_message(
                "server.agent.status",
                {
                    "uuid": agent.uuid,
                    "hostname": agent.hostname,
                    "status": agent.status,
                    "ip_address": agent.ip_address,
                    "last_seen": agent.last_seen.isoformat() if agent.last_seen else None,
                    "comm_mode": "http",
                },
            )
        )
    return now, config, commands, inventory_sync_required, pending_announcements

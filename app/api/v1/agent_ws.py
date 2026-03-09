from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect

from app.database import get_db
from app.models import Agent, AgentApplication, AgentIdentityHistory, AgentStatusHistory, Setting
from app.schemas import ServiceItem
from app.services import remote_support_service as rs
from app.services import inventory_service
from app.services.heartbeat_service import (
    _diff_services,
    _diff_system_profile,
    _diff_system_profile_pairs,
    _hash_json_dict,
    _hash_json_list,
    _is_remote_support_enabled_for_agent,
    _is_store_tray_enabled_for_agent,
    _normalize_services,
    _pending_commands,
    _resolve_active_remote_session_id,
    get_heartbeat_config,
)
from app.services.ws_manager import make_message, ws_manager

router = APIRouter(tags=["agent"])
logger = logging.getLogger("appcenter.ws.agent")
MAX_MESSAGE_BYTES = 64 * 1024


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _utc_iso() -> str:
    return _utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _setting_map(db, keys: list[str]) -> dict[str, str]:
    rows = db.query(Setting).filter(Setting.key.in_(keys)).all()
    out = {r.key: (r.value or "") for r in rows}
    for key in keys:
        out.setdefault(key, "")
    return out


def _to_bool(value: str | None, default: bool = False) -> bool:
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _to_int(value: str | None, default: int) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return default


async def _send_auth_error_and_close(websocket: WebSocket, code: int, message: str) -> None:
    await websocket.send_json(make_message("server.auth.result", {"ok": False, "error": message}))
    await websocket.close(code=code)


def _parse_message(raw_text: str) -> tuple[str, dict[str, Any]]:
    data = json.loads(raw_text)
    if not isinstance(data, dict):
        raise ValueError("Message must be a JSON object")
    msg_type = str(data.get("type") or "").strip()
    payload = data.get("payload")
    if not isinstance(payload, dict):
        payload = {}
    return msg_type, payload


@router.websocket("/ws")
async def agent_ws_endpoint(websocket: WebSocket):
    await websocket.accept()

    # 1) Feature flag + WS config.
    db = next(get_db())
    try:
        settings_map = _setting_map(
            db,
            [
                "ws_agent_enabled",
                "ws_auth_timeout_sec",
                "ws_ping_interval_sec",
                "agent_auth_recovery_enabled",
            ],
        )
    finally:
        db.close()

    if not _to_bool(settings_map.get("ws_agent_enabled"), default=False):
        logger.info("ws agent rejected: feature disabled")
        await _send_auth_error_and_close(websocket, 4000, "Agent WebSocket is disabled")
        return

    auth_timeout_sec = max(1, _to_int(settings_map.get("ws_auth_timeout_sec"), 10))
    ping_interval_sec = max(5, _to_int(settings_map.get("ws_ping_interval_sec"), 30))

    agent_uuid: str | None = None
    ping_task: asyncio.Task | None = None
    buffered_msg: tuple[str, dict[str, Any]] | None = None
    msg_count = 0
    msg_window_start = time.monotonic()
    MAX_MSGS_PER_MINUTE = 120

    try:
        # 2) Wait agent.auth (timeout).
        try:
            raw_auth = await asyncio.wait_for(websocket.receive_text(), timeout=auth_timeout_sec)
        except asyncio.TimeoutError:
            logger.warning("ws agent auth timeout")
            await websocket.close(code=4003)
            return
        if len(raw_auth.encode("utf-8")) > MAX_MESSAGE_BYTES:
            await websocket.close(code=1009, reason="message_too_large")
            return

        try:
            msg_type, payload = _parse_message(raw_auth)
        except Exception:
            await _send_auth_error_and_close(websocket, 4001, "Invalid auth message")
            return

        if msg_type != "agent.auth":
            await _send_auth_error_and_close(websocket, 4001, "Expected agent.auth")
            return

        req_uuid = str(payload.get("uuid") or "").strip()
        req_secret = str(payload.get("secret") or "").strip()
        if not req_uuid or not req_secret:
            await _send_auth_error_and_close(websocket, 4001, "Missing uuid/secret")
            return

        db = next(get_db())
        try:
            agent = (
                db.query(Agent)
                .filter(
                    Agent.uuid == req_uuid,
                    Agent.secret_key == req_secret,
                )
                .first()
            )
            recovery_enabled = _to_bool(settings_map.get("agent_auth_recovery_enabled"), default=False)
            if not agent and recovery_enabled:
                agent = db.query(Agent).filter(Agent.uuid == req_uuid).first()
                now = _utcnow()
                if not agent:
                    agent = Agent(
                        uuid=req_uuid,
                        hostname=req_uuid,
                        status="online",
                        last_seen=now,
                        updated_at=now,
                        secret_key=req_secret,
                    )
                    db.add(agent)
                else:
                    agent.secret_key = req_secret
                    agent.updated_at = now
                    db.add(agent)
                db.commit()
                db.refresh(agent)
        finally:
            db.close()

        if not agent:
            logger.warning("ws agent auth failed uuid=%s", req_uuid)
            await _send_auth_error_and_close(websocket, 4001, "Invalid credentials")
            return

        agent_uuid = agent.uuid
        logger.info("ws agent auth success uuid=%s", agent_uuid)
        await websocket.send_json(make_message("server.auth.ok", {"agent_uuid": agent.uuid}))

        # 3) Register connection.
        await ws_manager.register_agent(websocket, agent_uuid=agent.uuid)
        logger.info("ws agent connected uuid=%s", agent_uuid)

        # 4) Optional agent.hello (5s, non-fatal).
        try:
            raw_hello = await asyncio.wait_for(websocket.receive_text(), timeout=5)
            if len(raw_hello.encode("utf-8")) > MAX_MESSAGE_BYTES:
                await websocket.close(code=1009, reason="message_too_large")
                return
            try:
                hello_type, hello_payload = _parse_message(raw_hello)
                if hello_type == "agent.hello":
                    db = next(get_db())
                    try:
                        now = _utcnow()
                        agent = db.query(Agent).filter(Agent.uuid == agent_uuid).first()
                        if agent:
                            full_ip_list: list[str] = []
                            for raw in hello_payload.get("full_ip") or []:
                                ip = (str(raw) or "").strip()
                                if ip and ip not in full_ip_list:
                                    full_ip_list.append(ip)
                            payload_ip = (hello_payload.get("ip_address") or "").strip() or None
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
                            effective_ip = payload_ip or (full_ip_list[0] if full_ip_list else None) or persisted_ip or persisted_full_ip_first

                            old_hostname = agent.hostname
                            old_ip = agent.ip_address
                            new_hostname = (hello_payload.get("hostname") or "").strip() or agent.hostname
                            new_ip = effective_ip
                            if (old_hostname and new_hostname and old_hostname != new_hostname) or (
                                (old_ip or "") != (new_ip or "")
                            ):
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

                            old_status = agent.status
                            agent.hostname = new_hostname
                            agent.ip_address = effective_ip
                            if full_ip_list:
                                agent.full_ip = json.dumps(full_ip_list)
                            agent.os_version = (hello_payload.get("os_version") or agent.os_version)
                            agent.platform = (hello_payload.get("platform") or agent.platform or "windows")
                            agent.arch = (hello_payload.get("arch") or agent.arch)
                            agent.distro = (hello_payload.get("distro") or agent.distro)
                            agent.distro_version = (hello_payload.get("distro_version") or agent.distro_version)
                            agent_version = hello_payload.get("agent_version") or hello_payload.get("version", "")
                            agent.version = (agent_version or agent.version)
                            agent.cpu_model = (hello_payload.get("cpu_model") or agent.cpu_model)
                            if hello_payload.get("ram_gb") is not None:
                                try:
                                    agent.ram_gb = int(hello_payload.get("ram_gb"))
                                except Exception:
                                    pass
                            agent.status = "online"
                            agent.last_seen = now
                            agent.updated_at = now
                            db.add(agent)
                            if old_status != agent.status:
                                db.add(
                                    AgentStatusHistory(
                                        agent_uuid=agent.uuid,
                                        detected_at=now,
                                        old_status=old_status,
                                        new_status=agent.status,
                                        reason="ws_hello",
                                    )
                                )
                            db.commit()
                    finally:
                        db.close()
                else:
                    buffered_msg = (hello_type, hello_payload)
            except Exception:
                logger.warning("ws agent hello parse failed uuid=%s", agent_uuid)
        except asyncio.TimeoutError:
            pass

        # 5) Send server.hello with config + pending work.
        db = next(get_db())
        try:
            now = _utcnow()
            agent = db.query(Agent).filter(Agent.uuid == agent_uuid).first()
            if not agent:
                await websocket.close(code=1008)
                return

            config = get_heartbeat_config(db, agent.platform or "windows").model_dump()
            config["store_tray_enabled"] = _is_store_tray_enabled_for_agent(db, agent.uuid)
            config["remote_support_enabled"] = _is_remote_support_enabled_for_agent(db, agent.uuid)
            config["inventory_scan_interval_min"] = _to_int(
                _setting_map(db, ["inventory_scan_interval_min"]).get("inventory_scan_interval_min"),
                10,
            )

            pending_commands = [c.model_dump() for c in _pending_commands(db, agent, now)]
            pending_rs_request = None
            pending_rs_end = None
            try:
                req = rs.get_pending_for_agent(db, agent.uuid)
                if req:
                    pending_rs_request = {
                        "session_id": req.id,
                        "admin_name": rs.admin_name_for_session(db, req),
                        "reason": req.reason or "",
                        "requested_at": req.requested_at.isoformat() if req.requested_at else None,
                        "timeout_at": req.approval_timeout_at.isoformat() if req.approval_timeout_at else None,
                        "requires_approval": rs.is_approval_required_for_agent(db, agent.uuid),
                    }
                else:
                    end_sig = rs.get_end_signal_for_agent(db, agent.uuid)
                    if end_sig:
                        pending_rs_end = {"session_id": end_sig.id}
                        rs.mark_end_signal_delivered(db, end_sig.id, agent.uuid)
            except Exception:
                pending_rs_request = None
                pending_rs_end = None

            db.commit()
        finally:
            db.close()

        await websocket.send_json(
            make_message(
                "server.hello",
                {
                    "server_time": _utc_iso(),
                    "config": config,
                    "pending_commands": pending_commands,
                    "pending_rs_request": pending_rs_request,
                    "pending_rs_end": pending_rs_end,
                },
            )
        )

        # 6) Ping loop.
        async def _ping_loop():
            while True:
                await asyncio.sleep(ping_interval_sec)
                try:
                    await websocket.send_json(make_message("server.ping"))
                except Exception:
                    break

        ping_task = asyncio.create_task(_ping_loop())

        # 7) Main message loop.
        while True:
            if buffered_msg is not None:
                msg_type, payload = buffered_msg
                buffered_msg = None
            else:
                raw = await websocket.receive_text()
                if len(raw.encode("utf-8")) > MAX_MESSAGE_BYTES:
                    await websocket.close(code=1009, reason="message_too_large")
                    break
                msg_type, payload = _parse_message(raw)

            msg_count += 1
            now_mono = time.monotonic()
            if now_mono - msg_window_start >= 60:
                msg_count = 1
                msg_window_start = now_mono
            elif msg_count > MAX_MSGS_PER_MINUTE:
                logger.warning("ws agent rate limited uuid=%s", agent_uuid)
                await websocket.close(code=4029, reason="rate_limited")
                break

            if msg_type == "agent.pong":
                conn = ws_manager.get_agent(agent_uuid)
                if conn:
                    conn.last_pong = time.monotonic()
                # Keep agent online while WS is active.
                pong_db = next(get_db())
                try:
                    pong_db.query(Agent).filter(Agent.uuid == agent_uuid).update(
                        {"status": "online", "last_seen": _utcnow()}
                    )
                    pong_db.commit()
                except Exception:
                    pong_db.rollback()
                finally:
                    pong_db.close()
                continue

            if msg_type == "agent.ack":
                logger.info("ws agent ack uuid=%s ack_id=%s status=%s", agent_uuid, payload.get("ack_id"), payload.get("status"))
                continue

            if msg_type == "agent.task.progress":
                out = {
                    "agent_uuid": agent_uuid,
                    "task_id": payload.get("task_id"),
                    "status": payload.get("status"),
                    "progress_pct": payload.get("progress_pct"),
                    "message": payload.get("message"),
                }
                await ws_manager.broadcast_to_ui(make_message("server.task.update", out))
                continue

            db = next(get_db())
            try:
                now = _utcnow()
                agent = db.query(Agent).filter(Agent.uuid == agent_uuid).first()
                if not agent:
                    db.commit()
                    continue

                if msg_type == "agent.status":
                    if payload.get("disk_free_gb") is not None:
                        try:
                            agent.disk_free_gb = int(float(payload.get("disk_free_gb")))
                        except Exception:
                            pass
                    if payload.get("uptime_sec") is not None:
                        try:
                            up = int(payload.get("uptime_sec"))
                            if up >= 0:
                                agent.uptime_sec = up
                        except Exception:
                            pass
                    if payload.get("os_user") is not None:
                        agent.os_user = str(payload.get("os_user") or "").strip() or None
                    agent.status = "online"
                    agent.last_seen = now
                    agent.updated_at = now
                    db.add(agent)
                    await ws_manager.broadcast_to_ui(
                        make_message(
                            "server.agent.status",
                            {
                                "uuid": agent.uuid,
                                "hostname": agent.hostname,
                                "status": agent.status,
                                "ip_address": agent.ip_address,
                                "disk_free_gb": agent.disk_free_gb,
                                "cpu_usage": payload.get("cpu_usage"),
                                "ram_usage": payload.get("ram_usage"),
                                "current_status": payload.get("current_status"),
                                "last_seen": now.isoformat(),
                                "comm_mode": "ws",
                            },
                        )
                    )

                elif msg_type == "agent.apps.changed":
                    apps = payload.get("installed_apps") or []
                    if isinstance(apps, list):
                        for item in apps:
                            if not isinstance(item, dict):
                                continue
                            app_id = item.get("app_id")
                            version = str(item.get("version") or "").strip()
                            if not app_id:
                                continue
                            row = (
                                db.query(AgentApplication)
                                .filter(AgentApplication.agent_uuid == agent.uuid, AgentApplication.app_id == int(app_id))
                                .first()
                            )
                            if not row:
                                row = AgentApplication(
                                    agent_uuid=agent.uuid,
                                    app_id=int(app_id),
                                    status="installed",
                                    installed_version=version or None,
                                    last_attempt=now,
                                )
                            else:
                                row.status = "installed"
                                row.installed_version = version or row.installed_version
                                row.last_attempt = now
                            db.add(row)
                    agent.last_seen = now
                    db.add(agent)

                elif msg_type == "agent.services.changed":
                    incoming_services = payload.get("services") or []
                    if not isinstance(incoming_services, list):
                        incoming_services = []
                    service_items: list[ServiceItem] = []
                    for raw_item in incoming_services:
                        if not isinstance(raw_item, dict):
                            continue
                        try:
                            service_items.append(ServiceItem.model_validate(raw_item))
                        except Exception:
                            continue
                    normalized = _normalize_services(service_items)
                    incoming_hash = str(payload.get("services_hash") or "").strip() or _hash_json_list(normalized)
                    existing = agent.services or []
                    if agent.services_hash != incoming_hash or existing != normalized:
                        if existing and (agent.services_hash or "").strip():
                            for ch in _diff_services(existing, normalized):
                                old = ch.get("old")
                                new = ch.get("new")
                                ref = new or old or {}
                                from app.models import AgentServiceHistory

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
                    agent.last_seen = now

                elif msg_type == "agent.system_profile":
                    if isinstance(payload, dict):
                        profile_hash = _hash_json_dict(payload)
                        if agent.system_profile_hash != profile_hash:
                            from app.models import AgentSystemProfileHistory

                            changed_fields = _diff_system_profile(agent.system_profile, payload)
                            diff = _diff_system_profile_pairs(agent.system_profile, payload)
                            db.add(
                                AgentSystemProfileHistory(
                                    agent_uuid=agent.uuid,
                                    detected_at=now,
                                    profile_hash=profile_hash,
                                    profile_json=json.dumps(payload),
                                    changed_fields_json=json.dumps(changed_fields),
                                    diff_json=json.dumps(diff),
                                )
                            )
                            agent.system_profile_json = json.dumps(payload)
                            agent.system_profile_hash = profile_hash
                            agent.system_profile_updated_at = now
                            db.add(agent)
                    agent.last_seen = now

                elif msg_type == "agent.inventory.hash":
                    incoming_hash = str(payload.get("hash") or "").strip()
                    if incoming_hash and inventory_service.check_inventory_hash(db, agent.uuid, incoming_hash):
                        await websocket.send_json(make_message("server.inventory.sync_required", {}))
                    agent.last_seen = now
                    db.add(agent)

                elif msg_type == "agent.rs.status":
                    incoming_state = str(payload.get("state") or "").strip().lower()
                    incoming_sid = int(payload.get("session_id") or 0)
                    active_sid = _resolve_active_remote_session_id(db, agent.uuid)
                    accept = False
                    if active_sid is None:
                        accept = incoming_state in {"idle", "ended", "none", ""}
                    else:
                        accept = (incoming_sid == active_sid) or (
                            incoming_sid == 0 and incoming_state in {"approved", "connecting", "active"}
                        )
                    if accept:
                        agent.remote_support_state = payload.get("state")
                        agent.remote_support_session_id = payload.get("session_id")
                        agent.remote_support_helper_running = bool(payload.get("helper_running"))
                        pid = payload.get("helper_pid")
                        agent.remote_support_helper_pid = int(pid) if pid else None
                        agent.remote_support_updated_at = now
                        db.add(agent)
                    agent.last_seen = now

                else:
                    logger.info("ws agent unknown message uuid=%s type=%s", agent_uuid, msg_type)

                db.commit()
            finally:
                db.close()

    except WebSocketDisconnect:
        logger.info("ws agent disconnected uuid=%s", agent_uuid)
    except Exception as exc:
        logger.exception("ws agent handler error uuid=%s err=%s", agent_uuid, exc)
    finally:
        if ping_task:
            ping_task.cancel()
            try:
                await ping_task
            except BaseException:
                pass
        if agent_uuid:
            await ws_manager.unregister_agent(agent_uuid, ws=websocket)
            # Guard against reconnect races: if a newer WS for the same agent is active,
            # never force offline from this stale connection's teardown.
            if ws_manager.is_agent_connected(agent_uuid):
                return
            db = next(get_db())
            try:
                now = _utcnow()
                agent = db.query(Agent).filter(Agent.uuid == agent_uuid).first()
                if agent and agent.status != "offline":
                    old_status = agent.status
                    agent.status = "offline"
                    agent.last_seen = now
                    agent.updated_at = now
                    db.add(agent)
                    db.add(
                        AgentStatusHistory(
                            agent_uuid=agent.uuid,
                            detected_at=now,
                            old_status=old_status,
                            new_status=agent.status,
                            reason="ws_disconnect",
                        )
                    )
                    db.commit()
                    await ws_manager.broadcast_to_ui(
                        make_message(
                            "server.agent.status",
                            {
                                "uuid": agent.uuid,
                                "hostname": agent.hostname,
                                "status": "offline",
                                "ip_address": agent.ip_address,
                                "last_seen": now.isoformat(),
                                "comm_mode": "ws",
                            },
                        )
                    )
            finally:
                db.close()

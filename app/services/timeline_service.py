from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session


def _as_utc(dt_value):
    # Defensive parse: raw DB values may come as string/naive datetime.
    if dt_value is None:
        return None
    if isinstance(dt_value, str):
        s = dt_value.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        if " " in s and "T" not in s:
            s = s.replace(" ", "T", 1)
        try:
            dt_value = datetime.fromisoformat(s)
        except Exception:
            return None
    if isinstance(dt_value, datetime):
        if dt_value.tzinfo is None:
            return dt_value.replace(tzinfo=timezone.utc)
        return dt_value.astimezone(timezone.utc)
    return None


def get_agent_timeline(
    db: Session,
    agent_uuid: str,
    limit: int,
    offset: int,
) -> tuple[list[dict], int]:
    total_system = db.execute(
        text("SELECT COUNT(1) FROM agent_system_profile_history WHERE agent_uuid = :uuid"),
        {"uuid": agent_uuid},
    ).scalar() or 0
    total_identity = db.execute(
        text("SELECT COUNT(1) FROM agent_identity_history WHERE agent_uuid = :uuid"),
        {"uuid": agent_uuid},
    ).scalar() or 0
    total_status = db.execute(
        text("SELECT COUNT(1) FROM agent_status_history WHERE agent_uuid = :uuid"),
        {"uuid": agent_uuid},
    ).scalar() or 0
    total_tasks = db.execute(
        text("SELECT COUNT(1) FROM task_history WHERE agent_uuid = :uuid"),
        {"uuid": agent_uuid},
    ).scalar() or 0
    total_services = db.execute(
        text("SELECT COUNT(1) FROM agent_service_history WHERE agent_uuid = :uuid"),
        {"uuid": agent_uuid},
    ).scalar() or 0

    rows = db.execute(
        text(
            """
            SELECT 'system_profile' AS event_type,
                   detected_at,
                   id,
                   changed_fields_json,
                   diff_json,
                   profile_json,
                   NULL AS old_hostname,
                   NULL AS new_hostname,
                   NULL AS old_ip_address,
                   NULL AS new_ip_address,
                   NULL AS old_status,
                   NULL AS new_status,
                   NULL AS reason,
                   NULL AS task_action,
                   NULL AS task_status,
                   NULL AS app_name,
                   NULL AS message,
                   CAST(NULL AS INTEGER) AS exit_code,
                   NULL AS service_name,
                   NULL AS service_display_name,
                   NULL AS service_change_type,
                   NULL AS old_startup_type,
                   NULL AS new_startup_type
            FROM agent_system_profile_history
            WHERE agent_uuid = :uuid
            UNION ALL
            SELECT 'identity' AS event_type,
                   detected_at,
                   id,
                   NULL AS changed_fields_json,
                   NULL AS diff_json,
                   NULL AS profile_json,
                   old_hostname,
                   new_hostname,
                   old_ip_address,
                   new_ip_address,
                   NULL AS old_status,
                   NULL AS new_status,
                   NULL AS reason,
                   NULL AS task_action,
                   NULL AS task_status,
                   NULL AS app_name,
                   NULL AS message,
                   CAST(NULL AS INTEGER) AS exit_code,
                   NULL AS service_name,
                   NULL AS service_display_name,
                   NULL AS service_change_type,
                   NULL AS old_startup_type,
                   NULL AS new_startup_type
            FROM agent_identity_history
            WHERE agent_uuid = :uuid
            UNION ALL
            SELECT 'status' AS event_type,
                   detected_at,
                   id,
                   NULL AS changed_fields_json,
                   NULL AS diff_json,
                   NULL AS profile_json,
                   NULL AS old_hostname,
                   NULL AS new_hostname,
                   NULL AS old_ip_address,
                   NULL AS new_ip_address,
                   old_status,
                   new_status,
                   reason,
                   NULL AS task_action,
                   NULL AS task_status,
                   NULL AS app_name,
                   NULL AS message,
                   CAST(NULL AS INTEGER) AS exit_code,
                   NULL AS service_name,
                   NULL AS service_display_name,
                   NULL AS service_change_type,
                   NULL AS old_startup_type,
                   NULL AS new_startup_type
            FROM agent_status_history
            WHERE agent_uuid = :uuid
            UNION ALL
            SELECT 'task' AS event_type,
                   COALESCE(completed_at, started_at, created_at) AS detected_at,
                   id,
                   NULL AS changed_fields_json,
                   NULL AS diff_json,
                   NULL AS profile_json,
                   NULL AS old_hostname,
                   NULL AS new_hostname,
                   NULL AS old_ip_address,
                   NULL AS new_ip_address,
                   NULL AS old_status,
                   NULL AS new_status,
                   NULL AS reason,
                   action AS task_action,
                   status AS task_status,
                   (SELECT display_name FROM applications WHERE id = task_history.app_id) AS app_name,
                   message AS message,
                   exit_code AS exit_code,
                   NULL AS service_name,
                   NULL AS service_display_name,
                   NULL AS service_change_type,
                   NULL AS old_startup_type,
                   NULL AS new_startup_type
            FROM task_history
            WHERE agent_uuid = :uuid
            UNION ALL
            SELECT 'service' AS event_type,
                   detected_at,
                   id,
                   NULL AS changed_fields_json,
                   NULL AS diff_json,
                   NULL AS profile_json,
                   NULL AS old_hostname,
                   NULL AS new_hostname,
                   NULL AS old_ip_address,
                   NULL AS new_ip_address,
                   old_status,
                   new_status,
                   NULL AS reason,
                   NULL AS task_action,
                   NULL AS task_status,
                   NULL AS app_name,
                   NULL AS message,
                   CAST(NULL AS INTEGER) AS exit_code,
                   service_name,
                   display_name AS service_display_name,
                   change_type AS service_change_type,
                   old_startup_type,
                   new_startup_type
            FROM agent_service_history
            WHERE agent_uuid = :uuid
            ORDER BY detected_at DESC, id DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        {"uuid": agent_uuid, "limit": limit, "offset": offset},
    ).mappings().all()

    items: list[dict] = []
    for r in rows:
        detected_at = _as_utc(r["detected_at"])

        if r["event_type"] == "system_profile":
            changed_fields = []
            diff = []
            profile = None
            try:
                changed_fields = json.loads(r["changed_fields_json"] or "[]")
            except Exception:
                changed_fields = []
            try:
                diff = json.loads(r["diff_json"] or "[]")
            except Exception:
                diff = []
            try:
                profile = json.loads(r["profile_json"] or "null")
            except Exception:
                profile = None

            items.append(
                {
                    "event_type": "system_profile",
                    "detected_at": detected_at,
                    "changed_fields": changed_fields if isinstance(changed_fields, list) else [],
                    "diff": diff if isinstance(diff, list) else [],
                    "system_profile": profile if isinstance(profile, dict) else None,
                }
            )
        else:
            if r["event_type"] == "identity":
                items.append(
                    {
                        "event_type": "identity",
                        "detected_at": detected_at,
                        "old_hostname": r["old_hostname"],
                        "new_hostname": r["new_hostname"],
                        "old_ip_address": r["old_ip_address"],
                        "new_ip_address": r["new_ip_address"],
                    }
                )
            elif r["event_type"] == "status":
                items.append(
                    {
                        "event_type": "status",
                        "detected_at": detected_at,
                        "old_status": r["old_status"],
                        "new_status": r["new_status"],
                        "reason": r["reason"],
                    }
                )
            elif r["event_type"] == "task":
                items.append(
                    {
                        "event_type": "task",
                        "detected_at": detected_at,
                        "task_action": r["task_action"],
                        "task_status": r["task_status"],
                        "app_name": r["app_name"],
                        "message": r["message"],
                        "exit_code": r["exit_code"],
                    }
                )
            else:
                items.append(
                    {
                        "event_type": "service",
                        "detected_at": detected_at,
                        "service_name": r["service_name"],
                        "service_display_name": r["service_display_name"],
                        "service_change_type": r["service_change_type"],
                        "old_status": r["old_status"],
                        "new_status": r["new_status"],
                        "old_startup_type": r["old_startup_type"],
                        "new_startup_type": r["new_startup_type"],
                    }
                )

    return items, int(total_system) + int(total_identity) + int(total_status) + int(total_tasks) + int(total_services)

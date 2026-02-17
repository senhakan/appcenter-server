from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session


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
                   NULL AS new_ip_address
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
                   new_ip_address
            FROM agent_identity_history
            WHERE agent_uuid = :uuid
            ORDER BY detected_at DESC, id DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        {"uuid": agent_uuid, "limit": limit, "offset": offset},
    ).mappings().all()

    items: list[dict] = []
    for r in rows:
        detected_at = r["detected_at"]
        if isinstance(detected_at, str):
            # sqlite may return ISO string depending on driver.
            try:
                detected_at = datetime.fromisoformat(detected_at)
            except Exception:
                detected_at = None

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

    return items, int(total_system) + int(total_identity)


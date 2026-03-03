from __future__ import annotations

import fnmatch
import json
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Agent, AgentGroup, Group


MAX_PREVIEW_ITEMS = 5


def _sanitize_patterns(values: Optional[list[str]]) -> list[str]:
    out: list[str] = []
    for raw in values or []:
        item = (raw or "").strip()
        if not item:
            continue
        if item not in out:
            out.append(item)
    return out


def normalize_rules(rules: Optional[dict]) -> Optional[dict]:
    if not isinstance(rules, dict):
        return None
    hostname_patterns = _sanitize_patterns(rules.get("hostname_patterns") if isinstance(rules.get("hostname_patterns"), list) else [])
    ip_patterns = _sanitize_patterns(rules.get("ip_patterns") if isinstance(rules.get("ip_patterns"), list) else [])
    if not hostname_patterns and not ip_patterns:
        return None
    return {
        "hostname_patterns": hostname_patterns,
        "ip_patterns": ip_patterns,
    }


def _matches_any(patterns: list[str], value: Optional[str]) -> bool:
    if not patterns:
        return True
    src = (value or "").strip().lower()
    if not src:
        return False
    for p in patterns:
        if fnmatch.fnmatch(src, p.strip().lower()):
            return True
    return False


def agent_matches_rules(agent: Agent, rules: Optional[dict]) -> bool:
    normalized = normalize_rules(rules)
    if not normalized:
        return False
    hostname_ok = _matches_any(normalized.get("hostname_patterns") or [], agent.hostname)
    ip_ok = _matches_any(normalized.get("ip_patterns") or [], agent.ip_address)
    return hostname_ok and ip_ok


def _sync_agent_primary_group_id(db: Session, agent_uuid: str) -> None:
    agent = db.query(Agent).filter(Agent.uuid == agent_uuid).first()
    if not agent:
        return
    group_ids = sorted(
        {
            row.group_id
            for row in db.query(AgentGroup)
            .filter(AgentGroup.agent_uuid == agent_uuid)
            .all()
        }
    )
    agent.group_id = group_ids[0] if group_ids else None
    db.add(agent)


def apply_dynamic_groups_for_all_agents(db: Session) -> dict:
    dynamic_groups = (
        db.query(Group)
        .filter(Group.is_dynamic.is_(True), Group.is_active.is_(True))
        .all()
    )
    dynamic_ids = {g.id for g in dynamic_groups}

    agents = db.query(Agent).all()
    added = 0
    removed = 0

    for agent in agents:
        expected = {
            g.id
            for g in dynamic_groups
            if agent_matches_rules(agent, g.dynamic_rules)
        }
        current_rows = (
            db.query(AgentGroup)
            .filter(AgentGroup.agent_uuid == agent.uuid, AgentGroup.group_id.in_(dynamic_ids) if dynamic_ids else False)
            .all()
            if dynamic_ids
            else []
        )
        current = {r.group_id for r in current_rows}

        to_remove = current - expected
        to_add = expected - current

        if to_remove:
            db.query(AgentGroup).filter(
                AgentGroup.agent_uuid == agent.uuid,
                AgentGroup.group_id.in_(to_remove),
            ).delete(synchronize_session=False)
            removed += len(to_remove)

        for gid in to_add:
            db.add(AgentGroup(agent_uuid=agent.uuid, group_id=gid))
        added += len(to_add)

        if to_remove or to_add:
            _sync_agent_primary_group_id(db, agent.uuid)

    return {
        "dynamic_group_count": len(dynamic_groups),
        "agent_count": len(agents),
        "added": added,
        "removed": removed,
    }


def apply_dynamic_group_membership_for_group(db: Session, group: Group) -> dict:
    if not group.is_dynamic or not group.is_active:
        return {"added": 0, "removed": 0}
    result = apply_dynamic_groups_for_all_agents(db)
    return {"added": result.get("added", 0), "removed": result.get("removed", 0)}


def preview_agents(db: Session, rules: Optional[dict], limit: int = MAX_PREVIEW_ITEMS) -> dict:
    normalized = normalize_rules(rules)
    if not normalized:
        return {"total": 0, "items": []}

    all_agents = db.query(Agent).order_by(Agent.hostname.asc()).all()
    matched = [a for a in all_agents if agent_matches_rules(a, normalized)]
    sample = matched[: max(1, min(int(limit or MAX_PREVIEW_ITEMS), 20))]
    items = [
        {
            "uuid": a.uuid,
            "hostname": a.hostname,
            "ip_address": a.ip_address,
            "status": a.status,
        }
        for a in sample
    ]
    return {"total": len(matched), "items": items}


def rules_to_json(rules: Optional[dict]) -> Optional[str]:
    normalized = normalize_rules(rules)
    if not normalized:
        return None
    return json.dumps(normalized, ensure_ascii=True)

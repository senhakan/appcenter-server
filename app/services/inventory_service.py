from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unicodedata
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    Agent,
    AgentSoftwareInventory,
    SoftwareChangeHistory,
    SoftwareLicense,
    SoftwareNormalizationRule,
)


# --- Normalization helpers ---


def _apply_normalization(db: Session, software_name: str) -> Optional[str]:
    rules = (
        db.query(SoftwareNormalizationRule)
        .filter(SoftwareNormalizationRule.is_active.is_(True))
        .order_by(SoftwareNormalizationRule.id.asc())
        .all()
    )
    lower_name = _canon_key(software_name)
    for rule in rules:
        pattern_lower = _canon_key(rule.pattern)
        if rule.match_type == "exact" and lower_name == pattern_lower:
            return rule.normalized_name
        if rule.match_type == "contains" and pattern_lower in lower_name:
            return rule.normalized_name
        if rule.match_type == "starts_with" and lower_name.startswith(pattern_lower):
            return rule.normalized_name
    return None


# Basic cleanup: fixes issues like trailing spaces and NBSPs that cause duplicate rows/diffs.
def _clean_display_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    # NFKC also normalizes odd width/compatibility chars coming from registry entries.
    value = unicodedata.normalize("NFKC", value)
    value = value.replace("\u00A0", " ")  # NBSP
    # Collapse all whitespace runs to a single ASCII space and trim.
    value = " ".join(value.split())
    return value


def _canon_key(value: str) -> str:
    # Stable, case-insensitive compare key for diffs + rule matching.
    cleaned = _clean_display_text(value) or ""
    return cleaned.casefold()


# --- Inventory submission ---


def _compute_diff(
    old_dict: dict[str, AgentSoftwareInventory],
    new_items: list,
) -> list[dict]:
    changes: list[dict] = []
    new_dict: dict[str, object] = {}
    for item in new_items:
        name = item.name if hasattr(item, "name") else item["name"]
        name = _clean_display_text(name) or ""
        version = item.version if hasattr(item, "version") else item.get("version")
        publisher = item.publisher if hasattr(item, "publisher") else item.get("publisher")
        publisher = _clean_display_text(publisher)
        new_dict[_canon_key(name)] = {"name": name, "version": version, "publisher": publisher}

    for key, info in new_dict.items():
        if key not in old_dict:
            changes.append({
                "software_name": info["name"],
                "software_version": info["version"],
                "publisher": info["publisher"],
                "change_type": "installed",
            })
        else:
            old_ver = old_dict[key].software_version
            new_ver = info["version"]
            if old_ver != new_ver:
                changes.append({
                    "software_name": info["name"],
                    "software_version": new_ver,
                    "publisher": info["publisher"],
                    "previous_version": old_ver,
                    "change_type": "updated",
                })

    for key, old_row in old_dict.items():
        if key not in new_dict:
            changes.append({
                "software_name": _clean_display_text(old_row.software_name) or old_row.software_name,
                "software_version": old_row.software_version,
                "publisher": _clean_display_text(old_row.publisher) or old_row.publisher,
                "change_type": "removed",
            })

    return changes


def submit_inventory(
    db: Session,
    agent_uuid: str,
    inventory_hash: str,
    items: list,
) -> dict:
    existing = (
        db.query(AgentSoftwareInventory)
        .filter(AgentSoftwareInventory.agent_uuid == agent_uuid)
        .all()
    )
    old_dict = {_canon_key(row.software_name or ""): row for row in existing}
    is_first = len(existing) == 0

    counts = {"installed": 0, "removed": 0, "updated": 0}

    if not is_first:
        diff = _compute_diff(old_dict, items)
        now = datetime.now(timezone.utc)
        for ch in diff:
            db.add(SoftwareChangeHistory(
                agent_uuid=agent_uuid,
                software_name=ch["software_name"],
                software_version=ch.get("software_version"),
                publisher=ch.get("publisher"),
                previous_version=ch.get("previous_version"),
                change_type=ch["change_type"],
                detected_at=now,
            ))
            counts[ch["change_type"]] += 1

    db.query(AgentSoftwareInventory).filter(
        AgentSoftwareInventory.agent_uuid == agent_uuid
    ).delete()

    for item in items:
        name = item.name if hasattr(item, "name") else item["name"]
        name = _clean_display_text(name) or ""
        db.add(AgentSoftwareInventory(
            agent_uuid=agent_uuid,
            software_name=name,
            software_version=item.version if hasattr(item, "version") else item.get("version"),
            publisher=_clean_display_text(item.publisher if hasattr(item, "publisher") else item.get("publisher")),
            install_date=item.install_date if hasattr(item, "install_date") else item.get("install_date"),
            estimated_size_kb=item.estimated_size_kb if hasattr(item, "estimated_size_kb") else item.get("estimated_size_kb"),
            architecture=item.architecture if hasattr(item, "architecture") else item.get("architecture"),
            normalized_name=_apply_normalization(db, name) or name,
        ))

    agent = db.query(Agent).filter(Agent.uuid == agent_uuid).first()
    if agent:
        agent.inventory_hash = inventory_hash
        agent.inventory_updated_at = datetime.now(timezone.utc)
        agent.software_count = len(items)
        db.add(agent)

    db.commit()
    return counts


def check_inventory_hash(db: Session, agent_uuid: str, inventory_hash: str) -> bool:
    agent = db.query(Agent).filter(Agent.uuid == agent_uuid).first()
    if not agent or agent.inventory_hash is None:
        return True
    return agent.inventory_hash != inventory_hash


# --- Queries ---


def get_agent_inventory(db: Session, agent_uuid: str) -> list[AgentSoftwareInventory]:
    return (
        db.query(AgentSoftwareInventory)
        .filter(AgentSoftwareInventory.agent_uuid == agent_uuid)
        .order_by(AgentSoftwareInventory.software_name.asc())
        .all()
    )


def get_agent_change_history(
    db: Session,
    agent_uuid: str,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[SoftwareChangeHistory], int]:
    q = db.query(SoftwareChangeHistory).filter(
        SoftwareChangeHistory.agent_uuid == agent_uuid
    )
    total = q.count()
    items = (
        q.order_by(SoftwareChangeHistory.detected_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return items, total


def get_software_summary(
    db: Session,
    search: str = "",
    page: int = 1,
    per_page: int = 50,
) -> tuple[list[dict], int]:
    name_col = func.coalesce(
        AgentSoftwareInventory.normalized_name,
        AgentSoftwareInventory.software_name,
    )
    q = db.query(
        name_col.label("name"),
        func.count(func.distinct(AgentSoftwareInventory.agent_uuid)).label("agent_count"),
        func.group_concat(func.distinct(AgentSoftwareInventory.software_version)).label("versions"),
    ).group_by(name_col)

    if search:
        q = q.having(name_col.ilike(f"%{search}%"))

    total = q.count()
    rows = q.order_by(name_col.asc()).offset((page - 1) * per_page).limit(per_page).all()

    items = []
    for row in rows:
        versions = [v for v in (row.versions or "").split(",") if v] if row.versions else []
        items.append({
            "name": row.name,
            "agent_count": row.agent_count,
            "versions": versions,
        })
    return items, total


def get_software_agents(db: Session, software_name: str) -> list[dict]:
    rows = (
        db.query(AgentSoftwareInventory, Agent)
        .join(Agent, Agent.uuid == AgentSoftwareInventory.agent_uuid)
        .filter(
            (AgentSoftwareInventory.software_name == software_name)
            | (AgentSoftwareInventory.normalized_name == software_name)
        )
        .order_by(Agent.hostname.asc())
        .all()
    )
    return [
        {
            "agent_uuid": inv.agent_uuid,
            "hostname": agent.hostname,
            "software_version": inv.software_version,
            "status": agent.status,
        }
        for inv, agent in rows
    ]


def get_inventory_dashboard_stats(db: Session) -> dict:
    name_col = func.coalesce(
        AgentSoftwareInventory.normalized_name,
        AgentSoftwareInventory.software_name,
    )
    total_unique = db.query(func.count(func.distinct(name_col))).select_from(AgentSoftwareInventory).scalar() or 0
    agents_with_inv = (
        db.query(func.count(func.distinct(AgentSoftwareInventory.agent_uuid)))
        .select_from(AgentSoftwareInventory)
        .scalar() or 0
    )

    report = get_license_usage_report(db)
    violations = sum(1 for r in report if r["is_violation"] and r["license_type"] == "licensed")
    prohibited = sum(1 for r in report if r["is_violation"] and r["license_type"] == "prohibited")
    day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    added_today = (
        db.query(func.count(SoftwareChangeHistory.id))
        .filter(
            SoftwareChangeHistory.change_type == "installed",
            SoftwareChangeHistory.detected_at >= day_start,
            SoftwareChangeHistory.detected_at < day_end,
        )
        .scalar() or 0
    )
    removed_today = (
        db.query(func.count(SoftwareChangeHistory.id))
        .filter(
            SoftwareChangeHistory.change_type == "removed",
            SoftwareChangeHistory.detected_at >= day_start,
            SoftwareChangeHistory.detected_at < day_end,
        )
        .scalar() or 0
    )

    return {
        "total_unique_software": total_unique,
        "license_violations": violations,
        "prohibited_alerts": prohibited,
        "agents_with_inventory": agents_with_inv,
        "added_today": added_today,
        "removed_today": removed_today,
    }


# --- Normalization rules ---


def list_normalization_rules(db: Session) -> list[SoftwareNormalizationRule]:
    return db.query(SoftwareNormalizationRule).order_by(SoftwareNormalizationRule.id.asc()).all()


def create_normalization_rule(
    db: Session,
    pattern: str,
    normalized_name: str,
    match_type: str = "contains",
) -> SoftwareNormalizationRule:
    rule = SoftwareNormalizationRule(
        pattern=pattern,
        normalized_name=normalized_name,
        match_type=match_type,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    reapply_normalization_rules(db)
    return rule


def update_normalization_rule(
    db: Session,
    rule_id: int,
    **kwargs,
) -> Optional[SoftwareNormalizationRule]:
    rule = db.query(SoftwareNormalizationRule).filter(SoftwareNormalizationRule.id == rule_id).first()
    if not rule:
        return None
    for k, v in kwargs.items():
        if v is not None and hasattr(rule, k):
            setattr(rule, k, v)
    db.commit()
    db.refresh(rule)
    reapply_normalization_rules(db)
    return rule


def delete_normalization_rule(db: Session, rule_id: int) -> bool:
    rule = db.query(SoftwareNormalizationRule).filter(SoftwareNormalizationRule.id == rule_id).first()
    if not rule:
        return False
    db.delete(rule)
    db.commit()
    reapply_normalization_rules(db)
    return True


def reapply_normalization_rules(db: Session) -> int:
    all_inv = db.query(AgentSoftwareInventory).all()
    count = 0
    for inv in all_inv:
        cleaned_name = _clean_display_text(inv.software_name) or inv.software_name
        # Keep stored name tidy as well (e.g. trailing spaces / NBSP from registry entries).
        if inv.software_name != cleaned_name:
            inv.software_name = cleaned_name
            count += 1
        new_norm = _apply_normalization(db, cleaned_name) or cleaned_name
        if inv.normalized_name != new_norm:
            inv.normalized_name = new_norm
            count += 1
    db.commit()
    return count


# --- Licenses ---


def list_licenses(db: Session) -> list[SoftwareLicense]:
    return db.query(SoftwareLicense).order_by(SoftwareLicense.id.asc()).all()


def get_license(db: Session, license_id: int) -> Optional[SoftwareLicense]:
    return db.query(SoftwareLicense).filter(SoftwareLicense.id == license_id).first()


def create_license(db: Session, **kwargs) -> SoftwareLicense:
    lic = SoftwareLicense(**kwargs)
    db.add(lic)
    db.commit()
    db.refresh(lic)
    return lic


def update_license(db: Session, license_id: int, **kwargs) -> Optional[SoftwareLicense]:
    lic = db.query(SoftwareLicense).filter(SoftwareLicense.id == license_id).first()
    if not lic:
        return None
    for k, v in kwargs.items():
        if v is not None and hasattr(lic, k):
            setattr(lic, k, v)
    db.commit()
    db.refresh(lic)
    return lic


def delete_license(db: Session, license_id: int) -> bool:
    lic = db.query(SoftwareLicense).filter(SoftwareLicense.id == license_id).first()
    if not lic:
        return False
    db.delete(lic)
    db.commit()
    return True


def _match_software_count(db: Session, pattern: str, match_type: str) -> int:
    q = db.query(func.count(func.distinct(AgentSoftwareInventory.agent_uuid))).select_from(AgentSoftwareInventory)
    name_col = func.coalesce(
        AgentSoftwareInventory.normalized_name,
        AgentSoftwareInventory.software_name,
    )
    if match_type == "exact":
        q = q.filter(name_col == pattern)
    elif match_type == "starts_with":
        q = q.filter(name_col.ilike(f"{pattern}%"))
    else:
        q = q.filter(name_col.ilike(f"%{pattern}%"))
    return q.scalar() or 0


def get_license_usage_report(db: Session) -> list[dict]:
    licenses = db.query(SoftwareLicense).filter(SoftwareLicense.is_active.is_(True)).all()
    result = []
    for lic in licenses:
        usage = _match_software_count(db, lic.software_name_pattern, lic.match_type)
        surplus = lic.total_licenses - usage
        is_violation = (
            (lic.license_type == "prohibited" and usage > 0)
            or (lic.license_type == "licensed" and surplus < 0)
        )
        result.append({
            "license_id": lic.id,
            "pattern": lic.software_name_pattern,
            "license_type": lic.license_type,
            "total_licenses": lic.total_licenses,
            "usage": usage,
            "surplus": surplus,
            "is_violation": is_violation,
        })
    return result


# --- Cleanup ---


def cleanup_old_change_history(db: Session, retention_days: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    count = db.query(SoftwareChangeHistory).filter(
        SoftwareChangeHistory.detected_at < cutoff
    ).delete()
    db.commit()
    return count

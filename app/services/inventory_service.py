from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
import re
import unicodedata
from typing import Optional

from sqlalchemy import String, case, cast, func
from sqlalchemy.orm import Session

from app.models import (
    Agent,
    AgentSoftwareInventory,
    SamComplianceFinding,
    SamCostProfile,
    SamLifecyclePolicy,
    SamReportSchedule,
    SoftwareChangeHistory,
    SoftwareLicense,
    SoftwareNormalizationRule,
)


# --- Normalization helpers ---

_TRAILING_VERSION_RE = re.compile(
    r"^(?P<base>.+?)\s+v?(?P<ver>\d+\.\d+(?:\.\d+){0,6})\s*$",
    re.IGNORECASE,
)


def _strip_trailing_version_name(software_name: str) -> Optional[str]:
    """
    Generic fallback normalizer for names like:
    - "Advanced IP Scanner 2.5"
    - "Advanced IP Scanner 2.5.1"
    - "Tool v1.2.3"

    We intentionally require at least one dot in version token to avoid
    collapsing names that end with a year-like token (e.g. "Office 2021").
    """
    m = _TRAILING_VERSION_RE.match((software_name or "").strip())
    if not m:
        return None
    base = _clean_display_text(m.group("base")) or ""
    base = re.sub(r"[\s\-_:./]+$", "", base).strip()
    if len(base) < 3:
        return None
    if not any(ch.isalpha() for ch in base):
        return None
    return base


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
    generic = _strip_trailing_version_name(software_name)
    if generic:
        return generic
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
    versions_agg = func.string_agg(
        func.distinct(cast(AgentSoftwareInventory.software_version, String)),
        ",",
    )

    q = db.query(
        name_col.label("name"),
        func.count(func.distinct(AgentSoftwareInventory.agent_uuid)).label("agent_count"),
        versions_agg.label("versions"),
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


def get_sam_dashboard(db: Session) -> dict:
    name_col = func.coalesce(
        AgentSoftwareInventory.normalized_name,
        AgentSoftwareInventory.software_name,
    )
    total_agents = db.query(func.count(Agent.uuid)).scalar() or 0
    agents_with_inventory = (
        db.query(func.count(func.distinct(AgentSoftwareInventory.agent_uuid)))
        .select_from(AgentSoftwareInventory)
        .scalar()
        or 0
    )
    unique_raw = (
        db.query(func.count(func.distinct(AgentSoftwareInventory.software_name)))
        .select_from(AgentSoftwareInventory)
        .scalar()
        or 0
    )
    unique_normalized = (
        db.query(func.count(func.distinct(name_col)))
        .select_from(AgentSoftwareInventory)
        .scalar()
        or 0
    )
    normalized_rows = (
        db.query(func.count(AgentSoftwareInventory.id))
        .filter(AgentSoftwareInventory.normalized_name.is_not(None))
        .filter(AgentSoftwareInventory.normalized_name != AgentSoftwareInventory.software_name)
        .scalar()
        or 0
    )

    now = datetime.now(timezone.utc)
    since_24h = now - timedelta(hours=24)

    platform_items: list[dict] = []
    for platform in ("windows", "linux"):
        total_agents_p = (
            db.query(func.count(Agent.uuid))
            .filter(func.lower(Agent.platform) == platform)
            .scalar()
            or 0
        )
        inv_agents_p = (
            db.query(func.count(func.distinct(AgentSoftwareInventory.agent_uuid)))
            .join(Agent, Agent.uuid == AgentSoftwareInventory.agent_uuid)
            .filter(func.lower(Agent.platform) == platform)
            .scalar()
            or 0
        )
        unique_sw_p = (
            db.query(func.count(func.distinct(name_col)))
            .join(Agent, Agent.uuid == AgentSoftwareInventory.agent_uuid)
            .filter(func.lower(Agent.platform) == platform)
            .scalar()
            or 0
        )
        install_rows_p = (
            db.query(func.count(AgentSoftwareInventory.id))
            .join(Agent, Agent.uuid == AgentSoftwareInventory.agent_uuid)
            .filter(func.lower(Agent.platform) == platform)
            .scalar()
            or 0
        )
        changes_q = (
            db.query(
                SoftwareChangeHistory.change_type,
                func.count(SoftwareChangeHistory.id),
            )
            .join(Agent, Agent.uuid == SoftwareChangeHistory.agent_uuid)
            .filter(
                func.lower(Agent.platform) == platform,
                SoftwareChangeHistory.detected_at >= since_24h,
            )
            .group_by(SoftwareChangeHistory.change_type)
            .all()
        )
        counts = {"installed": 0, "removed": 0, "updated": 0}
        for change_type, count_value in changes_q:
            key = (change_type or "").strip().lower()
            if key in counts:
                counts[key] = int(count_value or 0)
        platform_items.append(
            {
                "platform": platform,
                "total_agents": int(total_agents_p),
                "agents_with_inventory": int(inv_agents_p),
                "unique_software": int(unique_sw_p),
                "install_rows": int(install_rows_p),
                "added_24h": int(counts["installed"]),
                "removed_24h": int(counts["removed"]),
                "updated_24h": int(counts["updated"]),
            }
        )

    top_software: list[dict] = []
    for platform in ("windows", "linux"):
        rows = (
            db.query(
                name_col.label("name"),
                func.count(func.distinct(AgentSoftwareInventory.agent_uuid)).label("agent_count"),
            )
            .join(Agent, Agent.uuid == AgentSoftwareInventory.agent_uuid)
            .filter(func.lower(Agent.platform) == platform)
            .group_by(name_col)
            .order_by(func.count(func.distinct(AgentSoftwareInventory.agent_uuid)).desc(), name_col.asc())
            .limit(5)
            .all()
        )
        top_software.extend(
            {
                "name": row.name,
                "platform": platform,
                "agent_count": int(row.agent_count or 0),
            }
            for row in rows
        )

    return {
        "total_agents": int(total_agents),
        "agents_with_inventory": int(agents_with_inventory),
        "unique_software": int(unique_raw),
        "normalized_unique_software": int(unique_normalized),
        "normalized_rows": int(normalized_rows),
        "platform_items": platform_items,
        "top_software": top_software,
    }


def get_sam_catalog(
    db: Session,
    *,
    search: str = "",
    platform: str = "all",
    page: int = 1,
    per_page: int = 50,
) -> tuple[list[dict], int]:
    safe_platform = (platform or "all").strip().lower()
    if safe_platform not in {"all", "windows", "linux"}:
        safe_platform = "all"

    name_col = func.coalesce(
        AgentSoftwareInventory.normalized_name,
        AgentSoftwareInventory.software_name,
    )
    versions_agg = func.string_agg(
        func.distinct(cast(AgentSoftwareInventory.software_version, String)),
        ",",
    )
    q = (
        db.query(
            name_col.label("name"),
            func.count(func.distinct(AgentSoftwareInventory.agent_uuid)).label("total_agents"),
            func.count(
                func.distinct(
                    case(
                        (func.lower(Agent.platform) == "windows", AgentSoftwareInventory.agent_uuid),
                        else_=None,
                    )
                )
            ).label("windows_agents"),
            func.count(
                func.distinct(
                    case(
                        (func.lower(Agent.platform) == "linux", AgentSoftwareInventory.agent_uuid),
                        else_=None,
                    )
                )
            ).label("linux_agents"),
            func.count(AgentSoftwareInventory.id).label("install_rows"),
            versions_agg.label("versions"),
        )
        .join(Agent, Agent.uuid == AgentSoftwareInventory.agent_uuid)
        .group_by(name_col)
    )
    if safe_platform in {"windows", "linux"}:
        q = q.filter(func.lower(Agent.platform) == safe_platform)
    if search:
        q = q.having(name_col.ilike(f"%{search}%"))

    total = q.count()
    rows = (
        q.order_by(func.count(func.distinct(AgentSoftwareInventory.agent_uuid)).desc(), name_col.asc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    items: list[dict] = []
    for row in rows:
        versions = [v for v in (row.versions or "").split(",") if v] if row.versions else []
        items.append(
            {
                "name": row.name,
                "total_agents": int(row.total_agents or 0),
                "windows_agents": int(row.windows_agents or 0),
                "linux_agents": int(row.linux_agents or 0),
                "install_rows": int(row.install_rows or 0),
                "versions": versions,
            }
        )
    return items, total


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


def _match_software_count_by_platform(db: Session, pattern: str, match_type: str, platform: str) -> int:
    q = (
        db.query(func.count(func.distinct(AgentSoftwareInventory.agent_uuid)))
        .select_from(AgentSoftwareInventory)
        .join(Agent, Agent.uuid == AgentSoftwareInventory.agent_uuid)
        .filter(func.lower(Agent.platform) == (platform or "").lower())
    )
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


# --- SAM compliance findings ---


def sync_sam_compliance_findings(db: Session) -> dict:
    now = datetime.now(timezone.utc)
    active_keys: set[tuple[str, str, str]] = set()
    created = 0
    updated = 0
    closed = 0

    licenses = db.query(SoftwareLicense).filter(SoftwareLicense.is_active.is_(True)).all()
    for lic in licenses:
        for platform in ("windows", "linux"):
            usage = _match_software_count_by_platform(db, lic.software_name_pattern, lic.match_type, platform)
            if usage <= 0:
                continue
            if lic.license_type == "prohibited":
                finding_type = "prohibited"
                severity = "critical"
            else:
                if usage <= int(lic.total_licenses or 0):
                    continue
                finding_type = "overuse"
                severity = "high"
            key = (lic.software_name_pattern, platform, finding_type)
            active_keys.add(key)
            finding = (
                db.query(SamComplianceFinding)
                .filter(
                    SamComplianceFinding.software_name == lic.software_name_pattern,
                    SamComplianceFinding.platform == platform,
                    SamComplianceFinding.finding_type == finding_type,
                )
                .first()
            )
            payload = {
                "license_id": lic.id,
                "license_type": lic.license_type,
                "match_type": lic.match_type,
                "total_licenses": int(lic.total_licenses or 0),
                "usage": int(usage),
                "surplus": int((lic.total_licenses or 0) - usage),
            }
            if not finding:
                finding = SamComplianceFinding(
                    software_name=lic.software_name_pattern,
                    platform=platform,
                    finding_type=finding_type,
                    severity=severity,
                    status="new",
                    affected_agents=int(usage),
                    details_json=json.dumps(payload, ensure_ascii=True),
                    first_seen_at=now,
                    last_seen_at=now,
                    resolved_at=None,
                )
                db.add(finding)
                created += 1
            else:
                finding.severity = severity
                finding.affected_agents = int(usage)
                finding.details_json = json.dumps(payload, ensure_ascii=True)
                finding.last_seen_at = now
                finding.resolved_at = None
                if finding.status == "closed":
                    finding.status = "new"
                db.add(finding)
                updated += 1

    open_items = (
        db.query(SamComplianceFinding)
        .filter(SamComplianceFinding.status != "closed")
        .all()
    )
    for item in open_items:
        key = (item.software_name, item.platform, item.finding_type)
        if key in active_keys:
            continue
        item.status = "closed"
        item.resolved_at = now
        item.updated_at = now
        db.add(item)
        closed += 1

    db.commit()
    return {"created": created, "updated": updated, "closed": closed}


def list_sam_compliance_findings(
    db: Session,
    *,
    status: str = "all",
    platform: str = "all",
    search: str = "",
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[SamComplianceFinding], int]:
    q = db.query(SamComplianceFinding)
    safe_status = (status or "all").strip().lower()
    if safe_status != "all":
        q = q.filter(func.lower(SamComplianceFinding.status) == safe_status)
    safe_platform = (platform or "all").strip().lower()
    if safe_platform != "all":
        q = q.filter(func.lower(SamComplianceFinding.platform) == safe_platform)
    if search:
        q = q.filter(SamComplianceFinding.software_name.ilike(f"%{search}%"))
    total = q.count()
    items = (
        q.order_by(
            SamComplianceFinding.status.asc(),
            SamComplianceFinding.severity.desc(),
            SamComplianceFinding.last_seen_at.desc(),
            SamComplianceFinding.id.desc(),
        )
        .offset(max(int(offset), 0))
        .limit(min(max(int(limit), 1), 500))
        .all()
    )
    return items, total


def update_sam_finding_status(db: Session, finding_id: int, status: str) -> Optional[SamComplianceFinding]:
    finding = db.query(SamComplianceFinding).filter(SamComplianceFinding.id == finding_id).first()
    if not finding:
        return None
    finding.status = (status or "").strip().lower()
    if finding.status == "closed":
        finding.resolved_at = datetime.now(timezone.utc)
    else:
        finding.resolved_at = None
    db.add(finding)
    db.commit()
    db.refresh(finding)
    return finding


# --- SAM report schedules ---


def list_sam_report_schedules(db: Session) -> list[SamReportSchedule]:
    return db.query(SamReportSchedule).order_by(SamReportSchedule.id.desc()).all()


def create_sam_report_schedule(db: Session, **kwargs) -> SamReportSchedule:
    item = SamReportSchedule(**kwargs)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def update_sam_report_schedule(db: Session, schedule_id: int, **kwargs) -> Optional[SamReportSchedule]:
    item = db.query(SamReportSchedule).filter(SamReportSchedule.id == schedule_id).first()
    if not item:
        return None
    for k, v in kwargs.items():
        if v is not None and hasattr(item, k):
            setattr(item, k, v)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def delete_sam_report_schedule(db: Session, schedule_id: int) -> bool:
    item = db.query(SamReportSchedule).filter(SamReportSchedule.id == schedule_id).first()
    if not item:
        return False
    db.delete(item)
    db.commit()
    return True


# --- SAM lifecycle/cost and risk overview ---


def _sam_pattern_matches(software_name: str, pattern: str, match_type: str) -> bool:
    left = _canon_key(software_name or "")
    right = _canon_key(pattern or "")
    if not right:
        return False
    if match_type == "exact":
        return left == right
    if match_type == "starts_with":
        return left.startswith(right)
    return right in left


def _sam_platform_matches(row_platform: str, policy_platform: str) -> bool:
    rule_platform = (policy_platform or "all").strip().lower()
    item_platform = (row_platform or "").strip().lower()
    return rule_platform == "all" or rule_platform == item_platform


def _sam_match_rank(match_type: str, pattern: str) -> tuple[int, int]:
    # exact > starts_with > contains, then longer pattern wins.
    rank = {"exact": 3, "starts_with": 2, "contains": 1}.get((match_type or "").strip().lower(), 0)
    return rank, len((pattern or "").strip())


def _pick_best_sam_lifecycle(
    software_name: str,
    platform: str,
    policies: list[SamLifecyclePolicy],
) -> Optional[SamLifecyclePolicy]:
    best: Optional[SamLifecyclePolicy] = None
    best_rank: tuple[int, int] = (0, 0)
    for item in policies:
        if not _sam_platform_matches(platform, item.platform):
            continue
        if not _sam_pattern_matches(software_name, item.software_name_pattern, item.match_type):
            continue
        candidate_rank = _sam_match_rank(item.match_type, item.software_name_pattern)
        if candidate_rank > best_rank:
            best = item
            best_rank = candidate_rank
    return best


def _pick_best_sam_cost(
    software_name: str,
    platform: str,
    profiles: list[SamCostProfile],
) -> Optional[SamCostProfile]:
    best: Optional[SamCostProfile] = None
    best_rank: tuple[int, int] = (0, 0)
    for item in profiles:
        if not _sam_platform_matches(platform, item.platform):
            continue
        if not _sam_pattern_matches(software_name, item.software_name_pattern, item.match_type):
            continue
        candidate_rank = _sam_match_rank(item.match_type, item.software_name_pattern)
        if candidate_rank > best_rank:
            best = item
            best_rank = candidate_rank
    return best


def list_sam_lifecycle_policies(db: Session) -> list[SamLifecyclePolicy]:
    return db.query(SamLifecyclePolicy).order_by(SamLifecyclePolicy.id.desc()).all()


def create_sam_lifecycle_policy(db: Session, **kwargs) -> SamLifecyclePolicy:
    item = SamLifecyclePolicy(**kwargs)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def update_sam_lifecycle_policy(db: Session, policy_id: int, **kwargs) -> Optional[SamLifecyclePolicy]:
    item = db.query(SamLifecyclePolicy).filter(SamLifecyclePolicy.id == policy_id).first()
    if not item:
        return None
    for k, v in kwargs.items():
        if v is not None and hasattr(item, k):
            setattr(item, k, v)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def delete_sam_lifecycle_policy(db: Session, policy_id: int) -> bool:
    item = db.query(SamLifecyclePolicy).filter(SamLifecyclePolicy.id == policy_id).first()
    if not item:
        return False
    db.delete(item)
    db.commit()
    return True


def list_sam_cost_profiles(db: Session) -> list[SamCostProfile]:
    return db.query(SamCostProfile).order_by(SamCostProfile.id.desc()).all()


def create_sam_cost_profile(db: Session, **kwargs) -> SamCostProfile:
    item = SamCostProfile(**kwargs)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def update_sam_cost_profile(db: Session, profile_id: int, **kwargs) -> Optional[SamCostProfile]:
    item = db.query(SamCostProfile).filter(SamCostProfile.id == profile_id).first()
    if not item:
        return None
    for k, v in kwargs.items():
        if v is not None and hasattr(item, k):
            setattr(item, k, v)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def delete_sam_cost_profile(db: Session, profile_id: int) -> bool:
    item = db.query(SamCostProfile).filter(SamCostProfile.id == profile_id).first()
    if not item:
        return False
    db.delete(item)
    db.commit()
    return True


def get_sam_risk_overview(
    db: Session,
    *,
    platform: str = "all",
    search: str = "",
    limit: int = 100,
    offset: int = 0,
) -> dict:
    name_col = func.coalesce(
        AgentSoftwareInventory.normalized_name,
        AgentSoftwareInventory.software_name,
    )
    q = (
        db.query(
            name_col.label("software_name"),
            func.lower(Agent.platform).label("platform"),
            func.count(func.distinct(AgentSoftwareInventory.agent_uuid)).label("agent_count"),
        )
        .select_from(AgentSoftwareInventory)
        .join(Agent, Agent.uuid == AgentSoftwareInventory.agent_uuid)
        .group_by(name_col, func.lower(Agent.platform))
    )
    safe_platform = (platform or "all").strip().lower()
    if safe_platform != "all":
        q = q.filter(func.lower(Agent.platform) == safe_platform)
    if search:
        q = q.filter(name_col.ilike(f"%{search}%"))
    grouped = q.all()

    lifecycle = (
        db.query(SamLifecyclePolicy)
        .filter(SamLifecyclePolicy.is_active.is_(True))
        .order_by(SamLifecyclePolicy.id.asc())
        .all()
    )
    cost_profiles = (
        db.query(SamCostProfile)
        .filter(SamCostProfile.is_active.is_(True))
        .order_by(SamCostProfile.id.asc())
        .all()
    )

    now = datetime.now(timezone.utc)
    items: list[dict] = []
    critical_count = 0
    warning_count = 0
    monthly_total = 0

    for row in grouped:
        software_name = str(row.software_name or "").strip()
        row_platform = str(row.platform or "all").strip().lower()
        agent_count = int(row.agent_count or 0)
        if not software_name or agent_count <= 0:
            continue

        lifecycle_rule = _pick_best_sam_lifecycle(software_name, row_platform, lifecycle)
        cost_rule = _pick_best_sam_cost(software_name, row_platform, cost_profiles)

        lifecycle_status = "supported"
        days_to_eol: Optional[int] = None
        days_to_eos: Optional[int] = None
        if lifecycle_rule:
            if lifecycle_rule.eol_date:
                days_to_eol = (lifecycle_rule.eol_date - now).days
            if lifecycle_rule.eos_date:
                days_to_eos = (lifecycle_rule.eos_date - now).days
            if days_to_eos is not None and days_to_eos <= 0:
                lifecycle_status = "eos"
                critical_count += 1
            elif days_to_eol is not None and days_to_eol <= 0:
                lifecycle_status = "eol"
                critical_count += 1
            elif days_to_eos is not None and days_to_eos <= 90:
                lifecycle_status = "eos_soon"
                warning_count += 1
            elif days_to_eol is not None and days_to_eol <= 90:
                lifecycle_status = "eol_soon"
                warning_count += 1

        estimated_cost = 0
        currency = "USD"
        if cost_rule:
            estimated_cost = int(cost_rule.monthly_cost_cents or 0) * agent_count
            currency = str(cost_rule.currency or "USD")
        monthly_total += estimated_cost

        items.append(
            {
                "software_name": software_name,
                "platform": row_platform,
                "agent_count": agent_count,
                "lifecycle_status": lifecycle_status,
                "days_to_eol": days_to_eol,
                "days_to_eos": days_to_eos,
                "estimated_monthly_cost_cents": estimated_cost,
                "currency": currency,
            }
        )

    severity_order = {"eos": 4, "eol": 3, "eos_soon": 2, "eol_soon": 1, "supported": 0}
    items.sort(
        key=lambda x: (
            -severity_order.get(str(x.get("lifecycle_status") or "supported"), 0),
            -int(x.get("estimated_monthly_cost_cents") or 0),
            -int(x.get("agent_count") or 0),
            str(x.get("software_name") or "").lower(),
        )
    )
    safe_offset = max(int(offset), 0)
    safe_limit = min(max(int(limit), 1), 500)
    paged = items[safe_offset:safe_offset + safe_limit]
    return {
        "items": paged,
        "total": len(items),
        "critical_count": critical_count,
        "warning_count": warning_count,
        "monthly_cost_cents_total": monthly_total,
    }


# --- Cleanup ---


def cleanup_old_change_history(db: Session, retention_days: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    count = db.query(SoftwareChangeHistory).filter(
        SoftwareChangeHistory.detected_at < cutoff
    ).delete()
    db.commit()
    return count

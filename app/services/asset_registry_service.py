from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from fastapi import HTTPException, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models import (
    Agent,
    AssetAgentLink,
    AssetChangeLog,
    AssetCostCenter,
    AssetDataQualityIssue,
    AssetLocationNode,
    AssetLocationNodeType,
    AssetMatchingDecision,
    AssetOrganizationNode,
    AssetOrganizationNodeType,
    AssetPerson,
    AssetRecord,
    Setting,
    User,
)


ORG_NODE_ORDER = ["company", "legal_entity", "region", "directorate", "department", "team", "unit"]
LOCATION_NODE_ORDER = ["campus", "building", "block", "floor", "area", "room"]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _day_key(value: Optional[datetime]) -> Optional[str]:
    if not value:
        return None
    dt = value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return dt.date().isoformat()


def _trend_points(rows: list[datetime], days: int = 7) -> list[dict]:
    today = utcnow().date()
    labels = [(today - timedelta(days=offset)).isoformat() for offset in range(days - 1, -1, -1)]
    counts = Counter(key for key in (_day_key(row) for row in rows) if key)
    return [{"label": label, "value": int(counts.get(label, 0))} for label in labels]


def _norm_text(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def _dict_setting(db: Session, key: str, fallback: list[str]) -> list[str]:
    row = db.query(Setting).filter(Setting.key == key).first()
    if not row or not row.value:
        return list(fallback)
    try:
        data = json.loads(row.value)
        return [str(x).strip() for x in data if str(x).strip()]
    except Exception:
        return list(fallback)


def get_dictionaries(db: Session) -> dict:
    org_types = db.query(AssetOrganizationNodeType).order_by(AssetOrganizationNodeType.sort_order.asc()).all()
    loc_types = db.query(AssetLocationNodeType).order_by(AssetLocationNodeType.sort_order.asc()).all()
    return {
        "organization_node_types": [
            {"code": x.code, "display_name": x.display_name, "sort_order": x.sort_order, "is_active": x.is_active}
            for x in org_types
        ],
        "location_node_types": [
            {"code": x.code, "display_name": x.display_name, "sort_order": x.sort_order, "is_active": x.is_active}
            for x in loc_types
        ],
        "device_types": _dict_setting(
            db,
            "asset_registry_device_types",
            ["desktop", "laptop", "tablet", "thin_client", "workstation", "kiosk", "shared_terminal", "meeting_room_terminal", "field_device"],
        ),
        "usage_types": _dict_setting(db, "asset_registry_usage_types", ["personal", "shared", "kiosk", "field", "meeting_room", "admin"]),
        "ownership_types": _dict_setting(db, "asset_registry_ownership_types", ["company", "leased", "partner", "personal"]),
        "lifecycle_statuses": _dict_setting(
            db, "asset_registry_lifecycle_statuses", ["planned", "active", "in_stock", "in_repair", "retired", "lost", "awaiting_match"]
        ),
    }


def _org_type_rank(code: Optional[str]) -> int:
    if not code:
        return 999
    try:
        return ORG_NODE_ORDER.index(code)
    except ValueError:
        return 999


def _loc_type_rank(code: Optional[str]) -> int:
    if not code:
        return 999
    try:
        return LOCATION_NODE_ORDER.index(code)
    except ValueError:
        return 999


def _ensure_unique_name_under_parent(
    db: Session,
    model,
    name: str,
    parent_id: Optional[int],
    type_field: str,
    type_value: str,
    exclude_id: Optional[int] = None,
) -> None:
    q = db.query(model).filter(
        func.lower(getattr(model, "name")) == name.strip().lower(),
        getattr(model, "parent_id") == parent_id,
        getattr(model, type_field) == type_value,
    )
    if exclude_id is not None:
        q = q.filter(model.id != exclude_id)
    exists = q.first()
    if exists:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Aynı parent altında aynı isimde kayıt zaten var")


def _ensure_org_parent_compatibility(node_type: str, parent: Optional[AssetOrganizationNode]) -> None:
    if not parent:
        return
    if _org_type_rank(parent.node_type) >= _org_type_rank(node_type):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Organizasyon seviye sırası geçersiz")


def _ensure_location_parent_compatibility(location_type: str, parent: Optional[AssetLocationNode]) -> None:
    if not parent:
        return
    if _loc_type_rank(parent.location_type) >= _loc_type_rank(location_type):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Lokasyon seviye sırası geçersiz")


def build_org_path(db: Session, node_id: Optional[int]) -> str:
    if not node_id:
        return ""
    pieces: list[str] = []
    current = db.query(AssetOrganizationNode).filter(AssetOrganizationNode.id == node_id).first()
    guard = 0
    while current and guard < 32:
        pieces.append(current.name)
        if not current.parent_id:
            break
        current = db.query(AssetOrganizationNode).filter(AssetOrganizationNode.id == current.parent_id).first()
        guard += 1
    return " > ".join(reversed(pieces))


def build_location_path(db: Session, node_id: Optional[int]) -> str:
    if not node_id:
        return ""
    pieces: list[str] = []
    current = db.query(AssetLocationNode).filter(AssetLocationNode.id == node_id).first()
    guard = 0
    while current and guard < 32:
        pieces.append(current.name)
        if not current.parent_id:
            break
        current = db.query(AssetLocationNode).filter(AssetLocationNode.id == current.parent_id).first()
        guard += 1
    return " > ".join(reversed(pieces))


def get_org_descendant_ids(db: Session, node_id: Optional[int]) -> list[int]:
    if not node_id:
        return []
    rows = db.query(AssetOrganizationNode.id, AssetOrganizationNode.parent_id).all()
    children: dict[Optional[int], list[int]] = {}
    for item_id, parent_id in rows:
        children.setdefault(parent_id, []).append(item_id)
    out: list[int] = []
    stack = [int(node_id)]
    seen: set[int] = set()
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        out.append(current)
        stack.extend(children.get(current, []))
    return out


def get_location_descendant_ids(db: Session, node_id: Optional[int]) -> list[int]:
    if not node_id:
        return []
    rows = db.query(AssetLocationNode.id, AssetLocationNode.parent_id).all()
    children: dict[Optional[int], list[int]] = {}
    for item_id, parent_id in rows:
        children.setdefault(parent_id, []).append(item_id)
    out: list[int] = []
    stack = [int(node_id)]
    seen: set[int] = set()
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        out.append(current)
        stack.extend(children.get(current, []))
    return out


def list_organization_nodes(db: Session, include_inactive: bool = False) -> list[dict]:
    q = db.query(AssetOrganizationNode)
    if not include_inactive:
        q = q.filter(AssetOrganizationNode.is_active.is_(True))
    rows = q.order_by(AssetOrganizationNode.sort_order.asc(), AssetOrganizationNode.name.asc()).all()
    counts = dict(
        db.query(AssetRecord.org_node_id, func.count(AssetRecord.id))
        .group_by(AssetRecord.org_node_id)
        .all()
    )
    items = []
    for row in rows:
        items.append(
            {
                "id": row.id,
                "parent_id": row.parent_id,
                "node_type": row.node_type,
                "name": row.name,
                "code": row.code,
                "is_active": row.is_active,
                "sort_order": row.sort_order,
                "notes": row.notes,
                "path": build_org_path(db, row.id),
                "asset_count": int(counts.get(row.id, 0)),
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
        )
    return items


def create_organization_node(db: Session, payload, current_user: Optional[User] = None) -> AssetOrganizationNode:
    parent = None
    if payload.parent_id:
        parent = db.query(AssetOrganizationNode).filter(AssetOrganizationNode.id == payload.parent_id).first()
        if not parent:
            raise HTTPException(status_code=404, detail="Parent organization node not found")
    _ensure_org_parent_compatibility(payload.node_type, parent)
    _ensure_unique_name_under_parent(db, AssetOrganizationNode, payload.name, payload.parent_id, "node_type", payload.node_type)
    row = AssetOrganizationNode(
        parent_id=payload.parent_id,
        node_type=payload.node_type,
        name=payload.name.strip(),
        code=(payload.code or "").strip() or None,
        is_active=bool(payload.is_active),
        sort_order=int(payload.sort_order or 0),
        notes=(payload.notes or "").strip() or None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_organization_node(db: Session, node_id: int, payload, current_user: Optional[User] = None) -> AssetOrganizationNode:
    row = db.query(AssetOrganizationNode).filter(AssetOrganizationNode.id == node_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Organization node not found")
    new_type = payload.node_type if payload.node_type is not None else row.node_type
    new_parent_id = payload.parent_id if payload.parent_id is not None else row.parent_id
    parent = None
    if new_parent_id:
        if new_parent_id == node_id:
            raise HTTPException(status_code=400, detail="Node kendi parent'ı olamaz")
        parent = db.query(AssetOrganizationNode).filter(AssetOrganizationNode.id == new_parent_id).first()
        if not parent:
            raise HTTPException(status_code=404, detail="Parent organization node not found")
    _ensure_org_parent_compatibility(new_type, parent)
    new_name = payload.name.strip() if payload.name is not None else row.name
    _ensure_unique_name_under_parent(db, AssetOrganizationNode, new_name, new_parent_id, "node_type", new_type, exclude_id=node_id)
    if payload.node_type is not None:
        row.node_type = payload.node_type
    row.parent_id = new_parent_id
    if payload.name is not None:
        row.name = payload.name.strip()
    if payload.code is not None:
        row.code = (payload.code or "").strip() or None
    if payload.is_active is not None:
        row.is_active = bool(payload.is_active)
    if payload.sort_order is not None:
        row.sort_order = int(payload.sort_order)
    if payload.notes is not None:
        row.notes = (payload.notes or "").strip() or None
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_location_nodes(db: Session, include_inactive: bool = False) -> list[dict]:
    q = db.query(AssetLocationNode)
    if not include_inactive:
        q = q.filter(AssetLocationNode.is_active.is_(True))
    rows = q.order_by(AssetLocationNode.name.asc()).all()
    counts = dict(
        db.query(AssetRecord.location_node_id, func.count(AssetRecord.id))
        .group_by(AssetRecord.location_node_id)
        .all()
    )
    items = []
    for row in rows:
        items.append(
            {
                "id": row.id,
                "parent_id": row.parent_id,
                "org_node_id": row.org_node_id,
                "location_type": row.location_type,
                "name": row.name,
                "code": row.code,
                "address_text": row.address_text,
                "is_active": row.is_active,
                "notes": row.notes,
                "path": build_location_path(db, row.id),
                "asset_count": int(counts.get(row.id, 0)),
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
        )
    return items


def create_location_node(db: Session, payload, current_user: Optional[User] = None) -> AssetLocationNode:
    parent = None
    if payload.parent_id:
        parent = db.query(AssetLocationNode).filter(AssetLocationNode.id == payload.parent_id).first()
        if not parent:
            raise HTTPException(status_code=404, detail="Parent location node not found")
    _ensure_location_parent_compatibility(payload.location_type, parent)
    _ensure_unique_name_under_parent(db, AssetLocationNode, payload.name, payload.parent_id, "location_type", payload.location_type)
    row = AssetLocationNode(
        parent_id=payload.parent_id,
        org_node_id=payload.org_node_id,
        location_type=payload.location_type,
        name=payload.name.strip(),
        code=(payload.code or "").strip() or None,
        address_text=(payload.address_text or "").strip() or None,
        is_active=bool(payload.is_active),
        notes=(payload.notes or "").strip() or None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_location_node(db: Session, node_id: int, payload, current_user: Optional[User] = None) -> AssetLocationNode:
    row = db.query(AssetLocationNode).filter(AssetLocationNode.id == node_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Location node not found")
    new_type = payload.location_type if payload.location_type is not None else row.location_type
    new_parent_id = payload.parent_id if payload.parent_id is not None else row.parent_id
    parent = None
    if new_parent_id:
        if new_parent_id == node_id:
            raise HTTPException(status_code=400, detail="Node kendi parent'ı olamaz")
        parent = db.query(AssetLocationNode).filter(AssetLocationNode.id == new_parent_id).first()
        if not parent:
            raise HTTPException(status_code=404, detail="Parent location node not found")
    _ensure_location_parent_compatibility(new_type, parent)
    new_name = payload.name.strip() if payload.name is not None else row.name
    _ensure_unique_name_under_parent(db, AssetLocationNode, new_name, new_parent_id, "location_type", new_type, exclude_id=node_id)
    if payload.location_type is not None:
        row.location_type = payload.location_type
    row.parent_id = new_parent_id
    if payload.org_node_id is not None:
        row.org_node_id = payload.org_node_id
    if payload.name is not None:
        row.name = payload.name.strip()
    if payload.code is not None:
        row.code = (payload.code or "").strip() or None
    if payload.address_text is not None:
        row.address_text = (payload.address_text or "").strip() or None
    if payload.is_active is not None:
        row.is_active = bool(payload.is_active)
    if payload.notes is not None:
        row.notes = (payload.notes or "").strip() or None
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_people(
    db: Session,
    q: Optional[str] = None,
    org_node_id: Optional[int] = None,
    cost_center_id: Optional[int] = None,
    include_inactive: bool = False,
) -> list[dict]:
    query = db.query(AssetPerson)
    if q:
        like = f"%{q.strip().lower()}%"
        query = query.filter(
            or_(
                func.lower(AssetPerson.full_name).like(like),
                func.lower(func.coalesce(AssetPerson.username, "")).like(like),
                func.lower(func.coalesce(AssetPerson.email, "")).like(like),
            )
        )
    if org_node_id:
        query = query.filter(AssetPerson.org_node_id.in_(get_org_descendant_ids(db, org_node_id)))
    if cost_center_id:
        query = query.filter(AssetPerson.cost_center_id == cost_center_id)
    if not include_inactive:
        query = query.filter(AssetPerson.is_active.is_(True))
    rows = query.order_by(AssetPerson.full_name.asc()).all()
    counts_map: dict[int, int] = {}
    for person_id, total in (
        db.query(AssetRecord.primary_person_id, func.count(AssetRecord.id))
        .filter(AssetRecord.primary_person_id.isnot(None))
        .group_by(AssetRecord.primary_person_id)
        .all()
    ):
        counts_map[int(person_id)] = int(total)
    for person_id, total in (
        db.query(AssetRecord.owner_person_id, func.count(AssetRecord.id))
        .filter(AssetRecord.owner_person_id.isnot(None))
        .group_by(AssetRecord.owner_person_id)
        .all()
    ):
        counts_map[int(person_id)] = counts_map.get(int(person_id), 0) + int(total)
    out = []
    for row in rows:
        out.append(
            {
                "id": row.id,
                "person_code": row.person_code,
                "username": row.username,
                "full_name": row.full_name,
                "email": row.email,
                "phone": row.phone,
                "title": row.title,
                "org_node_id": row.org_node_id,
                "org_path": build_org_path(db, row.org_node_id),
                "cost_center_id": row.cost_center_id,
                "cost_center_name": row.cost_center.name if row.cost_center else None,
                "source_type": row.source_type,
                "is_active": row.is_active,
                "asset_count": counts_map.get(row.id, 0),
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
        )
    return out


def list_cost_centers(db: Session, org_node_id: Optional[int] = None, include_inactive: bool = False) -> list[dict]:
    query = db.query(AssetCostCenter)
    if org_node_id:
        query = query.filter(AssetCostCenter.org_node_id.in_(get_org_descendant_ids(db, org_node_id)))
    if not include_inactive:
        query = query.filter(AssetCostCenter.is_active.is_(True))
    rows = query.order_by(AssetCostCenter.name.asc()).all()
    return [
        {
            "id": row.id,
            "parent_id": row.parent_id,
            "code": row.code,
            "name": row.name,
            "org_node_id": row.org_node_id,
            "org_path": build_org_path(db, row.org_node_id),
            "is_active": row.is_active,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
        for row in rows
    ]


def create_cost_center(db: Session, payload, current_user: Optional[User] = None) -> AssetCostCenter:
    exists = db.query(AssetCostCenter.id).filter(
        func.lower(AssetCostCenter.code) == payload.code.strip().lower(),
        AssetCostCenter.org_node_id == payload.org_node_id,
    ).first()
    if exists:
        raise HTTPException(status_code=409, detail="Bu organization altında aynı cost center code zaten var")
    row = AssetCostCenter(
        parent_id=payload.parent_id,
        code=payload.code.strip(),
        name=payload.name.strip(),
        org_node_id=payload.org_node_id,
        is_active=bool(payload.is_active),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_cost_center(db: Session, cost_center_id: int, payload, current_user: Optional[User] = None) -> AssetCostCenter:
    row = db.query(AssetCostCenter).filter(AssetCostCenter.id == cost_center_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Cost center not found")
    new_code = payload.code.strip() if payload.code is not None else row.code
    new_org_id = payload.org_node_id if payload.org_node_id is not None else row.org_node_id
    exists = db.query(AssetCostCenter.id).filter(
        AssetCostCenter.id != row.id,
        func.lower(AssetCostCenter.code) == new_code.lower(),
        AssetCostCenter.org_node_id == new_org_id,
    ).first()
    if exists:
        raise HTTPException(status_code=409, detail="Bu organization altında aynı cost center code zaten var")
    if payload.parent_id is not None:
        row.parent_id = payload.parent_id
    if payload.code is not None:
        row.code = payload.code.strip()
    if payload.name is not None:
        row.name = payload.name.strip()
    if payload.org_node_id is not None:
        row.org_node_id = payload.org_node_id
    if payload.is_active is not None:
        row.is_active = bool(payload.is_active)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def create_person(db: Session, payload, current_user: Optional[User] = None) -> AssetPerson:
    row = AssetPerson(
        person_code=(payload.person_code or "").strip() or None,
        username=(payload.username or "").strip() or None,
        full_name=payload.full_name.strip(),
        email=(payload.email or "").strip() or None,
        phone=(payload.phone or "").strip() or None,
        title=(payload.title or "").strip() or None,
        org_node_id=payload.org_node_id,
        cost_center_id=payload.cost_center_id,
        source_type=(payload.source_type or "manual").strip() or "manual",
        is_active=bool(payload.is_active),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_person(db: Session, person_id: int, payload, current_user: Optional[User] = None) -> AssetPerson:
    row = db.query(AssetPerson).filter(AssetPerson.id == person_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Person not found")
    for field in ("person_code", "username", "email", "phone", "title"):
        value = getattr(payload, field)
        if value is not None:
            setattr(row, field, (value or "").strip() or None)
    if payload.full_name is not None:
        row.full_name = payload.full_name.strip()
    if payload.org_node_id is not None:
        row.org_node_id = payload.org_node_id
    if payload.cost_center_id is not None:
        row.cost_center_id = payload.cost_center_id
    if payload.source_type is not None:
        row.source_type = (payload.source_type or "manual").strip() or "manual"
    if payload.is_active is not None:
        row.is_active = bool(payload.is_active)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_person_detail(db: Session, person_id: int) -> dict:
    row = db.query(AssetPerson).filter(AssetPerson.id == person_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Person not found")
    data = list_people(db, include_inactive=True)
    found = next((x for x in data if x["id"] == person_id), None)
    linked_assets = db.query(AssetRecord).filter(or_(AssetRecord.primary_person_id == person_id, AssetRecord.owner_person_id == person_id)).all()
    return {
        **(found or {}),
        "linked_assets": [{"id": x.id, "asset_tag": x.asset_tag, "device_type": x.device_type, "lifecycle_status": x.lifecycle_status} for x in linked_assets],
    }


def _validate_asset_payload(db: Session, payload, updating: bool = False, current_asset: Optional[AssetRecord] = None) -> None:
    dictionaries = get_dictionaries(db)
    if payload.device_type and payload.device_type not in dictionaries["device_types"]:
        raise HTTPException(status_code=400, detail="Unknown device_type")
    if payload.usage_type and payload.usage_type not in dictionaries["usage_types"]:
        raise HTTPException(status_code=400, detail="Unknown usage_type")
    if payload.ownership_type and payload.ownership_type not in dictionaries["ownership_types"]:
        raise HTTPException(status_code=400, detail="Unknown ownership_type")
    if payload.lifecycle_status and payload.lifecycle_status not in dictionaries["lifecycle_statuses"]:
        raise HTTPException(status_code=400, detail="Unknown lifecycle_status")
    usage = payload.usage_type or (current_asset.usage_type if current_asset else None)
    primary_person_id = payload.primary_person_id if payload.primary_person_id is not None else (current_asset.primary_person_id if current_asset else None)
    if usage == "personal" and not primary_person_id:
        raise HTTPException(status_code=400, detail="Bireysel cihazlar için primary person gereklidir")
    if payload.org_node_id is not None and not db.query(AssetOrganizationNode.id).filter(AssetOrganizationNode.id == payload.org_node_id, AssetOrganizationNode.is_active.is_(True)).first():
        raise HTTPException(status_code=400, detail="Geçerli organization seçiniz")
    if payload.location_node_id is not None and not db.query(AssetLocationNode.id).filter(AssetLocationNode.id == payload.location_node_id, AssetLocationNode.is_active.is_(True)).first():
        raise HTTPException(status_code=400, detail="Geçerli location seçiniz")


def _log_asset_changes(db: Session, asset_id: int, changed_by: Optional[int], before: dict, after: dict) -> None:
    for key, old_value in before.items():
        new_value = after.get(key)
        if old_value != new_value:
            db.add(
                AssetChangeLog(
                    asset_id=asset_id,
                    change_type="field_changed",
                    field_name=key,
                    old_value=None if old_value is None else str(old_value),
                    new_value=None if new_value is None else str(new_value),
                    changed_by=changed_by,
                )
            )


def recompute_asset_data_quality(db: Session, asset: AssetRecord, resolved_by: Optional[int] = None) -> None:
    existing = db.query(AssetDataQualityIssue).filter(AssetDataQualityIssue.asset_id == asset.id, AssetDataQualityIssue.status == "open").all()
    open_map = {x.issue_type: x for x in existing}
    issues: list[tuple[str, str, str]] = []
    if asset.usage_type == "personal" and not asset.primary_person_id:
        issues.append(("missing_primary_person", "high", "Primary user eksik"))
    if not asset.owner_person_id:
        issues.append(("missing_owner", "medium", "Owner eksik"))
    if not asset.org_node_id:
        issues.append(("missing_organization", "high", "Organizasyon eksik"))
    if not asset.location_node_id:
        issues.append(("missing_location", "high", "Lokasyon eksik"))
    if not asset.cost_center_id:
        issues.append(("missing_cost_center", "low", "Maliyet merkezi eksik"))
    if asset.serial_number:
        dup_count = (
            db.query(func.count(AssetRecord.id))
            .filter(AssetRecord.serial_number == asset.serial_number, AssetRecord.id != asset.id, AssetRecord.is_active.is_(True))
            .scalar()
            or 0
        )
        if dup_count > 0:
            issues.append(("duplicate_serial", "medium", "Aynı seri numarasına sahip başka asset var"))
    issue_types = {item[0] for item in issues}
    for issue_type, severity, summary in issues:
        current = open_map.get(issue_type)
        if current:
            current.severity = severity
            current.summary = summary
            db.add(current)
        else:
            db.add(
                AssetDataQualityIssue(
                    asset_id=asset.id,
                    issue_type=issue_type,
                    severity=severity,
                    status="open",
                    summary=summary,
                )
            )
    for issue_type, row in open_map.items():
        if issue_type not in issue_types:
            row.status = "resolved"
            row.resolved_at = utcnow()
            row.resolved_by = resolved_by
            db.add(row)


def create_asset(db: Session, payload, current_user: Optional[User] = None) -> AssetRecord:
    _validate_asset_payload(db, payload)
    exists = db.query(AssetRecord.id).filter(func.lower(AssetRecord.asset_tag) == payload.asset_tag.strip().lower()).first()
    if exists:
        raise HTTPException(status_code=409, detail="Asset tag already exists")
    row = AssetRecord(
        asset_tag=payload.asset_tag.strip(),
        serial_number=(payload.serial_number or "").strip() or None,
        inventory_number=(payload.inventory_number or "").strip() or None,
        device_type=payload.device_type,
        usage_type=payload.usage_type,
        ownership_type=payload.ownership_type,
        lifecycle_status=payload.lifecycle_status,
        criticality=(payload.criticality or "").strip() or None,
        manufacturer=(payload.manufacturer or "").strip() or None,
        model=(payload.model or "").strip() or None,
        purchase_date=(payload.purchase_date or "").strip() or None,
        warranty_end_date=(payload.warranty_end_date or "").strip() or None,
        org_node_id=payload.org_node_id,
        location_node_id=payload.location_node_id,
        cost_center_id=payload.cost_center_id,
        primary_person_id=payload.primary_person_id,
        owner_person_id=payload.owner_person_id,
        support_team=(payload.support_team or "").strip() or None,
        is_active=bool(payload.is_active),
        notes=(payload.notes or "").strip() or None,
        last_verified_at=utcnow(),
        last_verified_by=current_user.id if current_user else None,
    )
    db.add(row)
    db.flush()
    db.add(
        AssetChangeLog(
            asset_id=row.id,
            change_type="created",
            field_name=None,
            old_value=None,
            new_value=row.asset_tag,
            changed_by=current_user.id if current_user else None,
        )
    )
    recompute_asset_data_quality(db, row, resolved_by=current_user.id if current_user else None)
    db.commit()
    db.refresh(row)
    return row


def update_asset(db: Session, asset_id: int, payload, current_user: Optional[User] = None) -> AssetRecord:
    row = db.query(AssetRecord).filter(AssetRecord.id == asset_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Asset not found")
    _validate_asset_payload(db, payload, updating=True, current_asset=row)
    if payload.asset_tag is not None:
        exists = db.query(AssetRecord.id).filter(func.lower(AssetRecord.asset_tag) == payload.asset_tag.strip().lower(), AssetRecord.id != asset_id).first()
        if exists:
            raise HTTPException(status_code=409, detail="Asset tag already exists")
    before = {
        "asset_tag": row.asset_tag,
        "serial_number": row.serial_number,
        "device_type": row.device_type,
        "usage_type": row.usage_type,
        "ownership_type": row.ownership_type,
        "lifecycle_status": row.lifecycle_status,
        "org_node_id": row.org_node_id,
        "location_node_id": row.location_node_id,
        "cost_center_id": row.cost_center_id,
        "primary_person_id": row.primary_person_id,
        "owner_person_id": row.owner_person_id,
        "support_team": row.support_team,
        "is_active": row.is_active,
    }
    for field in (
        "asset_tag",
        "serial_number",
        "inventory_number",
        "device_type",
        "usage_type",
        "ownership_type",
        "lifecycle_status",
        "criticality",
        "manufacturer",
        "model",
        "purchase_date",
        "warranty_end_date",
        "support_team",
        "notes",
    ):
        value = getattr(payload, field)
        if value is not None:
            setattr(row, field, value.strip() if isinstance(value, str) else value)
    for field in ("org_node_id", "location_node_id", "cost_center_id", "primary_person_id", "owner_person_id"):
        value = getattr(payload, field)
        if value is not None:
            setattr(row, field, value)
    if payload.is_active is not None:
        row.is_active = bool(payload.is_active)
    row.last_verified_at = utcnow()
    row.last_verified_by = current_user.id if current_user else None
    after = {
        "asset_tag": row.asset_tag,
        "serial_number": row.serial_number,
        "device_type": row.device_type,
        "usage_type": row.usage_type,
        "ownership_type": row.ownership_type,
        "lifecycle_status": row.lifecycle_status,
        "org_node_id": row.org_node_id,
        "location_node_id": row.location_node_id,
        "cost_center_id": row.cost_center_id,
        "primary_person_id": row.primary_person_id,
        "owner_person_id": row.owner_person_id,
        "support_team": row.support_team,
        "is_active": row.is_active,
    }
    _log_asset_changes(db, row.id, current_user.id if current_user else None, before, after)
    recompute_asset_data_quality(db, row, resolved_by=current_user.id if current_user else None)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _active_link_for_asset(db: Session, asset_id: int) -> Optional[AssetAgentLink]:
    return (
        db.query(AssetAgentLink)
        .filter(AssetAgentLink.asset_id == asset_id, AssetAgentLink.link_status == "active", AssetAgentLink.is_primary.is_(True))
        .order_by(AssetAgentLink.linked_at.desc())
        .first()
    )


def _active_link_for_agent(db: Session, agent_uuid: str) -> Optional[AssetAgentLink]:
    return (
        db.query(AssetAgentLink)
        .filter(AssetAgentLink.agent_uuid == agent_uuid, AssetAgentLink.link_status == "active", AssetAgentLink.is_primary.is_(True))
        .order_by(AssetAgentLink.linked_at.desc())
        .first()
    )


def serialize_asset(db: Session, row: AssetRecord) -> dict:
    link = _active_link_for_asset(db, row.id)
    issue_count = db.query(func.count(AssetDataQualityIssue.id)).filter(AssetDataQualityIssue.asset_id == row.id, AssetDataQualityIssue.status == "open").scalar() or 0
    return {
        "id": row.id,
        "asset_tag": row.asset_tag,
        "serial_number": row.serial_number,
        "inventory_number": row.inventory_number,
        "device_type": row.device_type,
        "usage_type": row.usage_type,
        "ownership_type": row.ownership_type,
        "lifecycle_status": row.lifecycle_status,
        "criticality": row.criticality,
        "manufacturer": row.manufacturer,
        "model": row.model,
        "purchase_date": row.purchase_date,
        "warranty_end_date": row.warranty_end_date,
        "org_node_id": row.org_node_id,
        "org_path": build_org_path(db, row.org_node_id),
        "location_node_id": row.location_node_id,
        "location_path": build_location_path(db, row.location_node_id),
        "cost_center_id": row.cost_center_id,
        "cost_center_name": row.cost_center.name if row.cost_center else None,
        "primary_person_id": row.primary_person_id,
        "primary_person_name": row.primary_person.full_name if row.primary_person else None,
        "owner_person_id": row.owner_person_id,
        "owner_person_name": row.owner_person.full_name if row.owner_person else None,
        "support_team": row.support_team,
        "is_active": row.is_active,
        "notes": row.notes,
        "last_verified_at": row.last_verified_at,
        "last_verified_by": row.last_verified_by,
        "linked_agent_uuid": link.agent_uuid if link else None,
        "linked_agent_hostname": link.agent.hostname if link and link.agent else None,
        "linked_agent_status": link.agent.status if link and link.agent else None,
        "linked_agent_ip": link.agent.ip_address if link and link.agent else None,
        "linked_agent_last_seen": link.agent.last_seen if link and link.agent else None,
        "match_source": link.match_source if link else None,
        "confidence_score": link.confidence_score if link else None,
        "linked_at": link.linked_at if link else None,
        "data_quality_score": max(0, 100 - int(issue_count) * 15),
        "issue_count": int(issue_count),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def list_assets(
    db: Session,
    q: Optional[str] = None,
    org_node_id: Optional[int] = None,
    location_node_id: Optional[int] = None,
    person_id: Optional[int] = None,
    include_inactive: bool = False,
) -> list[dict]:
    query = db.query(AssetRecord)
    if q:
        like = f"%{q.strip().lower()}%"
        query = query.filter(
            or_(
                func.lower(AssetRecord.asset_tag).like(like),
                func.lower(func.coalesce(AssetRecord.serial_number, "")).like(like),
                func.lower(func.coalesce(AssetRecord.inventory_number, "")).like(like),
                func.lower(func.coalesce(AssetRecord.model, "")).like(like),
            )
        )
    if org_node_id:
        query = query.filter(AssetRecord.org_node_id.in_(get_org_descendant_ids(db, org_node_id)))
    if location_node_id:
        query = query.filter(AssetRecord.location_node_id.in_(get_location_descendant_ids(db, location_node_id)))
    if person_id:
        query = query.filter(or_(AssetRecord.primary_person_id == person_id, AssetRecord.owner_person_id == person_id))
    if not include_inactive:
        query = query.filter(AssetRecord.is_active.is_(True))
    rows = query.order_by(AssetRecord.asset_tag.asc()).all()
    return [serialize_asset(db, row) for row in rows]


def get_asset_detail(db: Session, asset_id: int) -> dict:
    row = db.query(AssetRecord).filter(AssetRecord.id == asset_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Asset not found")
    payload = serialize_asset(db, row)
    payload["issues"] = list_data_quality_issues(db, asset_id=asset_id)["items"]
    payload["history"] = list_asset_change_log(db, asset_id)["items"]
    return payload


def get_agent_asset_summary(db: Session, agent_uuid: str) -> Optional[dict]:
    link = _active_link_for_agent(db, agent_uuid)
    if not link or not link.asset:
        return None
    payload = serialize_asset(db, link.asset)
    return {
        "asset_id": payload["id"],
        "asset_tag": payload["asset_tag"],
        "device_type": payload["device_type"],
        "lifecycle_status": payload["lifecycle_status"],
        "org_path": payload.get("org_path"),
        "location_path": payload.get("location_path"),
        "primary_person_name": payload.get("primary_person_name"),
        "owner_person_name": payload.get("owner_person_name"),
        "support_team": payload.get("support_team"),
        "data_quality_score": payload.get("data_quality_score", 100),
        "issue_count": payload.get("issue_count", 0),
        "match_source": link.match_source,
        "confidence_score": link.confidence_score,
        "linked_at": link.linked_at,
        "last_verified_at": payload.get("last_verified_at"),
        "notes": payload.get("notes"),
    }


def link_asset_to_agent(db: Session, asset_id: int, agent_uuid: str, current_user: Optional[User] = None, match_source: Optional[str] = None, confidence_score: Optional[int] = None, is_primary: bool = True, unlink_reason: Optional[str] = None) -> AssetAgentLink:
    asset = db.query(AssetRecord).filter(AssetRecord.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    agent = db.query(Agent).filter(Agent.uuid == agent_uuid).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    active_for_agent = (
        db.query(AssetAgentLink)
        .filter(AssetAgentLink.agent_uuid == agent_uuid, AssetAgentLink.link_status == "active", AssetAgentLink.is_primary.is_(True))
        .all()
    )
    for row in active_for_agent:
        row.link_status = "inactive"
        row.is_primary = False
        row.unlinked_at = utcnow()
        row.unlink_reason = unlink_reason or "relinked"
        db.add(row)
    active_for_asset = (
        db.query(AssetAgentLink)
        .filter(AssetAgentLink.asset_id == asset_id, AssetAgentLink.link_status == "active", AssetAgentLink.is_primary.is_(True))
        .all()
    )
    for row in active_for_asset:
        row.link_status = "inactive"
        row.is_primary = False
        row.unlinked_at = utcnow()
        row.unlink_reason = unlink_reason or "relinked"
        db.add(row)
    link = AssetAgentLink(
        asset_id=asset_id,
        agent_uuid=agent_uuid,
        link_status="active",
        match_source=(match_source or "manual").strip() or "manual",
        confidence_score=confidence_score,
        is_primary=bool(is_primary),
        linked_by=current_user.id if current_user else None,
    )
    db.add(link)
    db.flush()
    db.add(
        AssetChangeLog(
            asset_id=asset_id,
            change_type="linked_agent",
            field_name="agent_uuid",
            old_value=None,
            new_value=agent_uuid,
            changed_by=current_user.id if current_user else None,
        )
    )
    db.commit()
    db.refresh(link)
    return link


def unlink_asset_agent(db: Session, asset_id: int, agent_uuid: str, current_user: Optional[User] = None, reason: Optional[str] = None) -> int:
    rows = db.query(AssetAgentLink).filter(AssetAgentLink.asset_id == asset_id, AssetAgentLink.agent_uuid == agent_uuid, AssetAgentLink.link_status == "active").all()
    for row in rows:
        row.link_status = "inactive"
        row.is_primary = False
        row.unlinked_at = utcnow()
        row.unlink_reason = reason or "manual_unlink"
        db.add(row)
    if rows:
        db.add(
            AssetChangeLog(
                asset_id=asset_id,
                change_type="unlinked_agent",
                field_name="agent_uuid",
                old_value=agent_uuid,
                new_value=None,
                changed_by=current_user.id if current_user else None,
            )
        )
    db.commit()
    return len(rows)


def matching_candidates(db: Session) -> list[dict]:
    items: list[dict] = []
    decisions = {
        row.candidate_key: row
        for row in db.query(AssetMatchingDecision).all()
    }
    linked_agent_ids = {x[0] for x in db.query(AssetAgentLink.agent_uuid).filter(AssetAgentLink.link_status == "active", AssetAgentLink.is_primary.is_(True)).all()}
    linked_asset_ids = {x[0] for x in db.query(AssetAgentLink.asset_id).filter(AssetAgentLink.link_status == "active", AssetAgentLink.is_primary.is_(True)).all()}
    unlinked_agents = db.query(Agent).filter(~Agent.uuid.in_(linked_agent_ids)).all() if linked_agent_ids else db.query(Agent).all()
    unlinked_assets = db.query(AssetRecord).filter(AssetRecord.is_active.is_(True), ~AssetRecord.id.in_(linked_asset_ids)).all() if linked_asset_ids else db.query(AssetRecord).filter(AssetRecord.is_active.is_(True)).all()
    assets_by_serial = {_norm_text(a.serial_number): a for a in unlinked_assets if _norm_text(a.serial_number)}
    assets_by_hostname = {_norm_text(a.asset_tag): a for a in unlinked_assets if _norm_text(a.asset_tag)}
    assets_by_inventory = {_norm_text(a.inventory_number): a for a in unlinked_assets if _norm_text(a.inventory_number)}
    people_by_username = {
        _norm_text(person.username): person
        for person in db.query(AssetPerson).filter(AssetPerson.is_active.is_(True)).all()
        if _norm_text(person.username)
    }
    for agent in unlinked_agents:
        reasons: list[str] = []
        confidence = 0
        candidate_asset: Optional[AssetRecord] = None
        normalized_hostname = _norm_text(agent.hostname)
        normalized_user = _norm_text(agent.os_user)
        if normalized_hostname and normalized_hostname in assets_by_hostname:
            candidate_asset = assets_by_hostname[normalized_hostname]
            reasons.append("hostname matches asset tag")
            confidence += 55
        if normalized_hostname and normalized_hostname in assets_by_inventory:
            candidate_asset = candidate_asset or assets_by_inventory[normalized_hostname]
            reasons.append("hostname matches inventory number")
            confidence += 20
        if normalized_user:
            person = people_by_username.get(normalized_user)
            if person:
                person_asset = db.query(AssetRecord).filter(AssetRecord.primary_person_id == person.id, AssetRecord.is_active.is_(True)).first()
                if person_asset:
                    candidate_asset = candidate_asset or person_asset
                    reasons.append("login user matches primary person")
                    confidence += 30
                owner_asset = db.query(AssetRecord).filter(AssetRecord.owner_person_id == person.id, AssetRecord.is_active.is_(True)).first()
                if owner_asset:
                    candidate_asset = candidate_asset or owner_asset
                    reasons.append("login user matches owner person")
                    confidence += 15
        if normalized_hostname and normalized_hostname in assets_by_serial:
            candidate_asset = candidate_asset or assets_by_serial[normalized_hostname]
            reasons.append("hostname matches serial")
            confidence += 20
        if candidate_asset:
            candidate_key = f"agent_to_asset:{agent.uuid}:{candidate_asset.id}"
            if candidate_key not in decisions:
                items.append(
                    {
                        "asset_id": candidate_asset.id,
                        "asset_tag": candidate_asset.asset_tag,
                        "agent_uuid": agent.uuid,
                        "hostname": agent.hostname,
                        "serial_hint": candidate_asset.serial_number,
                        "org_hint": build_org_path(db, candidate_asset.org_node_id),
                        "location_hint": build_location_path(db, candidate_asset.location_node_id),
                        "confidence": min(confidence, 100),
                        "reasons": reasons,
                        "candidate_type": "agent_to_asset",
                        "candidate_key": candidate_key,
                    }
                )
        else:
            candidate_key = f"agent_without_asset:{agent.uuid}"
            if candidate_key not in decisions:
                items.append(
                    {
                        "asset_id": None,
                        "asset_tag": None,
                        "agent_uuid": agent.uuid,
                        "hostname": agent.hostname,
                        "serial_hint": None,
                        "org_hint": None,
                        "location_hint": None,
                        "confidence": 0,
                        "reasons": ["no active asset match"],
                        "candidate_type": "agent_without_asset",
                        "candidate_key": candidate_key,
                    }
                )
    for asset in unlinked_assets:
        candidate_key = f"asset_without_agent:{asset.id}"
        if candidate_key not in decisions:
            items.append(
                {
                    "asset_id": asset.id,
                    "asset_tag": asset.asset_tag,
                    "agent_uuid": None,
                    "hostname": None,
                    "serial_hint": asset.serial_number,
                    "org_hint": build_org_path(db, asset.org_node_id),
                    "location_hint": build_location_path(db, asset.location_node_id),
                    "confidence": 0,
                    "reasons": ["no active agent link"],
                    "candidate_type": "asset_without_agent",
                    "candidate_key": candidate_key,
                }
            )
    return items


def reject_matching_candidate(
    db: Session,
    candidate_key: str,
    decision: str,
    current_user: Optional[User] = None,
    asset_id: Optional[int] = None,
    agent_uuid: Optional[str] = None,
    reason: Optional[str] = None,
) -> AssetMatchingDecision:
    existing = db.query(AssetMatchingDecision).filter(AssetMatchingDecision.candidate_key == candidate_key).first()
    if existing:
        existing.decision = decision
        existing.reason = (reason or "").strip() or None
        existing.decided_by = current_user.id if current_user else None
        db.add(existing)
        db.commit()
        db.refresh(existing)
        return existing
    row = AssetMatchingDecision(
        candidate_key=candidate_key,
        asset_id=asset_id,
        agent_uuid=agent_uuid,
        decision=decision,
        reason=(reason or "").strip() or None,
        decided_by=current_user.id if current_user else None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_data_quality_issues(db: Session, issue_type: Optional[str] = None, asset_id: Optional[int] = None, status_value: str = "open") -> dict:
    query = db.query(AssetDataQualityIssue)
    if issue_type:
        query = query.filter(AssetDataQualityIssue.issue_type == issue_type)
    if asset_id:
        query = query.filter(AssetDataQualityIssue.asset_id == asset_id)
    if status_value:
        query = query.filter(AssetDataQualityIssue.status == status_value)
    rows = query.order_by(AssetDataQualityIssue.detected_at.desc()).all()
    asset_tag_map = {x.id: x.asset_tag for x in db.query(AssetRecord).filter(AssetRecord.id.in_([r.asset_id for r in rows])).all()} if rows else {}
    return {
        "items": [
            {
                "id": row.id,
                "asset_id": row.asset_id,
                "asset_tag": asset_tag_map.get(row.asset_id),
                "issue_type": row.issue_type,
                "severity": row.severity,
                "status": row.status,
                "summary": row.summary,
                "details_json": row.details_json,
                "detected_at": row.detected_at,
                "resolved_at": row.resolved_at,
                "resolved_by": row.resolved_by,
            }
            for row in rows
        ],
        "total": len(rows),
    }


def list_asset_change_log(db: Session, asset_id: int) -> dict:
    rows = db.query(AssetChangeLog).filter(AssetChangeLog.asset_id == asset_id).order_by(AssetChangeLog.changed_at.desc()).all()
    return {
        "items": [
            {
                "id": row.id,
                "asset_id": row.asset_id,
                "change_type": row.change_type,
                "field_name": row.field_name,
                "old_value": row.old_value,
                "new_value": row.new_value,
                "changed_by": row.changed_by,
                "changed_at": row.changed_at,
            }
            for row in rows
        ],
        "total": len(rows),
    }


def overview(db: Session) -> dict:
    total_assets = db.query(func.count(AssetRecord.id)).filter(AssetRecord.is_active.is_(True)).scalar() or 0
    matched_assets = (
        db.query(func.count(func.distinct(AssetAgentLink.asset_id)))
        .filter(AssetAgentLink.link_status == "active", AssetAgentLink.is_primary.is_(True))
        .scalar()
        or 0
    )
    unmatched_assets = max(0, int(total_assets) - int(matched_assets))
    linked_agent_count = (
        db.query(func.count(func.distinct(AssetAgentLink.agent_uuid)))
        .filter(AssetAgentLink.link_status == "active", AssetAgentLink.is_primary.is_(True))
        .scalar()
        or 0
    )
    total_agents = db.query(func.count(Agent.uuid)).scalar() or 0
    unmatched_agents = max(0, int(total_agents) - int(linked_agent_count))
    owner_missing_count = db.query(func.count(AssetRecord.id)).filter(AssetRecord.is_active.is_(True), AssetRecord.owner_person_id.is_(None)).scalar() or 0
    location_missing_count = db.query(func.count(AssetDataQualityIssue.id)).filter(AssetDataQualityIssue.issue_type == "missing_location", AssetDataQualityIssue.status == "open").scalar() or 0
    organization_distribution = [
        {"label": label, "value": int(value)}
        for label, value in (
            db.query(AssetOrganizationNode.name, func.count(AssetRecord.id))
            .join(AssetRecord, AssetRecord.org_node_id == AssetOrganizationNode.id)
            .group_by(AssetOrganizationNode.name)
            .order_by(func.count(AssetRecord.id).desc())
            .limit(10)
            .all()
        )
    ]
    location_distribution = [
        {"label": label, "value": int(value)}
        for label, value in (
            db.query(AssetLocationNode.name, func.count(AssetRecord.id))
            .join(AssetRecord, AssetRecord.location_node_id == AssetLocationNode.id)
            .group_by(AssetLocationNode.name)
            .order_by(func.count(AssetRecord.id).desc())
            .limit(10)
            .all()
        )
    ]
    recent_assets = [
        row.created_at
        for row in db.query(AssetRecord.created_at)
        .filter(AssetRecord.created_at.isnot(None))
        .order_by(AssetRecord.created_at.desc())
        .limit(512)
        .all()
    ]
    recent_matches = [
        row.linked_at
        for row in db.query(AssetAgentLink.linked_at)
        .filter(AssetAgentLink.link_status == "active", AssetAgentLink.linked_at.isnot(None))
        .order_by(AssetAgentLink.linked_at.desc())
        .limit(512)
        .all()
    ]
    recent_issues = [
        row.detected_at
        for row in db.query(AssetDataQualityIssue.detected_at)
        .filter(AssetDataQualityIssue.detected_at.isnot(None))
        .order_by(AssetDataQualityIssue.detected_at.desc())
        .limit(512)
        .all()
    ]
    organization_risk = [
        {"label": label, "value": int(value)}
        for label, value in (
            db.query(AssetOrganizationNode.name, func.count(AssetDataQualityIssue.id))
            .join(AssetRecord, AssetRecord.org_node_id == AssetOrganizationNode.id)
            .join(AssetDataQualityIssue, AssetDataQualityIssue.asset_id == AssetRecord.id)
            .filter(AssetDataQualityIssue.status == "open")
            .group_by(AssetOrganizationNode.name)
            .order_by(func.count(AssetDataQualityIssue.id).desc())
            .limit(8)
            .all()
        )
    ]
    location_risk = [
        {"label": label, "value": int(value)}
        for label, value in (
            db.query(AssetLocationNode.name, func.count(AssetDataQualityIssue.id))
            .join(AssetRecord, AssetRecord.location_node_id == AssetLocationNode.id)
            .join(AssetDataQualityIssue, AssetDataQualityIssue.asset_id == AssetRecord.id)
            .filter(AssetDataQualityIssue.status == "open")
            .group_by(AssetLocationNode.name)
            .order_by(func.count(AssetDataQualityIssue.id).desc())
            .limit(8)
            .all()
        )
    ]
    return {
        "total_assets": int(total_assets),
        "matched_assets": int(matched_assets),
        "unmatched_assets": int(unmatched_assets),
        "unmatched_agents": int(unmatched_agents),
        "owner_missing_count": int(owner_missing_count),
        "location_missing_count": int(location_missing_count),
        "organization_distribution": organization_distribution,
        "location_distribution": location_distribution,
        "asset_created_trend": _trend_points(recent_assets),
        "match_created_trend": _trend_points(recent_matches),
        "issue_detected_trend": _trend_points(recent_issues),
        "organization_risk": organization_risk,
        "location_risk": location_risk,
    }


def report_assets_by_organization(db: Session, org_node_id: Optional[int] = None) -> list[dict]:
    query = db.query(AssetOrganizationNode.name, func.count(AssetRecord.id)).join(AssetRecord, AssetRecord.org_node_id == AssetOrganizationNode.id)
    if org_node_id:
        query = query.filter(AssetRecord.org_node_id.in_(get_org_descendant_ids(db, org_node_id)))
    rows = query.group_by(AssetOrganizationNode.name).order_by(func.count(AssetRecord.id).desc()).all()
    return [{"label": label, "value": int(value)} for label, value in rows]


def report_assets_by_location(db: Session, location_node_id: Optional[int] = None) -> list[dict]:
    query = db.query(AssetLocationNode.name, func.count(AssetRecord.id)).join(AssetRecord, AssetRecord.location_node_id == AssetLocationNode.id)
    if location_node_id:
        query = query.filter(AssetRecord.location_node_id.in_(get_location_descendant_ids(db, location_node_id)))
    rows = query.group_by(AssetLocationNode.name).order_by(func.count(AssetRecord.id).desc()).all()
    return [{"label": label, "value": int(value)} for label, value in rows]


def report_assets_without_owner(db: Session) -> list[dict]:
    rows = db.query(AssetRecord).filter(AssetRecord.owner_person_id.is_(None), AssetRecord.is_active.is_(True)).all()
    return [{"label": row.asset_tag, "value": 1} for row in rows]


def report_assets_without_location(db: Session) -> list[dict]:
    rows = db.query(AssetDataQualityIssue).join(AssetRecord, AssetRecord.id == AssetDataQualityIssue.asset_id).filter(
        AssetDataQualityIssue.issue_type == "missing_location",
        AssetDataQualityIssue.status == "open",
    ).all()
    return [{"label": row.asset.asset_tag if row.asset else str(row.asset_id), "value": 1} for row in rows]


def report_matching_quality(db: Session) -> list[dict]:
    rows = (
        db.query(AssetAgentLink.match_source, func.count(AssetAgentLink.id))
        .filter(AssetAgentLink.link_status == "active")
        .group_by(AssetAgentLink.match_source)
        .all()
    )
    return [{"label": label or "unknown", "value": int(value)} for label, value in rows]


def bulk_update_assets(db: Session, asset_ids: Iterable[int], payload, current_user: Optional[User] = None) -> int:
    ids = sorted({int(x) for x in asset_ids if x})
    if not ids:
        raise HTTPException(status_code=400, detail="asset_ids gerekli")
    rows = db.query(AssetRecord).filter(AssetRecord.id.in_(ids)).all()
    changed = 0
    for row in rows:
        before = {
            "org_node_id": row.org_node_id,
            "location_node_id": row.location_node_id,
            "cost_center_id": row.cost_center_id,
            "primary_person_id": row.primary_person_id,
            "owner_person_id": row.owner_person_id,
            "support_team": row.support_team,
        }
        if payload.org_node_id is not None:
            row.org_node_id = payload.org_node_id
        if payload.location_node_id is not None:
            row.location_node_id = payload.location_node_id
        if payload.cost_center_id is not None:
            row.cost_center_id = payload.cost_center_id
        if payload.primary_person_id is not None:
            row.primary_person_id = payload.primary_person_id
        if payload.owner_person_id is not None:
            row.owner_person_id = payload.owner_person_id
        if payload.support_team is not None:
            row.support_team = (payload.support_team or "").strip() or None
        row.last_verified_at = utcnow()
        row.last_verified_by = current_user.id if current_user else None
        after = {
            "org_node_id": row.org_node_id,
            "location_node_id": row.location_node_id,
            "cost_center_id": row.cost_center_id,
            "primary_person_id": row.primary_person_id,
            "owner_person_id": row.owner_person_id,
            "support_team": row.support_team,
        }
        _log_asset_changes(db, row.id, current_user.id if current_user else None, before, after)
        recompute_asset_data_quality(db, row, resolved_by=current_user.id if current_user else None)
        db.add(row)
        changed += 1
    db.commit()
    return changed


def update_dictionaries(db: Session, payload) -> dict:
    mapping = {
        "device_types": payload.device_types,
        "usage_types": payload.usage_types,
        "ownership_types": payload.ownership_types,
        "lifecycle_statuses": payload.lifecycle_statuses,
    }
    for key, value in mapping.items():
        if value is None:
            continue
        normalized = [str(x).strip() for x in value if str(x).strip()]
        setting_key = f"asset_registry_{key}"
        row = db.query(Setting).filter(Setting.key == setting_key).first()
        if not row:
            row = Setting(key=setting_key, value="[]", description=f"Asset Registry dictionary for {key}", updated_at=utcnow())
        row.value = json.dumps(normalized, ensure_ascii=True)
        row.updated_at = utcnow()
        db.add(row)
    db.commit()
    return get_dictionaries(db)


def update_node_type_labels(db: Session, payload) -> dict:
    updates = (
        (payload.organization_node_types, AssetOrganizationNodeType, "organizasyon"),
        (payload.location_node_types, AssetLocationNodeType, "lokasyon"),
    )
    for items, model, label in updates:
        seen: set[str] = set()
        for item in items or []:
            code = (item.code or "").strip().lower()
            display_name = (item.display_name or "").strip()
            if not code or not display_name:
                raise HTTPException(status_code=400, detail="Node label guncellemesi icin code ve display_name gerekli")
            if code in seen:
                raise HTTPException(status_code=400, detail=f"Ayni {label} node code birden fazla kez gonderildi")
            seen.add(code)
            row = db.query(model).filter(model.code == code).first()
            if not row:
                raise HTTPException(status_code=404, detail=f"Node type bulunamadi: {code}")
            row.display_name = display_name
            db.add(row)
    db.commit()
    return get_dictionaries(db)

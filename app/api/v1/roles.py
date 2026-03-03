from __future__ import annotations

import json
import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import require_permission
from app.database import get_db
from app.models import RoleProfile, User
from app.permissions import ALL_PERMISSIONS, PERMISSION_CATALOG
from app.schemas import (
    MessageResponse,
    RoleProfileCreateRequest,
    RoleProfileListResponse,
    RoleProfileResponse,
    RoleProfileUpdateRequest,
)
from app.services import audit_service as audit

router = APIRouter(prefix="/roles", tags=["roles"])
ADMIN_ROLE = Depends(require_permission("roles.manage"))
ROLE_OR_USER_MANAGE = Depends(require_permission("roles.manage", "users.manage"))
KEY_RE = re.compile(r"^[a-z0-9_\-]+$")


def _normalize_permissions(values: list[str] | None) -> list[str]:
    out: list[str] = []
    for raw in values or []:
        p = (raw or "").strip()
        if not p:
            continue
        if p != "*" and p not in ALL_PERMISSIONS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown permission: {p}")
        if p not in out:
            out.append(p)
    return out


def _normalize_key(value: str | None) -> str:
    key = (value or "").strip().lower()
    if not key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Role key is required")
    if not KEY_RE.match(key):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Role key format is invalid")
    return key


@router.get("", response_model=RoleProfileListResponse)
def list_roles(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    _: User = ROLE_OR_USER_MANAGE,
) -> RoleProfileListResponse:
    q = db.query(RoleProfile)
    if not include_inactive:
        q = q.filter(RoleProfile.is_active.is_(True))
    items = q.order_by(RoleProfile.is_system.desc(), RoleProfile.name.asc()).all()
    return RoleProfileListResponse(items=[RoleProfileResponse.model_validate(x) for x in items], total=len(items))


@router.get("/catalog")
def role_permission_catalog(
    _: User = ADMIN_ROLE,
) -> dict:
    return {
        "items": [
            {
                "group": group.get("group") or "",
                "permissions": [
                    {"key": key, "label": label}
                    for key, label in (group.get("permissions") or [])
                ],
            }
            for group in PERMISSION_CATALOG
        ],
        "total": len(ALL_PERMISSIONS),
    }


@router.post("", response_model=RoleProfileResponse, status_code=201)
def create_role(
    payload: RoleProfileCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = ADMIN_ROLE,
) -> RoleProfileResponse:
    key = _normalize_key(payload.key)
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Role name is required")
    if db.query(RoleProfile.id).filter(func.lower(RoleProfile.key) == key.lower()).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Role key already exists")
    if db.query(RoleProfile.id).filter(func.lower(RoleProfile.name) == name.lower()).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Role name already exists")

    role = RoleProfile(
        key=key,
        name=name,
        description=(payload.description or "").strip() or None,
        permissions_json=json.dumps(_normalize_permissions(payload.permissions), ensure_ascii=True),
        is_system=False,
        is_active=bool(payload.is_active),
    )
    db.add(role)
    db.commit()
    db.refresh(role)
    audit.record_audit(
        db,
        user_id=current_user.id,
        action="role_profile.create",
        resource_type="role_profile",
        resource_id=str(role.id),
        details={"key": role.key, "name": role.name},
    )
    return RoleProfileResponse.model_validate(role)


@router.put("/{role_id}", response_model=RoleProfileResponse)
def update_role(
    role_id: int,
    payload: RoleProfileUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = ADMIN_ROLE,
) -> RoleProfileResponse:
    role = db.query(RoleProfile).filter(RoleProfile.id == role_id).first()
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")

    if role.is_system and payload.is_active is False:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="System role cannot be deactivated")

    if payload.name is not None:
        name = (payload.name or "").strip()
        if not name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Role name is required")
        exists = (
            db.query(RoleProfile.id)
            .filter(RoleProfile.id != role.id, func.lower(RoleProfile.name) == name.lower())
            .first()
        )
        if exists:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Role name already exists")
        role.name = name

    if payload.description is not None:
        role.description = (payload.description or "").strip() or None

    if payload.permissions is not None:
        role.permissions_json = json.dumps(_normalize_permissions(payload.permissions), ensure_ascii=True)

    if payload.is_active is not None:
        role.is_active = bool(payload.is_active)
        if not role.is_active:
            in_use = db.query(func.count(User.id)).filter(User.role_profile_id == role.id).scalar() or 0
            if in_use > 0:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Role is in use by users")

    db.add(role)
    db.commit()
    db.refresh(role)
    audit.record_audit(
        db,
        user_id=current_user.id,
        action="role_profile.update",
        resource_type="role_profile",
        resource_id=str(role.id),
        details={"key": role.key, "name": role.name, "is_active": role.is_active},
    )
    return RoleProfileResponse.model_validate(role)


@router.delete("/{role_id}", response_model=MessageResponse)
def delete_role(
    role_id: int,
    db: Session = Depends(get_db),
    current_user: User = ADMIN_ROLE,
) -> MessageResponse:
    role = db.query(RoleProfile).filter(RoleProfile.id == role_id).first()
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    if role.is_system:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="System role cannot be deleted")

    in_use = db.query(func.count(User.id)).filter(User.role_profile_id == role.id).scalar() or 0
    if in_use > 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Role is in use by users")

    role.is_active = False
    db.add(role)
    db.commit()
    audit.record_audit(
        db,
        user_id=current_user.id,
        action="role_profile.deactivate",
        resource_type="role_profile",
        resource_id=str(role.id),
        details={"key": role.key, "name": role.name},
    )
    return MessageResponse(status="success", message="Role deactivated")

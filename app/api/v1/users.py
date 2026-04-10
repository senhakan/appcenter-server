from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_password_hash, require_permission, user_permissions
from app.database import get_db
from app.models import RoleProfile, User
from app.schemas import MessageResponse, UserCreateRequest, UserListResponse, UserPublic, UserUpdateRequest
from app.services import audit_service as audit

router = APIRouter(prefix="/users", tags=["users"])
ADMIN_ROLE = Depends(require_permission("users.manage"))
VALID_ROLES = {"admin", "operator", "viewer"}


def _legacy_role_from_profile_key(profile_key: str | None) -> str:
    key = (profile_key or "").strip().lower()
    if key in VALID_ROLES:
        return key
    return "viewer"


def _resolve_role_profile(db: Session, role_profile_id: int | None) -> RoleProfile | None:
    if role_profile_id is None:
        return None
    role = db.query(RoleProfile).filter(RoleProfile.id == int(role_profile_id)).first()
    if not role:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Role profile not found")
    if not role.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Role profile is inactive")
    return role


def _resolve_role_profile_by_key(db: Session, role_key: str | None) -> RoleProfile | None:
    key = (role_key or "").strip().lower()
    if not key:
        return None
    role = db.query(RoleProfile).filter(func.lower(RoleProfile.key) == key).first()
    if not role:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Role profile not found")
    if not role.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Role profile is inactive")
    return role


def _to_user_public(db: Session, user: User) -> UserPublic:
    role_profile = None
    if user.role_profile_id:
        role_profile = db.query(RoleProfile).filter(RoleProfile.id == user.role_profile_id).first()
    return UserPublic(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        email=user.email,
        phone=user.phone,
        phone_ext=user.phone_ext,
        organization=user.organization,
        department=user.department,
        avatar_url=user.avatar_url,
        auth_source=user.auth_source,
        role=user.role,
        role_profile_id=role_profile.id if role_profile else None,
        role_profile_key=role_profile.key if role_profile else None,
        role_profile_name=role_profile.name if role_profile else None,
        permissions=sorted(list(user_permissions(db, user))),
        is_active=user.is_active,
    )


def _active_admin_count(db: Session) -> int:
    return db.query(func.count(User.id)).filter(User.role == "admin", User.is_active.is_(True)).scalar() or 0


def _assert_last_admin_not_removed(
    db: Session,
    target: User,
    new_role: str | None = None,
    new_is_active: bool | None = None,
) -> None:
    role_after = new_role if new_role is not None else target.role
    active_after = new_is_active if new_is_active is not None else bool(target.is_active)
    if target.role == "admin" and bool(target.is_active):
        if role_after != "admin" or not active_after:
            if _active_admin_count(db) <= 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="At least one active admin user is required",
                )


@router.get("", response_model=UserListResponse)
def list_users(
    db: Session = Depends(get_db),
    _: User = ADMIN_ROLE,
) -> UserListResponse:
    items = db.query(User).order_by(User.username.asc()).all()
    mapped = [_to_user_public(db, item) for item in items]
    return UserListResponse(items=mapped, total=len(mapped))


@router.post("", response_model=UserPublic, status_code=201)
def create_user(
    payload: UserCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = ADMIN_ROLE,
) -> UserPublic:
    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username is required")
    exists = db.query(User.id).filter(func.lower(User.username) == username.lower()).first()
    if exists:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")

    role_profile = _resolve_role_profile(db, payload.role_profile_id)
    if role_profile is None:
        role_profile = _resolve_role_profile_by_key(db, payload.role)
    if role_profile is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Role profile is required")
    role = _legacy_role_from_profile_key(role_profile.key)
    user = User(
        username=username,
        password_hash=get_password_hash(payload.password),
        full_name=(payload.full_name or "").strip() or None,
        email=(payload.email or "").strip() or None,
        role=role,
        role_profile_id=role_profile.id,
        is_active=bool(payload.is_active),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    audit.record_audit(
        db,
        user_id=current_user.id,
        action="user.create",
        resource_type="user",
        resource_id=str(user.id),
        details={
            "username": user.username,
            "role": user.role,
            "role_profile_id": user.role_profile_id,
            "is_active": user.is_active,
        },
    )
    return _to_user_public(db, user)


@router.put("/{user_id}", response_model=UserPublic)
def update_user(
    user_id: int,
    payload: UserUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = ADMIN_ROLE,
) -> UserPublic:
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if payload.username is not None:
        username = payload.username.strip()
        if not username:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username is required")
        exists = (
            db.query(User.id)
            .filter(User.id != user_id, func.lower(User.username) == username.lower())
            .first()
        )
        if exists:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")
        target.username = username

    next_role: str | None = None
    next_role_profile_id: int | None = None
    if payload.role_profile_id is not None:
        role_profile = _resolve_role_profile(db, payload.role_profile_id)
        if role_profile is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Role profile not found")
        next_role = _legacy_role_from_profile_key(role_profile.key)
        next_role_profile_id = role_profile.id
    elif payload.role is not None:
        role_profile = _resolve_role_profile_by_key(db, payload.role)
        if role_profile is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Role profile not found")
        next_role = _legacy_role_from_profile_key(role_profile.key)
        next_role_profile_id = role_profile.id

    next_active: bool | None = None
    if payload.is_active is not None:
        next_active = bool(payload.is_active)

    _assert_last_admin_not_removed(db, target, new_role=next_role, new_is_active=next_active)

    if next_role is not None:
        target.role = next_role
        target.role_profile_id = next_role_profile_id
    if next_active is not None:
        target.is_active = next_active
    if payload.password is not None:
        if (target.auth_source or "local").strip().lower() == "ldap":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password cannot be set for LDAP users")
        target.password_hash = get_password_hash(payload.password)
    if payload.full_name is not None:
        target.full_name = payload.full_name.strip() or None
    if payload.email is not None:
        target.email = payload.email.strip() or None

    db.add(target)
    db.commit()
    db.refresh(target)
    audit.record_audit(
        db,
        user_id=current_user.id,
        action="user.update",
        resource_type="user",
        resource_id=str(target.id),
        details={
            "username": target.username,
            "role": target.role,
            "role_profile_id": target.role_profile_id,
            "is_active": target.is_active,
        },
    )
    return _to_user_public(db, target)


@router.delete("/{user_id}", response_model=MessageResponse)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = ADMIN_ROLE,
) -> MessageResponse:
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    _assert_last_admin_not_removed(db, target, new_role="viewer", new_is_active=False)
    db.delete(target)
    db.commit()
    audit.record_audit(
        db,
        user_id=current_user.id,
        action="user.delete",
        resource_type="user",
        resource_id=str(user_id),
        details={"username": target.username},
    )
    return MessageResponse(status="success", message="User deleted")

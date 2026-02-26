from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_password_hash, require_role
from app.database import get_db
from app.models import User
from app.schemas import MessageResponse, UserCreateRequest, UserListResponse, UserPublic, UserUpdateRequest
from app.services import audit_service as audit

router = APIRouter(prefix="/users", tags=["users"])
ADMIN_ROLE = Depends(require_role("admin"))
VALID_ROLES = {"admin", "operator", "viewer"}


def _normalize_role(raw_role: str | None) -> str:
    role = (raw_role or "").strip().lower()
    if role not in VALID_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid role",
        )
    return role


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
    mapped = [UserPublic.model_validate(item) for item in items]
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

    role = _normalize_role(payload.role)
    user = User(
        username=username,
        password_hash=get_password_hash(payload.password),
        full_name=(payload.full_name or "").strip() or None,
        email=(payload.email or "").strip() or None,
        role=role,
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
        details={"username": user.username, "role": user.role, "is_active": user.is_active},
    )
    return UserPublic.model_validate(user)


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
    if payload.role is not None:
        next_role = _normalize_role(payload.role)

    next_active: bool | None = None
    if payload.is_active is not None:
        next_active = bool(payload.is_active)

    _assert_last_admin_not_removed(db, target, new_role=next_role, new_is_active=next_active)

    if next_role is not None:
        target.role = next_role
    if next_active is not None:
        target.is_active = next_active
    if payload.password is not None:
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
        details={"username": target.username, "role": target.role, "is_active": target.is_active},
    )
    return UserPublic.model_validate(target)


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

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.auth import (
    authenticate_user,
    create_access_token_with_exp,
    get_current_user,
    get_password_hash,
    user_permissions,
    verify_password,
)
from app.config import get_settings
from app.database import get_db
from app.models import Setting, User
from app.schemas import (
    LoginRequest,
    MessageResponse,
    PasswordChangeRequest,
    ProfileUpdateRequest,
    TokenResponse,
    UserPublic,
)
from app.services import audit_service as audit
from app.services import ldap_service
from app.utils.file_handler import save_avatar_file

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()

MIN_SESSION_TIMEOUT_MINUTES = 1
MAX_SESSION_TIMEOUT_MINUTES = 1440


def _resolve_session_timeout_minutes(db: Session) -> int:
    item = db.query(Setting).filter(Setting.key == "session_timeout_minutes").first()
    raw = (item.value or "").strip() if item else ""
    if not raw:
        return max(int(settings.jwt_expire_minutes), MIN_SESSION_TIMEOUT_MINUTES)
    try:
        value = int(raw)
    except Exception:
        return max(int(settings.jwt_expire_minutes), MIN_SESSION_TIMEOUT_MINUTES)
    if value < MIN_SESSION_TIMEOUT_MINUTES or value > MAX_SESSION_TIMEOUT_MINUTES:
        return max(int(settings.jwt_expire_minutes), MIN_SESSION_TIMEOUT_MINUTES)
    return value


def _issue_token_response(username: str, db: Session, auth_source: str = "local") -> TokenResponse:
    timeout_minutes = _resolve_session_timeout_minutes(db)
    token, expires_at = create_access_token_with_exp(
        {"sub": username},
        expires_delta=timedelta(minutes=timeout_minutes),
    )
    return TokenResponse(
        access_token=token,
        expires_at=expires_at,
        expires_in_sec=timeout_minutes * 60,
        auth_source=auth_source,
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    ldap_is_enabled = ldap_service.ldap_enabled(db)
    local_allowed = (not ldap_is_enabled) or ldap_service.allow_local_fallback(db)
    user = authenticate_user(db, payload.username, payload.password) if local_allowed else None
    if user:
        user.last_login = datetime.now(timezone.utc)
        db.add(user)
        db.commit()
        audit.record_audit(
            db,
            user_id=user.id,
            action="auth.login.local",
            resource_type="auth",
            resource_id=str(user.id),
            details={"username": user.username, "auth_source": "local"},
        )
        return _issue_token_response(user.username, db, auth_source="local")

    if ldap_is_enabled:
        try:
            identity = ldap_service.authenticate_directory_user(payload.username, payload.password, db)
            ldap_user = ldap_service.sync_authenticated_user(db, identity)
            if ldap_user:
                audit.record_audit(
                    db,
                    user_id=ldap_user.id,
                    action="auth.login.ldap",
                    resource_type="auth",
                    resource_id=str(ldap_user.id),
                    details={
                        "username": ldap_user.username,
                        "auth_source": "ldap",
                        "ldap_dn": identity.dn,
                        "groups": identity.groups or [],
                    },
                )
                return _issue_token_response(ldap_user.username, db, auth_source="ldap")
        except ldap_service.LdapConfigurationError as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
        except ldap_service.LdapError:
            pass
        except Exception:
            pass

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect username or password",
    )


@router.post("/extend", response_model=TokenResponse)
def extend_session(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TokenResponse:
    return _issue_token_response(user.username, db)


def _to_user_public(db: Session, user: User) -> UserPublic:
    role_profile = user.role_profile
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
        role_profile_id=role_profile.id if role_profile else user.role_profile_id,
        role_profile_key=role_profile.key if role_profile else None,
        role_profile_name=role_profile.name if role_profile else None,
        permissions=sorted(list(user_permissions(db, user))),
        is_active=user.is_active,
    )


@router.get("/me", response_model=UserPublic)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserPublic:
    return _to_user_public(db, user)


@router.put("/profile", response_model=UserPublic)
def update_profile(
    payload: ProfileUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UserPublic:
    if payload.full_name is not None:
        user.full_name = (payload.full_name or "").strip() or None
    if payload.email is not None:
        user.email = (payload.email or "").strip() or None
    if payload.phone is not None:
        user.phone = (payload.phone or "").strip() or None
    if payload.phone_ext is not None:
        user.phone_ext = (payload.phone_ext or "").strip() or None
    if payload.organization is not None:
        user.organization = (payload.organization or "").strip() or None
    if payload.department is not None:
        user.department = (payload.department or "").strip() or None
    db.add(user)
    db.commit()
    db.refresh(user)
    return _to_user_public(db, user)


@router.put("/password", response_model=MessageResponse)
def change_password(
    payload: PasswordChangeRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MessageResponse:
    if (user.auth_source or "local").strip().lower() == "ldap":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password change is not allowed for LDAP users",
        )
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New password must be different")
    user.password_hash = get_password_hash(payload.new_password)
    db.add(user)
    db.commit()
    return MessageResponse(status="success", message="Password updated")


@router.put("/avatar", response_model=UserPublic)
async def upload_avatar(
    avatar: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UserPublic:
    old_avatar = (user.avatar_url or "").strip()
    _name, avatar_url = await save_avatar_file(
        avatar_file=avatar,
        upload_dir=settings.upload_dir,
        max_avatar_size=settings.max_icon_size,
        user_id=user.id,
    )
    user.avatar_url = avatar_url
    db.add(user)
    db.commit()
    db.refresh(user)

    if old_avatar.startswith("/uploads/avatars/"):
        old_name = old_avatar.split("/uploads/avatars/", 1)[-1].strip()
        if old_name:
            old_path = Path(settings.upload_dir) / "avatars" / old_name
            old_path.unlink(missing_ok=True)
    return _to_user_public(db, user)


@router.delete("/avatar", response_model=UserPublic)
def delete_avatar(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UserPublic:
    old_avatar = (user.avatar_url or "").strip()
    user.avatar_url = None
    db.add(user)
    db.commit()
    db.refresh(user)

    if old_avatar.startswith("/uploads/avatars/"):
        old_name = old_avatar.split("/uploads/avatars/", 1)[-1].strip()
        if old_name:
            old_path = Path(settings.upload_dir) / "avatars" / old_name
            old_path.unlink(missing_ok=True)
    return _to_user_public(db, user)

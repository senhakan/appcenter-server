from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import RoleProfile, User
from app.permissions import SYSTEM_ROLE_DEFAULTS

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
settings = get_settings()
ROLE_LEVELS = {"viewer": 10, "operator": 20, "admin": 30}

DEFAULT_PERMISSIONS_BY_ROLE = SYSTEM_ROLE_DEFAULTS


class TokenPayload(dict):
    sub: str


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    token, _ = create_access_token_with_exp(data, expires_delta=expires_delta)
    return token


def create_access_token_with_exp(
    data: dict[str, Any], expires_delta: Optional[timedelta] = None
) -> tuple[str, datetime]:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta if expires_delta else timedelta(minutes=settings.jwt_expire_minutes)
    )
    to_encode.update({"exp": expire})
    token = jwt.encode(to_encode, settings.secret_key, algorithm=settings.jwt_algorithm)
    return token, expire


def decode_access_token(token: str) -> str:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
        username = payload.get("sub")
        if not username:
            raise credentials_exception
        return username
    except JWTError as exc:
        raise credentials_exception from exc


def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return None
    if not user.is_active:
        return None
    if (user.auth_source or "local").strip().lower() != "local":
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    username = decode_access_token(token)
    user = db.query(User).filter(User.username == username).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Inactive or missing user",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def _load_role_profile(db: Session, user: User) -> RoleProfile | None:
    if user.role_profile is not None:
        return user.role_profile
    if not user.role_profile_id:
        return None
    return db.query(RoleProfile).filter(RoleProfile.id == user.role_profile_id).first()


def user_permissions(db: Session, user: User) -> set[str]:
    rp = _load_role_profile(db, user)
    if not rp:
        return set()
    return {p.strip() for p in (rp.permissions or []) if p and str(p).strip()}


def require_role(*roles: str) -> Callable[..., User]:
    allowed = {role.strip().lower() for role in roles if role and role.strip()}
    if not allowed:
        raise ValueError("At least one role must be provided")

    def _dependency(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
        role = (user.role or "").strip().lower()
        if role not in ROLE_LEVELS:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        rp = _load_role_profile(db, user)
        if rp is not None and not rp.is_system:
            # Custom profiles must pass explicit permission checks.
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        if role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user

    return _dependency


def require_permission(*permissions: str) -> Callable[..., User]:
    needed = {p.strip() for p in permissions if p and p.strip()}
    if not needed:
        raise ValueError("At least one permission must be provided")

    def _dependency(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
        perms = user_permissions(db, user)
        if "*" in perms:
            return user
        if not any(p in perms for p in needed):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user

    return _dependency

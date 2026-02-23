from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import authenticate_user, create_access_token_with_exp, get_current_user
from app.config import get_settings
from app.database import get_db
from app.models import Setting, User
from app.schemas import LoginRequest, TokenResponse

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


def _issue_token_response(username: str, db: Session) -> TokenResponse:
    timeout_minutes = _resolve_session_timeout_minutes(db)
    token, expires_at = create_access_token_with_exp(
        {"sub": username},
        expires_delta=timedelta(minutes=timeout_minutes),
    )
    return TokenResponse(
        access_token=token,
        expires_at=expires_at,
        expires_in_sec=timeout_minutes * 60,
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = authenticate_user(db, payload.username, payload.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    user.last_login = datetime.now(timezone.utc)
    db.add(user)
    db.commit()

    return _issue_token_response(user.username, db)


@router.post("/extend", response_model=TokenResponse)
def extend_session(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TokenResponse:
    return _issue_token_response(user.username, db)

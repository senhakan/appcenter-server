from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth import require_permission
from app.database import get_db
from app.models import AuditLog, User
from app.schemas import AuditLogItemResponse, AuditLogListResponse

router = APIRouter(prefix="/audit", tags=["audit"])


def _parse_created_at(value: str, *, is_end: bool) -> tuple[datetime, bool]:
    raw = (value or "").strip()
    if not raw:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid date filter")
    try:
        if len(raw) == 10:
            base = datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if is_end:
                return base + timedelta(days=1), True
            return base, False
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt, False
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid date filter") from exc


@router.get("/logs", response_model=AuditLogListResponse)
def list_audit_logs(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    action: str = Query(default="", max_length=120),
    resource_type: str = Query(default="", max_length=120),
    username: str = Query(default="", max_length=120),
    created_from: str = Query(default="", max_length=40),
    created_to: str = Query(default="", max_length=40),
    _: User = Depends(require_permission("audit.view")),
    db: Session = Depends(get_db),
) -> AuditLogListResponse:
    q = db.query(AuditLog)

    action_val = action.strip()
    if action_val:
        q = q.filter(AuditLog.action.ilike(f"%{action_val}%"))

    resource_val = resource_type.strip()
    if resource_val:
        q = q.filter(AuditLog.resource_type.ilike(f"%{resource_val}%"))

    username_val = username.strip()
    if username_val:
        q = q.join(User, User.id == AuditLog.user_id).filter(User.username.ilike(f"%{username_val}%"))

    created_from_val = created_from.strip()
    if created_from_val:
        created_from_dt, _ = _parse_created_at(created_from_val, is_end=False)
        q = q.filter(AuditLog.created_at >= created_from_dt)

    created_to_val = created_to.strip()
    if created_to_val:
        created_to_dt, is_date_end = _parse_created_at(created_to_val, is_end=True)
        if is_date_end:
            q = q.filter(AuditLog.created_at < created_to_dt)
        else:
            q = q.filter(AuditLog.created_at <= created_to_dt)

    total = q.count()
    rows = q.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).offset(offset).limit(limit).all()

    user_ids = sorted({row.user_id for row in rows if row.user_id is not None})
    users = db.query(User).filter(User.id.in_(user_ids)).all() if user_ids else []
    usernames = {item.id: item.username for item in users}

    items = [
        AuditLogItemResponse(
            id=row.id,
            user_id=row.user_id,
            username=usernames.get(row.user_id) if row.user_id is not None else None,
            action=row.action,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            details_json=row.details_json,
            created_at=row.created_at,
        )
        for row in rows
    ]
    return AuditLogListResponse(items=items, total=total)

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth import require_role
from app.database import get_db
from app.models import AuditLog, User
from app.schemas import AuditLogItemResponse, AuditLogListResponse

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/logs", response_model=AuditLogListResponse)
def list_audit_logs(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    action: str = Query(default="", max_length=120),
    resource_type: str = Query(default="", max_length=120),
    username: str = Query(default="", max_length=120),
    _: User = Depends(require_role("admin")),
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

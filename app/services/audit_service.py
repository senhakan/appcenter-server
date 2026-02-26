from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models import AuditLog

logger = logging.getLogger("appcenter.audit")


def record_audit(
    db: Session,
    *,
    user_id: Optional[int],
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
) -> None:
    try:
        payload = json.dumps(details or {}, ensure_ascii=True)
        db.add(
            AuditLog(
                user_id=user_id,
                action=action,
                resource_type=resource_type,
                resource_id=(str(resource_id) if resource_id is not None else None),
                details_json=payload,
                created_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("audit log write failed action=%s resource=%s id=%s err=%s", action, resource_type, resource_id, exc)

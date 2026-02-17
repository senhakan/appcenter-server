from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import AgentSystemProfileHistory


def get_agent_system_history(
    db: Session,
    agent_uuid: str,
    limit: int,
    offset: int,
) -> tuple[list[AgentSystemProfileHistory], int]:
    q = db.query(AgentSystemProfileHistory).filter(AgentSystemProfileHistory.agent_uuid == agent_uuid)
    total = q.count()
    items = (
        q.order_by(AgentSystemProfileHistory.detected_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return items, total


def cleanup_old_system_history(db: Session, retention_days: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    count = db.query(AgentSystemProfileHistory).filter(
        AgentSystemProfileHistory.detected_at < cutoff
    ).delete()
    db.commit()
    return count


def cleanup_old_identity_history(db: Session, retention_days: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    res = db.execute(
        text("DELETE FROM agent_identity_history WHERE detected_at < :cutoff"),
        {"cutoff": cutoff},
    )
    count = res.rowcount or 0
    db.commit()
    return count

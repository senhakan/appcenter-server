from __future__ import annotations

from datetime import datetime, timedelta, timezone

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


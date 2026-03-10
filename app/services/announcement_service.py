from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models import Agent, AgentGroup, Announcement, AnnouncementDelivery, Group
from app.services.ws_manager import make_message, ws_manager

logger = logging.getLogger("appcenter.announcement")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _pending_count(db: Session, announcement_id: int) -> int:
    return (
        db.query(AnnouncementDelivery)
        .filter(
            AnnouncementDelivery.announcement_id == announcement_id,
            AnnouncementDelivery.status == "pending",
        )
        .count()
    )


def _get_announcement_or_error(db: Session, announcement_id: int) -> Announcement:
    announcement = db.query(Announcement).filter(Announcement.id == announcement_id).first()
    if not announcement:
        raise ValueError("Announcement not found")
    return announcement


def create_announcement(
    db: Session,
    title: str,
    message: str,
    priority: str,
    target_type: str,
    target_id: Optional[str],
    delivery_mode: str,
    scheduled_at: Optional[datetime],
    expires_at: Optional[datetime],
    created_by_id: Optional[int],
) -> Announcement:
    now = _utcnow()
    scheduled_at_utc = _as_utc(scheduled_at)
    expires_at_utc = _as_utc(expires_at)

    if target_type == "Group":
        if not target_id:
            raise ValueError("target_id is required for Group target_type")
        try:
            group_id = int(str(target_id).strip())
        except Exception as exc:
            raise ValueError("target_id must be a valid group id for Group target_type") from exc
        group = db.query(Group).filter(Group.id == group_id).first()
        if not group:
            raise ValueError("Group target does not exist")
        target_id = str(group_id)
    elif target_type == "Agent":
        if not target_id:
            raise ValueError("target_id is required for Agent target_type")
        agent = db.query(Agent).filter(Agent.uuid == target_id).first()
        if not agent:
            raise ValueError("Agent target does not exist")
    elif target_type != "All":
        raise ValueError("Invalid target_type")

    if scheduled_at_utc is not None and scheduled_at_utc <= now:
        raise ValueError("scheduled_at must be in the future")
    compare_start = scheduled_at_utc or now
    if expires_at_utc is not None and expires_at_utc <= compare_start:
        raise ValueError("expires_at must be after scheduled_at")

    announcement = Announcement(
        title=title,
        message=message,
        priority=priority,
        target_type=target_type,
        target_id=target_id,
        delivery_mode=delivery_mode,
        scheduled_at=scheduled_at_utc,
        expires_at=expires_at_utc,
        created_by=created_by_id,
        status="scheduled" if scheduled_at_utc is not None else "publishing",
    )
    db.add(announcement)
    db.flush()

    if scheduled_at_utc is None:
        publish_announcement(db, announcement)
    else:
        db.commit()
        db.refresh(announcement)

    return announcement


def update_announcement(db: Session, announcement_id: int, **kwargs: Any) -> Announcement:
    announcement = _get_announcement_or_error(db, announcement_id)
    if announcement.status != "scheduled":
        raise ValueError("Only scheduled announcements can be updated")

    next_target_type = kwargs.get("target_type", announcement.target_type)
    next_target_id = kwargs.get("target_id", announcement.target_id)
    next_scheduled_at = _as_utc(kwargs.get("scheduled_at", announcement.scheduled_at))
    next_expires_at = _as_utc(kwargs.get("expires_at", announcement.expires_at))
    now = _utcnow()

    if next_target_type == "Group":
        if not next_target_id:
            raise ValueError("target_id is required for Group target_type")
        try:
            group_id = int(str(next_target_id).strip())
        except Exception as exc:
            raise ValueError("target_id must be a valid group id for Group target_type") from exc
        group = db.query(Group).filter(Group.id == group_id).first()
        if not group:
            raise ValueError("Group target does not exist")
        kwargs["target_id"] = str(group_id)
    elif next_target_type == "Agent":
        if not next_target_id:
            raise ValueError("target_id is required for Agent target_type")
        agent = db.query(Agent).filter(Agent.uuid == str(next_target_id)).first()
        if not agent:
            raise ValueError("Agent target does not exist")
    elif next_target_type != "All":
        raise ValueError("Invalid target_type")

    if next_scheduled_at is not None and next_scheduled_at <= now:
        raise ValueError("scheduled_at must be in the future")

    compare_start = next_scheduled_at or now
    if next_expires_at is not None and next_expires_at <= compare_start:
        raise ValueError("expires_at must be after scheduled_at")

    for key, value in kwargs.items():
        if key in {"scheduled_at", "expires_at"}:
            setattr(announcement, key, _as_utc(value))
        else:
            setattr(announcement, key, value)

    db.add(announcement)
    db.commit()
    db.refresh(announcement)
    return announcement


def cancel_announcement(db: Session, announcement_id: int) -> Announcement:
    announcement = _get_announcement_or_error(db, announcement_id)
    if announcement.status in {"completed", "cancelled"}:
        raise ValueError("Announcement cannot be cancelled in current status")

    now = _utcnow()
    announcement.status = "cancelled"
    announcement.cancelled_at = now
    db.add(announcement)

    pending_deliveries = (
        db.query(AnnouncementDelivery)
        .filter(
            AnnouncementDelivery.announcement_id == announcement.id,
            AnnouncementDelivery.status == "pending",
        )
        .all()
    )
    for delivery in pending_deliveries:
        delivery.status = "cancelled"
        db.add(delivery)

    db.commit()
    db.refresh(announcement)
    _broadcast_delivery_update(announcement)
    return announcement


def publish_announcement(db: Session, announcement: Announcement) -> None:
    now = _utcnow()
    announcement.status = "publishing"
    announcement.published_at = now
    db.add(announcement)
    db.flush()

    targets = resolve_targets(db, announcement.target_type, announcement.target_id)
    unique_targets = list(dict.fromkeys(targets))
    deliveries = [
        AnnouncementDelivery(
            announcement_id=announcement.id,
            agent_uuid=agent_uuid,
            status="pending",
        )
        for agent_uuid in unique_targets
    ]
    if deliveries:
        db.bulk_save_objects(deliveries)
        db.flush()

    announcement.total_targets = len(unique_targets)
    announcement.delivered_count = 0
    announcement.acknowledged_count = 0
    announcement.failed_count = 0
    db.add(announcement)
    db.flush()

    db_deliveries = (
        db.query(AnnouncementDelivery)
        .filter(AnnouncementDelivery.announcement_id == announcement.id)
        .all()
    )
    for delivery in db_deliveries:
        deliver_to_agent(db, announcement, delivery)

    announcement.status = "published"
    db.add(announcement)
    db.commit()
    db.refresh(announcement)
    _check_and_complete(db, announcement)
    _broadcast_delivery_update(announcement)


def resolve_targets(db: Session, target_type: str, target_id: Optional[str]) -> list[str]:
    if target_type == "All":
        rows = db.query(Agent.uuid).all()
        return [str(row[0]) for row in rows if row and row[0]]

    if target_type == "Group":
        if not target_id:
            return []
        try:
            group_id = int(str(target_id).strip())
        except Exception:
            return []
        rows = (
            db.query(Agent.uuid)
            .join(AgentGroup, AgentGroup.agent_uuid == Agent.uuid)
            .filter(AgentGroup.group_id == group_id)
            .all()
        )
        return [str(row[0]) for row in rows if row and row[0]]

    if target_type == "Agent":
        if not target_id:
            return []
        exists = db.query(Agent.uuid).filter(Agent.uuid == target_id).first()
        return [str(target_id)] if exists else []

    return []


def deliver_to_agent(db: Session, announcement: Announcement, delivery: AnnouncementDelivery) -> str:
    if delivery.status != "pending":
        return delivery.status

    now = _utcnow()
    connected = ws_manager.is_agent_connected(delivery.agent_uuid)
    if connected:
        ws_manager.schedule_send_to_agent(
            delivery.agent_uuid,
            make_message(
                "server.announcement.push",
                {
                    "announcement_id": announcement.id,
                    "title": announcement.title,
                    "message": announcement.message,
                    "priority": announcement.priority,
                },
            ),
        )
        delivery.status = "delivered"
        delivery.delivered_at = now
        announcement.delivered_count += 1
        result = "delivered"
    elif announcement.delivery_mode == "online_only":
        delivery.status = "failed"
        delivery.failed_at = now
        delivery.failure_reason = "agent_offline"
        announcement.failed_count += 1
        result = "failed"
    else:
        result = "pending"

    db.add(delivery)
    db.add(announcement)
    db.flush()
    _broadcast_delivery_update(announcement)
    _check_and_complete(db, announcement)
    return result


def deliver_pending_to_agent(db: Session, agent_uuid: str) -> list[dict]:
    now = _utcnow()
    rows = (
        db.query(AnnouncementDelivery)
        .join(Announcement, Announcement.id == AnnouncementDelivery.announcement_id)
        .filter(
            AnnouncementDelivery.agent_uuid == agent_uuid,
            AnnouncementDelivery.status == "pending",
        )
        .all()
    )

    payloads: list[dict] = []
    changed_ann_ids: set[int] = set()
    for delivery in rows:
        announcement = delivery.announcement
        if announcement.status == "cancelled":
            delivery.status = "cancelled"
            db.add(delivery)
            changed_ann_ids.add(announcement.id)
            continue
        if announcement.expires_at is not None and _as_utc(announcement.expires_at) < now:
            delivery.status = "expired"
            db.add(delivery)
            changed_ann_ids.add(announcement.id)
            continue
        payloads.append(
            {
                "announcement_id": announcement.id,
                "title": announcement.title,
                "message": announcement.message,
                "priority": announcement.priority,
            }
        )

    if changed_ann_ids:
        db.flush()
        for announcement_id in changed_ann_ids:
            updated = _get_announcement_or_error(db, announcement_id)
            _check_and_complete(db, updated)
            _broadcast_delivery_update(updated)
        db.commit()

    return payloads


def process_agent_ack(db: Session, agent_uuid: str, announcement_id: int) -> None:
    delivery = (
        db.query(AnnouncementDelivery)
        .filter(
            AnnouncementDelivery.agent_uuid == agent_uuid,
            AnnouncementDelivery.announcement_id == announcement_id,
        )
        .first()
    )
    if not delivery:
        return

    announcement = _get_announcement_or_error(db, announcement_id)
    if announcement.status == "cancelled":
        return
    if delivery.status == "acknowledged":
        return
    if delivery.status in {"failed", "expired", "cancelled"}:
        return

    now = _utcnow()
    if delivery.status == "delivered" and announcement.delivered_count > 0:
        announcement.delivered_count -= 1
    delivery.status = "acknowledged"
    delivery.acknowledged_at = now
    announcement.acknowledged_count += 1

    db.add(delivery)
    db.add(announcement)
    db.commit()
    db.refresh(announcement)
    _broadcast_delivery_update(announcement)
    _check_and_complete(db, announcement)


def check_scheduled_announcements(db: Session) -> None:
    now = _utcnow()
    scheduled = (
        db.query(Announcement)
        .filter(
            Announcement.status == "scheduled",
            Announcement.scheduled_at.isnot(None),
            Announcement.scheduled_at <= now,
        )
        .all()
    )
    for announcement in scheduled:
        publish_announcement(db, announcement)


def check_expired_deliveries(db: Session) -> None:
    now = _utcnow()
    expired_rows = (
        db.query(AnnouncementDelivery)
        .join(Announcement, Announcement.id == AnnouncementDelivery.announcement_id)
        .filter(
            AnnouncementDelivery.status == "pending",
            Announcement.expires_at.isnot(None),
            Announcement.expires_at < now,
        )
        .all()
    )

    changed_ann_ids: set[int] = set()
    for delivery in expired_rows:
        delivery.status = "expired"
        db.add(delivery)
        changed_ann_ids.add(delivery.announcement_id)

    if not changed_ann_ids:
        return

    db.flush()
    for announcement_id in changed_ann_ids:
        announcement = _get_announcement_or_error(db, announcement_id)
        _check_and_complete(db, announcement)
        _broadcast_delivery_update(announcement)
    db.commit()


def _broadcast_delivery_update(announcement: Announcement) -> None:
    stats = {
        "announcement_id": announcement.id,
        "total_targets": announcement.total_targets,
        "delivered_count": announcement.delivered_count,
        "acknowledged_count": announcement.acknowledged_count,
        "failed_count": announcement.failed_count,
        "pending_count": max(
            0,
            announcement.total_targets
            - announcement.delivered_count
            - announcement.acknowledged_count
            - announcement.failed_count,
        ),
    }
    ws_manager.schedule_broadcast_to_ui(make_message("ui.announcement.delivery_update", stats))


def _check_and_complete(db: Session, announcement: Announcement) -> None:
    if announcement.status == "cancelled":
        return
    pending = _pending_count(db, announcement.id)
    if pending == 0:
        announcement.status = "completed"
        db.add(announcement)
        db.commit()
        db.refresh(announcement)

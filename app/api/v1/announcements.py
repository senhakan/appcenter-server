from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func

from app.auth import get_current_user, require_permission
from app.database import get_db
from app.models import Agent, Announcement, AnnouncementDelivery, Group, User
from app.schemas import (
    AnnouncementCreateRequest,
    AnnouncementDeliveryItemResponse,
    AnnouncementDeliveryListResponse,
    AnnouncementListResponse,
    AnnouncementResponse,
    AnnouncementUpdateRequest,
)
from app.services import announcement_service
from app.services import audit_service as audit

router = APIRouter(prefix="/api/v1/announcements", tags=["announcements"])


def _pending_counts_by_announcement(db, announcement_ids: list[int]) -> dict[int, int]:
    if not announcement_ids:
        return {}
    rows = (
        db.query(
            AnnouncementDelivery.announcement_id,
            func.count(AnnouncementDelivery.id).label("pending_count"),
        )
        .filter(
            AnnouncementDelivery.announcement_id.in_(announcement_ids),
            AnnouncementDelivery.status == "pending",
        )
        .group_by(AnnouncementDelivery.announcement_id)
        .all()
    )
    return {int(announcement_id): int(pending_count or 0) for announcement_id, pending_count in rows}


def _created_by_username_map(db, user_ids: set[int]) -> dict[int, str]:
    if not user_ids:
        return {}
    rows = db.query(User.id, User.username).filter(User.id.in_(user_ids)).all()
    return {int(user_id): str(username) for user_id, username in rows if user_id is not None and username}


def _target_name_maps(
    db,
    group_ids: set[int],
    agent_uuids: set[str],
) -> tuple[dict[int, str], dict[str, str]]:
    group_name_map: dict[int, str] = {}
    agent_name_map: dict[str, str] = {}
    if group_ids:
        group_rows = db.query(Group.id, Group.name).filter(Group.id.in_(group_ids)).all()
        group_name_map = {int(group_id): str(name) for group_id, name in group_rows if group_id is not None and name}
    if agent_uuids:
        agent_rows = db.query(Agent.uuid, Agent.hostname).filter(Agent.uuid.in_(agent_uuids)).all()
        agent_name_map = {str(agent_uuid): str(hostname or agent_uuid) for agent_uuid, hostname in agent_rows if agent_uuid}
    return group_name_map, agent_name_map


def _enrich_announcements(db, announcements: list[Announcement]) -> list[AnnouncementResponse]:
    if not announcements:
        return []

    announcement_ids = [int(item.id) for item in announcements]
    pending_map = _pending_counts_by_announcement(db, announcement_ids)

    user_ids: set[int] = {int(item.created_by) for item in announcements if item.created_by is not None}
    created_by_map = _created_by_username_map(db, user_ids)

    group_ids: set[int] = set()
    agent_uuids: set[str] = set()
    for item in announcements:
        if item.target_type == "Group" and item.target_id:
            try:
                group_ids.add(int(str(item.target_id).strip()))
            except Exception:
                pass
        elif item.target_type == "Agent" and item.target_id:
            agent_uuids.add(str(item.target_id))

    group_name_map, agent_name_map = _target_name_maps(db, group_ids, agent_uuids)

    enriched: list[AnnouncementResponse] = []
    for item in announcements:
        target_name: Optional[str] = None
        if item.target_type == "All":
            target_name = "All"
        elif item.target_type == "Group" and item.target_id:
            try:
                group_id = int(str(item.target_id).strip())
            except Exception:
                group_id = 0
            target_name = group_name_map.get(group_id) or str(item.target_id)
        elif item.target_type == "Agent" and item.target_id:
            target_name = agent_name_map.get(str(item.target_id)) or str(item.target_id)

        response_item = AnnouncementResponse.model_validate(item).model_copy(
            update={
                "target_name": target_name,
                "created_by_username": created_by_map.get(int(item.created_by)) if item.created_by is not None else None,
                "pending_count": int(pending_map.get(int(item.id), 0)),
            }
        )
        enriched.append(response_item)

    return enriched


@router.post("", response_model=AnnouncementResponse, status_code=status.HTTP_201_CREATED)
def create_announcement(
    payload: AnnouncementCreateRequest,
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("announcements.manage")),
) -> AnnouncementResponse:
    db = next(get_db())
    try:
        try:
            announcement = announcement_service.create_announcement(
                db,
                title=payload.title,
                message=payload.message,
                priority=payload.priority,
                target_type=payload.target_type,
                target_id=payload.target_id,
                delivery_mode=payload.delivery_mode,
                scheduled_at=payload.scheduled_at,
                expires_at=payload.expires_at,
                created_by_id=current_user.id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

        audit.record_audit(
            db,
            user_id=current_user.id,
            action="announcement.create",
            resource_type="announcement",
            resource_id=str(announcement.id),
            details={
                "title": announcement.title,
                "priority": announcement.priority,
                "target_type": announcement.target_type,
                "target_id": announcement.target_id,
                "delivery_mode": announcement.delivery_mode,
            },
        )
        return _enrich_announcements(db, [announcement])[0]
    finally:
        db.close()


@router.get("", response_model=AnnouncementListResponse)
def list_announcements(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    priority: Optional[str] = Query(default=None),
    target_type: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(require_permission("announcements.view")),
) -> AnnouncementListResponse:
    db = next(get_db())
    try:
        query = db.query(Announcement)
        if status_filter:
            query = query.filter(Announcement.status == status_filter)
        if priority:
            query = query.filter(Announcement.priority == priority)
        if target_type:
            query = query.filter(Announcement.target_type == target_type)

        total = query.count()
        announcements = (
            query.order_by(Announcement.created_at.desc(), Announcement.id.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        items = _enrich_announcements(db, announcements)
        return AnnouncementListResponse(items=items, total=total)
    finally:
        db.close()


@router.get("/{announcement_id}", response_model=AnnouncementResponse)
def get_announcement(
    announcement_id: int,
    _: User = Depends(require_permission("announcements.view")),
) -> AnnouncementResponse:
    db = next(get_db())
    try:
        announcement = db.query(Announcement).filter(Announcement.id == announcement_id).first()
        if not announcement:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Announcement not found")
        return _enrich_announcements(db, [announcement])[0]
    finally:
        db.close()


@router.put("/{announcement_id}", response_model=AnnouncementResponse)
def update_announcement(
    announcement_id: int,
    payload: AnnouncementUpdateRequest,
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("announcements.manage")),
) -> AnnouncementResponse:
    db = next(get_db())
    try:
        existing = db.query(Announcement).filter(Announcement.id == announcement_id).first()
        if not existing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Announcement not found")

        fields = payload.model_dump(exclude_unset=True)
        try:
            announcement = announcement_service.update_announcement(db, announcement_id, **fields)
        except ValueError as exc:
            message = str(exc)
            http_status = status.HTTP_409_CONFLICT if "Only scheduled announcements can be updated" in message else status.HTTP_400_BAD_REQUEST
            raise HTTPException(status_code=http_status, detail=message) from exc

        audit.record_audit(
            db,
            user_id=current_user.id,
            action="announcement.update",
            resource_type="announcement",
            resource_id=str(announcement.id),
            details={"changed_fields": sorted(list(fields.keys()))},
        )
        return _enrich_announcements(db, [announcement])[0]
    finally:
        db.close()


@router.post("/{announcement_id}/cancel", response_model=AnnouncementResponse)
def cancel_announcement(
    announcement_id: int,
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("announcements.manage")),
) -> AnnouncementResponse:
    db = next(get_db())
    try:
        announcement = db.query(Announcement).filter(Announcement.id == announcement_id).first()
        if not announcement:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Announcement not found")

        try:
            announcement = announcement_service.cancel_announcement(db, announcement_id)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

        audit.record_audit(
            db,
            user_id=current_user.id,
            action="announcement.cancel",
            resource_type="announcement",
            resource_id=str(announcement.id),
            details={"status": announcement.status},
        )
        return _enrich_announcements(db, [announcement])[0]
    finally:
        db.close()


@router.get("/{announcement_id}/deliveries", response_model=AnnouncementDeliveryListResponse)
def list_announcement_deliveries(
    announcement_id: int,
    status_filter: Optional[str] = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(require_permission("announcements.view")),
) -> AnnouncementDeliveryListResponse:
    db = next(get_db())
    try:
        exists = db.query(Announcement.id).filter(Announcement.id == announcement_id).first()
        if not exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Announcement not found")

        query = db.query(AnnouncementDelivery).filter(AnnouncementDelivery.announcement_id == announcement_id)
        if status_filter:
            query = query.filter(AnnouncementDelivery.status == status_filter)

        total = query.count()
        rows = (
            query.order_by(AnnouncementDelivery.id.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        agent_uuids = {str(row.agent_uuid) for row in rows if row.agent_uuid}
        agent_rows = db.query(Agent.uuid, Agent.hostname, Agent.status).filter(Agent.uuid.in_(agent_uuids)).all() if agent_uuids else []
        agent_map = {
            str(agent_uuid): {"hostname": hostname, "status": agent_status}
            for agent_uuid, hostname, agent_status in agent_rows
            if agent_uuid
        }

        items = [
            AnnouncementDeliveryItemResponse(
                id=row.id,
                agent_uuid=row.agent_uuid,
                agent_hostname=(agent_map.get(row.agent_uuid) or {}).get("hostname"),
                agent_status=(agent_map.get(row.agent_uuid) or {}).get("status"),
                status=row.status,
                delivered_at=row.delivered_at,
                acknowledged_at=row.acknowledged_at,
                failed_at=row.failed_at,
                failure_reason=row.failure_reason,
                retry_count=row.retry_count,
            )
            for row in rows
        ]
        return AnnouncementDeliveryListResponse(items=items, total=total)
    finally:
        db.close()

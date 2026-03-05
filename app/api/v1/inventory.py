from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth import require_permission
from app.database import get_db
from app.models import Agent, AgentServiceHistory
from app.services import inventory_service
from app.services import system_profile_service
from app.services import timeline_service
from app.schemas import (
    AgentSystemHistoryListResponse,
    AgentServiceHistoryItemResponse,
    AgentServiceHistoryListResponse,
    AgentServiceItemResponse,
    AgentServiceListResponse,
    AgentTimelineListResponse,
    AgentTimelineItemResponse,
    SystemProfileHistoryItemResponse,
    AgentChangeHistoryListResponse,
    AgentInventoryListResponse,
    ChangeHistoryItemResponse,
    InventoryDashboardResponse,
    InventoryItemResponse,
    LicenseCreateRequest,
    LicenseListResponse,
    LicenseResponse,
    LicenseUpdateRequest,
    LicenseUsageReportItem,
    LicenseUsageReportResponse,
    MessageResponse,
    NormalizationRuleCreateRequest,
    NormalizationRuleListResponse,
    NormalizationRuleResponse,
    NormalizationRuleUpdateRequest,
    SoftwareAgentItem,
    SoftwareAgentListResponse,
    SamCatalogItem,
    SamCatalogListResponse,
    SamDashboardResponse,
    SamTopSoftwareItem,
    SamPlatformKpi,
    SoftwareSummaryItem,
    SoftwareSummaryListResponse,
)

router = APIRouter(tags=["inventory"])


# --- Agent inventory queries ---


@router.get("/agents/{agent_uuid}/inventory", response_model=AgentInventoryListResponse)
def get_agent_inventory(
    agent_uuid: str,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("inventory.view")),
):
    items = inventory_service.get_agent_inventory(db, agent_uuid)
    return AgentInventoryListResponse(
        items=[InventoryItemResponse.model_validate(i) for i in items],
        total=len(items),
    )


@router.get("/agents/{agent_uuid}/inventory/changes", response_model=AgentChangeHistoryListResponse)
def get_agent_change_history(
    agent_uuid: str,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _user=Depends(require_permission("inventory.view")),
):
    items, total = inventory_service.get_agent_change_history(db, agent_uuid, limit, offset)
    return AgentChangeHistoryListResponse(
        items=[ChangeHistoryItemResponse.model_validate(i) for i in items],
        total=total,
    )


@router.get("/agents/{agent_uuid}/system/history", response_model=AgentSystemHistoryListResponse)
def get_agent_system_history(
    agent_uuid: str,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _user=Depends(require_permission("inventory.view")),
):
    items, total = system_profile_service.get_agent_system_history(db, agent_uuid, limit, offset)
    return AgentSystemHistoryListResponse(
        items=[SystemProfileHistoryItemResponse.model_validate(i) for i in items],
        total=total,
    )


@router.get("/agents/{agent_uuid}/timeline", response_model=AgentTimelineListResponse)
def get_agent_timeline(
    agent_uuid: str,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _user=Depends(require_permission("inventory.view")),
):
    items, total = timeline_service.get_agent_timeline(db, agent_uuid, limit, offset)
    return AgentTimelineListResponse(
        items=[AgentTimelineItemResponse(**i) for i in items],
        total=total,
    )


@router.get("/agents/{agent_uuid}/services", response_model=AgentServiceListResponse)
def get_agent_services(
    agent_uuid: str,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("inventory.view")),
):
    agent = db.query(Agent).filter(Agent.uuid == agent_uuid).first()
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    items: list[dict] = []
    try:
        raw = json.loads(agent.services_json or "[]")
        if isinstance(raw, list):
            items = [x for x in raw if isinstance(x, dict)]
    except Exception:
        items = []
    mapped = [AgentServiceItemResponse(**i) for i in items if (i.get("name") or "").strip()]
    return AgentServiceListResponse(items=mapped, total=len(mapped))


@router.get("/agents/{agent_uuid}/services/history", response_model=AgentServiceHistoryListResponse)
def get_agent_services_history(
    agent_uuid: str,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _user=Depends(require_permission("inventory.view")),
):
    q = (
        db.query(AgentServiceHistory)
        .filter(AgentServiceHistory.agent_uuid == agent_uuid)
        .order_by(AgentServiceHistory.detected_at.desc(), AgentServiceHistory.id.desc())
    )
    total = q.count()
    rows = q.offset(offset).limit(limit).all()
    return AgentServiceHistoryListResponse(
        items=[
            AgentServiceHistoryItemResponse(
                id=r.id,
                detected_at=r.detected_at,
                service_name=r.service_name,
                display_name=r.display_name,
                change_type=r.change_type,
                old_status=r.old_status,
                new_status=r.new_status,
                old_startup_type=r.old_startup_type,
                new_startup_type=r.new_startup_type,
            )
            for r in rows
        ],
        total=total,
    )


# --- Cross-agent software queries ---


@router.get("/inventory/software", response_model=SoftwareSummaryListResponse)
def get_software_summary(
    search: str = Query("", max_length=200),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _user=Depends(require_permission("inventory.view")),
):
    items, total = inventory_service.get_software_summary(db, search, page, per_page)
    return SoftwareSummaryListResponse(
        items=[SoftwareSummaryItem(**i) for i in items],
        total=total,
    )


@router.get("/inventory/software/{software_name}/agents", response_model=SoftwareAgentListResponse)
def get_software_agents(
    software_name: str,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("inventory.view")),
):
    items = inventory_service.get_software_agents(db, software_name)
    return SoftwareAgentListResponse(
        items=[SoftwareAgentItem(**i) for i in items],
        total=len(items),
    )


@router.get("/inventory/dashboard", response_model=InventoryDashboardResponse)
def get_inventory_dashboard(
    db: Session = Depends(get_db),
    _user=Depends(require_permission("inventory.view")),
):
    stats = inventory_service.get_inventory_dashboard_stats(db)
    return InventoryDashboardResponse(**stats)


@router.get("/sam/dashboard", response_model=SamDashboardResponse)
def get_sam_dashboard(
    db: Session = Depends(get_db),
    _user=Depends(require_permission("inventory.view")),
):
    data = inventory_service.get_sam_dashboard(db)
    return SamDashboardResponse(
        total_agents=data["total_agents"],
        agents_with_inventory=data["agents_with_inventory"],
        unique_software=data["unique_software"],
        normalized_unique_software=data["normalized_unique_software"],
        normalized_rows=data["normalized_rows"],
        platform_items=[SamPlatformKpi(**x) for x in data["platform_items"]],
        top_software=[SamTopSoftwareItem(**x) for x in data["top_software"]],
    )


@router.get("/sam/catalog", response_model=SamCatalogListResponse)
def get_sam_catalog(
    search: str = Query("", max_length=200),
    platform: str = Query("all", pattern="^(all|windows|linux)$"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _user=Depends(require_permission("inventory.view")),
):
    items, total = inventory_service.get_sam_catalog(
        db,
        search=search,
        platform=platform,
        page=page,
        per_page=per_page,
    )
    return SamCatalogListResponse(
        items=[SamCatalogItem(**x) for x in items],
        total=total,
        page=page,
        per_page=per_page,
    )


# --- Normalization rules ---


@router.get("/inventory/normalization", response_model=NormalizationRuleListResponse)
def list_normalization_rules(
    db: Session = Depends(get_db),
    _user=Depends(require_permission("inventory.view")),
):
    items = inventory_service.list_normalization_rules(db)
    return NormalizationRuleListResponse(
        items=[NormalizationRuleResponse.model_validate(i) for i in items],
        total=len(items),
    )


@router.post("/inventory/normalization", response_model=NormalizationRuleResponse, status_code=201)
def create_normalization_rule(
    payload: NormalizationRuleCreateRequest,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("inventory.manage")),
):
    rule = inventory_service.create_normalization_rule(
        db, payload.pattern, payload.normalized_name, payload.match_type,
    )
    return NormalizationRuleResponse.model_validate(rule)


@router.put("/inventory/normalization/{rule_id}", response_model=NormalizationRuleResponse)
def update_normalization_rule(
    rule_id: int,
    payload: NormalizationRuleUpdateRequest,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("inventory.manage")),
):
    rule = inventory_service.update_normalization_rule(
        db, rule_id, **payload.model_dump(exclude_unset=True),
    )
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    return NormalizationRuleResponse.model_validate(rule)


@router.delete("/inventory/normalization/{rule_id}", response_model=MessageResponse)
def delete_normalization_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("inventory.manage")),
):
    if not inventory_service.delete_normalization_rule(db, rule_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    return MessageResponse(status="ok", message="Rule deleted")


# --- Licenses ---


@router.get("/licenses", response_model=LicenseListResponse)
def list_licenses(
    db: Session = Depends(get_db),
    _user=Depends(require_permission("licenses.view")),
):
    items = inventory_service.list_licenses(db)
    return LicenseListResponse(
        items=[LicenseResponse.model_validate(i) for i in items],
        total=len(items),
    )


@router.get("/licenses/report", response_model=LicenseUsageReportResponse)
def get_license_usage_report(
    db: Session = Depends(get_db),
    _user=Depends(require_permission("licenses.view")),
):
    items = inventory_service.get_license_usage_report(db)
    return LicenseUsageReportResponse(
        items=[LicenseUsageReportItem(**i) for i in items],
        total=len(items),
    )


@router.get("/licenses/{license_id}", response_model=LicenseResponse)
def get_license(
    license_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("licenses.view")),
):
    lic = inventory_service.get_license(db, license_id)
    if not lic:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="License not found")
    return LicenseResponse.model_validate(lic)


@router.post("/licenses", response_model=LicenseResponse, status_code=201)
def create_license(
    payload: LicenseCreateRequest,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("licenses.manage")),
):
    lic = inventory_service.create_license(db, **payload.model_dump())
    return LicenseResponse.model_validate(lic)


@router.put("/licenses/{license_id}", response_model=LicenseResponse)
def update_license(
    license_id: int,
    payload: LicenseUpdateRequest,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("licenses.manage")),
):
    lic = inventory_service.update_license(db, license_id, **payload.model_dump(exclude_unset=True))
    if not lic:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="License not found")
    return LicenseResponse.model_validate(lic)


@router.delete("/licenses/{license_id}", response_model=MessageResponse)
def delete_license(
    license_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("licenses.manage")),
):
    if not inventory_service.delete_license(db, license_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="License not found")
    return MessageResponse(status="ok", message="License deleted")

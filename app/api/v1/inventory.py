from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.services import inventory_service
from app.schemas import (
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
    SoftwareSummaryItem,
    SoftwareSummaryListResponse,
)

router = APIRouter(tags=["inventory"])


# --- Agent inventory queries ---


@router.get("/agents/{agent_uuid}/inventory", response_model=AgentInventoryListResponse)
def get_agent_inventory(
    agent_uuid: str,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
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
    _user=Depends(get_current_user),
):
    items, total = inventory_service.get_agent_change_history(db, agent_uuid, limit, offset)
    return AgentChangeHistoryListResponse(
        items=[ChangeHistoryItemResponse.model_validate(i) for i in items],
        total=total,
    )


# --- Cross-agent software queries ---


@router.get("/inventory/software", response_model=SoftwareSummaryListResponse)
def get_software_summary(
    search: str = Query("", max_length=200),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
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
    _user=Depends(get_current_user),
):
    items = inventory_service.get_software_agents(db, software_name)
    return SoftwareAgentListResponse(
        items=[SoftwareAgentItem(**i) for i in items],
        total=len(items),
    )


@router.get("/inventory/dashboard", response_model=InventoryDashboardResponse)
def get_inventory_dashboard(
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    stats = inventory_service.get_inventory_dashboard_stats(db)
    return InventoryDashboardResponse(**stats)


# --- Normalization rules ---


@router.get("/inventory/normalization", response_model=NormalizationRuleListResponse)
def list_normalization_rules(
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
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
    _user=Depends(get_current_user),
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
    _user=Depends(get_current_user),
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
    _user=Depends(get_current_user),
):
    if not inventory_service.delete_normalization_rule(db, rule_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    return MessageResponse(status="ok", message="Rule deleted")


# --- Licenses ---


@router.get("/licenses", response_model=LicenseListResponse)
def list_licenses(
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    items = inventory_service.list_licenses(db)
    return LicenseListResponse(
        items=[LicenseResponse.model_validate(i) for i in items],
        total=len(items),
    )


@router.get("/licenses/report", response_model=LicenseUsageReportResponse)
def get_license_usage_report(
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
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
    _user=Depends(get_current_user),
):
    lic = inventory_service.get_license(db, license_id)
    if not lic:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="License not found")
    return LicenseResponse.model_validate(lic)


@router.post("/licenses", response_model=LicenseResponse, status_code=201)
def create_license(
    payload: LicenseCreateRequest,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    lic = inventory_service.create_license(db, **payload.model_dump())
    return LicenseResponse.model_validate(lic)


@router.put("/licenses/{license_id}", response_model=LicenseResponse)
def update_license(
    license_id: int,
    payload: LicenseUpdateRequest,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    lic = inventory_service.update_license(db, license_id, **payload.model_dump(exclude_unset=True))
    if not lic:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="License not found")
    return LicenseResponse.model_validate(lic)


@router.delete("/licenses/{license_id}", response_model=MessageResponse)
def delete_license(
    license_id: int,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    if not inventory_service.delete_license(db, license_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="License not found")
    return MessageResponse(status="ok", message="License deleted")

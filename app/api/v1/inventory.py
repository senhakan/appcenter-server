from __future__ import annotations

import csv
import json
import io
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth import require_permission
from app.config import get_settings
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
    SamComplianceFindingItem,
    SamComplianceFindingListResponse,
    SamComplianceStatusUpdateRequest,
    SamCostProfileCreateRequest,
    SamCostProfileItem,
    SamCostProfileListResponse,
    SamCostProfileUpdateRequest,
    SamDashboardResponse,
    SamGeneratedReportItem,
    SamGeneratedReportListResponse,
    SamLifecyclePolicyCreateRequest,
    SamLifecyclePolicyItem,
    SamLifecyclePolicyListResponse,
    SamLifecyclePolicyUpdateRequest,
    SamRiskOverviewItem,
    SamRiskOverviewResponse,
    SamReportScheduleCreateRequest,
    SamReportScheduleItem,
    SamReportScheduleListResponse,
    SamReportScheduleUpdateRequest,
    SamTopSoftwareItem,
    SamPlatformKpi,
    SoftwareSummaryItem,
    SoftwareSummaryListResponse,
)

router = APIRouter(tags=["inventory"])
settings = get_settings()


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


@router.get("/sam/compliance/findings", response_model=SamComplianceFindingListResponse)
def list_sam_compliance_findings(
    status_filter: str = Query("all", alias="status"),
    platform: str = Query("all", pattern="^(all|windows|linux)$"),
    search: str = Query("", max_length=200),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _user=Depends(require_permission("inventory.view")),
):
    items, total = inventory_service.list_sam_compliance_findings(
        db,
        status=status_filter,
        platform=platform,
        search=search,
        limit=limit,
        offset=offset,
    )
    return SamComplianceFindingListResponse(
        items=[
            SamComplianceFindingItem(
                id=i.id,
                software_name=i.software_name,
                platform=i.platform,
                finding_type=i.finding_type,
                severity=i.severity,
                status=i.status,
                affected_agents=i.affected_agents,
                details_json=i.details_json,
                first_seen_at=i.first_seen_at,
                last_seen_at=i.last_seen_at,
                resolved_at=i.resolved_at,
            )
            for i in items
        ],
        total=total,
    )


@router.post("/sam/compliance/findings/sync", response_model=MessageResponse)
def sync_sam_compliance_findings(
    db: Session = Depends(get_db),
    _user=Depends(require_permission("inventory.manage")),
):
    stats = inventory_service.sync_sam_compliance_findings(db)
    return MessageResponse(
        status="ok",
        message=f"Compliance sync completed (created={stats['created']}, updated={stats['updated']}, closed={stats['closed']})",
    )


@router.put("/sam/compliance/findings/{finding_id}/status", response_model=SamComplianceFindingItem)
def update_sam_compliance_finding_status(
    finding_id: int,
    payload: SamComplianceStatusUpdateRequest,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("inventory.manage")),
):
    item = inventory_service.update_sam_finding_status(db, finding_id, payload.status)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding not found")
    return SamComplianceFindingItem(
        id=item.id,
        software_name=item.software_name,
        platform=item.platform,
        finding_type=item.finding_type,
        severity=item.severity,
        status=item.status,
        affected_agents=item.affected_agents,
        details_json=item.details_json,
        first_seen_at=item.first_seen_at,
        last_seen_at=item.last_seen_at,
        resolved_at=item.resolved_at,
    )


@router.get("/sam/reports/export")
def export_sam_report(
    report_type: str = Query("sam_prevalence", pattern="^(sam_prevalence|sam_compliance|sam_catalog)$"),
    platform: str = Query("all", pattern="^(all|windows|linux)$"),
    db: Session = Depends(get_db),
    _user=Depends(require_permission("inventory.view")),
):
    buf = io.StringIO()
    writer = csv.writer(buf)
    filename = f"{report_type}.csv"
    try:
        header, rows = inventory_service.build_sam_report_data(db, report_type=report_type, platform=platform)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/sam/report-schedules", response_model=SamReportScheduleListResponse)
def list_sam_report_schedules(
    db: Session = Depends(get_db),
    _user=Depends(require_permission("inventory.view")),
):
    items = inventory_service.list_sam_report_schedules(db)
    return SamReportScheduleListResponse(
        items=[
            SamReportScheduleItem(
                id=i.id,
                name=i.name,
                report_type=i.report_type,
                format=i.format,
                cron_expr=i.cron_expr,
                recipients=i.recipients,
                is_active=i.is_active,
                last_run_at=i.last_run_at,
                next_run_at=i.next_run_at,
                created_by=i.created_by,
                created_at=i.created_at,
                updated_at=i.updated_at,
            )
            for i in items
        ],
        total=len(items),
    )


@router.post("/sam/report-schedules", response_model=SamReportScheduleItem, status_code=201)
def create_sam_report_schedule(
    payload: SamReportScheduleCreateRequest,
    db: Session = Depends(get_db),
    user=Depends(require_permission("inventory.manage")),
):
    try:
        item = inventory_service.create_sam_report_schedule(
            db,
            name=payload.name,
            report_type=payload.report_type,
            format=payload.format,
            cron_expr=payload.cron_expr,
            recipients=payload.recipients,
            is_active=payload.is_active,
            created_by=getattr(user, "username", None),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return SamReportScheduleItem(
        id=item.id,
        name=item.name,
        report_type=item.report_type,
        format=item.format,
        cron_expr=item.cron_expr,
        recipients=item.recipients,
        is_active=item.is_active,
        last_run_at=item.last_run_at,
        next_run_at=item.next_run_at,
        created_by=item.created_by,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.put("/sam/report-schedules/{schedule_id}", response_model=SamReportScheduleItem)
def update_sam_report_schedule(
    schedule_id: int,
    payload: SamReportScheduleUpdateRequest,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("inventory.manage")),
):
    try:
        item = inventory_service.update_sam_report_schedule(db, schedule_id, **payload.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
    return SamReportScheduleItem(
        id=item.id,
        name=item.name,
        report_type=item.report_type,
        format=item.format,
        cron_expr=item.cron_expr,
        recipients=item.recipients,
        is_active=item.is_active,
        last_run_at=item.last_run_at,
        next_run_at=item.next_run_at,
        created_by=item.created_by,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.delete("/sam/report-schedules/{schedule_id}", response_model=MessageResponse)
def delete_sam_report_schedule(
    schedule_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("inventory.manage")),
):
    ok = inventory_service.delete_sam_report_schedule(db, schedule_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
    return MessageResponse(status="ok", message="Schedule deleted")


@router.get("/sam/risk-overview", response_model=SamRiskOverviewResponse)
def get_sam_risk_overview(
    platform: str = Query("all", pattern="^(all|windows|linux)$"),
    search: str = Query("", max_length=200),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _user=Depends(require_permission("inventory.view")),
):
    data = inventory_service.get_sam_risk_overview(
        db,
        platform=platform,
        search=search,
        limit=limit,
        offset=offset,
    )
    return SamRiskOverviewResponse(
        items=[SamRiskOverviewItem(**x) for x in data["items"]],
        total=data["total"],
        critical_count=data["critical_count"],
        warning_count=data["warning_count"],
        monthly_cost_cents_total=data["monthly_cost_cents_total"],
    )


@router.get("/sam/lifecycle-policies", response_model=SamLifecyclePolicyListResponse)
def list_sam_lifecycle_policies(
    db: Session = Depends(get_db),
    _user=Depends(require_permission("inventory.view")),
):
    items = inventory_service.list_sam_lifecycle_policies(db)
    return SamLifecyclePolicyListResponse(
        items=[
            SamLifecyclePolicyItem(
                id=i.id,
                software_name_pattern=i.software_name_pattern,
                match_type=i.match_type,
                platform=i.platform,
                eol_date=i.eol_date,
                eos_date=i.eos_date,
                is_active=i.is_active,
                notes=i.notes,
                created_at=i.created_at,
                updated_at=i.updated_at,
            )
            for i in items
        ],
        total=len(items),
    )


@router.post("/sam/lifecycle-policies", response_model=SamLifecyclePolicyItem, status_code=201)
def create_sam_lifecycle_policy(
    payload: SamLifecyclePolicyCreateRequest,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("inventory.manage")),
):
    item = inventory_service.create_sam_lifecycle_policy(db, **payload.model_dump())
    return SamLifecyclePolicyItem(
        id=item.id,
        software_name_pattern=item.software_name_pattern,
        match_type=item.match_type,
        platform=item.platform,
        eol_date=item.eol_date,
        eos_date=item.eos_date,
        is_active=item.is_active,
        notes=item.notes,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.put("/sam/lifecycle-policies/{policy_id}", response_model=SamLifecyclePolicyItem)
def update_sam_lifecycle_policy(
    policy_id: int,
    payload: SamLifecyclePolicyUpdateRequest,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("inventory.manage")),
):
    item = inventory_service.update_sam_lifecycle_policy(db, policy_id, **payload.model_dump(exclude_unset=True))
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")
    return SamLifecyclePolicyItem(
        id=item.id,
        software_name_pattern=item.software_name_pattern,
        match_type=item.match_type,
        platform=item.platform,
        eol_date=item.eol_date,
        eos_date=item.eos_date,
        is_active=item.is_active,
        notes=item.notes,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.delete("/sam/lifecycle-policies/{policy_id}", response_model=MessageResponse)
def delete_sam_lifecycle_policy(
    policy_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("inventory.manage")),
):
    ok = inventory_service.delete_sam_lifecycle_policy(db, policy_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")
    return MessageResponse(status="ok", message="Lifecycle policy deleted")


@router.get("/sam/cost-profiles", response_model=SamCostProfileListResponse)
def list_sam_cost_profiles(
    db: Session = Depends(get_db),
    _user=Depends(require_permission("inventory.view")),
):
    items = inventory_service.list_sam_cost_profiles(db)
    return SamCostProfileListResponse(
        items=[
            SamCostProfileItem(
                id=i.id,
                software_name_pattern=i.software_name_pattern,
                match_type=i.match_type,
                platform=i.platform,
                monthly_cost_cents=i.monthly_cost_cents,
                currency=i.currency,
                is_active=i.is_active,
                notes=i.notes,
                created_at=i.created_at,
                updated_at=i.updated_at,
            )
            for i in items
        ],
        total=len(items),
    )


@router.post("/sam/cost-profiles", response_model=SamCostProfileItem, status_code=201)
def create_sam_cost_profile(
    payload: SamCostProfileCreateRequest,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("inventory.manage")),
):
    item = inventory_service.create_sam_cost_profile(db, **payload.model_dump())
    return SamCostProfileItem(
        id=item.id,
        software_name_pattern=item.software_name_pattern,
        match_type=item.match_type,
        platform=item.platform,
        monthly_cost_cents=item.monthly_cost_cents,
        currency=item.currency,
        is_active=item.is_active,
        notes=item.notes,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.put("/sam/cost-profiles/{profile_id}", response_model=SamCostProfileItem)
def update_sam_cost_profile(
    profile_id: int,
    payload: SamCostProfileUpdateRequest,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("inventory.manage")),
):
    item = inventory_service.update_sam_cost_profile(db, profile_id, **payload.model_dump(exclude_unset=True))
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cost profile not found")
    return SamCostProfileItem(
        id=item.id,
        software_name_pattern=item.software_name_pattern,
        match_type=item.match_type,
        platform=item.platform,
        monthly_cost_cents=item.monthly_cost_cents,
        currency=item.currency,
        is_active=item.is_active,
        notes=item.notes,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.delete("/sam/cost-profiles/{profile_id}", response_model=MessageResponse)
def delete_sam_cost_profile(
    profile_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("inventory.manage")),
):
    ok = inventory_service.delete_sam_cost_profile(db, profile_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cost profile not found")
    return MessageResponse(status="ok", message="Cost profile deleted")


@router.get("/sam/reports/generated", response_model=SamGeneratedReportListResponse)
def list_generated_sam_reports(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _user=Depends(require_permission("inventory.view")),
):
    _ = db  # keep dependency for consistent auth/db pattern
    report_dir = Path(settings.upload_dir) / "reports" / "sam"
    if not report_dir.exists():
        return SamGeneratedReportListResponse(items=[], total=0)
    files: list[SamGeneratedReportItem] = []
    for fp in sorted(report_dir.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True):
        name = fp.name
        report_type = "unknown"
        if name.startswith("sam_prevalence_"):
            report_type = "sam_prevalence"
        elif name.startswith("sam_catalog_"):
            report_type = "sam_catalog"
        elif name.startswith("sam_compliance_"):
            report_type = "sam_compliance"
        st = fp.stat()
        files.append(
            SamGeneratedReportItem(
                filename=name,
                report_type=report_type,
                created_at=datetime.fromtimestamp(st.st_mtime, tz=timezone.utc),
                size_bytes=int(st.st_size),
                download_url=f"/uploads/reports/sam/{name}",
            )
        )
        if len(files) >= limit:
            break
    return SamGeneratedReportListResponse(items=files, total=len(files))


@router.delete("/sam/reports/generated/{filename}", response_model=MessageResponse)
def delete_generated_sam_report(
    filename: str,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("inventory.manage")),
):
    _ = db
    safe_name = Path(filename).name
    if not safe_name.endswith(".csv"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only CSV report files can be deleted")
    report_dir = Path(settings.upload_dir) / "reports" / "sam"
    target = report_dir / safe_name
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report file not found")
    target.unlink()
    return MessageResponse(status="ok", message="Report file deleted")


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

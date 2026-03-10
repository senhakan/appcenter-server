from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
import csv
import io
from sqlalchemy.orm import Session

from app.auth import require_permission
from app.database import get_db
from app.models import User
from app.schemas import (
    AssetAgentSummaryResponse,
    AssetAgentLinkRequest,
    AssetChangeLogListResponse,
    AssetCostCenterCreateRequest,
    AssetCostCenterListResponse,
    AssetCostCenterResponse,
    AssetCostCenterUpdateRequest,
    AssetDataQualityIssueListResponse,
    AssetDataQualityBulkUpdateRequest,
    AssetDictionaryResponse,
    AssetDictionaryUpdateRequest,
    AssetLocationNodeBase,
    AssetLocationNodeListResponse,
    AssetLocationNodeResponse,
    AssetLocationNodeUpdateRequest,
    AssetMatchingCandidateListResponse,
    AssetMatchingDecisionRequest,
    AssetNodeLabelUpdateRequest,
    AssetOrganizationNodeBase,
    AssetOrganizationNodeListResponse,
    AssetOrganizationNodeResponse,
    AssetOrganizationNodeUpdateRequest,
    AssetOverviewResponse,
    AssetPersonCreateRequest,
    AssetPersonListResponse,
    AssetPersonDetailResponse,
    AssetPersonResponse,
    AssetPersonUpdateRequest,
    AssetRecordDetailResponse,
    AssetRecordCreateRequest,
    AssetRecordListResponse,
    AssetRecordResponse,
    AssetRecordUpdateRequest,
    AssetReportListResponse,
    MessageResponse,
)
from app.services import audit_service as audit
from app.services import asset_registry_service as service

router = APIRouter(prefix="/asset-registry", tags=["asset-registry"])


@router.get("/dictionaries", response_model=AssetDictionaryResponse)
def asset_registry_dictionaries(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("asset_registry.view")),
) -> AssetDictionaryResponse:
    return AssetDictionaryResponse(**service.get_dictionaries(db))


@router.get("/overview", response_model=AssetOverviewResponse)
def asset_registry_overview(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("asset_registry.view")),
) -> AssetOverviewResponse:
    return AssetOverviewResponse(**service.overview(db))


@router.get("/agents/{agent_uuid}/summary", response_model=AssetAgentSummaryResponse)
def asset_registry_agent_summary(
    agent_uuid: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("agents.view", "asset_registry.view")),
) -> AssetAgentSummaryResponse:
    data = service.get_agent_asset_summary(db, agent_uuid)
    if not data:
        raise HTTPException(status_code=404, detail="Ajan icin aktif asset baglami bulunamadi")
    return AssetAgentSummaryResponse(**data)


@router.get("/organization", response_model=AssetOrganizationNodeListResponse)
def asset_registry_org_list(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("asset_registry.view")),
) -> AssetOrganizationNodeListResponse:
    items = [AssetOrganizationNodeResponse(**item) for item in service.list_organization_nodes(db, include_inactive=include_inactive)]
    return AssetOrganizationNodeListResponse(items=items, total=len(items))


@router.post("/organization", response_model=AssetOrganizationNodeResponse, status_code=201)
def asset_registry_org_create(
    payload: AssetOrganizationNodeBase,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("asset_registry.manage")),
) -> AssetOrganizationNodeResponse:
    row = service.create_organization_node(db, payload, user)
    audit.record_audit(db, user_id=user.id, action="asset_registry.organization.create", resource_type="asset_org_node", resource_id=str(row.id), details={"name": row.name, "node_type": row.node_type})
    data = next(item for item in service.list_organization_nodes(db, include_inactive=True) if item["id"] == row.id)
    return AssetOrganizationNodeResponse(**data)


@router.put("/organization/{node_id}", response_model=AssetOrganizationNodeResponse)
def asset_registry_org_update(
    node_id: int,
    payload: AssetOrganizationNodeUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("asset_registry.manage")),
) -> AssetOrganizationNodeResponse:
    row = service.update_organization_node(db, node_id, payload, user)
    audit.record_audit(db, user_id=user.id, action="asset_registry.organization.update", resource_type="asset_org_node", resource_id=str(row.id), details={"name": row.name, "node_type": row.node_type})
    data = next(item for item in service.list_organization_nodes(db, include_inactive=True) if item["id"] == row.id)
    return AssetOrganizationNodeResponse(**data)


@router.post("/organization/{node_id}/deactivate", response_model=MessageResponse)
def asset_registry_org_deactivate(
    node_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("asset_registry.manage")),
) -> MessageResponse:
    payload = AssetOrganizationNodeUpdateRequest(is_active=False)
    row = service.update_organization_node(db, node_id, payload, user)
    audit.record_audit(db, user_id=user.id, action="asset_registry.organization.deactivate", resource_type="asset_org_node", resource_id=str(row.id), details={"name": row.name})
    return MessageResponse(status="success", message="Organization node deactivated")


@router.get("/locations", response_model=AssetLocationNodeListResponse)
def asset_registry_location_list(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("asset_registry.view")),
) -> AssetLocationNodeListResponse:
    items = [AssetLocationNodeResponse(**item) for item in service.list_location_nodes(db, include_inactive=include_inactive)]
    return AssetLocationNodeListResponse(items=items, total=len(items))


@router.post("/locations", response_model=AssetLocationNodeResponse, status_code=201)
def asset_registry_location_create(
    payload: AssetLocationNodeBase,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("asset_registry.manage")),
) -> AssetLocationNodeResponse:
    row = service.create_location_node(db, payload, user)
    audit.record_audit(db, user_id=user.id, action="asset_registry.location.create", resource_type="asset_location_node", resource_id=str(row.id), details={"name": row.name, "location_type": row.location_type})
    data = next(item for item in service.list_location_nodes(db, include_inactive=True) if item["id"] == row.id)
    return AssetLocationNodeResponse(**data)


@router.put("/locations/{node_id}", response_model=AssetLocationNodeResponse)
def asset_registry_location_update(
    node_id: int,
    payload: AssetLocationNodeUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("asset_registry.manage")),
) -> AssetLocationNodeResponse:
    row = service.update_location_node(db, node_id, payload, user)
    audit.record_audit(db, user_id=user.id, action="asset_registry.location.update", resource_type="asset_location_node", resource_id=str(row.id), details={"name": row.name, "location_type": row.location_type})
    data = next(item for item in service.list_location_nodes(db, include_inactive=True) if item["id"] == row.id)
    return AssetLocationNodeResponse(**data)


@router.post("/locations/{node_id}/deactivate", response_model=MessageResponse)
def asset_registry_location_deactivate(
    node_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("asset_registry.manage")),
) -> MessageResponse:
    payload = AssetLocationNodeUpdateRequest(is_active=False)
    row = service.update_location_node(db, node_id, payload, user)
    audit.record_audit(db, user_id=user.id, action="asset_registry.location.deactivate", resource_type="asset_location_node", resource_id=str(row.id), details={"name": row.name})
    return MessageResponse(status="success", message="Location node deactivated")


@router.get("/people", response_model=AssetPersonListResponse)
def asset_registry_people_list(
    q: str = None,
    org_node_id: int = None,
    cost_center_id: int = None,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("asset_registry.view")),
) -> AssetPersonListResponse:
    items = [AssetPersonResponse(**item) for item in service.list_people(db, q=q, org_node_id=org_node_id, cost_center_id=cost_center_id, include_inactive=include_inactive)]
    return AssetPersonListResponse(items=items, total=len(items))


@router.get("/people/{person_id}", response_model=AssetPersonDetailResponse)
def asset_registry_person_detail(
    person_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("asset_registry.view")),
) -> AssetPersonDetailResponse:
    data = service.get_person_detail(db, person_id)
    return AssetPersonDetailResponse(**data)


@router.post("/people", response_model=AssetPersonResponse, status_code=201)
def asset_registry_person_create(
    payload: AssetPersonCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("asset_registry.manage")),
) -> AssetPersonResponse:
    row = service.create_person(db, payload, user)
    audit.record_audit(db, user_id=user.id, action="asset_registry.person.create", resource_type="asset_person", resource_id=str(row.id), details={"full_name": row.full_name})
    data = service.get_person_detail(db, row.id)
    return AssetPersonResponse(**data)


@router.put("/people/{person_id}", response_model=AssetPersonResponse)
def asset_registry_person_update(
    person_id: int,
    payload: AssetPersonUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("asset_registry.manage")),
) -> AssetPersonResponse:
    row = service.update_person(db, person_id, payload, user)
    audit.record_audit(db, user_id=user.id, action="asset_registry.person.update", resource_type="asset_person", resource_id=str(row.id), details={"full_name": row.full_name})
    data = service.get_person_detail(db, row.id)
    return AssetPersonResponse(**data)


@router.get("/cost-centers", response_model=AssetCostCenterListResponse)
def asset_registry_cost_centers(
    org_node_id: int = None,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("asset_registry.view")),
) -> AssetCostCenterListResponse:
    items = [AssetCostCenterResponse(**item) for item in service.list_cost_centers(db, org_node_id=org_node_id, include_inactive=include_inactive)]
    return AssetCostCenterListResponse(items=items, total=len(items))


@router.post("/cost-centers", response_model=AssetCostCenterResponse, status_code=201)
def asset_registry_cost_center_create(
    payload: AssetCostCenterCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("asset_registry.manage")),
) -> AssetCostCenterResponse:
    row = service.create_cost_center(db, payload, user)
    audit.record_audit(db, user_id=user.id, action="asset_registry.cost_center.create", resource_type="asset_cost_center", resource_id=str(row.id), details={"code": row.code, "name": row.name})
    data = next(item for item in service.list_cost_centers(db, include_inactive=True) if item["id"] == row.id)
    return AssetCostCenterResponse(**data)


@router.put("/cost-centers/{cost_center_id}", response_model=AssetCostCenterResponse)
def asset_registry_cost_center_update(
    cost_center_id: int,
    payload: AssetCostCenterUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("asset_registry.manage")),
) -> AssetCostCenterResponse:
    row = service.update_cost_center(db, cost_center_id, payload, user)
    audit.record_audit(db, user_id=user.id, action="asset_registry.cost_center.update", resource_type="asset_cost_center", resource_id=str(row.id), details={"code": row.code, "name": row.name})
    data = next(item for item in service.list_cost_centers(db, include_inactive=True) if item["id"] == row.id)
    return AssetCostCenterResponse(**data)


@router.post("/cost-centers/{cost_center_id}/deactivate", response_model=MessageResponse)
def asset_registry_cost_center_deactivate(
    cost_center_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("asset_registry.manage")),
) -> MessageResponse:
    payload = AssetCostCenterUpdateRequest(is_active=False)
    row = service.update_cost_center(db, cost_center_id, payload, user)
    audit.record_audit(db, user_id=user.id, action="asset_registry.cost_center.deactivate", resource_type="asset_cost_center", resource_id=str(row.id), details={"code": row.code, "name": row.name})
    return MessageResponse(status="success", message="Cost center deactivated")


@router.get("/assets", response_model=AssetRecordListResponse)
def asset_registry_assets_list(
    q: str = None,
    org_node_id: int = None,
    location_node_id: int = None,
    person_id: int = None,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("asset_registry.view")),
) -> AssetRecordListResponse:
    items = [AssetRecordResponse(**item) for item in service.list_assets(db, q=q, org_node_id=org_node_id, location_node_id=location_node_id, person_id=person_id, include_inactive=include_inactive)]
    return AssetRecordListResponse(items=items, total=len(items))


@router.get("/assets/{asset_id}", response_model=AssetRecordDetailResponse)
def asset_registry_asset_detail(
    asset_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("asset_registry.view")),
) -> AssetRecordDetailResponse:
    return AssetRecordDetailResponse(**service.get_asset_detail(db, asset_id))


@router.post("/assets", response_model=AssetRecordDetailResponse, status_code=201)
def asset_registry_asset_create(
    payload: AssetRecordCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("asset_registry.manage")),
) -> AssetRecordDetailResponse:
    row = service.create_asset(db, payload, user)
    audit.record_audit(db, user_id=user.id, action="asset_registry.asset.create", resource_type="asset", resource_id=str(row.id), details={"asset_tag": row.asset_tag})
    return AssetRecordDetailResponse(**service.get_asset_detail(db, row.id))


@router.put("/assets/{asset_id}", response_model=AssetRecordDetailResponse)
def asset_registry_asset_update(
    asset_id: int,
    payload: AssetRecordUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("asset_registry.manage")),
) -> AssetRecordDetailResponse:
    row = service.update_asset(db, asset_id, payload, user)
    audit.record_audit(db, user_id=user.id, action="asset_registry.asset.update", resource_type="asset", resource_id=str(row.id), details={"asset_tag": row.asset_tag})
    return AssetRecordDetailResponse(**service.get_asset_detail(db, row.id))


@router.post("/assets/{asset_id}/deactivate", response_model=MessageResponse)
def asset_registry_asset_deactivate(
    asset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("asset_registry.manage")),
) -> MessageResponse:
    payload = AssetRecordUpdateRequest(is_active=False)
    row = service.update_asset(db, asset_id, payload, user)
    audit.record_audit(db, user_id=user.id, action="asset_registry.asset.deactivate", resource_type="asset", resource_id=str(row.id), details={"asset_tag": row.asset_tag})
    return MessageResponse(status="success", message="Asset deactivated")


@router.get("/assets/{asset_id}/history", response_model=AssetChangeLogListResponse)
def asset_registry_asset_history(
    asset_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("asset_registry.view")),
) -> AssetChangeLogListResponse:
    data = service.list_asset_change_log(db, asset_id)
    return AssetChangeLogListResponse(items=data["items"], total=data["total"])


@router.get("/matching/candidates", response_model=AssetMatchingCandidateListResponse)
def asset_registry_matching_candidates(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("asset_registry.view")),
) -> AssetMatchingCandidateListResponse:
    items = [item for item in service.matching_candidates(db)]
    return AssetMatchingCandidateListResponse(items=items, total=len(items))


@router.post("/matching/link", response_model=MessageResponse)
def asset_registry_matching_link(
    payload: AssetAgentLinkRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("asset_registry.manage")),
) -> MessageResponse:
    service.link_asset_to_agent(
        db,
        payload.asset_id,
        payload.agent_uuid,
        current_user=user,
        match_source=payload.match_source,
        confidence_score=payload.confidence_score,
        is_primary=payload.is_primary,
        unlink_reason=payload.unlink_reason,
    )
    audit.record_audit(db, user_id=user.id, action="asset_registry.matching.link", resource_type="asset_agent_link", resource_id=f"{payload.asset_id}:{payload.agent_uuid}", details={"asset_id": payload.asset_id, "agent_uuid": payload.agent_uuid})
    return MessageResponse(status="success", message="Asset-agent link updated")


@router.post("/matching/unlink", response_model=MessageResponse)
def asset_registry_matching_unlink(
    payload: AssetAgentLinkRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("asset_registry.manage")),
) -> MessageResponse:
    affected = service.unlink_asset_agent(db, payload.asset_id, payload.agent_uuid, current_user=user, reason=payload.unlink_reason)
    audit.record_audit(db, user_id=user.id, action="asset_registry.matching.unlink", resource_type="asset_agent_link", resource_id=f"{payload.asset_id}:{payload.agent_uuid}", details={"affected": affected})
    return MessageResponse(status="success", message="Asset-agent link removed")


@router.post("/matching/reject", response_model=MessageResponse)
def asset_registry_matching_reject(
    payload: AssetMatchingDecisionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("asset_registry.manage")),
) -> MessageResponse:
    row = service.reject_matching_candidate(
        db,
        candidate_key=payload.candidate_key,
        decision=payload.decision,
        current_user=user,
        asset_id=payload.asset_id,
        agent_uuid=payload.agent_uuid,
        reason=payload.reason,
    )
    audit.record_audit(db, user_id=user.id, action="asset_registry.matching.reject", resource_type="asset_matching_decision", resource_id=str(row.id), details={"candidate_key": payload.candidate_key, "decision": payload.decision})
    return MessageResponse(status="success", message="Matching karari kaydedildi")


@router.get("/data-quality", response_model=AssetDataQualityIssueListResponse)
def asset_registry_data_quality(
    issue_type: str = None,
    asset_id: int = None,
    status_value: str = "open",
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("asset_registry.view")),
) -> AssetDataQualityIssueListResponse:
    data = service.list_data_quality_issues(db, issue_type=issue_type, asset_id=asset_id, status_value=status_value)
    return AssetDataQualityIssueListResponse(items=data["items"], total=data["total"])


@router.post("/data-quality/bulk-update", response_model=MessageResponse)
def asset_registry_data_quality_bulk_update(
    payload: AssetDataQualityBulkUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("asset_registry.manage")),
) -> MessageResponse:
    changed = service.bulk_update_assets(db, payload.asset_ids, payload, current_user=user)
    audit.record_audit(db, user_id=user.id, action="asset_registry.data_quality.bulk_update", resource_type="asset", resource_id="bulk", details={"asset_ids": payload.asset_ids, "changed": changed})
    return MessageResponse(status="success", message=f"{changed} asset guncellendi")


@router.put("/settings/dictionaries", response_model=AssetDictionaryResponse)
def asset_registry_update_dictionaries(
    payload: AssetDictionaryUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("asset_registry.settings.manage")),
) -> AssetDictionaryResponse:
    data = service.update_dictionaries(db, payload)
    audit.record_audit(db, user_id=user.id, action="asset_registry.settings.update_dictionaries", resource_type="asset_registry_settings", resource_id="dictionaries", details={"updated": True})
    return AssetDictionaryResponse(**data)


@router.put("/settings/node-labels", response_model=AssetDictionaryResponse)
def asset_registry_update_node_labels(
    payload: AssetNodeLabelUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("asset_registry.settings.manage")),
) -> AssetDictionaryResponse:
    data = service.update_node_type_labels(db, payload)
    audit.record_audit(
        db,
        user_id=user.id,
        action="asset_registry.settings.update_node_labels",
        resource_type="asset_registry_settings",
        resource_id="node_labels",
        details={
            "organization_node_types": [item.code for item in payload.organization_node_types],
            "location_node_types": [item.code for item in payload.location_node_types],
        },
    )
    return AssetDictionaryResponse(**data)


@router.get("/reports/assets-by-organization", response_model=AssetReportListResponse)
def asset_registry_report_org(
    org_node_id: int = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("asset_registry.reports.view", "asset_registry.view")),
) -> AssetReportListResponse:
    items = service.report_assets_by_organization(db, org_node_id=org_node_id)
    return AssetReportListResponse(items=items, total=len(items))


@router.get("/reports/assets-by-location", response_model=AssetReportListResponse)
def asset_registry_report_location(
    location_node_id: int = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("asset_registry.reports.view", "asset_registry.view")),
) -> AssetReportListResponse:
    items = service.report_assets_by_location(db, location_node_id=location_node_id)
    return AssetReportListResponse(items=items, total=len(items))


@router.get("/reports/assets-without-owner", response_model=AssetReportListResponse)
def asset_registry_report_without_owner(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("asset_registry.reports.view", "asset_registry.view")),
) -> AssetReportListResponse:
    items = service.report_assets_without_owner(db)
    return AssetReportListResponse(items=items, total=len(items))


@router.get("/reports/assets-without-location", response_model=AssetReportListResponse)
def asset_registry_report_without_location(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("asset_registry.reports.view", "asset_registry.view")),
) -> AssetReportListResponse:
    items = service.report_assets_without_location(db)
    return AssetReportListResponse(items=items, total=len(items))


@router.get("/reports/matching-quality", response_model=AssetReportListResponse)
def asset_registry_report_matching_quality(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("asset_registry.reports.view", "asset_registry.view")),
) -> AssetReportListResponse:
    items = service.report_matching_quality(db)
    return AssetReportListResponse(items=items, total=len(items))


@router.get("/reports/assets-by-organization.csv")
def asset_registry_report_org_csv(
    org_node_id: int = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("asset_registry.reports.view", "asset_registry.view")),
):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["label", "value"])
    for item in service.report_assets_by_organization(db, org_node_id=org_node_id):
        writer.writerow([item["label"], item["value"]])
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=assets-by-organization.csv"})


@router.get("/reports/assets-by-location.csv")
def asset_registry_report_location_csv(
    location_node_id: int = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("asset_registry.reports.view", "asset_registry.view")),
):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["label", "value"])
    for item in service.report_assets_by_location(db, location_node_id=location_node_id):
        writer.writerow([item["label"], item["value"]])
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=assets-by-location.csv"})

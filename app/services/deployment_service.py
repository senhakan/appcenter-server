from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Agent, AgentApplication, Application, Deployment
from app.schemas import DeploymentCreateRequest, DeploymentUpdateRequest


def _resolve_target_agents(db: Session, target_type: str, target_id: Optional[str]) -> list[Agent]:
    if target_type == "All":
        return db.query(Agent).all()
    if target_type == "Group":
        if not target_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="target_id required for Group")
        try:
            group_id = int(target_id)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="target_id must be group id") from exc
        return db.query(Agent).filter(Agent.group_id == group_id).all()
    if target_type == "Agent":
        if not target_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="target_id required for Agent")
        agent = db.query(Agent).filter(Agent.uuid == target_id).first()
        return [agent] if agent else []
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid target_type")


def _ensure_application_exists(db: Session, app_id: int) -> None:
    app = db.query(Application).filter(Application.id == app_id).first()
    if not app:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")


def _seed_agent_applications(db: Session, deployment: Deployment) -> int:
    agents = _resolve_target_agents(db, deployment.target_type, deployment.target_id)
    created = 0
    for agent in agents:
        existing = (
            db.query(AgentApplication)
            .filter(AgentApplication.agent_uuid == agent.uuid, AgentApplication.app_id == deployment.app_id)
            .first()
        )
        if existing:
            existing.deployment_id = deployment.id
            if deployment.force_update:
                existing.status = "pending"
            db.add(existing)
            continue

        db.add(
            AgentApplication(
                agent_uuid=agent.uuid,
                app_id=deployment.app_id,
                deployment_id=deployment.id,
                status="pending",
            )
        )
        created += 1
    return created


def create_deployment(db: Session, payload: DeploymentCreateRequest, created_by: Optional[str]) -> Deployment:
    _ensure_application_exists(db, payload.app_id)

    deployment = Deployment(
        app_id=payload.app_id,
        target_type=payload.target_type,
        target_id=payload.target_id,
        is_mandatory=payload.is_mandatory,
        force_update=payload.force_update,
        priority=payload.priority,
        is_active=payload.is_active,
        created_by=created_by,
    )
    db.add(deployment)
    db.flush()
    _seed_agent_applications(db, deployment)
    db.commit()
    db.refresh(deployment)
    return deployment


def list_deployments(db: Session) -> list[Deployment]:
    return db.query(Deployment).order_by(Deployment.created_at.desc()).all()


def get_deployment(db: Session, deployment_id: int) -> Deployment:
    deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
    if not deployment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deployment not found")
    return deployment


def update_deployment(db: Session, deployment_id: int, payload: DeploymentUpdateRequest) -> Deployment:
    deployment = get_deployment(db, deployment_id)
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(deployment, key, value)
    db.add(deployment)
    if deployment.is_active:
        _seed_agent_applications(db, deployment)
    db.commit()
    db.refresh(deployment)
    return deployment


def delete_deployment(db: Session, deployment_id: int) -> None:
    deployment = get_deployment(db, deployment_id)
    db.delete(deployment)
    db.commit()


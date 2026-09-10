"""Authenticated API routes for Microsoft Foundry Architecture Advisor.

Invokes the pre-configured Microsoft Foundry Prompt Agent (`zeroops-architecture-advisor`, version 2)
with Entra ID authentication (DefaultAzureCredential).
Enforces the ZeroOps security boundary: advisory recommendations only; infrastructure
changes require immutable plan approval before Terraform generation.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc

try:
    from backend import auth, models, schemas
    from backend.database import get_db
    from backend.services import foundry_advisor, planner
    from backend.contracts.architecture_advisor import ArchitectureRecommendation
except ImportError:  # pragma: no cover
    import auth, models, schemas
    from database import get_db
    from services import foundry_advisor, planner
    from contracts.architecture_advisor import ArchitectureRecommendation

logger = logging.getLogger("zeroops.routes.architecture_advisor")
router = APIRouter(tags=["architecture-advisor"])


async def _owned_project_or_404(
    project_id: uuid.UUID,
    current_user: models.User,
    db: AsyncSession,
) -> models.Project:
    result = await db.execute(
        select(models.Project).filter(
            models.Project.id == project_id,
            models.Project.user_id == current_user.id,
        )
    )
    project = result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project


async def _latest_project_analysis(
    db: AsyncSession,
    project_id: uuid.UUID,
) -> models.AIAnalysis | None:
    result = await db.execute(
        select(models.AIAnalysis)
        .filter(models.AIAnalysis.project_id == project_id)
        .order_by(desc(models.AIAnalysis.created_at))
        .limit(1)
    )
    return result.scalars().first()


def _analysis_to_plan_facts(analysis: models.AIAnalysis | None) -> dict[str, Any]:
    if not analysis:
        return {}
    return {
        "framework": analysis.framework,
        "version": analysis.framework_version,
        "runtime": analysis.runtime,
        "package_manager": analysis.package_manager,
        "docker_support": analysis.docker_support,
        "database_dependencies": analysis.database_dependencies or [],
        "environment_variables": analysis.environment_variables or [],
        "port": analysis.port,
        "vulnerabilities": analysis.vulnerabilities or [],
    }


@router.post(
    "/api/projects/{project_id}/architecture-advisor/recommend",
    response_model=dict,
)
async def consult_architecture_advisor(
    project_id: uuid.UUID,
    req: Optional[schemas.ArchitectureAdvisorRequest] = None,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Invoke Microsoft Foundry Prompt Agent (zeroops-architecture-advisor v2).

    Uses Microsoft Entra ID (DefaultAzureCredential) and server-side agent tools
    (File Search, Web Search, GPT-5.6 Terra) to generate an evidence-backed architecture recommendation.
    """
    project = await _owned_project_or_404(project_id, current_user, db)
    analysis = await _latest_project_analysis(db, project.id)
    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Analyze this application before consulting the Architecture Advisor.",
        )

    facts = _analysis_to_plan_facts(analysis)
    user_query = req.user_query if req else None

    try:
        recommendation = await asyncio.to_thread(
            foundry_advisor.invoke_architecture_advisor,
            facts,
            project_name=project.full_name or project.name or "application",
            user_query=user_query,
        )
    except foundry_advisor.FoundryAuthenticationError as auth_err:
        logger.warning("Architecture Advisor authentication failed: %s", auth_err)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Microsoft Foundry authentication failed: {auth_err}",
        ) from auth_err
    except foundry_advisor.FoundryAuthorizationError as authz_err:
        logger.warning("Architecture Advisor access forbidden: %s", authz_err)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Microsoft Foundry access denied: {authz_err}",
        ) from authz_err
    except Exception as err:
        logger.error("Architecture Advisor invocation error: %s", err)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Microsoft Foundry Architecture Advisor is temporarily unavailable. Please try again later.",
        ) from err

    rec_data = recommendation.model_dump(mode="json")

    # If an infrastructure plan already exists, attach the advisor recommendation to it
    plan_result = await db.execute(
        select(models.InfrastructurePlan).filter(
            models.InfrastructurePlan.project_id == project_id,
            models.InfrastructurePlan.user_id == current_user.id,
        )
    )
    plan_record = plan_result.scalars().first()
    if plan_record:
        updated_plan_data = planner.attach_advisor_recommendation(
            plan_record.plan_data or {},
            rec_data,
        )
        plan_record.plan_data = updated_plan_data
        plan_record.ai_explanations = updated_plan_data.get("ai_explanations")
        await db.commit()
        await db.refresh(plan_record)

    db.add(
        models.ActivityEvent(
            user_id=current_user.id,
            project_id=project_id,
            action="Architecture Advisor consulted",
            details="Microsoft Foundry Architecture Advisor generated evidence-based recommendations.",
        )
    )
    await db.commit()

    return rec_data


@router.get(
    "/api/projects/{project_id}/architecture-advisor/recommend",
    response_model=dict,
)
async def get_architecture_advisor_recommendation(
    project_id: uuid.UUID,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve the latest cached Architecture Advisor recommendation for this project."""
    project = await _owned_project_or_404(project_id, current_user, db)
    plan_result = await db.execute(
        select(models.InfrastructurePlan).filter(
            models.InfrastructurePlan.project_id == project_id,
            models.InfrastructurePlan.user_id == current_user.id,
        )
    )
    plan_record = plan_result.scalars().first()
    if plan_record and plan_record.plan_data and "advisor_recommendation" in plan_record.plan_data:
        return plan_record.plan_data["advisor_recommendation"]

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="No architecture advisor recommendation found for this project. Consult the advisor first.",
    )


@router.post(
    "/api/projects/{project_id}/architecture-advisor/chat",
    response_model=dict,
)
async def chat_with_architecture_advisor(
    project_id: uuid.UUID,
    req: schemas.ChatRequest,
    conversation_id: Optional[str] = None,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Interactive chat with the Microsoft Foundry Architecture Advisor."""
    project = await _owned_project_or_404(project_id, current_user, db)
    plan_result = await db.execute(
        select(models.InfrastructurePlan).filter(
            models.InfrastructurePlan.project_id == project_id,
            models.InfrastructurePlan.user_id == current_user.id,
        )
    )
    plan = plan_result.scalars().first()
    plan_data = plan.plan_data if plan else {}

    try:
        updated_plan, reply, new_conversation_id, citations = await asyncio.to_thread(
            foundry_advisor.advisor_chat,
            req.message,
            plan_data,
            conversation_id=conversation_id,
        )
    except Exception as err:
        logger.error("Architecture Advisor chat error: %s", err)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Microsoft Foundry Architecture Advisor is temporarily unavailable.",
        ) from err

    return {
        "reply": reply,
        "conversation_id": new_conversation_id,
        "citations": [c.model_dump(mode="json") for c in citations],
    }

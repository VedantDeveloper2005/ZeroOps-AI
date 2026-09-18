"""
Ephemeral Cloud Resources & Integrations API Routes
===================================================
Endpoints for on-demand cloud sandboxes, AI resource chat, service catalog,
Jira webhooks, and developer email-to-cloud ops automation.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

try:
    from backend import auth, models, schemas
    from backend.database import get_db
    from backend.services.ephemeral_resources import (
        RESOURCE_CATALOG,
        REGIONS,
        provision_ephemeral_resource,
        extend_ephemeral_resource,
        destroy_ephemeral_resource,
    )
    from backend.services.resource_chat import process_resource_chat
    from backend.services.jira_service import process_jira_webhook
    from backend.services.inbound_email_service import process_inbound_developer_email
except ImportError:
    import auth
    import models
    import schemas
    from database import get_db
    from services.ephemeral_resources import (
        RESOURCE_CATALOG,
        REGIONS,
        provision_ephemeral_resource,
        extend_ephemeral_resource,
        destroy_ephemeral_resource,
    )
    from services.resource_chat import process_resource_chat
    from services.jira_service import process_jira_webhook
    from services.inbound_email_service import process_inbound_developer_email

logger = logging.getLogger("zeroops.routes.ephemeral_resources")

router = APIRouter(tags=["Ephemeral Cloud Sandboxes & Integrations"])


def _serialize_resource(res: models.EphemeralResource) -> schemas.EphemeralResourceResponse:
    now = datetime.now(timezone.utc)
    expires = res.expires_at.replace(tzinfo=timezone.utc) if res.expires_at.tzinfo is None else res.expires_at
    remaining_secs = max(0, int((expires - now).total_seconds())) if res.status == "active" else 0
    return schemas.EphemeralResourceResponse(
        id=res.id,
        user_id=res.user_id,
        name=res.name,
        resource_type=res.resource_type,
        region=res.region,
        sku=res.sku,
        status=res.status,
        source=res.source,
        source_reference=res.source_reference,
        ttl_minutes=res.ttl_minutes,
        expires_at=res.expires_at,
        time_remaining_seconds=remaining_secs,
        cost_estimate_hourly=res.cost_estimate_hourly,
        connection_info=res.connection_info or {},
        configuration=res.configuration or {},
        azure_resource_id=res.azure_resource_id,
        azure_resource_group=res.azure_resource_group,
        logs=res.logs or [],
        created_at=res.created_at,
        updated_at=res.updated_at,
        destroyed_at=res.destroyed_at,
    )


# ──────────────────────────────────────────────
# CATALOG & ACTIVE RESOURCES
# ──────────────────────────────────────────────

@router.get("/api/resources/catalog")
async def get_resource_catalog():
    """Returns available cloud resource categories, SKUs, OS distros, and regions."""
    return {
        "catalog": RESOURCE_CATALOG,
        "regions": REGIONS,
    }


@router.get("/api/resources", response_model=List[schemas.EphemeralResourceResponse])
async def list_ephemeral_resources(
    status_filter: Optional[str] = Query(None, alias="status"),
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lists on-demand cloud sandboxes for the current user."""
    query = select(models.EphemeralResource).filter(models.EphemeralResource.user_id == current_user.id)
    if status_filter:
        query = query.filter(models.EphemeralResource.status == status_filter)
    query = query.order_by(desc(models.EphemeralResource.created_at))

    result = await db.execute(query)
    resources = result.scalars().all()
    return [_serialize_resource(r) for r in resources]


@router.post("/api/resources", response_model=schemas.EphemeralResourceResponse, status_code=status.HTTP_201_CREATED)
async def create_ephemeral_resource(
    req: schemas.EphemeralResourceCreateRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Provisions a new on-demand cloud resource from the catalog dropdown form."""
    try:
        resource = await provision_ephemeral_resource(
            db=db,
            user=current_user,
            request=req,
            source=req.source or "catalog_ui",
        )
        return _serialize_resource(resource)
    except Exception as e:
        logger.exception("Failed to provision ephemeral resource")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Resource provisioning failed: {str(e)}",
        )


@router.get("/api/resources/{resource_id}", response_model=schemas.EphemeralResourceResponse)
async def get_ephemeral_resource(
    resource_id: uuid.UUID,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieves full details and connection info for a specific cloud sandbox."""
    res_query = await db.execute(
        select(models.EphemeralResource).filter(
            models.EphemeralResource.id == resource_id,
            models.EphemeralResource.user_id == current_user.id,
        )
    )
    resource = res_query.scalars().first()
    if not resource:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    return _serialize_resource(resource)


@router.post("/api/resources/{resource_id}/extend", response_model=schemas.EphemeralResourceResponse)
async def extend_resource_ttl(
    resource_id: uuid.UUID,
    req: schemas.EphemeralResourceExtendRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Extends the Time-To-Live countdown of an active ephemeral resource."""
    try:
        resource = await extend_ephemeral_resource(
            db=db,
            user_id=current_user.id,
            resource_id=resource_id,
            extend_minutes=req.extend_minutes,
        )
        return _serialize_resource(resource)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.exception("Failed to extend resource TTL")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to extend TTL")


@router.delete("/api/resources/{resource_id}", response_model=schemas.EphemeralResourceResponse)
async def destroy_resource_now(
    resource_id: uuid.UUID,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Immediately tears down and destroys an active ephemeral cloud sandbox."""
    res_query = await db.execute(
        select(models.EphemeralResource).filter(
            models.EphemeralResource.id == resource_id,
            models.EphemeralResource.user_id == current_user.id,
        )
    )
    resource = res_query.scalars().first()
    if not resource:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")

    try:
        destroyed = await destroy_ephemeral_resource(db=db, resource=resource, reason="User triggered manual destroy")
        return _serialize_resource(destroyed)
    except Exception as e:
        logger.exception("Failed to destroy ephemeral resource")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to destroy resource")


# ──────────────────────────────────────────────
# CONVERSATIONAL AI RESOURCE CHAT
# ──────────────────────────────────────────────

@router.post("/api/resources/chat", response_model=schemas.EphemeralChatResponse)
async def chat_for_resources(
    req: schemas.EphemeralChatRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Conversational AI DevOps Assistant: translates natural language requests into
    structured resource proposals, plans, and lifecycle management actions.
    Supports instant auto-deployment with zero manual confirmation.
    """
    count_query = await db.execute(
        select(models.EphemeralResource).filter(
            models.EphemeralResource.user_id == current_user.id,
            models.EphemeralResource.status == "active",
        )
    )
    active_count = len(count_query.scalars().all())

    response = await process_resource_chat(
        message=req.message,
        user=current_user,
        active_resources_count=active_count,
    )

    # Fully automatic zero-touch provisioning if auto_deploy flag is set or requested in prompt
    should_auto_deploy = bool(
        req.auto_deploy
        or any(k in req.message.lower() for k in ["now", "immediately", "auto deploy", "launch now", "spin up right now"])
    )
    if should_auto_deploy and response.proposed_resource:
        prop = response.proposed_resource
        create_req = schemas.EphemeralResourceCreateRequest(
            name=prop.name,
            resource_type=prop.resource_type,
            region=prop.region,
            sku=prop.sku,
            ttl_minutes=prop.ttl_minutes,
            os_distro=prop.os_distro,
            startup_script=prop.startup_script or None,
            open_ports=prop.open_ports,
            source="ai_chat_autopilot",
        )
        created = await provision_ephemeral_resource(
            db=db,
            user=current_user,
            request=create_req,
            source="ai_chat_autopilot",
        )
        serialized = _serialize_resource(created)
        response.created_resource = serialized
        response.reply = (
            f"⚡ **Auto-Pilot Launched!** Your sandbox **{created.name}** ({created.sku}) is live!\n\n"
            f"• **Public IP:** `{created.connection_info.get('public_ip', 'Allocated')}`\n"
            f"• **SSH / Access:** `{created.connection_info.get('ssh_command') or created.connection_info.get('connection_string') or 'Active'}`\n"
            f"• **Auto-Teardown:** In {created.ttl_minutes} minutes ({created.expires_at.strftime('%H:%M UTC')})\n\n"
            "Zero manual setup required—connect and run your workloads right now!"
        )

    return response


# ──────────────────────────────────────────────
# INTEGRATIONS (JIRA & EMAIL-TO-OPS)
# ──────────────────────────────────────────────

@router.get("/api/integrations/settings", response_model=schemas.IntegrationSettingsResponse)
async def get_integration_settings(
    request: Request,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieves Jira and Email integration configuration."""
    base_url = str(request.base_url).rstrip("/")
    cfg_query = await db.execute(
        select(models.IntegrationConfig).filter(models.IntegrationConfig.user_id == current_user.id)
    )
    cfg = cfg_query.scalars().first()

    if not cfg:
        jira = schemas.JiraIntegrationSettings()
        email = schemas.EmailIntegrationSettings(allowed_domains=[current_user.email.split("@")[-1]])
    else:
        jira = schemas.JiraIntegrationSettings(
            jira_enabled=cfg.jira_enabled,
            jira_host=cfg.jira_host,
            jira_email=cfg.jira_email,
            jira_api_token="••••••••" if cfg.jira_api_token else None,
            jira_project_keys=cfg.jira_project_keys or ["QA", "DEV", "INFRA"],
            jira_auto_provision=cfg.jira_auto_provision,
        )
        email = schemas.EmailIntegrationSettings(
            email_enabled=cfg.email_enabled,
            inbound_email_address=cfg.inbound_email_address or "sandbox@zeroops.ai",
            allowed_domains=cfg.allowed_domains or [],
            default_ttl_minutes=cfg.default_ttl_minutes or 120,
        )

    return schemas.IntegrationSettingsResponse(
        jira=jira,
        email=email,
        webhook_url=f"{base_url}/api/integrations/jira/webhook",
        inbound_email_url=f"{base_url}/api/integrations/email/inbound",
    )


@router.put("/api/integrations/settings", response_model=schemas.IntegrationSettingsResponse)
async def update_integration_settings(
    settings: schemas.IntegrationSettingsResponse,
    request: Request,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Updates Jira and Email integration configuration."""
    cfg_query = await db.execute(
        select(models.IntegrationConfig).filter(models.IntegrationConfig.user_id == current_user.id)
    )
    cfg = cfg_query.scalars().first()
    if not cfg:
        cfg = models.IntegrationConfig(user_id=current_user.id)
        db.add(cfg)

    cfg.jira_enabled = settings.jira.jira_enabled
    cfg.jira_host = settings.jira.jira_host
    cfg.jira_email = settings.jira.jira_email
    if settings.jira.jira_api_token and not settings.jira.jira_api_token.startswith("••"):
        cfg.jira_api_token = settings.jira.jira_api_token
    cfg.jira_project_keys = settings.jira.jira_project_keys
    cfg.jira_auto_provision = settings.jira.jira_auto_provision

    cfg.email_enabled = settings.email.email_enabled
    cfg.inbound_email_address = settings.email.inbound_email_address
    cfg.allowed_domains = settings.email.allowed_domains
    cfg.default_ttl_minutes = settings.email.default_ttl_minutes
    cfg.updated_at = datetime.now(timezone.utc)

    await db.commit()
    return await get_integration_settings(request, current_user, db)


@router.post("/api/integrations/jira/webhook")
async def jira_webhook_endpoint(
    payload: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
):
    """Public webhook receiver called by Atlassian Jira Cloud/Server."""
    try:
        result = await process_jira_webhook(db=db, payload=payload)
        return result
    except Exception as e:
        logger.exception("Jira webhook processing error")
        return {"status": "error", "detail": str(e)}


@router.post("/api/integrations/jira/test-sync")
async def test_jira_ticket_sync(
    data: Dict[str, Any],
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Test endpoint that simulates a Jira ticket webhook payload."""
    issue_key = data.get("issue_key", "QA-501")
    summary = data.get("summary", "Need test Ubuntu VM for payment gateway stress testing")
    description = data.get("description", "Please provision a 4-core Linux VM with Docker in East US for 3 hours.")
    labels = data.get("labels", ["zeroops-sandbox"])

    payload = {
        "webhookEvent": "jira:issue_created",
        "issue": {
            "key": issue_key,
            "fields": {
                "summary": summary,
                "description": description,
                "labels": labels,
                "status": {"name": "In Progress"},
            },
        },
    }

    result = await process_jira_webhook(db=db, payload=payload, fallback_user_id=current_user.id)
    return result


@router.post("/api/integrations/email/inbound")
async def inbound_email_webhook(
    payload: schemas.InboundEmailPayload,
    db: AsyncSession = Depends(get_db),
):
    """Inbound webhook receiver for developer emails (compatible with SendGrid, Mailgun, SES, Postmark)."""
    try:
        result = await process_inbound_developer_email(db=db, payload=payload)
        return result
    except Exception as e:
        logger.exception("Inbound email processing error")
        return {"status": "error", "detail": str(e)}


@router.post("/api/integrations/email/test-parse")
async def test_email_developer_request(
    data: Dict[str, Any],
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Test endpoint simulating a developer emailing the firm's ops address."""
    from_email = data.get("from_email", current_user.email)
    from_name = data.get("from_name", f"{current_user.first_name or 'Dev'} {current_user.last_name or ''}".strip())
    subject = data.get("subject", "Requesting test Postgres DB for database migration verification")
    body = data.get("body_text", "Hi Ops team, please spin up a test PostgreSQL database in East US for 2 hours. Thanks!")

    payload = schemas.InboundEmailPayload(
        from_email=from_email,
        from_name=from_name,
        to_email="sandbox@zeroops.ai",
        subject=subject,
        body_text=body,
    )

    result = await process_inbound_developer_email(db=db, payload=payload)
    return result

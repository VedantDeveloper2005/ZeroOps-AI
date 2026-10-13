"""
Ephemeral Cloud Resources & Integrations API Routes
===================================================
Endpoints for on-demand cloud sandboxes, AI resource chat, service catalog,
Jira webhooks, and developer email-to-cloud ops automation.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

try:
    from backend import auth, models, schemas
    from backend.database import get_db
    from backend.services.ephemeral_resources import (
        RESOURCE_CATALOG,
        REGIONS,
        AzureResourceProvisioningError,
        provision_ephemeral_resource,
        extend_ephemeral_resource,
        destroy_ephemeral_resource,
    )
    from backend.services.resource_chat import process_resource_chat
    from backend.services.jira_service import process_jira_webhook
    from backend.services.inbound_email_service import process_inbound_developer_email
    from backend.services.cost_engine import calculate_custom_subtotal
except ImportError:
    import auth
    import models
    import schemas
    from database import get_db
    from services.ephemeral_resources import (
        RESOURCE_CATALOG,
        REGIONS,
        AzureResourceProvisioningError,
        provision_ephemeral_resource,
        extend_ephemeral_resource,
        destroy_ephemeral_resource,
    )
    from services.resource_chat import process_resource_chat
    from services.jira_service import process_jira_webhook
    from services.inbound_email_service import process_inbound_developer_email
    from services.cost_engine import calculate_custom_subtotal

logger = logging.getLogger("zeroops.routes.ephemeral_resources")

router = APIRouter(tags=["Ephemeral Cloud Sandboxes & Integrations"])


def _serialize_resource(res: models.EphemeralResource) -> schemas.EphemeralResourceResponse:
    managed_resources = (res.configuration or {}).get("managed_resources") or []
    is_unverified = not managed_resources
    now = datetime.now(timezone.utc)
    expires = res.expires_at.replace(tzinfo=timezone.utc) if res.expires_at.tzinfo is None else res.expires_at
    remaining_secs = max(0, int((expires - now).total_seconds())) if res.status == "active" and not is_unverified else 0
    hourly = 0.0 if is_unverified else res.cost_estimate_hourly
    total = 0.0 if is_unverified else round(hourly * (res.ttl_minutes / 60.0), 3)
    return schemas.EphemeralResourceResponse(
        id=res.id,
        user_id=res.user_id,
        name=res.name,
        resource_type=res.resource_type,
        region=res.region,
        sku=res.sku,
        status="unverified" if is_unverified else res.status,
        source=res.source,
        source_reference=res.source_reference,
        ttl_minutes=res.ttl_minutes,
        expires_at=res.expires_at,
        time_remaining_seconds=remaining_secs,
        cost_estimate_hourly=hourly,
        hourly_subtotal=hourly,
        total_subtotal=total,
        connection_info={} if is_unverified else res.connection_info or {},
        configuration={} if is_unverified else res.configuration or {},
        azure_resource_id=None if is_unverified else res.azure_resource_id,
        azure_resource_group=None if is_unverified else res.azure_resource_group,
        logs=([{
            "timestamp": res.updated_at.isoformat(),
            "message": "No Azure resource IDs were recorded for this legacy entry. Its Azure status is unverified; check the Azure portal before taking action.",
        }] if is_unverified else res.logs or []),
        created_at=res.created_at,
        updated_at=res.updated_at,
        destroyed_at=None if is_unverified else res.destroyed_at,
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


@router.post("/api/resources/quote")
async def quote_custom_resource(
    req: schemas.CustomResourceQuoteRequest,
    current_user: models.User = Depends(auth.get_current_user),
):
    """Return one all-inclusive estimate; internal platform and AI components stay embedded."""
    quote = calculate_custom_subtotal(req.estimated_resource_hourly_usd, req.ttl_minutes)
    return quote.to_dict()


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
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except AzureResourceProvisioningError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        logger.exception("Failed to provision ephemeral resource")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Azure resource provisioning failed. Check the Azure deployment activity before retrying.",
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
    active_count = sum(
        bool((resource.configuration or {}).get("managed_resources"))
        for resource in count_query.scalars().all()
    )

    response = await process_resource_chat(
        message=req.message,
        user=current_user,
        active_resources_count=active_count,
        selected_region=req.region,
    )

    # Infrastructure changes require an explicit UI/API confirmation. Natural
    # language such as "now" is not an authorization signal.
    should_auto_deploy = bool(req.auto_deploy)
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
            arm_template=prop.arm_template,
            estimated_resource_hourly_usd=prop.estimated_resource_hourly_usd,
            source="ai_chat_autopilot",
        )
        try:
            created = await provision_ephemeral_resource(
                db=db,
                user=current_user,
                request=create_req,
                source="ai_chat_autopilot",
            )
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
        except AzureResourceProvisioningError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
        serialized = _serialize_resource(created)
        response.created_resource = serialized
        response.reply = (
            f"Azure confirmed **{created.name}** is deployed in resource group "
            f"**{created.azure_resource_group}**. The all-inclusive subtotal is "
            f"${created.cost_estimate_hourly:.3f}/hr. Auto-teardown is scheduled for "
            f"{created.expires_at.strftime('%Y-%m-%d %H:%M UTC')}."
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
            jira_webhook_secret="••••••••" if cfg.jira_webhook_secret_encrypted else None,
            jira_project_keys=cfg.jira_project_keys or ["QA", "DEV", "INFRA"],
            jira_auto_provision=cfg.jira_auto_provision,
        )
        email = schemas.EmailIntegrationSettings(
            email_enabled=cfg.email_enabled,
            inbound_email_address=cfg.inbound_email_address or "sandbox@zeroops.ai",
            allowed_domains=cfg.allowed_domains or [],
            default_ttl_minutes=cfg.default_ttl_minutes or 120,
            email_webhook_secret="••••••••" if cfg.email_webhook_secret_encrypted else None,
        )

    return schemas.IntegrationSettingsResponse(
        jira=jira,
        email=email,
        webhook_url=f"{base_url}/api/integrations/jira/webhook/{current_user.id}",
        inbound_email_url=f"{base_url}/api/integrations/email/inbound/{current_user.id}",
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
        cfg.jira_api_token = auth.encrypt_mfa_secret(settings.jira.jira_api_token)
    if settings.jira.jira_webhook_secret and not settings.jira.jira_webhook_secret.startswith("••"):
        cfg.jira_webhook_secret_encrypted = auth.encrypt_mfa_secret(settings.jira.jira_webhook_secret)
    cfg.jira_project_keys = settings.jira.jira_project_keys
    cfg.jira_auto_provision = settings.jira.jira_auto_provision

    cfg.email_enabled = settings.email.email_enabled
    cfg.inbound_email_address = settings.email.inbound_email_address
    cfg.allowed_domains = settings.email.allowed_domains
    cfg.default_ttl_minutes = settings.email.default_ttl_minutes
    if settings.email.email_webhook_secret and not settings.email.email_webhook_secret.startswith("••"):
        cfg.email_webhook_secret_encrypted = auth.encrypt_mfa_secret(settings.email.email_webhook_secret)
    cfg.updated_at = datetime.now(timezone.utc)

    await db.commit()
    return await get_integration_settings(request, current_user, db)


@router.post("/api/integrations/jira/webhook/{integration_user_id}")
async def jira_webhook_endpoint(
    integration_user_id: uuid.UUID,
    request: Request,
    x_hub_signature: Optional[str] = Header(None, alias="X-Hub-Signature"),
    db: AsyncSession = Depends(get_db),
):
    """Verify Atlassian's HMAC signature and bind the event to one integration owner."""
    config_query = await db.execute(
        select(models.IntegrationConfig).filter(
            models.IntegrationConfig.user_id == integration_user_id,
            models.IntegrationConfig.jira_enabled.is_(True),
        )
    )
    integration = config_query.scalars().first()
    secret = (
        auth.decrypt_mfa_secret(integration.jira_webhook_secret_encrypted)
        if integration and integration.jira_webhook_secret_encrypted
        else None
    )
    body = await request.body()
    if not secret or not x_hub_signature:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Jira webhook authentication is not configured.")
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, x_hub_signature.strip()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Jira webhook signature.")
    try:
        payload = json.loads(body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Webhook body must be a JSON object.")
        result = await process_jira_webhook(db=db, payload=payload, fallback_user_id=integration_user_id)
        return result
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Jira webhook JSON payload.") from e
    except Exception as e:
        logger.exception("Jira webhook processing error")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Jira event processing failed. Check resource activity before retrying.") from e


@router.post("/api/integrations/jira/webhook")
async def legacy_jira_webhook_endpoint():
    raise HTTPException(status_code=status.HTTP_410_GONE, detail="Use the tenant-specific signed Jira webhook URL from Integration settings.")


@router.post("/api/integrations/jira/test-sync")
async def test_jira_ticket_sync(
    current_user: models.User = Depends(auth.get_current_user),
):
    raise HTTPException(status_code=status.HTTP_410_GONE, detail="Simulated webhook runs were removed. Send a signed Jira event to the configured webhook URL.")


@router.post("/api/integrations/email/inbound/{integration_user_id}")
async def inbound_email_webhook(
    integration_user_id: uuid.UUID,
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: AsyncSession = Depends(get_db),
):
    """Receive a tenant-owned normalized email payload using a bearer webhook secret."""
    config_query = await db.execute(
        select(models.IntegrationConfig).filter(
            models.IntegrationConfig.user_id == integration_user_id,
            models.IntegrationConfig.email_enabled.is_(True),
        )
    )
    integration = config_query.scalars().first()
    secret = (
        auth.decrypt_mfa_secret(integration.email_webhook_secret_encrypted)
        if integration and integration.email_webhook_secret_encrypted
        else None
    )
    bearer = authorization[7:].strip() if authorization and authorization.lower().startswith("bearer ") else ""
    if not secret or not bearer or not hmac.compare_digest(secret, bearer):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid inbound email webhook credential.")
    try:
        body = await request.body()
        payload = schemas.InboundEmailPayload.model_validate_json(body)
        result = await process_inbound_developer_email(db=db, payload=payload, owner_user_id=integration_user_id)
        return result
    except Exception as e:
        logger.exception("Inbound email processing error")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Inbound email processing failed. Check resource activity before retrying.") from e


@router.post("/api/integrations/email/inbound")
async def legacy_inbound_email_webhook():
    raise HTTPException(status_code=status.HTTP_410_GONE, detail="Use the tenant-specific email webhook URL and bearer secret from Integration settings.")


@router.post("/api/integrations/email/test-parse")
async def test_email_developer_request(
    current_user: models.User = Depends(auth.get_current_user),
):
    raise HTTPException(status_code=status.HTTP_410_GONE, detail="Simulated email runs were removed. Send a normalized, authenticated email event to the configured inbound URL.")

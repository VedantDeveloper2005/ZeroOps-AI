"""
Inbound Email Provisioning Agent Service
========================================
Parses infrastructure requests received via email from developers and QA engineers.
Extracts specifications using AI/rule parsing, automatically provisions the required
Azure resources in minutes, and emails back a full deployment report with SSH/access
credentials, public IP endpoints, and auto-destruction countdowns.
"""

from __future__ import annotations

import logging
from html import escape
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

try:
    from backend import models, schemas
    from backend.services import email_service
    from backend.services.ephemeral_resources import provision_ephemeral_resource
    from backend.services.resource_chat import process_resource_chat
except ImportError:
    import models
    import schemas
    from services import email_service
    from services.ephemeral_resources import provision_ephemeral_resource
    from services.resource_chat import process_resource_chat

logger = logging.getLogger("zeroops.inbound_email")


def generate_developer_reply_email(
    resource: models.EphemeralResource,
    developer_name: Optional[str] = None,
    original_subject: str = "",
) -> tuple[str, str, str]:
    """Generate a truthful deployment receipt without inventing network details."""
    conn = resource.connection_info or {}
    dev_name = (developer_name or "Engineer").replace("\r", " ").replace("\n", " ")[:120]
    expires_str = resource.expires_at.strftime("%Y-%m-%d %H:%M:%S UTC")
    safe_original_subject = original_subject.replace("\r", " ").replace("\n", " ")[:160]
    subject = f"Re: {safe_original_subject} - [Ready: {resource.name}]"
    if not original_subject:
        subject = f"[ZeroOps AI] Azure resources for {resource.name} are ready"
    resource_count = int((resource.configuration or {}).get("resource_count", 1))
    portal_url = str(conn.get("portal_url") or "")
    text_body = (
        f"Hi {dev_name},\n\n"
        f"Azure confirmed {resource_count} resource(s) from your request.\n\n"
        f"Name: {resource.name}\nType: {resource.resource_type} ({resource.sku})\n"
        f"Region: {resource.region}\nResource group: {resource.azure_resource_group or 'See Azure portal'}\n"
        f"All-inclusive subtotal: ${resource.cost_estimate_hourly:.3f}/hr\n"
        f"Estimated subtotal for {resource.ttl_minutes} minutes: ${round(resource.cost_estimate_hourly * resource.ttl_minutes / 60.0, 3):.3f}\n"
        f"Auto-teardown: {expires_str} ({resource.ttl_minutes} minutes)\n"
        f"Azure portal: {portal_url or 'Open ZeroOps to view the deployment'}\n\n"
        "ZeroOps only reports connection details Azure returned; this message does not include credentials.\n"
    )
    safe_name = escape(resource.name)
    safe_type = escape(resource.resource_type)
    safe_sku = escape(resource.sku)
    safe_region = escape(resource.region)
    safe_group = escape(resource.azure_resource_group or "See Azure portal")
    safe_developer = escape(dev_name)
    safe_expiry = escape(expires_str)
    safe_portal = escape(portal_url, quote=True)
    portal_link = f'<a href="{safe_portal}">Open Azure resource group</a>' if portal_url.startswith("https://portal.azure.com/") else "Open ZeroOps to view the deployment"
    html_content = (
        '<div style="font-family:Segoe UI,Arial,sans-serif;line-height:1.6;color:#172033">'
        f"<p>Hi {safe_developer},</p><p>Azure confirmed {resource_count} resource(s) from your request.</p>"
        "<table><tbody>"
        f"<tr><td>Name</td><td>{safe_name}</td></tr><tr><td>Type</td><td>{safe_type} ({safe_sku})</td></tr>"
        f"<tr><td>Region</td><td>{safe_region}</td></tr><tr><td>Resource group</td><td>{safe_group}</td></tr>"
        f"<tr><td>All-inclusive subtotal</td><td>${resource.cost_estimate_hourly:.3f}/hr</td></tr>"
        f"<tr><td>Estimated subtotal for {resource.ttl_minutes} minutes</td><td>${round(resource.cost_estimate_hourly * resource.ttl_minutes / 60.0, 3):.3f}</td></tr>"
        f"<tr><td>Auto-teardown</td><td>{safe_expiry} ({resource.ttl_minutes} minutes)</td></tr>"
        f"</tbody></table><p>{portal_link}</p>"
        "<p>Connection details are available only when Azure returns them and are not included as generated credentials.</p></div>"
    )
    return subject, html_content, text_body


async def process_inbound_developer_email(
    db: AsyncSession,
    payload: schemas.InboundEmailPayload,
    owner_user_id: Optional[uuid.UUID] = None,
) -> Dict[str, Any]:
    """
    Parses incoming developer email, authorizes the sender, extracts requirements,
    provisions the Azure resource, and emails back deployment access details.
    """
    from_email = payload.from_email.strip().lower()
    from_name = payload.from_name or from_email.split("@")[0]
    subject = payload.subject.strip()
    body_text = payload.body_text.strip()
    combined_content = f"{subject}\n{body_text}"

    if "@" not in from_email:
        return {"status": "rejected", "reason": "Sender address is invalid."}
    sender_domain = from_email.rsplit("@", 1)[1]

    if owner_user_id:
        config_result = await db.execute(
            select(models.IntegrationConfig).filter(
                models.IntegrationConfig.user_id == owner_user_id,
                models.IntegrationConfig.email_enabled.is_(True),
            )
        )
        integration_cfg = config_result.scalars().first()
        owner_result = await db.execute(select(models.User).filter(models.User.id == owner_user_id))
        user = owner_result.scalars().first()
        if not integration_cfg or not user:
            return {"status": "rejected", "reason": "The email integration owner is not configured."}
        allowed_domains = {str(value).strip().casefold() for value in (integration_cfg.allowed_domains or [])}
        if sender_domain.casefold() not in allowed_domains and from_email != user.email.casefold():
            return {"status": "rejected", "reason": "Sender domain is not allowed for this integration."}
    else:
        # Legacy direct service calls may resolve an exact registered sender only.
        # Never route an unowned email to the first account in the database.
        owner_result = await db.execute(select(models.User).filter(models.User.email == from_email))
        user = owner_result.scalars().first()
        if not user:
            return {"status": "rejected", "reason": "No integration owner is authorized for this sender."}

    if payload.message_id:
        duplicate_result = await db.execute(
            select(models.EphemeralResource).filter(
                models.EphemeralResource.user_id == user.id,
                models.EphemeralResource.source == "email",
                models.EphemeralResource.source_reference == payload.message_id,
            )
        )
        duplicate = duplicate_result.scalars().first()
        if duplicate:
            return {"status": "already_processed", "resource_id": str(duplicate.id)}

    # The AI prepares a reviewed template, but the organization's explicit email
    # automation policy authorizes apply. Missing price/model details get a reply,
    # never a guessed resource or a fabricated success email.
    plan = await process_resource_chat(combined_content, user)
    if not plan.proposed_resource:
        email_service._send_email(
            to_email=from_email,
            subject=f"Re: {subject.replace(chr(13), ' ').replace(chr(10), ' ')[:160]} - more details needed",
            html_body=f"<p>{escape(plan.reply)}</p>",
            text_body=plan.reply,
        )
        return {"status": "needs_details", "recipient": from_email}

    proposal = plan.proposed_resource
    create_req = schemas.EphemeralResourceCreateRequest(
        name=proposal.name,
        resource_type=proposal.resource_type,
        region=proposal.region,
        sku=proposal.sku,
        ttl_minutes=min(proposal.ttl_minutes, integration_cfg.default_ttl_minutes if owner_user_id else proposal.ttl_minutes),
        arm_template=proposal.arm_template,
        arm_parameters=proposal.arm_parameters,
        estimated_resource_hourly_usd=proposal.estimated_resource_hourly_usd,
        tags={"requester_domain": sender_domain, "source": "email"},
        source="email",
    )
    resource = await provision_ephemeral_resource(
        db=db,
        user=user,
        request=create_req,
        source="email",
        source_reference=payload.message_id or f"{from_email}:{subject[:80]}",
    )

    # 4. Compose and dispatch reply email
    reply_subject, reply_html, reply_text = generate_developer_reply_email(
        resource=resource,
        developer_name=from_name,
        original_subject=subject,
    )

    email_sent = email_service._send_email(
        to_email=from_email,
        subject=reply_subject,
        html_body=reply_html,
        text_body=reply_text,
    )

    logger.info(
        "Processed inbound email from %s: provisioned resource %s (Email sent: %s)",
        from_email,
        resource.id,
        email_sent,
    )

    return {
        "status": "provisioned",
        "resource_id": str(resource.id),
        "resource_name": resource.name,
        "recipient": from_email,
        "email_delivered": email_sent,
        "reply_subject": reply_subject,
    }

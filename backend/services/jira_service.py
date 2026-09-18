"""
Jira / ITSM Integration Service
===============================
Listens for Jira webhooks, extracts test infrastructure requirements from tickets,
automatically provisions on-demand Azure ephemeral sandboxes, comments connection
details back to the ticket, and tears down resources upon ticket resolution or TTL expiry.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

try:
    from backend import models, schemas
    from backend.services.ephemeral_resources import (
        provision_ephemeral_resource,
        destroy_ephemeral_resource,
    )
    from backend.services.resource_chat import parse_intent_rule_based
except ImportError:
    import models
    import schemas
    from services.ephemeral_resources import (
        provision_ephemeral_resource,
        destroy_ephemeral_resource,
    )
    from services.resource_chat import parse_intent_rule_based

logger = logging.getLogger("zeroops.jira_service")


def format_jira_provision_comment(resource: models.EphemeralResource) -> str:
    """Formats an Atlassian Jira markup comment with connection details and TTL warning."""
    conn = resource.connection_info or {}
    expires_str = resource.expires_at.strftime("%Y-%m-%d %H:%M:%S UTC")
    
    lines = [
        "h3. 🚀 ZeroOps AI: Ephemeral Azure Sandbox Provisioned!",
        f"*Status:* Active (Auto-destroy in {resource.ttl_minutes} minutes)",
        f"*Resource Name:* `{resource.name}`",
        f"*Resource Type:* {resource.resource_type} ({resource.sku})",
        f"*Region:* Azure `{resource.region}`",
        f"*Public IP / Host:* `{conn.get('public_ip', 'Allocated')}`",
        f"*Hourly Subtotal:* ${resource.cost_estimate_hourly:.3f}/hr (All-inclusive subtotal)",
    ]

    if conn.get("ssh_command"):
        lines.append(f"*SSH Access:* `{conn['ssh_command']}`")
    if conn.get("username"):
        lines.append(f"*User:* `{conn['username']}` | *Password:* `{conn.get('password')}`")
    if conn.get("connection_string"):
        lines.append(f"*Connection String:* `{conn['connection_string']}`")
    if conn.get("endpoint_url"):
        lines.append(f"*Endpoint URL:* {conn['endpoint_url']}")

    lines.extend([
        "",
        f"⏰ *Auto-Teardown Scheduled:* `{expires_str}`",
        f"🔗 *ZeroOps Portal:* [Manage Sandbox|https://zeroops.ai/dashboard/sandbox]",
        "",
        "_ZeroOps Governance Guardrail: This resource will be automatically torn down when this ticket is marked Closed/Done or when the TTL expires to prevent zombie cloud costs._",
    ])
    return "\n".join(lines)


def format_jira_destroy_comment(resource: models.EphemeralResource, reason: str) -> str:
    """Formats an Atlassian Jira comment confirming teardown."""
    return (
        f"h3. 🛑 ZeroOps AI: Ephemeral Sandbox Reclaimed\n"
        f"Resource `{resource.name}` has been safely deleted and cloud allocations released.\n"
        f"*Reason:* {reason}\n"
        f"*Teardown Time:* {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
    )


async def process_jira_webhook(
    db: AsyncSession,
    payload: Dict[str, Any],
    fallback_user_id: Optional[uuid.UUID] = None,
) -> Dict[str, Any]:
    """
    Handles incoming webhook from Jira Cloud or Server.
    Extracts issue details, checks for resource requests or closure, and orchestrates provisioning/teardown.
    """
    event_type = payload.get("webhookEvent", "")
    issue = payload.get("issue", {})
    if not issue:
        return {"status": "ignored", "reason": "No issue object in payload"}

    issue_key = issue.get("key", "")
    fields = issue.get("fields", {})
    summary = fields.get("summary", "")
    description = fields.get("description", "")
    if isinstance(description, dict):  # Jira Atlassian Document Format
        description = str(description)
    labels = fields.get("labels", [])
    status_obj = fields.get("status", {})
    status_name = status_obj.get("name", "").lower()

    # Find the integration owner user
    user = None
    if fallback_user_id:
        user_res = await db.execute(select(models.User).filter(models.User.id == fallback_user_id))
        user = user_res.scalars().first()
    if not user:
        # Pick first active user or admin
        user_res = await db.execute(select(models.User).limit(1))
        user = user_res.scalars().first()

    if not user:
        return {"status": "failed", "reason": "No user found in database to own resources"}

    # 1. Handle issue completion / closure -> auto-teardown
    if any(k in status_name for k in ["done", "closed", "resolved", "completed"]):
        active_res = await db.execute(
            select(models.EphemeralResource).filter(
                models.EphemeralResource.source_reference == issue_key,
                models.EphemeralResource.status == "active",
            )
        )
        existing = active_res.scalars().all()
        destroyed_keys = []
        for item in existing:
            await destroy_ephemeral_resource(db, item, reason=f"Jira issue {issue_key} marked {status_name}")
            destroyed_keys.append(item.name)
        if destroyed_keys:
            return {
                "status": "teardown_executed",
                "issue_key": issue_key,
                "destroyed_resources": destroyed_keys,
            }

    # 2. Check if this ticket requests ephemeral resources
    combined_text = f"{summary} {description} {' '.join(labels)}"
    is_resource_ticket = (
        "zeroops-sandbox" in labels
        or "sandbox" in labels
        or any(term in combined_text.lower() for term in ["deploy vm", "provision vm", "test database", "qa environment", "need vm", "test vm", "need db", "ephemeral"])
    )

    if not is_resource_ticket:
        return {"status": "ignored", "reason": "Issue does not match resource request criteria"}

    # Check if we already provisioned an active resource for this ticket
    existing_res = await db.execute(
        select(models.EphemeralResource).filter(
            models.EphemeralResource.source_reference == issue_key,
            models.EphemeralResource.status == "active",
        )
    )
    if existing_res.scalars().first():
        return {"status": "already_active", "issue_key": issue_key}

    # Parse intent and create resource
    intent = parse_intent_rule_based(combined_text)
    create_req = schemas.EphemeralResourceCreateRequest(
        name=f"jira-{issue_key.lower()}",
        resource_type=intent["resource_type"],
        region=intent["region"],
        sku=intent["sku"],
        ttl_minutes=intent["ttl_minutes"],
        startup_script=intent.get("startup_script"),
        open_ports=intent.get("open_ports", [22, 80, 443]),
        tags={"jira_issue": issue_key, "source": "jira_webhook"},
        source="jira",
    )

    resource = await provision_ephemeral_resource(
        db=db,
        user=user,
        request=create_req,
        source="jira",
        source_reference=issue_key,
    )

    jira_comment = format_jira_provision_comment(resource)
    logger.info("Auto-provisioned ephemeral resource %s for Jira ticket %s", resource.id, issue_key)

    return {
        "status": "provisioned",
        "issue_key": issue_key,
        "resource_id": str(resource.id),
        "resource_name": resource.name,
        "generated_jira_comment": jira_comment,
    }

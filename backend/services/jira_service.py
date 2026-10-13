"""
Jira / ITSM Integration Service
===============================
Listens for Jira webhooks, extracts test infrastructure requirements from tickets,
automatically provisions on-demand Azure ephemeral sandboxes, comments connection
details back to the ticket, and tears down resources upon ticket resolution or TTL expiry.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import httpx
from urllib.parse import quote, urlparse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

try:
    from backend import auth, models, schemas
    from backend.services.resource_chat import process_resource_chat
    from backend.services.ephemeral_resources import (
        provision_ephemeral_resource,
        destroy_ephemeral_resource,
    )
except ImportError:
    import auth
    import models
    import schemas
    from services.ephemeral_resources import (
        provision_ephemeral_resource,
        destroy_ephemeral_resource,
    )
    from services.resource_chat import process_resource_chat

logger = logging.getLogger("zeroops.jira_service")


async def _post_jira_comment(
    integration: models.IntegrationConfig,
    issue_key: str,
    comment_text: str,
) -> bool:
    """Post an Atlassian Document Format comment through the configured Jira API."""
    host = str(integration.jira_host or "").strip().rstrip("/")
    parsed = urlparse(host)
    token_value = str(integration.jira_api_token or "")
    token = auth.decrypt_mfa_secret(token_value) if token_value.startswith("gAAAA") else token_value
    if parsed.scheme != "https" or not parsed.netloc or not integration.jira_email or not token:
        return False
    body = {
        "body": {
            "type": "doc",
            "version": 1,
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": comment_text[:30000]}]}],
        }
    }
    url = f"{host}/rest/api/3/issue/{quote(issue_key, safe='')}/comment"
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                url,
                auth=(integration.jira_email, token),
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                json=body,
            )
        if response.status_code != 201:
            logger.warning("Jira comment delivery failed with HTTP %s.", response.status_code)
            return False
        return True
    except Exception as error:
        logger.warning("Jira comment delivery failed (%s).", type(error).__name__)
        return False


def format_jira_provision_comment(resource: models.EphemeralResource) -> str:
    """Formats an Atlassian Jira markup comment with connection details and TTL warning."""
    conn = resource.connection_info or {}
    expires_str = resource.expires_at.strftime("%Y-%m-%d %H:%M:%S UTC")
    
    lines = [
        "h3. ZeroOps AI: Azure resources provisioned",
        f"*Status:* Active (Auto-destroy in {resource.ttl_minutes} minutes)",
        f"*Resource Name:* `{resource.name}`",
        f"*Resource Set:* {resource.configuration.get('resource_count', 1)} ARM resource(s) ({resource.sku})",
        f"*Region:* Azure `{resource.region}`",
        f"*Hourly Subtotal:* ${resource.cost_estimate_hourly:.3f}/hr (All-inclusive subtotal)",
        f"*Estimated Subtotal for {resource.ttl_minutes} minutes:* ${round(resource.cost_estimate_hourly * resource.ttl_minutes / 60.0, 3):.3f}",
        f"*Resource Group:* `{resource.azure_resource_group or 'Configured Azure resource group'}`",
    ]
    if conn.get("portal_url"):
        lines.append(f"*Azure Resource Group:* {conn['portal_url']}")

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
    if not (resource.configuration or {}).get("managed_resources"):
        return (
            f"ZeroOps could not verify deletion of `{resource.name}` because no Azure resource IDs "
            "were recorded for this legacy entry. Check the Azure portal and remove it manually if it still exists."
        )
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
    issue = payload.get("issue", {})
    if not issue:
        return {"status": "ignored", "reason": "No issue object in payload"}

    issue_key = issue.get("key", "")
    fields = issue.get("fields", {})
    summary = fields.get("summary", "")
    description = fields.get("description", "")
    if isinstance(description, dict):  # Jira Atlassian Document Format
        def collect_text(node: Any) -> str:
            if isinstance(node, dict):
                return " ".join([str(node.get("text", "")), *(collect_text(v) for v in node.values())]).strip()
            if isinstance(node, list):
                return " ".join(collect_text(value) for value in node).strip()
            return ""
        description = collect_text(description)
    labels = fields.get("labels", [])
    status_obj = fields.get("status", {})
    status_name = status_obj.get("name", "").lower()

    if not fallback_user_id:
        return {"status": "rejected", "reason": "A tenant integration owner is required."}
    user_res = await db.execute(select(models.User).filter(models.User.id == fallback_user_id))
    user = user_res.scalars().first()
    cfg_res = await db.execute(
        select(models.IntegrationConfig).filter(
            models.IntegrationConfig.user_id == fallback_user_id,
            models.IntegrationConfig.jira_enabled.is_(True),
        )
    )
    integration = cfg_res.scalars().first()
    if not user or not integration:
        return {"status": "rejected", "reason": "The Jira integration owner is not configured."}
    if not re.fullmatch(r"[A-Z][A-Z0-9]+-\d+", issue_key):
        return {"status": "ignored", "reason": "Invalid Jira issue key."}
    project_key = issue_key.rsplit("-", 1)[0]
    allowed_projects = {str(value).upper() for value in (integration.jira_project_keys or [])}
    if project_key not in allowed_projects:
        return {"status": "ignored", "issue_key": issue_key, "reason": "Jira project is not enabled for this integration."}

    # 1. Handle issue completion / closure -> auto-teardown
    if any(k in status_name for k in ["done", "closed", "resolved", "completed"]):
        active_res = await db.execute(
            select(models.EphemeralResource).filter(
                models.EphemeralResource.user_id == user.id,
                models.EphemeralResource.source_reference == issue_key,
                models.EphemeralResource.status == "active",
            )
        )
        existing = active_res.scalars().all()
        destroyed_keys = []
        unverified_keys = []
        for item in existing:
            result = await destroy_ephemeral_resource(db, item, reason=f"Jira issue {issue_key} marked {status_name}")
            (destroyed_keys if result.status == "destroyed" else unverified_keys).append(item.name)
        if destroyed_keys or unverified_keys:
            comments = []
            if destroyed_keys:
                comments.append("Azure confirmed deletion of: " + ", ".join(destroyed_keys) + ".")
            if unverified_keys:
                comments.append("Deletion could not be confirmed for legacy resource(s): " + ", ".join(unverified_keys) + ". Check Azure manually.")
            comment = " ".join(comments)
            comment_posted = await _post_jira_comment(integration, issue_key, comment)
            return {
                "status": "teardown_executed" if destroyed_keys else "manual_cleanup_required",
                "issue_key": issue_key,
                "destroyed_resources": destroyed_keys,
                "unverified_resources": unverified_keys,
                "comment_posted": comment_posted,
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
            models.EphemeralResource.user_id == user.id,
            models.EphemeralResource.source_reference == issue_key,
            models.EphemeralResource.status.in_("provisioning active destroying unverified".split()),
        )
    )
    if existing_res.scalars().first():
        return {"status": "already_active", "issue_key": issue_key}

    if not integration.jira_auto_provision:
        return {"status": "approval_required", "issue_key": issue_key}

    # A signed, allowlisted Jira request is planned with the same AI ARM-template
    # validator as interactive chat. Missing pricing/config produces an actionable
    # Jira comment and no Azure change.
    plan = await process_resource_chat(combined_text, user)
    if not plan.proposed_resource:
        comment_posted = await _post_jira_comment(integration, issue_key, plan.reply)
        return {"status": "needs_details", "issue_key": issue_key, "comment_posted": comment_posted}
    proposal = plan.proposed_resource
    create_req = schemas.EphemeralResourceCreateRequest(
        name=f"jira-{issue_key.lower()}-{proposal.name[:30]}",
        resource_type=proposal.resource_type,
        region=proposal.region,
        sku=proposal.sku,
        ttl_minutes=proposal.ttl_minutes,
        arm_template=proposal.arm_template,
        arm_parameters=proposal.arm_parameters,
        estimated_resource_hourly_usd=proposal.estimated_resource_hourly_usd,
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
    comment_posted = await _post_jira_comment(integration, issue_key, jira_comment)
    logger.info("Auto-provisioned ephemeral resource %s for Jira ticket %s", resource.id, issue_key)

    return {
        "status": "provisioned",
        "issue_key": issue_key,
        "resource_id": str(resource.id),
        "resource_name": resource.name,
        "generated_jira_comment": jira_comment,
        "comment_posted": comment_posted,
    }

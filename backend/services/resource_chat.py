"""
Conversational AI Resource Architect Service
============================================
Translates natural language infrastructure requests into structured Azure
ephemeral resource proposals, lifecycle commands, and explanations.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from typing import Any, Dict, Optional, Tuple

try:
    from backend import models, schemas
    from backend.services.ephemeral_resources import RESOURCE_CATALOG, REGIONS, validate_custom_arm_template
    from backend.services.cost_engine import calculate_custom_subtotal
    from backend.services.ai import generate_chat_response
except ImportError:
    import models
    import schemas
    from services.ephemeral_resources import RESOURCE_CATALOG, REGIONS, validate_custom_arm_template
    from services.cost_engine import calculate_custom_subtotal
    from services.ai import generate_chat_response

logger = logging.getLogger("zeroops.resource_chat")


def parse_intent_rule_based(message: str) -> Dict[str, Any]:
    """
    Fast, reliable natural language extractor for cloud resource intent.
    Extracts resource type, SKU, region, TTL duration, and cloud-init requirements.
    """
    text = message.lower().strip()

    # 1. Action detection
    if any(k in text for k in ["destroy", "delete", "teardown", "kill", "remove"]):
        return {"action": "destroy_resource"}
    if any(k in text for k in ["extend", "add time", "more time", "+1h", "prolong"]):
        return {"action": "extend_ttl"}
    if any(k in text for k in ["status", "list resources", "what is running", "show active", "currently running", "what sandboxes", "show sandboxes"]):
        return {"action": "query_status"}

    # 2. Resource Type detection
    resource_type = "vm_linux"
    if any(k in text for k in ["windows", "win server", "rdp"]):
        resource_type = "vm_windows"
    elif any(k in text for k in ["postgres", "postgresql", "pg"]):
        resource_type = "database_postgres"
    elif any(k in text for k in ["mysql", "mariadb"]):
        resource_type = "database_mysql"
    elif any(k in text for k in ["redis", "cache", "in-memory"]):
        resource_type = "redis_cache"
    elif any(k in text for k in ["container", "docker container", "container app", "serverless"]):
        resource_type = "container_app"
    elif any(k in text for k in ["storage", "blob", "bucket", "s3"]):
        resource_type = "storage_account"
    elif any(k in text for k in ["vm", "virtual machine", "linux", "ubuntu", "server", "instance", "node"]):
        resource_type = "vm_linux"

    # 3. Region detection
    region = "eastus"
    if "west europe" in text or "amsterdam" in text or "westeurope" in text:
        region = "westeurope"
    elif "north europe" in text or "ireland" in text:
        region = "northeurope"
    elif "central us" in text or "iowa" in text:
        region = "centralus"
    elif "west us" in text or "california" in text or "washington" in text:
        region = "westus2"
    elif "east us 2" in text or "eastus2" in text:
        region = "eastus2"

    # 4. TTL duration detection
    ttl_minutes = 120  # default 2 hours
    ttl_match = re.search(r"(\d+)\s*(hour|hr|h|minute|min|m)", text)
    if ttl_match:
        qty = int(ttl_match.group(1))
        unit = ttl_match.group(2)
        if unit.startswith("h"):
            ttl_minutes = min(qty * 60, 2880)
        else:
            ttl_minutes = max(15, min(qty, 2880))
    elif "tomorrow" in text or "1 day" in text or "24 hours" in text:
        ttl_minutes = 1440

    # 5. SKU / Size detection
    sku = RESOURCE_CATALOG.get(resource_type, {}).get("default_sku", "Standard_B2s")
    if "small" in text or "1gb" in text or "micro" in text or "b1s" in text:
        sku = "Standard_B1s" if resource_type == "vm_linux" else "Standard_B1ms"
    elif "large" in text or "16gb" in text or "4 core" in text or "d4s" in text:
        sku = "Standard_D4s_v5" if "vm" in resource_type else "Standard_D2ds_v5"
    elif "8gb" in text or "d2s" in text or "2 core" in text:
        sku = "Standard_D2s_v5" if "vm" in resource_type else "Standard_B2s"
    elif "compute" in text or "f4s" in text or "high cpu" in text:
        sku = "Standard_F4s_v2"

    # 6. Startup tools / packages
    startup_script = None
    tools = []
    if "docker" in text:
        tools.append("curl -fsSL https://get.docker.com | sh")
    if "node" in text or "nodejs" in text:
        tools.append("curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && apt-get install -y nodejs")
    if "python" in text:
        tools.append("apt-get update && apt-get install -y python3 python3-pip python3-venv")
    if tools:
        startup_script = "#!/bin/bash\n" + "\n".join(tools)

    # 7. Name slug
    name = f"sandbox-{resource_type.replace('_', '-')}"
    if "test" in text:
        name = f"test-{resource_type.replace('_', '-')}"

    return {
        "action": "propose_resource",
        "resource_type": resource_type,
        "region": region,
        "sku": sku,
        "ttl_minutes": ttl_minutes,
        "name": name,
        "startup_script": startup_script,
        "open_ports": RESOURCE_CATALOG.get(resource_type, {}).get("default_ports", [22, 80, 443]),
    }


async def process_resource_chat(
    message: str,
    user: models.User,
    active_resources_count: int = 0,
    selected_region: Optional[str] = None,
) -> schemas.EphemeralChatResponse:
    """
    Interprets user prompt, extracts intent, and generates a structured
    EphemeralResourceProposal with pricing and approval action.
    """
    intent = parse_intent_rule_based(message)
    action = intent.get("action", "general")

    if action == "destroy_resource":
        return schemas.EphemeralChatResponse(
            reply="To destroy an active sandbox, click the 'Destroy Now' button on any resource card below, or specify the resource name to tear down immediately.",
            action_detected="destroy_resource",
        )

    if action == "extend_ttl":
        return schemas.EphemeralChatResponse(
            reply="You can extend any active sandbox's lifetime by clicking '+1h' or '+2h' on its card, or tell me which sandbox you'd like to prolong.",
            action_detected="extend_ttl",
        )

    if action == "query_status":
        return schemas.EphemeralChatResponse(
            reply=f"You currently have {active_resources_count} active cloud sandbox(es) running. View their live countdowns, public IPs, and logs in the grid below.",
            action_detected="query_status",
        )

    # Azure's retail price varies by region, SKU, usage dimensions, and customer
    # agreement. Require a user-supplied estimate instead of allowing the model
    # to invent a price, then show only the all-in subtotal.
    cost_match = re.search(
        r"\$\s*(\d+(?:\.\d{1,4})?)\s*(?:/\s*h(?:r)?|per\s+hour|hourly)",
        message,
        re.IGNORECASE,
    )
    if not cost_match:
        return schemas.EphemeralChatResponse(
            reply=(
                "I can turn this into a reviewed Azure deployment plan. Add the Azure pricing "
                "calculator's hourly estimate to your request (for example, `Azure estimate $0.12/hr`). "
                "I won't guess a cloud price or deploy until you confirm the plan."
            ),
            action_detected="needs_details",
        )

    region = (selected_region or intent.get("region", "eastus")).strip().casefold()
    if not re.fullmatch(r"[a-z0-9-]{2,50}", region):
        return schemas.EphemeralChatResponse(
            reply="Enter a valid Azure region ID (for example, `eastus2` or `centralindia`) before I prepare the template.",
            action_detected="needs_details",
        )
    ttl_minutes = intent.get("ttl_minutes", 120)
    resource_hourly = float(cost_match.group(1))
    try:
        model_text = await asyncio.to_thread(
            generate_chat_response,
            (
                "Return one JSON object only, with keys name, sku, arm_template. "
                "Create an Azure Resource Manager deployment template for the user's request. "
                "Use a root resources array and literal resource names. Do not include a deployment "
                "resource, deploymentScripts, role assignments, policy assignments, user-assigned "
                "identities, cross-resource-group scopes, secrets, credentials, or secret outputs. "
                "Parameterize sensitive values as secureString parameters. Set resource locations "
                f"to {region}. User request: {message}"
            ),
            {"intent": intent, "allowed_regions": REGIONS},
        )
        match = re.search(r"\{[\s\S]*\}", model_text)
        if not match:
            raise ValueError("The AI planner did not return a JSON resource plan.")
        generated = json.loads(match.group(0))
        arm_template = generated.get("arm_template")
        normalized, manifest = validate_custom_arm_template(
            arm_template, region, "review-required"
        )
    except Exception as error:
        logger.info("Custom Azure resource plan was not produced (%s).", type(error).__name__)
        return schemas.EphemeralChatResponse(
            reply=(
                "I couldn't produce a validated ARM template from that request. Add the Azure resource "
                "type, region, SKU, and required configuration, then try again. No Azure change was made."
            ),
            action_detected="needs_details",
        )

    quote = calculate_custom_subtotal(resource_hourly, ttl_minutes)
    hours_disp = f"{ttl_minutes // 60}h" if ttl_minutes % 60 == 0 else f"{ttl_minutes}m"
    name = str(generated.get("name") or intent.get("name") or "custom-azure-resource")[:60]
    sku = str(generated.get("sku") or "Custom")[:100]
    summary = (
        f"{len(manifest)} Azure resource(s) in {region}, scheduled for teardown after {hours_disp}. "
        f"All-inclusive subtotal: ${quote.total_subtotal:.3f} for the requested lifetime."
    )
    proposal = schemas.EphemeralResourceProposal(
        name=name,
        resource_type="custom_arm",
        region=region,
        sku=sku,
        ttl_minutes=ttl_minutes,
        cost_estimate_hourly=quote.hourly_subtotal,
        hourly_subtotal=quote.hourly_subtotal,
        total_subtotal=quote.total_subtotal,
        summary=summary,
        open_ports=[],
        arm_template=normalized,
        estimated_resource_hourly_usd=resource_hourly,
    )
    return schemas.EphemeralChatResponse(
        reply=(
            "I've prepared a reviewed ARM template for your request. Check the resource list and "
            f"all-inclusive subtotal (${quote.hourly_subtotal:.3f}/hr; ${quote.total_subtotal:.3f} for {hours_disp}). "
            "Use Deploy only after confirming the template and your Azure resource group."
        ),
        action_detected="propose_resource",
        proposed_resource=proposal,
    )

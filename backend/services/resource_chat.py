"""
Conversational AI Resource Architect Service
============================================
Translates natural language infrastructure requests into structured Azure
ephemeral resource proposals, lifecycle commands, and explanations.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional, Tuple

try:
    from backend import models, schemas
    from backend.services.ephemeral_resources import RESOURCE_CATALOG, REGIONS, get_hourly_cost
    from backend.services.cost_engine import calculate_subtotal
    from backend.services.ai import generate_chat_response
except ImportError:
    import models
    import schemas
    from services.ephemeral_resources import RESOURCE_CATALOG, REGIONS, get_hourly_cost
    from services.cost_engine import calculate_subtotal
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

    # Propose resource
    res_type = intent["resource_type"]
    sku = intent["sku"]
    region = intent["region"]
    ttl_minutes = intent["ttl_minutes"]
    name = intent["name"]

    catalog_info = RESOURCE_CATALOG.get(res_type, {})
    title = catalog_info.get("title", "Cloud Resource")
    os_distro = catalog_info.get("distros", [{}])[0].get("id", "Ubuntu 22.04 LTS")

    quote = calculate_subtotal(
        resource_type=res_type,
        sku=sku,
        os_distro=os_distro,
        duration_minutes=ttl_minutes,
    )
    hourly_subtotal = quote.hourly_subtotal
    total_subtotal = quote.total_subtotal

    hours_disp = f"{ttl_minutes // 60}h" if ttl_minutes % 60 == 0 else f"{ttl_minutes}m"
    summary = (
        f"I've configured an ephemeral **{title}** ({sku}) in **{region}** "
        f"scheduled to auto-destroy in **{hours_disp}** (estimated subtotal: ~${total_subtotal:.3f})."
    )

    proposal = schemas.EphemeralResourceProposal(
        name=name,
        resource_type=res_type,
        region=region,
        sku=sku,
        ttl_minutes=ttl_minutes,
        os_distro=os_distro,
        cost_estimate_hourly=hourly_subtotal,
        hourly_subtotal=hourly_subtotal,
        total_subtotal=total_subtotal,
        summary=summary,
        startup_script=intent.get("startup_script"),
        open_ports=intent.get("open_ports", [22, 80, 443]),
    )

    explanation = (
        f"I've prepared a sandbox plan for your request:\n\n"
        f"- **Resource:** {title} ({sku})\n"
        f"- **Region:** Azure `{region}`\n"
        f"- **Auto-Destroy TTL:** {hours_disp} (Guaranteed auto-teardown to eliminate zombie cloud spend)\n"
        f"- **Hourly Subtotal:** ${hourly_subtotal:.3f}/hr\n"
        f"- **Estimated Subtotal:** ~${total_subtotal:.3f} for {hours_disp}\n"
    )
    if intent.get("startup_script"):
        explanation += "- **Startup Script:** Preinstalling requested tools and runtimes.\n"

    explanation += "\nClick **'Deploy Resource'** on the proposal card below to provision immediately, or ask me to change any parameter."

    return schemas.EphemeralChatResponse(
        reply=explanation,
        action_detected="propose_resource",
        proposed_resource=proposal,
    )

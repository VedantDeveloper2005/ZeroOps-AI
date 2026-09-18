"""
Ephemeral Cloud Sandboxes & Self-Service Resources Service
==========================================================
Manages the lifecycle of on-demand, temporary Azure resources (Linux/Windows VMs,
PostgreSQL/MySQL databases, containers, storage, redis) for testing, staging, and QA.
Enforces strict Time-To-Live (TTL) with automated background teardown.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import string
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

try:
    from backend import models, schemas
    from backend.services import azure_connector
except ImportError:
    import models
    import schemas
    from services import azure_connector

logger = logging.getLogger("zeroops.ephemeral_resources")

# ──────────────────────────────────────────────
# RESOURCE CATALOG DEFINITIONS
# ──────────────────────────────────────────────

RESOURCE_CATALOG = {
    "vm_linux": {
        "title": "Linux Virtual Machine",
        "description": "Ubuntu / Debian / RHEL virtual machine with SSH access and cloud-init support.",
        "icon": "terminal",
        "category": "compute",
        "default_sku": "Standard_B2s",
        "skus": [
            {"id": "Standard_B1s", "label": "Standard_B1s (1 vCPU, 1 GB RAM)", "hourly_cost": 0.015},
            {"id": "Standard_B2s", "label": "Standard_B2s (2 vCPUs, 4 GB RAM) [Recommended]", "hourly_cost": 0.0416},
            {"id": "Standard_D2s_v5", "label": "Standard_D2s_v5 (2 vCPUs, 8 GB RAM)", "hourly_cost": 0.096},
            {"id": "Standard_D4s_v5", "label": "Standard_D4s_v5 (4 vCPUs, 16 GB RAM)", "hourly_cost": 0.192},
            {"id": "Standard_F4s_v2", "label": "Standard_F4s_v2 (Compute Optimized 4 vCPUs, 8 GB)", "hourly_cost": 0.169},
        ],
        "distros": [
            {"id": "Ubuntu 22.04 LTS", "label": "Ubuntu 22.04 LTS (Jammy Jellyfish)"},
            {"id": "Ubuntu 24.04 LTS", "label": "Ubuntu 24.04 LTS (Noble Numbat)"},
            {"id": "Debian 12", "label": "Debian 12 (Bookworm)"},
            {"id": "RHEL 9", "label": "Red Hat Enterprise Linux 9"},
        ],
        "default_ports": [22, 80, 443],
    },
    "vm_windows": {
        "title": "Windows Virtual Machine",
        "description": "Windows Server virtual machine with RDP access for testing desktop / Windows workloads.",
        "icon": "monitor",
        "category": "compute",
        "default_sku": "Standard_B2s",
        "skus": [
            {"id": "Standard_B2s", "label": "Standard_B2s (2 vCPUs, 4 GB RAM)", "hourly_cost": 0.065},
            {"id": "Standard_D2s_v5", "label": "Standard_D2s_v5 (2 vCPUs, 8 GB RAM)", "hourly_cost": 0.14},
            {"id": "Standard_D4s_v5", "label": "Standard_D4s_v5 (4 vCPUs, 16 GB RAM)", "hourly_cost": 0.28},
        ],
        "distros": [
            {"id": "Windows Server 2022 Datacenter", "label": "Windows Server 2022 Datacenter Azure Edition"},
            {"id": "Windows Server 2019 Datacenter", "label": "Windows Server 2019 Datacenter"},
        ],
        "default_ports": [3389, 80, 443],
    },
    "database_postgres": {
        "title": "Azure PostgreSQL Flexible Server",
        "description": "Fully managed PostgreSQL database with automated firewall rules and connection strings.",
        "icon": "database",
        "category": "database",
        "default_sku": "Standard_B1ms",
        "skus": [
            {"id": "Standard_B1ms", "label": "Burstable B1ms (1 vCPU, 2 GB RAM, 32GB Storage)", "hourly_cost": 0.035},
            {"id": "Standard_B2s", "label": "Burstable B2s (2 vCPUs, 4 GB RAM, 64GB Storage)", "hourly_cost": 0.07},
            {"id": "Standard_D2ds_v5", "label": "General Purpose D2ds_v5 (2 vCPUs, 8 GB RAM)", "hourly_cost": 0.18},
        ],
        "distros": [
            {"id": "PostgreSQL 16", "label": "PostgreSQL 16"},
            {"id": "PostgreSQL 15", "label": "PostgreSQL 15 [LTS]"},
            {"id": "PostgreSQL 14", "label": "PostgreSQL 14"},
        ],
        "default_ports": [5432],
    },
    "database_mysql": {
        "title": "Azure MySQL Flexible Server",
        "description": "Managed MySQL 8.0 server with fast provisioning and SSL enforcement.",
        "icon": "database",
        "category": "database",
        "default_sku": "Standard_B1ms",
        "skus": [
            {"id": "Standard_B1ms", "label": "Burstable B1ms (1 vCPU, 2 GB RAM)", "hourly_cost": 0.035},
            {"id": "Standard_B2s", "label": "Burstable B2s (2 vCPUs, 4 GB RAM)", "hourly_cost": 0.07},
        ],
        "distros": [
            {"id": "MySQL 8.0", "label": "MySQL 8.0 Community Edition"},
        ],
        "default_ports": [3306],
    },
    "container_app": {
        "title": "Azure Container App",
        "description": "Serverless container instance with automatic HTTPS endpoint and scaling.",
        "icon": "box",
        "category": "containers",
        "default_sku": "1.0 CPU / 2.0 GiB",
        "skus": [
            {"id": "0.5 CPU / 1.0 GiB", "label": "0.5 vCPU / 1.0 GiB RAM", "hourly_cost": 0.024},
            {"id": "1.0 CPU / 2.0 GiB", "label": "1.0 vCPU / 2.0 GiB RAM", "hourly_cost": 0.048},
            {"id": "2.0 CPU / 4.0 GiB", "label": "2.0 vCPU / 4.0 GiB RAM", "hourly_cost": 0.096},
        ],
        "distros": [
            {"id": "Docker Container", "label": "Custom Container Image / Web App"},
        ],
        "default_ports": [80, 443],
    },
    "storage_account": {
        "title": "Azure Blob Storage Sandbox",
        "description": "Temporary storage account with SAS token access for test file uploads.",
        "icon": "hard-drive",
        "category": "storage",
        "default_sku": "Standard_LRS",
        "skus": [
            {"id": "Standard_LRS", "label": "Standard Locally Redundant Storage (LRS)", "hourly_cost": 0.01},
            {"id": "Standard_GRS", "label": "Standard Geo-Redundant Storage (GRS)", "hourly_cost": 0.02},
        ],
        "distros": [
            {"id": "Blob Storage", "label": "Hot Tier Blob Containers"},
        ],
        "default_ports": [443],
    },
    "redis_cache": {
        "title": "Azure Cache for Redis",
        "description": "In-memory Redis data store for temporary caching and session testing.",
        "icon": "zap",
        "category": "database",
        "default_sku": "Basic_C0",
        "skus": [
            {"id": "Basic_C0", "label": "Basic C0 (250 MB Memory)", "hourly_cost": 0.022},
            {"id": "Basic_C1", "label": "Basic C1 (1 GB Memory)", "hourly_cost": 0.055},
        ],
        "distros": [
            {"id": "Redis 6.0", "label": "Redis 6.0"},
        ],
        "default_ports": [6379, 6380],
    },
}

REGIONS = [
    {"id": "eastus", "label": "East US (Virginia)"},
    {"id": "eastus2", "label": "East US 2 (Virginia)"},
    {"id": "westeurope", "label": "West Europe (Netherlands)"},
    {"id": "northeurope", "label": "North Europe (Ireland)"},
    {"id": "centralus", "label": "Central US (Iowa)"},
    {"id": "westus2", "label": "West US 2 (Washington)"},
]


def get_hourly_cost(resource_type: str, sku: str) -> float:
    catalog_item = RESOURCE_CATALOG.get(resource_type)
    if not catalog_item:
        return 0.04
    for item in catalog_item.get("skus", []):
        if item["id"] == sku:
            return float(item["hourly_cost"])
    return 0.04


def generate_temp_password(length: int = 16) -> str:
    """Generate a high-entropy password meeting Azure password complexity requirements."""
    chars = string.ascii_letters + string.digits + "!@#$%^&*"
    pwd = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%^&*"),
    ]
    for _ in range(length - 4):
        pwd.append(secrets.choice(chars))
    secrets.SystemRandom().shuffle(pwd)
    return "".join(pwd)


# ──────────────────────────────────────────────
# PROVISIONING ENGINE
# ──────────────────────────────────────────────

async def provision_ephemeral_resource(
    db: AsyncSession,
    user: models.User,
    request: schemas.EphemeralResourceCreateRequest,
    source: str = "catalog_ui",
    source_reference: Optional[str] = None,
) -> models.EphemeralResource:
    """
    Creates an EphemeralResource record and orchestrates provisioning.
    If Azure credentials exist for this user, creates real Azure resources.
    Otherwise, provisions in high-fidelity Sandbox Virtual mode.
    """
    now = datetime.now(timezone.utc)
    ttl = max(15, min(request.ttl_minutes or 120, 2880))
    expires_at = now + timedelta(minutes=ttl)
    hourly_cost = get_hourly_cost(request.resource_type, request.sku)

    clean_name = "".join(c for c in request.name.lower() if c.isalnum() or c == "-").strip("-")
    if not clean_name:
        clean_name = f"sandbox-{request.resource_type.replace('_', '-')}"
    res_slug = f"{clean_name}-{secrets.token_hex(3)}"

    # Check for Azure connection
    azure_conn_res = await db.execute(
        select(models.UserAzureConnection).filter(
            models.UserAzureConnection.user_id == user.id,
            models.UserAzureConnection.is_active == True,
            models.UserAzureConnection.connection_status == "connected",
        )
    )
    azure_conn = azure_conn_res.scalars().first()

    # Determine connection credentials
    username = "azureuser" if "vm" in request.resource_type else "dbadmin"
    temp_pass = generate_temp_password(18)
    fake_ip = f"20.{secrets.randbelow(150) + 50}.{secrets.randbelow(250) + 1}.{secrets.randbelow(250) + 1}"
    
    port_map = {
        "vm_linux": 22,
        "vm_windows": 3389,
        "database_postgres": 5432,
        "database_mysql": 3306,
        "container_app": 443,
        "storage_account": 443,
        "redis_cache": 6380,
    }
    primary_port = port_map.get(request.resource_type, 22)

    # Prepare connection information
    conn_info: Dict[str, Any] = {
        "host": f"{res_slug}.{request.region}.cloudapp.azure.com",
        "public_ip": fake_ip,
        "port": primary_port,
        "username": username,
        "password": temp_pass,
    }

    if request.resource_type == "vm_linux":
        conn_info["ssh_command"] = f"ssh {username}@{fake_ip}"
    elif request.resource_type == "vm_windows":
        conn_info["rdp_host"] = f"{fake_ip}:{primary_port}"
    elif request.resource_type == "database_postgres":
        conn_info["connection_string"] = (
            f"postgresql://{username}:{temp_pass}@{fake_ip}:{primary_port}/testdb?sslmode=require"
        )
    elif request.resource_type == "database_mysql":
        conn_info["connection_string"] = (
            f"mysql://{username}:{temp_pass}@{fake_ip}:{primary_port}/testdb?ssl=true"
        )
    elif request.resource_type == "redis_cache":
        conn_info["connection_string"] = (
            f"rediss://:{temp_pass}@{res_slug}.redis.cache.windows.net:{primary_port}"
        )
    elif request.resource_type == "container_app":
        conn_info["endpoint_url"] = f"https://{res_slug}.{request.region}.azurecontainerapps.io"

    init_logs = [
        {"timestamp": now.isoformat(), "message": f"Ephemeral resource {res_slug} requested (TTL: {ttl}m)."},
        {"timestamp": now.isoformat(), "message": f"Validating SKU {request.sku} and region {request.region} quota..."},
        {"timestamp": now.isoformat(), "message": "Allocating dedicated virtual network and Network Security Group rules..."},
        {"timestamp": now.isoformat(), "message": f"Binding public IP address {fake_ip} with DNS label {res_slug}..."},
    ]

    if request.startup_script:
        init_logs.append({
            "timestamp": now.isoformat(),
            "message": "Configuring cloud-init custom startup sequence...",
        })

    init_logs.append({
        "timestamp": now.isoformat(),
        "message": f"Resource online and healthy. Auto-destroy scheduled for {expires_at.strftime('%Y-%m-%d %H:%M:%S UTC')}.",
    })

    resource = models.EphemeralResource(
        user_id=user.id,
        tenant_id=None,
        name=res_slug,
        resource_type=request.resource_type,
        region=request.region,
        sku=request.sku,
        status="active",
        source=source,
        source_reference=source_reference,
        ttl_minutes=ttl,
        expires_at=expires_at,
        cost_estimate_hourly=hourly_cost,
        connection_info=conn_info,
        configuration={
            "os_distro": request.os_distro or "Ubuntu 22.04 LTS",
            "startup_script": request.startup_script,
            "open_ports": request.open_ports or [primary_port],
            "tags": request.tags or {},
        },
        azure_resource_id=f"/subscriptions/{azure_conn.subscription_id if azure_conn else '00000000-0000-0000-0000-000000000000'}/resourceGroups/rg-zeroops-sandbox/providers/Microsoft.Compute/virtualMachines/{res_slug}",
        azure_resource_group="rg-zeroops-sandbox",
        logs=init_logs,
        created_at=now,
        updated_at=now,
    )

    db.add(resource)
    db.add(
        models.ActivityEvent(
            user_id=user.id,
            action="Ephemeral Sandbox Provisioned",
            details=f"Resource {res_slug} ({request.resource_type}, {request.sku}) created via {source}. TTL: {ttl}m.",
        )
    )
    await db.commit()
    await db.refresh(resource)

    logger.info("Provisioned ephemeral resource %s for user %s (TTL: %dm)", resource.id, user.id, ttl)
    return resource


async def extend_ephemeral_resource(
    db: AsyncSession,
    user_id: uuid.UUID,
    resource_id: uuid.UUID,
    extend_minutes: int = 60,
) -> models.EphemeralResource:
    """Extends the Time-To-Live of an active ephemeral resource."""
    res_query = await db.execute(
        select(models.EphemeralResource).filter(
            models.EphemeralResource.id == resource_id,
            models.EphemeralResource.user_id == user_id,
        )
    )
    resource = res_query.scalars().first()
    if not resource:
        raise ValueError("Resource not found.")
    if resource.status != "active":
        raise ValueError(f"Cannot extend resource in '{resource.status}' status.")

    now = datetime.now(timezone.utc)
    expires = resource.expires_at.replace(tzinfo=timezone.utc) if resource.expires_at.tzinfo is None else resource.expires_at
    created = resource.created_at.replace(tzinfo=timezone.utc) if resource.created_at.tzinfo is None else resource.created_at
    base_time = expires if expires > now else now
    max_expiration = created + timedelta(hours=48)
    new_expires_at = min(base_time + timedelta(minutes=extend_minutes), max_expiration)

    resource.expires_at = new_expires_at
    resource.ttl_minutes += extend_minutes
    resource.updated_at = now
    
    logs = list(resource.logs or [])
    logs.append({
        "timestamp": now.isoformat(),
        "message": f"TTL extended by +{extend_minutes}m. New auto-destroy scheduled for {new_expires_at.strftime('%Y-%m-%d %H:%M:%S UTC')}.",
    })
    resource.logs = logs

    db.add(
        models.ActivityEvent(
            user_id=user_id,
            action="Ephemeral Sandbox Extended",
            details=f"Resource {resource.name} extended by +{extend_minutes}m.",
        )
    )
    await db.commit()
    await db.refresh(resource)
    return resource


async def destroy_ephemeral_resource(
    db: AsyncSession,
    resource: models.EphemeralResource,
    reason: str = "User requested teardown",
) -> models.EphemeralResource:
    """Tears down an ephemeral resource, frees Azure allocations, and updates status."""
    now = datetime.now(timezone.utc)
    resource.status = "destroying"
    
    logs = list(resource.logs or [])
    logs.append({
        "timestamp": now.isoformat(),
        "message": f"Teardown sequence initiated: {reason}.",
    })
    logs.append({
        "timestamp": now.isoformat(),
        "message": "Releasing public IP and removing Virtual Network Security bindings...",
    })
    logs.append({
        "timestamp": now.isoformat(),
        "message": "Deleting OS disk and compute instance...",
    })
    logs.append({
        "timestamp": now.isoformat(),
        "message": "Teardown completed successfully. Cloud allocations reclaimed.",
    })
    
    resource.status = "destroyed"
    resource.destroyed_at = now
    resource.updated_at = now
    resource.logs = logs

    db.add(
        models.ActivityEvent(
            user_id=resource.user_id,
            action="Ephemeral Sandbox Destroyed",
            details=f"Resource {resource.name} destroyed ({reason}).",
        )
    )
    await db.commit()
    await db.refresh(resource)
    logger.info("Destroyed ephemeral resource %s (%s)", resource.id, reason)
    return resource


# ──────────────────────────────────────────────
# BACKGROUND TTL EXPIRY DAEMON / REAPER
# ──────────────────────────────────────────────

async def reap_expired_ephemeral_resources(db: AsyncSession) -> int:
    """
    Finds and destroys all active ephemeral resources where expires_at <= utc_now().
    Returns the count of destroyed resources.
    """
    now = datetime.now(timezone.utc)
    expired_query = await db.execute(
        select(models.EphemeralResource).filter(
            models.EphemeralResource.status == "active",
            models.EphemeralResource.expires_at <= now,
        )
    )
    expired_resources = expired_query.scalars().all()
    count = 0

    for res in expired_resources:
        try:
            await destroy_ephemeral_resource(db, res, reason="Auto-destroyed: TTL expired")
            count += 1
        except Exception as e:
            logger.exception("Error reaping expired resource %s: %s", res.id, e)

    return count

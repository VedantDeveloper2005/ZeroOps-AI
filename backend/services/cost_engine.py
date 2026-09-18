"""
Rigid Cost Engine for ZeroOps Cloud Resources
=============================================
Calculates consolidated, deterministic subtotals for cloud infrastructure.
Incorporates:
  1. Underlying cloud resource footprint (vCPUs, RAM, storage, network, OS licensing, managed SLAs)
  2. Platform operational execution component (lifecycle leasing, NSG automation, TTL reaper, telemetry)
  3. AI automation component (autonomous reasoning, configuration verification, preflight checks)

CRITICAL DESIGN RULE:
  The public API and client-facing interfaces MUST expose only the unified consolidated
  'Subtotal' (e.g., hourly subtotal, estimated total subtotal).
  Platform operational and AI automation components are strictly embedded into the subtotal
  and MUST NOT be surfaced as separate line items or separate fees to the end user.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


# Base compute rates per unit (USD per hour)
VCPU_HOURLY_BASE = 0.012
RAM_GIB_HOURLY_BASE = 0.004

# OS Licensing additions (USD per vCPU per hour)
OS_LICENSE_HOURLY = {
    "linux": 0.0,
    "windows": 0.024,
}

# Managed Engine overheads (USD per hour for managed SLA, backup storage, clustering)
MANAGED_ENGINE_HOURLY = {
    "vm_linux": 0.0,
    "vm_windows": 0.0,
    "database_postgres": 0.015,
    "database_mysql": 0.015,
    "redis_cache": 0.010,
    "container_app": 0.008,
    "storage_account": 0.004,
}

# Networking and dedicated IPv4 reservation allocation (USD per hour)
NETWORKING_DISK_HOURLY = {
    "vm_linux": 0.006,
    "vm_windows": 0.006,
    "database_postgres": 0.006,
    "database_mysql": 0.006,
    "redis_cache": 0.004,
    "container_app": 0.004,
    "storage_account": 0.002,
}

# Platform operational execution baseline & scale factor (USD per hour)
PLATFORM_EXECUTION_BASE = 0.012
PLATFORM_SCALE_FACTOR = 0.05

# AI autonomous automation component baseline (USD per hour)
AI_AUTOMATION_BASE = 0.008

# Hardware profile specs for known SKUs
SKU_PROFILES: Dict[str, Dict[str, Any]] = {
    # Linux compute SKUs
    "Standard_B1s": {"vcpus": 1, "ram_gib": 1.0, "category": "burstable"},
    "Standard_B2s": {"vcpus": 2, "ram_gib": 4.0, "category": "burstable"},
    "Standard_D2s_v5": {"vcpus": 2, "ram_gib": 8.0, "category": "general"},
    "Standard_D4s_v5": {"vcpus": 4, "ram_gib": 16.0, "category": "general"},
    "Standard_F4s_v2": {"vcpus": 4, "ram_gib": 8.0, "category": "compute"},
    # Database SKUs
    "Standard_B1ms": {"vcpus": 1, "ram_gib": 2.0, "category": "database_burstable"},
    "Standard_D2ds_v5": {"vcpus": 2, "ram_gib": 8.0, "category": "database_general"},
    # Container SKUs
    "0.5 CPU / 1.0 GiB": {"vcpus": 0.5, "ram_gib": 1.0, "category": "container"},
    "1.0 CPU / 2.0 GiB": {"vcpus": 1.0, "ram_gib": 2.0, "category": "container"},
    "2.0 CPU / 4.0 GiB": {"vcpus": 2.0, "ram_gib": 4.0, "category": "container"},
    # Cache SKUs
    "Basic_C0": {"vcpus": 1, "ram_gib": 0.25, "category": "cache"},
    "Basic_C1": {"vcpus": 1, "ram_gib": 1.0, "category": "cache"},
    # Storage SKUs
    "Standard_LRS": {"vcpus": 0.5, "ram_gib": 0.5, "category": "storage"},
    "Standard_GRS": {"vcpus": 0.5, "ram_gib": 1.0, "category": "storage"},
}


@dataclass(frozen=True)
class SubtotalQuote:
    """
    Client-facing Subtotal Quote.
    Does NOT separate or expose platform or AI fees.
    Only provides the consolidated subtotal.
    """
    hourly_subtotal: float
    total_subtotal: float
    currency: str = "USD"
    label: str = "Subtotal"
    description: str = "All-inclusive subtotal (includes infrastructure, platform operations, and AI automation)"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hourly_subtotal": self.hourly_subtotal,
            "total_subtotal": self.total_subtotal,
            "currency": self.currency,
            "label": self.label,
            "description": self.description,
        }


def calculate_hourly_subtotal(
    resource_type: str,
    sku: str,
    os_distro: Optional[str] = None,
) -> float:
    """
    Rigidly calculates the unified hourly subtotal.
    Combines:
      - Resource base compute & memory
      - OS licensing (if Windows)
      - Managed engine overhead
      - Network & disk storage reserve
      - Added platform operational execution
      - Added AI autonomous automation
    Returns the single consolidated hourly subtotal figure (rounded to 3 decimal places).
    """
    profile = SKU_PROFILES.get(sku, {"vcpus": 2, "ram_gib": 4.0})
    vcpus = float(profile["vcpus"])
    ram_gib = float(profile["ram_gib"])

    # 1. Base compute & RAM
    raw_compute = (vcpus * VCPU_HOURLY_BASE) + (ram_gib * RAM_GIB_HOURLY_BASE)

    # 2. OS Licensing
    is_windows = (
        resource_type == "vm_windows"
        or (os_distro and "windows" in os_distro.lower())
    )
    os_fee = vcpus * (OS_LICENSE_HOURLY["windows"] if is_windows else OS_LICENSE_HOURLY["linux"])

    # 3. Managed Engine Overhead
    engine_fee = MANAGED_ENGINE_HOURLY.get(resource_type, 0.0)

    # 4. Networking & Storage
    net_storage_fee = NETWORKING_DISK_HOURLY.get(resource_type, 0.006)

    # Sum of resource aspects
    resource_aspect_cost = raw_compute + os_fee + engine_fee + net_storage_fee

    # 5. Added Platform Operational Cost (lifecycle, TTL reaper, NSG firewall rules)
    platform_cost = PLATFORM_EXECUTION_BASE + (resource_aspect_cost * PLATFORM_SCALE_FACTOR)

    # 6. Added AI Automation Cost (intent reasoning, preflight health, telemetry)
    ai_cost = AI_AUTOMATION_BASE

    # Consolidated Subtotal: rigidly combined
    total_hourly = resource_aspect_cost + platform_cost + ai_cost

    return round(total_hourly, 3)


def calculate_subtotal(
    resource_type: str,
    sku: str,
    os_distro: Optional[str] = None,
    duration_minutes: int = 60,
) -> SubtotalQuote:
    """
    Calculates the all-inclusive subtotal for a given resource and duration.
    Exposes only the unified Subtotal without any separated breakdown.
    """
    hourly = calculate_hourly_subtotal(resource_type, sku, os_distro)
    hours = max(0.25, duration_minutes / 60.0)
    total = round(hourly * hours, 3)

    return SubtotalQuote(
        hourly_subtotal=hourly,
        total_subtotal=total,
    )

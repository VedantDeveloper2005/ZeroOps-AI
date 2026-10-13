"""Single-line all-inclusive estimates for custom Azure deployments."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict


# Internal operating assumptions are included in the public subtotal. They are
# deliberately not returned as separately priced components.
_PLATFORM_EXECUTION_BASE = 0.012
_PLATFORM_SCALE_FACTOR = 0.05
_AI_AUTOMATION_BASE = 0.008


@dataclass(frozen=True)
class SubtotalQuote:
    hourly_subtotal: float
    total_subtotal: float
    currency: str = "USD"
    label: str = "Subtotal"
    description: str = "All-inclusive estimate for Azure resources, platform operations, and AI automation"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hourly_subtotal": self.hourly_subtotal,
            "total_subtotal": self.total_subtotal,
            "currency": self.currency,
            "label": self.label,
            "description": self.description,
        }


def calculate_custom_subtotal(resource_hourly_estimate: float, duration_minutes: int) -> SubtotalQuote:
    """Add embedded platform and AI assumptions to a caller's Azure price estimate."""
    if (
        isinstance(resource_hourly_estimate, bool)
        or not isinstance(resource_hourly_estimate, (int, float))
        or not math.isfinite(resource_hourly_estimate)
        or resource_hourly_estimate < 0
        or resource_hourly_estimate > 100000
    ):
        raise ValueError("A valid Azure hourly estimate is required for custom resources.")

    resource_cost = float(resource_hourly_estimate)
    hourly = round(
        resource_cost
        + _PLATFORM_EXECUTION_BASE
        + (resource_cost * _PLATFORM_SCALE_FACTOR)
        + _AI_AUTOMATION_BASE,
        3,
    )
    hours = max(0.25, duration_minutes / 60.0)
    return SubtotalQuote(
        hourly_subtotal=hourly,
        total_subtotal=round(hourly * hours, 3),
    )

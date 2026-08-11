"""Deterministic incident rules over persisted telemetry samples."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable


@dataclass(frozen=True)
class IncidentSignal:
    rule_key: str
    severity: str
    title: str
    summary: str
    first_observed_at: datetime
    last_observed_at: datetime
    evidence: tuple[dict[str, Any], ...]


def _value(sample: Any, field: str) -> Any:
    return getattr(sample, field, None)


def _sustained_window(
    samples: list[Any],
    field: str,
    predicate,
    *,
    minimum_samples: int = 3,
) -> list[Any]:
    relevant = [sample for sample in samples if _value(sample, field) is not None]
    window = relevant[-minimum_samples:]
    if len(window) < minimum_samples:
        return []
    return window if all(predicate(_value(sample, field)) for sample in window) else []


def _metric_evidence(samples: list[Any], field: str, unit: str) -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "source": "metric",
            "metric": field,
            "value": _value(sample, field),
            "unit": unit,
            "recorded_at": _value(sample, "timestamp").isoformat()
            if _value(sample, "timestamp")
            else None,
        }
        for sample in samples[-3:]
        if _value(sample, field) is not None
    )


def evaluate_incident_rules(samples: Iterable[Any]) -> tuple[IncidentSignal, ...]:
    """Return active rule signals; absent metrics cannot trigger or clear a rule."""
    ordered = sorted(
        (sample for sample in samples if _value(sample, "timestamp") is not None),
        key=lambda sample: _value(sample, "timestamp"),
    )
    if not ordered:
        return ()
    last_at = ordered[-1].timestamp
    signals: list[IncidentSignal] = []

    rules = (
        (
            "sustained_cpu_high",
            "high",
            "Sustained CPU utilization",
            "CPU utilization remained at or above 90% for three telemetry samples.",
            "cpu_utilization",
            lambda value: float(value) >= 90,
            "%",
        ),
        (
            "sustained_memory_high",
            "high",
            "Sustained memory utilization",
            "Memory utilization remained at or above 90% for three telemetry samples.",
            "memory_utilization",
            lambda value: float(value) >= 90,
            "%",
        ),
        (
            "http_error_rate_spike",
            "high",
            "HTTP error-rate spike",
            "HTTP errors remained at or above 5% for three telemetry samples.",
            "error_rate",
            lambda value: float(value) >= 5,
            "%",
        ),
        (
            "sustained_high_latency",
            "medium",
            "Sustained response latency",
            "Response latency remained at or above 2,000 ms for three telemetry samples.",
            "response_time_ms",
            lambda value: float(value) >= 2_000,
            "ms",
        ),
        (
            "availability_degraded",
            "high",
            "Application availability degraded",
            "Availability remained below 99% for three telemetry samples.",
            "availability_percent",
            lambda value: float(value) < 99,
            "%",
        ),
    )
    for rule_key, severity, title, summary, field, predicate, unit in rules:
        window = _sustained_window(ordered, field, predicate)
        if window:
            signals.append(IncidentSignal(
                rule_key=rule_key,
                severity=severity,
                title=title,
                summary=summary,
                first_observed_at=window[0].timestamp,
                last_observed_at=window[-1].timestamp,
                evidence=_metric_evidence(window, field, unit),
            ))

    latest = ordered[-1]
    failed_pods = _value(latest, "failed_pods")
    if failed_pods is not None and int(failed_pods) > 0:
        signals.append(IncidentSignal(
            rule_key="aks_failed_pods",
            severity="critical",
            title="AKS workload has failed pods",
            summary="The latest AKS telemetry sample reports one or more failed pods.",
            first_observed_at=last_at,
            last_observed_at=last_at,
            evidence=_metric_evidence(ordered, "failed_pods", "pods"),
        ))

    health = str(_value(latest, "deployment_health") or "").strip().lower()
    if health in {"failed", "unhealthy", "rollout_failed", "unavailable"}:
        signals.append(IncidentSignal(
            rule_key="deployment_health_failed",
            severity="critical",
            title="Deployment health check failed",
            summary=f"The deployment target reported the factual health state {health!r}.",
            first_observed_at=last_at,
            last_observed_at=last_at,
            evidence=({
                "source": "health_check",
                "state": health,
                "recorded_at": last_at.isoformat(),
            },),
        ))

    restart_samples = [sample for sample in ordered if _value(sample, "pod_restarts") is not None]
    if len(restart_samples) >= 2:
        increase = int(_value(restart_samples[-1], "pod_restarts")) - int(
            _value(restart_samples[max(0, len(restart_samples) - 3)], "pod_restarts")
        )
        if increase >= 3:
            signals.append(IncidentSignal(
                rule_key="aks_restart_burst",
                severity="high",
                title="AKS container restart burst",
                summary=f"Container restart count increased by {increase} within the sampled interval.",
                first_observed_at=restart_samples[max(0, len(restart_samples) - 3)].timestamp,
                last_observed_at=last_at,
                evidence=_metric_evidence(
                    restart_samples[max(0, len(restart_samples) - 3):],
                    "pod_restarts",
                    "restarts",
                ),
            ))
    return tuple(signals)

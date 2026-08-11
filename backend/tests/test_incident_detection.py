from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from backend.services.incident_detection import evaluate_incident_rules


def sample(at, **values):
    defaults = {
        "cpu_utilization": None,
        "memory_utilization": None,
        "error_rate": None,
        "response_time_ms": None,
        "availability_percent": None,
        "pod_restarts": None,
        "failed_pods": None,
        "deployment_health": None,
    }
    return SimpleNamespace(timestamp=at, **{**defaults, **values})


def test_cpu_rule_requires_three_sustained_samples():
    now = datetime.now(timezone.utc)
    two = [sample(now - timedelta(minutes=1), cpu_utilization=95), sample(now, cpu_utilization=96)]
    assert evaluate_incident_rules(two) == ()

    signals = evaluate_incident_rules([sample(now - timedelta(minutes=2), cpu_utilization=94), *two])
    assert [signal.rule_key for signal in signals] == ["sustained_cpu_high"]


def test_sustained_rule_timestamps_and_evidence_use_only_observed_metric_samples():
    now = datetime.now(timezone.utc)
    first_cpu = now - timedelta(minutes=10)
    samples = [
        sample(first_cpu, cpu_utilization=91),
        sample(now - timedelta(minutes=2), memory_utilization=20),
        sample(now - timedelta(minutes=1), cpu_utilization=92),
        sample(now, cpu_utilization=93),
    ]

    signal = evaluate_incident_rules(samples)[0]

    assert signal.first_observed_at == first_cpu
    assert signal.last_observed_at == now
    assert [item["recorded_at"] for item in signal.evidence] == [
        first_cpu.isoformat(),
        (now - timedelta(minutes=1)).isoformat(),
        now.isoformat(),
    ]


def test_missing_metrics_do_not_become_zero_or_trigger_incidents():
    now = datetime.now(timezone.utc)
    assert evaluate_incident_rules([sample(now)]) == ()


def test_failed_pod_and_health_states_trigger_factual_signals():
    now = datetime.now(timezone.utc)
    signals = evaluate_incident_rules([
        sample(now, failed_pods=1, deployment_health="rollout_failed"),
    ])
    assert {signal.rule_key for signal in signals} == {
        "aks_failed_pods",
        "deployment_health_failed",
    }

# Monitoring and Telemetry

ZeroOps stores and displays only telemetry that was received from an
authenticated worker or collector. Missing measurements remain `NULL`, and an
empty time window is reported as `no_telemetry`.

## Implementation status

- **Implemented and covered by repository tests:** authenticated ingestion,
  nullable metric persistence, coverage-aware windows, project-owned queries,
  AKS pod/replica fields, health state, and deterministic incident evaluation.
- **Partially implemented:** the ingestion contract accepts Azure Monitor,
  Application Insights, Container Insights, health-check, and worker source
  labels, but no Azure collector/poller or scheduled ingestion job is deployed
  by this change.
- **Not implemented:** a claim that merely connecting Azure automatically
  enables telemetry. It does not.
- **Not live verified:** no live Azure metric stream was connected for this
  change set.

## Ingestion contract

Trusted workers or collectors send:

```text
POST /api/deployments/{deployment_id}/metrics
X-ZeroOps-Worker-Token: <WORKER_EVENT_TOKEN>
```

The endpoint returns `503` when `WORKER_EVENT_TOKEN` is not configured and
`403` for a missing or mismatched token. The token belongs in Key Vault and
must not be sent to browsers.

The request accepts an optional timestamp and one declared source:

```text
azure-monitor
application-insights
container-insights
health-check
worker
```

The source label identifies the trusted caller's adapter; the API does not
independently query Azure to prove that label. The collector remains
responsible for Azure authentication, metric namespace/dimension selection,
and timestamp integrity.

Accepted measurements are nullable:

| Field | Unit/range |
|---|---|
| `cpu_percent` | 0-100 percent |
| `memory_percent` | 0-100 percent |
| `request_count` | non-negative count |
| `request_rate` | non-negative requests per collector interval/unit |
| `response_latency_ms` | non-negative milliseconds |
| `http_error_rate_percent` | 0-100 percent |
| `availability_percent` | 0-100 percent |
| `pod_restarts` | non-negative cumulative count |
| `pods_ready` | non-negative count |
| `replica_count` | non-negative count |
| `failed_pods` | non-negative count |
| `deployment_health` | `healthy`, `degraded`, `unhealthy`, `unknown`, `rollout_failed`, or `unavailable` |

Timestamps more than five minutes in the future or seven days in the past are
rejected. A missing timestamp uses the API receipt time.

## Query contract

Authenticated project owners request:

```text
GET /api/projects/{project_id}/monitoring?window=live|1h|6h|24h
```

`live` represents the most recent 15 minutes. Longer selectors are advertised
in `available_windows` only after persisted history spans that duration. A
query is bounded to 1,000 samples.

If no deployment exists, the response states that no telemetry can be
collected. If a deployment exists but no samples fall in the window, the
response includes:

```json
{
  "availability": "no_telemetry",
  "source": null,
  "deployment_health": null,
  "samples": [],
  "message": "No telemetry received in the selected window."
}
```

The UI must preserve that empty state. It must not draw zero-valued charts,
invent an uptime percentage, or infer healthy pods from the absence of an
error.

## Deterministic incident rules

After accepting a sample, the API evaluates up to the latest ten deployment
samples. The current rules are:

| Rule | Condition | Severity |
|---|---|---|
| Sustained CPU | at least 90% for three available CPU samples | High |
| Sustained memory | at least 90% for three available memory samples | High |
| HTTP error spike | at least 5% for three available error-rate samples | High |
| Sustained latency | at least 2,000 ms for three available latency samples | Medium |
| Availability degraded | below 99% for three available availability samples | High |
| AKS failed pods | latest `failed_pods` is greater than zero | Critical |
| Deployment health failure | latest health is unhealthy, rollout failed, or unavailable | Critical |
| AKS restart burst | cumulative restarts increase by at least three within the sampled comparison | High |

Absent metrics cannot trigger or clear a rule. Evidence contains the metric,
value, unit, and timestamp only. An active incident with the same deployment
and rule is updated rather than duplicated.

## What monitoring registration means

The pipeline's monitoring-registration stage may record that a deployed target
has target identifiers, but the current pipeline explicitly skips/unclaims
registration and writes telemetry status `unavailable` with the reason that no
collector is configured. It does not provision Application Insights, install
Container Insights, create diagnostic settings, or start a collector by
itself.

Until a collector is configured and the first authenticated sample is stored,
the correct product state is `no_telemetry`.

## Collector requirements

A production collector should:

1. authenticate to Azure with managed identity and least privilege;
2. bind every query to the exact subscription, resource group, target, and
   deployment revision;
3. normalize source units explicitly;
4. send only accepted numeric/health fields and no raw logs or credentials;
5. authenticate to the backend using a rotated worker token over HTTPS;
6. avoid blind duplicate delivery: the current metric endpoint has no
   observation-id idempotency key, so repeated samples can affect a sustained
   rule; a production contract should add deduplication before enabling
   automatic retries; and
7. expose its own lag/error health so a stopped collector is distinguishable
   from a healthy application.

That collector/poller is a remaining production task.

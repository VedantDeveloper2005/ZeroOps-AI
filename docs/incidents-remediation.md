# Incidents, Investigations, and Remediation

Incidents and remediation are durable, tenant-owned records. Detection is
deterministic; AI can explain redacted evidence but cannot authorize or execute
an action.

## Implementation status

- **Implemented and covered by repository tests:** deterministic telemetry
  rules, incident persistence/upsert, project-owned list/detail APIs,
  acknowledgement/dismissal, structured investigation records, risk-bearing
  remediation proposals, user approval/rejection records, execution attempts,
  and one non-mutating health-check executor.
- **Partially implemented:** sanitized pipeline-failure investigation is
  connected where the durable failure path invokes it. Manual incident
  investigation has no background investigation worker and returns a persisted
  `unavailable` result.
- **Not implemented:** automatic restart, scale, rollback, configuration
  mutation, Terraform apply, arbitrary shell commands, or direct execution of
  model-produced instructions. Stored auto-retry/rollback preferences do not
  imply that such executors exist.
- **Not live verified:** no live Azure incident or remediation was executed for
  this change set.

## Incident sources and lifecycle

The current connected source is deterministic evaluation of persisted
deployment telemetry. See [Monitoring and telemetry](monitoring.md) for exact
rules and thresholds. The schema also allows incidents to reference a
pipeline run and stage so future deterministic pipeline/security detections do
not need an unrelated record format.

Incident states are:

```text
open -> investigating -> mitigated -> resolved
  \-> dismissed
```

Not every transition is automated today. The connected APIs expose:

```text
GET  /api/projects/{project_id}/incidents
GET  /api/incidents/{incident_id}
POST /api/incidents/{incident_id}/acknowledge
POST /api/incidents/{incident_id}/dismiss
POST /api/incidents/{incident_id}/investigate
```

Acknowledgement records the acting user and timestamp without claiming the
condition is fixed. Dismissal closes a non-resolved incident and records the
actor. A repeated active telemetry rule updates the existing incident's last
observation and evidence instead of creating a duplicate.

Missing telemetry does not resolve an incident. The current implementation
does not automatically infer recovery from silence.

## Evidence policy

Incident evidence is a bounded factual list such as:

- metric name, normalized value, unit, and recorded timestamp;
- deployment health state;
- project/deployment/revision identifiers; or
- a redacted pipeline stage failure category.

It must not contain credentials, raw environment values, repository source,
scanner raw output, secret matches, full command logs, model prompts,
Terraform state, or saved plans.

## AI investigations

`AIInvestigation` records:

- the trigger and failed stage/incident references;
- provider, model, model version, and prompt version;
- a SHA-256 digest of the bounded evidence;
- sanitized evidence supplied to the model;
- structured summary, root cause, severity, recommendation, resolution steps,
  confidence, and user-action flags; and
- explicit error/unavailable fields when diagnosis cannot run.

Pipeline failure diagnosis runs only after the deterministic pipeline has
already recorded failure. Its output cannot convert a failed stage to passed,
skip a required gate, or create deployment authority.

The pipeline commits the investigation as `running` before crossing the model
boundary and supplies bounded, redacted failed-stage diagnostics plus revision
and change evidence. A validated model response is stored as `succeeded` with
its actual provider/model provenance and token counts. Provider failure or an
invalid response uses deterministic local analysis for a useful explanation,
but persists `status=unavailable` and `AI_PROVIDER_UNAVAILABLE`; the UI must not
describe that fallback as completed AI work.

The API maintenance loop marks any `running` investigation older than fifteen
minutes as `unavailable` with `AI_INVESTIGATION_INTERRUPTED`. This prevents a
worker/process loss from leaving the UI in an indefinite investigating state;
it does not retry the model or claim a diagnosis was produced.

The manual incident investigation endpoint currently creates an
`AIInvestigation` with status `unavailable` and the reason that no durable
incident-investigation worker is configured. A GET request never invokes a
model. This explicit unavailable record is intentional; the UI must not render
an invented root cause.

## Remediation proposals

A proposal is not an action. It stores:

- a stable action type and idempotency key;
- title, description, rationale, and risk tier;
- whether approval is required;
- a digest and redacted representation of its parameters;
- expiration and decision metadata; and
- links to the incident, deployment, and investigation.

Proposal states are:

```text
proposed, pending_approval, approved, denied, expired, cancelled, executed
```

Authenticated project owners use:

```text
POST /api/remediation-proposals/{proposal_id}/approve
POST /api/remediation-proposals/{proposal_id}/reject
POST /api/remediation-proposals/{proposal_id}/execute
```

Approval and rejection persist the acting user and timestamp. Approval-required
proposals cannot execute before approval. Expired, denied, cancelled, or
already executed proposals cannot be replayed as a new first attempt.

Migration `006_secure_pending_approvals` also clears legacy plaintext
parameters from the older pending-approval path. New compatibility entries use
a versioned Fernet envelope that is erased after use. This is a migration
safety measure, not permission for new arbitrary executors.

## Connected executor: repeat health check

When the latest telemetry explicitly reports a failed deployment health state
and the deployment has a verified `live_url`, ZeroOps can propose
`rerun_health_check`:

- risk: low;
- mutation: none;
- approval required: no for the current generated proposal;
- executor: deterministic App Service public-endpoint verifier bound to the
  persisted release application name;
- verification: the exact expected HTTPS `azurewebsites.net` origin must
  resolve only to global addresses and return a direct 2xx response; redirects,
  proxies, alternate hosts, and private targets are rejected.

On success, the execution and verification states become `succeeded`, the
proposal becomes `executed`, and the linked incident becomes `resolved`. On a
factual check failure, execution/verification become `failed` with a redacted
error. When the deployment has no endpoint, the result is `unavailable`.

Any other action type currently returns `unavailable` with
`REMEDIATION_EXECUTOR_UNAVAILABLE`. It is not passed to a shell, Azure CLI,
Terraform, Kubernetes, or a model.

## Risk and authority boundary

The safe operating rule is:

- low-risk, demonstrably non-mutating checks may be executable without a
  separate approval when their proposal says so;
- any proposal marked approval-required must have an authenticated actor
  decision;
- medium/high-risk or mutating actions require a purpose-built deterministic
  executor, explicit scope and rollback/verification contracts, and end-to-end
  tests before they can be enabled; and
- AI text is advisory evidence only.

There is currently no purpose-built medium/high-risk mutating executor. Do not
present approval buttons as evidence that an action implementation exists.

## Remaining production work

1. Connect a durable incident-investigation queue/worker with idempotent model
   invocation and cost/provenance controls.
2. Define explicit recovery/closure policies for telemetry rules rather than
   inferring recovery from absent samples.
3. Add an operator-audited executor registry if mutating remediations are
   approved later.
4. Give every executor resource scope, preconditions, idempotency, timeout,
   rollback, and post-action verification contracts.
5. Verify the full incident-to-remediation flow against a disposable Azure
   deployment before enabling it for production.

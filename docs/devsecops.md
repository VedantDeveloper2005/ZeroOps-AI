# DevSecOps Implementation

This document describes the DevSecOps extension as it exists in the
repository. “Implemented” means code plus repository test coverage, not a live
Azure production verification.

## Status summary

### Implemented

- Versioned, tenant-owned project pipeline configuration
- Durable pipeline runs and normalized, ordered stage attempts
- Signed and idempotent GitHub push webhook processing
- Bounded repository snapshots, deterministic change classification, and
  explainable AI-analysis reuse decisions with factual model provenance
- Deterministic repository-command planning, fail-closed isolation-attestation
  validation, and scanner adapters with redacted evidence
- Security scan and finding persistence without raw source or secret matches
- Existing Azure App Service target selection and deployment path
- Strict deployment adapter contracts for an existing AKS cluster
- Authenticated pipeline approval/rejection, HMAC-bound fresh-run evidence,
  and factual dashboard states and controls
- Worker-authenticated metric ingestion and deterministic incident detection
- Incident acknowledgement/dismissal and proposal approval/rejection records
- One non-mutating remediation executor: repeat a verified public health check

### Partially implemented

- Pipeline orchestration is integrated with durable stage records, but a stage
  can run only where its corresponding runtime/tool integration is available.
  Applicability and tool availability are separate: an applicable missing tool
  becomes `unavailable`, not `skipped`.
- No production disposable repository-command executor is connected. The
  active release worker therefore refuses to run dependency, lint, test, or
  build commands from tenant repositories and blocks those applicable stages.
- Monitoring stores and serves real samples, but no Azure Monitor,
  Application Insights, or Container Insights collector/poller is deployed by
  this repository change.
- Pipeline-failure investigation accepts only sanitized evidence. Manual
  incident investigation has no durable investigation worker and persists an
  explicit unavailable result.
- Pipeline settings expose automatic retry and rollback preferences, but no
  general-purpose retry/rollback executor is enabled.
- AKS application deployment is implemented only for an already existing
  cluster. Cluster provisioning, node-pool changes, and cluster-wide policy
  administration are outside the adapter. The active pipeline currently stops
  before cluster mutation because external endpoint verification is not ready.
- The production API worker does not dispatch the separate repository-analysis
  Function, so required fresh analysis currently remains deterministic and is
  recorded with `ai_used=false` in production.

### Planned or blocked

- The Service Bus/Functions/VMSS Terraform architecture is not connected to a
  complete API producer and atomic saved-plan approval/apply flow.
- Terraform apply remains intentionally disabled until that flow is integrated
  and verified end to end in a disposable workload resource group.
- Live App Service and AKS end-to-end verification was not performed for this
  change set. AKS discovery in the available CLI session was blocked by MFA.
- Medium/high-risk mutating remediation executors, automatic cluster changes,
  and arbitrary AI-generated shell or cloud commands are not implemented.

## Durable domain

Migration `005_devsecops_domain` introduces these normalized records:

| Record | Purpose |
|---|---|
| `ProjectPipelineConfiguration` | Immutable configuration version for a project |
| `PipelineRun` | One trigger, branch, immutable source revision, target, and overall lifecycle |
| `PipelineStageAttempt` | One ordered attempt for one stage, including redacted evidence and result metadata |
| `RepositoryAnalysisSnapshot` | Content-free fingerprint and bounded analysis summary that can be reused |
| `ChangeAnalysis` | Deterministic categories and the reason AI was required or reused |
| `SecurityScan` / `SecurityFinding` | Tool provenance, counts, policy result, and safe finding metadata |
| `WebhookDelivery` | Signature state, delivery idempotency, payload digest, and processing outcome |
| `Incident` | A deterministic signal with timestamps and bounded factual evidence |
| `AIInvestigation` | Model provenance and structured diagnosis over redacted evidence |
| `RemediationProposal` / `RemediationExecution` | Risk decision, actor, execution attempt, and verification outcome |

Core lifecycle state is not stored only in a JSON blob. JSON fields are
reserved for bounded evidence and presentation metadata. Tenant/project
ownership and idempotency keys are part of the schema constraints.

Migration `006_secure_pending_approvals` clears pre-existing plaintext
executor parameters and changes the compatibility path to a versioned,
single-use encrypted envelope. It does not make the separate Terraform apply
flow production-ready by itself.

Migration `007_change_analysis_retry_history` removes the cross-run uniqueness
constraint on revision/fingerprint change decisions. Distinct approval-bound
runs of the same immutable commit can therefore retain separate
`ChangeAnalysis` evidence, while the tenant idempotency constraint still
prevents duplicate persistence within a run.

## Project pipeline configuration

The authenticated configuration endpoints are:

```text
GET  /api/projects/{project_id}/pipeline-config
PUT  /api/projects/{project_id}/pipeline-config
POST /api/projects/{project_id}/github-webhook-secret/regenerate
```

Approval decisions use authenticated project-owner endpoints:

```text
POST /api/pipeline-runs/{run_id}/approve
POST /api/pipeline-runs/{run_id}/reject
```

Configuration versions include the tracked branch, automatic push behavior,
deployment mode, test/scanner toggles, production approval preference, AI
failure diagnosis, and stored retry/rollback preferences. Enabling automatic
deployment is rejected until a project webhook secret exists.

`production_approval_required` is currently a stored compatibility/preference
field, not a second independent enforcement gate. Effective release approval
behavior is selected by `deployment_mode=require_approval` (and by the
infrastructure-change safety gate). The UI must not imply that changing only
the redundant preference changes runtime authority.

The deployment modes are:

| Mode | Intended behavior | Current boundary |
|---|---|---|
| `validate_only` | Run applicable checks without a cloud release | The stage graph supports it. Push-triggered durable validation must have a connected worker path; otherwise it reports unavailable rather than pretending validation ran. |
| `deploy_after_checks` | Deploy only after every required check succeeds | This is the connected PostgreSQL deployment-worker mode. |
| `require_approval` | Run non-mutating checks, stop at Approval, then require an authenticated decision | The project-owner API and dashboard can approve or reject. Approval creates and opens a fresh, bound run that repeats checks; consumed and rejected states are no longer actionable. Backend tests and frontend type checking pass, but no live Azure end-to-end release was performed. |

## Signed GitHub webhook

The unauthenticated network endpoint is project-specific, but it accepts a
delivery only after validating its project-scoped Key Vault secret:

```text
POST /api/webhooks/github/{project_id}
```

It requires `X-GitHub-Event`, `X-GitHub-Delivery`, and
`X-Hub-Signature-256`. The implementation:

- limits the body to 2 MiB;
- verifies HMAC-SHA256 using constant-time comparison;
- records only a payload digest and bounded metadata, not the raw body;
- deduplicates GitHub delivery IDs within a tenant;
- verifies repository identity, branch, event type, and a 40-character commit
  SHA;
- skips deleted refs, untracked branches, and unsupported events explicitly;
- requires an approved infrastructure plan and a ready deployment target
  before queueing a release.

The generated secret is displayed once and stored as a project-scoped Key
Vault secret. Configure only the returned HTTPS webhook URL.

## Security tools and policy

| Scan | Tool | Persisted evidence |
|---|---|---|
| SAST | Semgrep | Rule, severity, safe title, path/line, tool version, counts |
| Dependencies | Trivy filesystem vulnerability scan | Vulnerability metadata and counts |
| Secrets | Gitleaks with redaction | Rule/location metadata only; match, secret, and entropy fields are discarded |
| Container | Trivy image scan | Findings bound to the verified image target |
| IaC | Checkov adapter | Rule/location metadata and tool provenance; Terraform fmt/init/validate/TFLint remain unavailable in the active pipeline until an isolated executor is connected |
| Kubernetes | Trivy configuration scan plus kubeconform | Repository configuration findings are persisted; the AKS adapter separately gates its rendered manifests, but that rendered scan is not yet a distinct `SecurityScan` record |
| SBOM | Syft CycloneDX source scan | Component count and bounded repository evidence; raw output is not retained and the result is not labeled as an image SBOM |

Scanner subprocesses run without a shell, with bounded time/output and a
restricted environment that does not inherit deployment credentials. Required
tools must return parseable output and a verifiable version. A missing tool,
unexpected exit code, malformed output, or unverifiable required version is
`unavailable` and blocking. A disabled or irrelevant scan is `skipped` with a
reason; those states are not interchangeable.

The connected general pipeline policy blocks critical findings. High findings
currently complete with a warning because no project setting for high-severity
blocking exists yet. The AKS rendered-manifest scan deliberately uses a stricter
policy that blocks critical and high findings. Do not describe high findings
as globally blocking until that project policy is implemented.

The checked-in `worker/Dockerfile` is the Service Bus VMSS Terraform executor
image. `worker/Dockerfile.pipeline` separately packages the PostgreSQL release
worker and pinned scanner/AKS tools. Platform CI builds and inspects that image,
but it was not built on this host, published, or deployed. Neither image is the
missing disposable tenant-command executor. Both keep `/app` root-owned and
read-only and use the root default-deny Docker build context.

## API evidence surfaces

The dashboard reads authenticated, project-owned APIs rather than generating
demonstration records:

```text
GET /api/deployments/{deployment_id}/pipeline
GET /api/projects/{project_id}/change-analysis
GET /api/projects/{project_id}/security-scans
GET /api/projects/{project_id}/monitoring?window=live|1h|6h|24h
GET /api/projects/{project_id}/incidents
GET /api/incidents/{incident_id}
```

See the focused documents for execution, change detection, AKS, monitoring,
and remediation details.

## Production configuration boundary

Production configuration is Key Vault-backed. `APP_ENV=production` refuses to
start without required database, authentication, URL, host, TLS, email, and
phone-verification configuration. The DevSecOps paths additionally require:

- `ZEROOPS_BACKEND_URL` for issuing a usable webhook URL;
- `WORKER_EVENT_TOKEN` for metric ingestion;
- AI workload settings if model-backed analysis or failure diagnosis is
  expected;
- an active Azure connection with target-specific metadata;
- a project-scoped GitHub webhook secret for push triggers;
- the required scanner executables in the release-worker image; and
- a separately deployed source-bound `RepositoryCheckExecutor` for untrusted
  dependency, quality, test, and build commands.

Do not place service-principal secrets, GitHub tokens, scanner raw output,
Terraform plan/state, or model prompts in pipeline evidence. The App Service
adapter writes secret application settings through a short-lived permission-
restricted file and redacts Azure CLI output.

## Verification boundary

Repository tests exercise the state machine, persistence adapters, change
classification, scanner parsing/fail-closed behavior, webhook signature and
idempotency rules, incident detection, remediation policy, target selection,
and AKS manifest/rollout validation. They use controlled doubles for cloud and
tool responses.

They do not prove current Azure subscription capacity, RBAC, ACR/cluster
connectivity, ingress availability, scanner installation in a deployed worker,
or a successful live rollout. Record those checks separately when an
authorized environment is available.

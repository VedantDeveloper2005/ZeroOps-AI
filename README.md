# ZeroOps AI

ZeroOps AI is an Azure-first DevSecOps control plane for authenticated,
commit-pinned application releases. It preserves the existing Azure App
Service path and contains a constrained deployment adapter for an existing
Azure Kubernetes Service (AKS) cluster. The active pipeline does not yet cross
the AKS mutation boundary because external endpoint verification is incomplete.

> [!IMPORTANT]
> This repository contains locally tested implementation work; it is not a
> certificate that a production Azure rollout has succeeded. This change set
> did not deploy an App Service application, connect to an AKS workload, run a
> Terraform apply, or complete a live Azure end-to-end verification. Required
> tools and external services fail closed or report `unavailable` rather than
> producing synthetic success data.

## Current status

| Area | Status | What that means |
|---|---|---|
| Durable pipeline records | Implemented and covered by repository tests | Project configuration, runs, ordered stage attempts, repository snapshots, change analyses, security scans, webhook deliveries, incidents, investigations, and remediation attempts are normalized in PostgreSQL. |
| Repository checks and security evidence | Safety boundary implemented; production executor not connected | Deterministic dependency, quality, test, and build plans return bounded, redacted results only through a fresh source-bound disposable-executor attestation. The active worker has no local subprocess fallback, so those applicable stages are `unavailable` and blocking until a production executor is connected. Scanner adapters are implemented and covered by repository tests. |
| Change-aware repository analysis | Decision and provenance implemented; production model handoff partial | Repository fingerprints and Git path changes decide when prior analysis can be reused. A validated model result is the only case recorded as AI-used. The active production worker currently returns deterministic analysis because its separate repository-analysis Function handoff is not connected. |
| Azure App Service | Code-preserved and hardened; not live verified | App Service remains the default target for ordinary web workloads. Health and smoke checks require a direct 2xx response from the exact expected public `azurewebsites.net` origin, with redirects, proxies, and private/non-global DNS results rejected. |
| Existing-cluster AKS | Adapter code-tested; active deployment blocked before mutation | The adapter can validate a namespace-scoped release, bind an immutable image digest, use an isolated cluster-user kubeconfig, and inspect rollout/pod evidence. Because external Service/Ingress verification is not implemented, the active pipeline returns `unavailable` before invoking server-side apply. It does not create or modify an AKS cluster. |
| GitHub push webhook | Implemented and covered by repository tests | Project-scoped HMAC-SHA256 secrets, bounded payloads, repository/branch/revision validation, and delivery idempotency are implemented. |
| Pipeline approval handoff | Implemented and locally verified; not live verified | Authenticated project-owner APIs and the deployments dashboard expose factual pending, approved-consumed, and rejected states. Approval queues and opens a fresh run pinned to the same source, target, plan, and configuration; that run repeats checks. Backend tests and the frontend type check pass, but no live API-to-worker Azure release was verified. |
| Monitoring and incidents | Partially implemented | Authenticated metric ingestion, truthful no-telemetry responses, deterministic incident rules, and persisted evidence are implemented. An Azure Monitor/Application Insights collector or poller is not connected. |
| Investigation and remediation | Partially implemented | Sanitized pipeline-failure investigations and a deterministic health-check remediation path are represented. Manual incident investigation has no durable worker and reports `unavailable`; restart, scale, rollback, and arbitrary command executors are not enabled. |
| Terraform execution plane | Blocked from apply | Service Bus, Functions, and an isolated VMSS executor exist as infrastructure/code contracts, but the active control plane is not connected to the atomic saved-plan approval/apply flow. Terraform apply remains disabled. |

Live AKS discovery was also blocked by an interactive Microsoft Entra MFA
requirement in the available Azure CLI session. No attempt was made to bypass
that boundary.

## Runtime architecture

The application has two deliberately distinct execution paths:

1. The active application-release path stores a `DeploymentJob` in PostgreSQL.
   A leased worker claims it, prepares the immutable Git revision, runs the
   applicable pipeline stages, and can deploy to App Service. AKS target
   selection is recorded, but the current runtime blocks before cluster
   mutation until external verification is available. Repository-declared commands require a
   separate attested disposable executor; none is connected in this change
   set, so a production run that needs those commands stops before deployment.
2. The Terraform architecture under `infra/`, `functions/`, and
   `worker/vmss_main.py` uses Service Bus and an isolated VMSS. Its plan/apply
   safety contracts are present, but the control-plane producer and durable,
   single-use approval handoff are not complete. It must not be treated as an
   active apply path.

See [Pipeline execution](docs/pipeline.md) and
[DevSecOps implementation](docs/devsecops.md) for the detailed boundaries.

## Local setup

Prerequisites:

- Node.js 22 and npm
- Python 3 with the packages in `backend/requirements.txt`
- PostgreSQL for migration and worker behavior that cannot be represented by
  SQLite
- Git for commit-pinned GitHub deployments and path-level change detection
- Azure CLI for the App Service worker path
- Azure Key Vault for production configuration and project-scoped secrets

Install and start the frontend:

```powershell
npm install
npm run dev
```

Install and start the API:

```powershell
cd backend
python -m pip install -r requirements.txt
$env:APP_ENV = "development"
python -m uvicorn main:app --reload --port 8000
```

`APP_ENV` must be exactly `development`, `test`, or `production`. In
production, `AZURE_KEYVAULT_URL` is the only configuration bootstrap alongside
`APP_ENV`; application settings are read from Key Vault. See
[Production Key Vault configuration](docs/production-key-vault.md).

## Required external tools

The deployment worker must provide each tool required by the repository and
selected target. Tool absence is not converted into a pass.

| Purpose | Tool |
|---|---|
| Source control | `git` |
| SAST | `semgrep` |
| Dependency, container, and Kubernetes scanning | `trivy` |
| Secret scanning | `gitleaks` |
| IaC policy | `checkov` |
| Terraform linting | `tflint` |
| Optional SBOM generation | `syft` |
| AKS validation and deployment | `kubectl`, `kubeconform`, and `helm` when a chart is used |
| Terraform validation/plan in its isolated plane | the pinned Terraform CLI |

`worker/Dockerfile` packages the separate Service Bus VMSS Terraform executor.
`worker/Dockerfile.pipeline` packages the PostgreSQL application-release worker
with pinned Terraform, TFLint, Checkov, Semgrep, Gitleaks, Trivy, Syft,
kubeconform, Helm, and kubectl versions. Its downloaded tool checksums and Azure
CLI base-image digest are pinned, and platform CI builds the image and checks
its entry point and tool availability. The local Docker daemon was unavailable,
so that image was not built or run on this development host, has not been
published to a registry, and has not been deployed to a production worker.

The root `.dockerignore` is default-deny, and both worker images keep `/app`
root-owned and read-only while running as the non-root `zeroops` user. Those
image controls reduce the worker attack surface, but they are not a substitute
for the required per-run executor: untrusted package-manager, test, lint, and
build commands must run with no worker-filesystem, database, Key Vault, or IMDS
access and with an explicit network policy.

Repository-declared package managers and runtimes are additionally required
for dependency installation, code-quality commands, tests, and builds. Details
are in [Pipeline execution](docs/pipeline.md).

The current general scanner policy blocks critical findings and records high
findings as warnings; there is no per-project high-severity blocking toggle
yet. The stricter AKS manifest path blocks both critical and high findings.

## Configuration required for real releases

At minimum, the control plane needs durable database/authentication settings,
a worker event token, a public backend URL for webhook setup, and a connected
Azure account. The Azure connection stores identifiers and target metadata;
the service-principal secret remains in Key Vault.

- Common Azure fields: tenant ID, subscription ID, client ID, resource group,
  region, and ACR login server
- App Service: an existing Linux App Service plan
- AKS: an existing cluster name and deterministic Kubernetes repository
  evidence
- Webhooks: `ZEROOPS_BACKEND_URL`, a project-scoped webhook secret generated
  through the authenticated API, and matching GitHub branch configuration
- Metrics: `WORKER_EVENT_TOKEN`, supplied as `X-ZeroOps-Worker-Token` by the
  trusted collector or worker

No AKS provisioning credential or cluster-admin kubeconfig is accepted by the
AKS adapter.

## Database migrations

`backend.database.run_migrations` applies append-only PostgreSQL migrations in
one transaction and records them in `schema_migrations`.

- `005_devsecops_domain` adds the normalized DevSecOps records and nullable
  telemetry fields. Missing measurements remain `NULL`; the migration does not
  invent historical zeroes.
- `006_secure_pending_approvals` invalidates legacy plaintext pending-action
  parameters. New compatibility approvals use a versioned Fernet envelope and
  erase it after use.
- `007_change_analysis_retry_history` lets each distinct pipeline retry against
  the same immutable revision retain its own change decision while preserving
  per-run idempotency.

Review [the migration notes](backend/migrations/README.md) before upgrading a
shared database, and validate the upgrade on a backup or staging copy first.

## Verification

Run the local suites without interpreting unavailable external tools or Azure
access as a live-cloud pass:

```powershell
npm run lint
npm run typecheck
npm run test:device-gate
npm run build
$env:APP_ENV = "test"
python -m pytest backend/tests -q
python -m unittest discover -s worker/tests -v
python -m unittest discover -s functions/tests -v
python -m unittest discover -s infra/tests -v
```

The repository also contains Terraform, TFLint, Checkov, and scanner checks.
If a required executable is absent, record that verification as unavailable;
do not mark it passed.

## Documentation

- [DevSecOps implementation and status](docs/devsecops.md)
- [Pipeline stages, modes, and worker queue](docs/pipeline.md)
- [Change detection and AI reuse](docs/change-detection.md)
- [Existing-cluster AKS deployment](docs/aks-deployment.md)
- [Monitoring and telemetry truthfulness](docs/monitoring.md)
- [Incidents, investigations, and remediation](docs/incidents-remediation.md)
- [Azure App Service hosting](docs/azure-app-service.md)
- [GitHub Actions Azure OIDC setup](docs/github-actions-azure-oidc.md)
- [Azure infrastructure plan](.azure/deployment-plan.md)

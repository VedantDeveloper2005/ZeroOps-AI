# ZeroOps AI Terraform Worker Migration Plan

> **Status:** Planning — awaiting owner approval. This plan changes application code only; it does not create, modify, or delete Azure resources.

Generated: 2026-07-20

## 1. Project overview

**Goal:** Evolve the existing ZeroOps deployment path into an AI Cloud Architect workflow. The backend remains a control plane: it records repository analysis, architecture decisions, approvals, and deployment jobs. A separately deployed worker performs all repository cloning, Terraform lifecycle commands, Azure provisioning, application deployment, health verification, and status reporting.

**Path:** Modify existing Azure-aware SaaS.

**Non-goals for this migration:** expose Terraform or cloud credentials; execute Terraform in FastAPI; create a new application; provision the ZeroOps control-plane Azure environment; add AWS/GCP implementations.

## 2. Requirements and operating assumptions

| Attribute | Decision |
|---|---|
| Classification | Production-style SaaS MVP / demonstration environment |
| Scale | Small to medium control plane; deployment workers scale independently |
| Budget posture | Balanced; actual customer cost estimates remain unavailable until subscription pricing and policy validation are connected |
| Cloud provider | Azure, through a provider interface that permits AWS/GCP implementations later |
| Default region | Central India, overridable through the approved infrastructure specification |
| Subscription | Not supplied. No Azure operation is included in this migration. Each approved deployment must validate its own subscription, policy, quota, and region before `terraform apply`. |
| Compliance/data residency | Not supplied. Private networking and residency controls must be supplied as explicit approved-plan requirements before a customer deployment. |

## 3. Repository audit

### Reusable components

| Area | Existing implementation | Migration use |
|---|---|---|
| Authentication and ownership | FastAPI dependencies plus project/user-scoped queries | Preserve for all plan, job, approval, and status endpoints |
| Repository access | GitHub OAuth encryption and repository-analysis endpoints | Worker decrypts a token only for an active job and clones with a non-logging credential mechanism |
| Analysis | `backend/services/analysis.py`, `ai.py`, persisted `AIAnalysis` data | Normalize into a structured repository-analysis report used by the planner |
| Architecture plan | `InfrastructurePlan`, planner APIs, architect chat, plan approval | Retain as the customer-facing infrastructure specification; never return Terraform source |
| Queue and status | `DeploymentJob`, Postgres row locking, deployment logs, event relay | Extend into the durable worker state machine and timeline |
| Frontend | Infrastructure workspace, deployment timeline, logs, API client | Keep the business-facing experience; bind it to real worker stages and resource summaries |
| Security | Azure Key Vault configuration and project-secret storage | Preserve; worker uses managed identity/Key Vault references and never persists plaintext credentials |

### Obsolete or incomplete deployment path

| Finding | Required change |
|---|---|
| `start_deploy` creates an internal HCL artifact in FastAPI | Move all Terraform source generation and filesystem writes into the worker |
| `worker/terraform_runner.py` calls `pipeline.run_deployment_pipeline` | Replace with a real Terraform execution adapter; retain the App Service deploy helper only as a post-provision deployment action |
| Existing Terraform generator is one incomplete file | Replace with internal, provider-scoped generator modules and no user-visible Terraform output |
| Legacy FastAPI background-task pipeline calls still exist for retry/rollback paths | Route every provisioning/release path through the queue; FastAPI must not spawn deployment pipelines |
| Deployment job status is broad `queued/running/completed/failed` | Enforce typed stage transitions, attempts, timestamps, redacted logs, idempotency, cancellation, and failure details |
| User Azure service-principal secret is supported | Prefer worker managed identity. When cross-subscription credentials are unavoidable, retrieve them from Key Vault only for the active job and never return/store them in job data |

## 4. Target architecture

```text
Next.js UI
  -> FastAPI control plane
       -> Repository analysis + AI architecture planner
       -> Approved InfrastructurePlan (customer-visible resource decisions)
       -> PostgreSQL deployment_jobs queue
            -> Independent Terraform Worker
                 -> secure repository clone
                 -> internal provider/generator modules
                 -> terraform fmt / validate / init / plan / apply
                 -> Azure provisioning + application release
                 -> health checks + redacted events/logs
       <- deployment timeline, live URL, monitoring state
```

Terraform files, Terraform state handles, raw plans, provider credentials, and Key Vault secret values remain worker-only. The API returns only resource summaries, stage state, safe diagnostics, and a verified live URL.

## 5. Architecture and recipe selection

**Selected recipe:** Application-managed Terraform worker (not `azd up`).

**Rationale:** ZeroOps generates per-customer Azure infrastructure from an approved architecture specification. Terraform is therefore an internal job artifact rather than static project infrastructure. The worker executes Terraform using a managed identity, an isolated per-job workspace, a remote encrypted state backend, and a deployment-specific lock.

### Provider abstraction

| Interface | Responsibility |
|---|---|
| `CloudProvider` | Validate a specification, translate supported components, produce a safe resource summary, execute provider lifecycle hooks, and derive verified URLs |
| `AzureProvider` | Initial implementation for App Service, App Service Plan, PostgreSQL Flexible Server, Blob Storage, Key Vault, Application Insights, managed identity, and VNet |
| Future providers | AWS/GCP implementations behind the same interface; no provider-specific details in plan APIs or React components |

### Supported V1 resource matrix

| Specification component | Azure implementation | Execution policy |
|---|---|---|
| Application | Linux App Service and Plan | Supported for deploy when source/build prerequisites pass |
| Database | PostgreSQL Flexible Server | Provision after explicit plan approval; use Entra/managed identity patterns, never generated admin passwords |
| Storage | Storage Account and private Blob container | Managed identity/RBAC access; no storage keys returned |
| Secrets | Key Vault | Key Vault references and least-privilege role assignments |
| Monitoring | Log Analytics + Application Insights | Required for a completed deployment |
| Networking | VNet, subnets, private endpoints where approved | Validate CIDRs, DNS, policy, and quota before apply |
| Container Apps, AKS, Redis, Cosmos DB, Azure Functions | Architecture choices may be planned | Explicitly marked unsupported for V1 execution until a provider module and validation coverage exist |

## 6. Implementation phases

1. **Domain and database migration**
   - Version the infrastructure specification and repository-analysis report.
   - Add job attempt, locked-by/locked-at, stage, approval, redacted event, idempotency, and Terraform-state metadata columns/indexes.
   - Preserve existing jobs and map legacy statuses safely; create an append-only deployment-event table for durable timelines.

2. **Provider and planner boundaries**
   - Introduce `backend/services/cloud/` with `CloudProvider` and `AzureProvider`.
   - Split analysis normalization, specification validation, cost/estimate capability status, and provider resource summaries.
   - Keep architect chat updates constrained to validated specification mutations. Unsupported choices remain visible as planned but are not deployable.

3. **Terraform worker engine**
   - Move HCL generation, workspace creation, and all Terraform commands to `worker/`.
   - Implement command allowlists, timeouts, cancellation, process cleanup, per-job directories, source cleanup, plan/apply locks, redaction, and structured event emission.
   - Execute `fmt`, `validate`, `init`, `plan`, and `apply` in order. A plan that needs approval transitions to `awaiting_approval`; an approved specification is the default V1 approval gate.
   - Reuse the existing App Service deployment helper only after Terraform has provisioned a valid target; then perform an HTTP health check before completion.

4. **Control-plane API refactor**
   - Make plan approval and job creation transactional and idempotent.
   - Remove FastAPI-side internal-IaC generation and background deployment execution from deploy/retry/rollback paths.
   - Add authenticated worker lease/event endpoints and typed job/timeline responses; never return raw Terraform or credentials.

5. **Frontend alignment**
   - Retain the existing infrastructure workspace and resource cards.
   - Replace inferred progress/countdown UI with actual job stages, approval states, provider validation results, redacted logs, verified endpoint status, and unsupported-choice guidance.
   - Keep all Terraform implementation details hidden.

6. **Documentation, migration, and tests**
   - Document worker deployment, managed-identity RBAC, remote Terraform state, supported-resource matrix, rollback/cancellation behavior, and operator runbooks.
   - Add unit tests for specification/provider validation and status transitions; integration tests with a fake Terraform binary; API ownership tests; and frontend lint/build verification.
   - Run a non-production Azure smoke test only after the owner supplies a subscription, region, permitted resources, and explicit deployment approval.

## 7. Security controls

- The worker runs with a managed identity; the FastAPI service has no Terraform binary or Terraform credentials.
- Azure Key Vault is the only secret source. Per-job credentials, if required, are read into process memory only and redacted from command lines, logs, and database rows.
- Terraform state uses a remote encrypted backend with locking. State locations are never returned to the browser.
- Generated IaC is constrained to a schema-validated specification and a fixed provider version; arbitrary Terraform blocks, shell fragments, and user supplied paths are rejected.
- Repository checkout uses isolated workspaces, branch validation, size/time limits, and cleanup in `finally` blocks.
- Apply is gated on an approved specification, a current plan revision, Azure target validation, policy/quota checks, and idempotency/lease ownership.

## 8. Capacity and Azure prerequisites

This code migration provisions no resources, so subscription quotas and Azure Policy cannot be queried yet. Before the first customer deployment, the worker must validate the supplied subscription and region for App Service capacity, PostgreSQL Flexible Server, Storage, Key Vault, Application Insights/Log Analytics, VNet/private endpoints, provider registration, and organization policy. Any failed prerequisite blocks the job before `terraform apply`.

## 9. Validation and acceptance criteria

- FastAPI contains no Terraform command invocation, Terraform file generation, or deployment background task.
- The worker is the only process that runs Terraform, writes Terraform artifacts, and performs Azure provisioning.
- A job cannot apply an unapproved or superseded specification and can be safely retried without duplicate resources.
- Every worker transition is durable, authenticated, redacted, and visible in the deployment timeline.
- No endpoint or UI surface exposes HCL, Terraform plan output, provider credentials, Key Vault values, or state locations.
- Existing GitHub, analysis, plan, deployment, logs, and App Service flows remain functional through compatibility tests.
- Backend tests, Python compilation, frontend lint, and production build pass before each phase is marked complete.

## 10. Files expected to change

| Area | Planned work |
|---|---|
| `backend/models.py`, `database.py`, `schemas.py` | Versioned spec, durable job/event model, safe migrations |
| `backend/services/cloud/` | New provider contracts and Azure implementation |
| `backend/services/analysis.py`, `planner.py` | Structured evidence and validated architecture mutations |
| `backend/services/terraform_generator.py` | Remove control-plane generation responsibility; replace with worker-only generator modules |
| `backend/main.py` | Queue-only deployment APIs, approval/status/event flows, removal of direct pipeline starts |
| `worker/` | Secure executor, generator, provider adapter, event publisher, lifecycle/health handling |
| `src/app/dashboard/*`, `src/components/dashboard/*`, `src/lib/api.ts` | Real architecture and deployment-stage UI without Terraform exposure |
| `backend/tests/`, documentation | Migration, security, contract, and end-to-end coverage plus operator guidance |

## 11. Execution checklist

- [x] Audit repository and identify reusable/obsolete deployment modules.
- [x] Create this implementation plan.
- [ ] Owner approves the plan and confirms that code refactoring may begin.
- [ ] Implement phases 1–6 with tests after each phase.
- [ ] Obtain Azure subscription/region and explicit authorization for any non-production smoke deployment.
- [ ] Validate Azure policy, quota, identity, state backend, and provider registration before any `terraform apply`.

## 12. Next step

Await approval to begin the code refactor. Azure provisioning remains deferred until separately authorized.

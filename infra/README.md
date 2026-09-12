> Configuration update (2026-09-11): Microsoft Foundry is the sole supported AI provider. NVIDIA, Groq, GitHub Models, and their fallback settings below are historical and must not be configured. See [the live repair report](../docs/production-repair-2026-09-11.md).

# ZeroOps Azure execution plane

This directory is a pure Terraform implementation of the approved ZeroOps
enterprise architecture. It has **not** been deployed by Codex. Existing
production resources are read through data sources and are not imported,
recreated, resized, or reconfigured by this root.

## What this root creates

- Four user-assigned managed identities: repository analysis, Terraform
  generation, history projection, and Terraform execution.
- Three separate FC1 Python 3.13 Function Apps, plans, host storage accounts,
  and identities: repository analysis, Terraform generation, and history
  projection. The two AI Functions also have separate model Key Vaults.
  Terraform creates no secrets. NVIDIA primary and Groq fallback credentials
  must be written out of band to four workload-specific secret names.
- Service Bus queues for repository analysis, generation, plan, apply, and
  workflow events. Plan/apply queues use sessions and duplicate detection. The
  backend can send only to the apply queue; the executor can receive only from
  the plan/apply queues and send only workflow events.
- A versioned tenant artifact account and a different executor-only account for
  Terraform state, leases, completion receipts, and saved binary plans.
- A Basic ACR in test or Premium ACR in production, with admin access disabled.
- A regular `Standard_B2as_v2` Uniform VMSS spread across zones 1 and 2 for the
  test profile. It starts at zero, scales from Terraform plan/apply queue depth
  to one, uses a managed Standard SSD, and has a static NAT egress IP with no
  per-VM public IP. Trusted Launch, Secure Boot, and vTPM are set on the initial
  VMSS model; both the Ubuntu base image and worker container are immutable.
  Cloud-init installs a checksum-pinned Docker static bundle and exchanges the
  VMSS managed-identity token directly with ACR, so it neither upgrades moving
  OS packages nor installs Azure CLI on the host.
- VNet integration, private DNS, and production private endpoints, plus Log
  Analytics, Application Insights, Azure Monitor diagnostics, DCR, alerting,
  and an optional resource-group budget.

Existing `zeroopsai`, `zeroops-backend`, `zeroops-db-prod`,
`zeroops-kv-prod`, their App Service plan, and their managed identities are
referenced only. Production adds private endpoints to the existing backend,
PostgreSQL server, and control vault, but deliberately does not switch off
their public endpoints or rewrite app settings. That cutover needs a separately
approved migration after private connectivity is tested.

## Data and authority boundaries

| Identity | Can receive | Can send | Storage | Key Vault |
|---|---|---|---|---|
| Existing backend | none | repository-analysis, Terraform-generation, and approved apply requests | tenant artifacts only | existing control vault remains external |
| Analysis Function | repository analysis | workflow events | tenant artifacts | analysis model vault only |
| Terraform generation Function | Terraform generation | Terraform plan | tenant artifacts | generation model vault only |
| VMSS executor | Terraform plan and apply | workflow events | tenant artifacts plus executor-only plans/state | no model key vault |
| History projector Function | workflow events | none | none | none; PostgreSQL Entra login only |

The backend and AI Functions receive no RBAC on the executor storage account.
Saved `.tfplan` files, Terraform state, and lease blobs therefore cannot be read
through the user-facing application. User history receives only sanitized
action counts, resource kinds, immutable digests, status, and timestamps.
The customer workload scope is explicit and grants the executor Contributor on
one dedicated resource group only. Terraform rejects the platform resource
group and subscription scope. Apply remains bound to the durable, single-use
approval contract and an exact saved plan; the worker receives no general
platform or subscription write role.

## Cost profile

`environments/test.tfvars.example` is the default demonstration profile:
Standard Service Bus, Basic ACR, FC1 Functions, LRS Function host storage, and a
VMSS maximum of one. The executor stays at zero when the plan queue is empty.

`environments/production.tfvars.example` enables private endpoints, Premium
Service Bus/ACR, ZRS storage, longer retention, and a two-instance
`Standard_B2as_v2` VMSS cap. That is the maximum currently deployable runner
capacity for the connected Azure for Students subscription: the existing
validation VM consumes two regional vCPUs and Central India exposes four more.
Raise the cap or change the SKU only after a fresh quota and zone-capacity
check. Premium services are explicit rather than silently enabled in test. The
monthly budget is also explicit and refuses to enable without dates, an amount,
and a receiver.

The regular VMSS uses plan/apply-queue-driven scale-to-zero, a bounded SKU,
lifecycle tiering, FC1 serverless compute, and per-environment caps. Central
India live quota validation selected `Standard_B2as_v2` for test (2 vCPU,
8 GiB); this SKU requires a managed OS disk. No runner VM or disk exists during
the foundation stage or while the VMSS capacity is zero.

## Template composition provenance

The Azure Functions template manifest available to the preparation workflow did
not include a Python + Service Bus Terraform template. The Function module is
therefore a documented composition of:

1. The Azure Functions FC1 AzAPI `functionAppConfig` base pattern.
2. The Python 3.13 runtime required by the packaged Function projects.
3. The Service Bus identity-based connection convention
   (`fullyQualifiedNamespace`, `credential=managedidentity`, and `clientId`).
4. Separate user-assigned identities, Function host storage, model vaults, and
   60-second RBAC propagation gates.

No connection strings, API keys, SAS tokens, storage keys, or secret values are
generated. References:

- [Azure Functions Flex Consumption Terraform quickstart](https://learn.microsoft.com/en-us/azure/azure-functions/functions-create-first-function-terraform)
- [Flex Consumption networking and subnet delegation](https://learn.microsoft.com/en-us/azure/azure-functions/flex-consumption-how-to)
- [Identity-based Azure Functions connections](https://learn.microsoft.com/en-us/azure/azure-functions/functions-reference)
- [Service Bus managed identity authentication](https://learn.microsoft.com/en-us/azure/service-bus-messaging/service-bus-managed-service-identity)
- [Azure Terraform state storage guidance](https://learn.microsoft.com/en-us/azure/developer/terraform/get-started/store-state-in-azure-storage)

## Preparation and validation

Prerequisites that are currently external to this code:

1. Confirm all required providers are registered with explicit authorization.
   `Microsoft.App` is required by Flex Consumption subnet delegation, and
   `Microsoft.Quota` is required only if the generic live quota API is used.
   A previous planning attempt automatically registered 31 subscription
   providers; `providers.tf` now sets
   `resource_provider_registrations = "none"` to prevent any future implicit
   registration. Never unregister providers without an explicit approval.
2. Run the explicit [`bootstrap/`](bootstrap/) sequence to create the separate
   Entra-only state account and federated plan/apply identities. Configure a
   required reviewer on the `azure-test-apply` GitHub environment. The
   temporary validation VM remains read-only and is never reused for release.
3. Use `plan-foundation`, review its sanitized summary and exact plan digest,
   then invoke `apply-saved-plan` with `APPLY <digest>`. This creates the ACR and
   platform with `deploy_runner=false`; it does not accept a fake image digest
   and does not create the VMSS, NAT gateway, or apply-queue send/receive roles.
4. Run `publish-artifacts` with `PUBLISH <commit>`. It pushes the worker image,
   resolves its registry digest, retains versioned Function ZIPs, and deploys
   the Functions through Flex Consumption One Deploy.
5. Use the returned `@sha256:` reference in `plan-runner`, set
   `execution_scope_resource_id` to one dedicated customer workload resource
   group, review the exact plan, then consume it once with
   `apply-saved-plan`. The VMSS model pins Ubuntu `22.04.202608060` and the
   worker digest.
6. Put `ai-repository-api-key` and `ai-repository-fallback-api-key` in the
   analysis vault, and `ai-terraform-api-key` and
   `ai-terraform-fallback-api-key` in the Terraform-generation vault, outside
   Terraform. Their versionless app-setting references are
   `AI_REPOSITORY_API_KEY`, `AI_REPOSITORY_FALLBACK_API_KEY`,
   `AI_TERRAFORM_API_KEY`, and `AI_TERRAFORM_FALLBACK_API_KEY`. A generic
   `GROQ_API_KEY` is not wired. The same Groq value may be entered into both
   fallback secrets only for an explicit local test; production credentials
   must remain independently rotatable.
7. Map the history managed identity to PostgreSQL principal
   `POSTGRES_ENTRA_USER` and grant only the required `operation_runs`,
   `activity_events`, `artifacts`, and tenant membership permissions. Azure
   RBAC cannot create that database-local role without crossing the existing
   database administration boundary.
8. Configure the non-secret GitHub IDs/state names returned by the bootstrap
   output plus the dedicated execution scope and runner SSH public key.

Run locally before any deployment:

```powershell
terraform -chdir=infra fmt -check -recursive
terraform -chdir=infra init -backend=false
terraform -chdir=infra validate
terraform -chdir=infra providers lock -platform=linux_amd64 -platform=windows_amd64
tflint --chdir=infra --recursive
checkov --config-file infra/.checkov.yml --directory infra --framework terraform --var-file infra/environments/production.tfvars.example --compact
```

The deployment workflow escrows a saved binary plan in the separate
`deployment-plans` container, records its SHA-256, validates the commit and
metadata before apply, and deletes it after the first apply attempt. A lifecycle
rule removes abandoned plans after two days. Full plan JSON, state, backend
credentials, and binary plans are never uploaded as GitHub artifacts or logged.

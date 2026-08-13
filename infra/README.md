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
  workflow events. The apply queue is retained as a reserved contract name but
  has no application sender, executor receiver, or autoscale rule in the
  current plan-only phase. Plan/apply queues use sessions and duplicate
  detection.
- A versioned tenant artifact account and a different executor-only account for
  Terraform state, leases, completion receipts, and saved binary plans.
- A Basic ACR in test or Premium ACR in production, with admin access disabled.
- A regular `Standard_D2ads_v5` Flexible VMSS spread across zones 1 and 2. It
  starts at zero, scales from Terraform plan queue depth to one in test or at
  most ten in production, and uses a static NAT egress IP with no per-VM public
  IP.
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
| Existing backend | none | repository-analysis and Terraform-generation requests | tenant artifacts only | existing control vault remains external |
| Analysis Function | repository analysis | workflow events | tenant artifacts | analysis model vault only |
| Terraform generation Function | Terraform generation | Terraform plan | tenant artifacts | generation model vault only |
| VMSS executor | Terraform plan only | workflow events | tenant artifacts plus executor-only plans/state | no model key vault |
| History projector Function | workflow events | none | none | none; PostgreSQL Entra login only |

The backend and AI Functions receive no RBAC on the executor storage account.
Saved `.tfplan` files, Terraform state, and lease blobs therefore cannot be read
through the user-facing application. User history receives only sanitized
action counts, resource kinds, immutable digests, status, and timestamps.
The optional customer workload scope grants the executor Reader, not
Contributor. Apply message contracts and execution code are retained for future
work, but the deployed entry point does not read an apply queue and neither the
backend nor executor identity has apply-queue RBAC.

## Cost profile

`environments/test.tfvars.example` is the default demonstration profile:
Standard Service Bus, Basic ACR, FC1 Functions, LRS Function host storage, and a
VMSS maximum of one. The executor stays at zero when the plan queue is empty.

`environments/production.tfvars.example` enables private endpoints, Premium
Service Bus/ACR, ZRS storage, longer retention, and a VMSS cap of ten. Premium
services are explicit rather than silently enabled in test. The monthly budget
is also explicit and refuses to enable without dates, an amount, and a receiver.

The regular VMSS is intentional so a future, separately authorized apply path
does not require changing the compute safety model. In the current plan-only
phase, the worker uses plan-queue-driven scale-to-zero, ephemeral OS disks, a
bounded SKU, lifecycle tiering, FC1 serverless compute, and per-environment
caps.

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

1. Treat Trusted Launch as a deployment blocker, not as a validated property of
   the current Flexible VMSS. The pinned AzureRM `4.81.0`
   `azurerm_orchestrated_virtual_machine_scale_set` schema has no initial
   security-profile, security-type, Secure Boot, or vTPM fields. The module's
   AzAPI update therefore enables Trusted Launch after creation, a path Azure
   currently classifies as preview for Flexible VMSS. Do not apply until that
   preview is explicitly authorized and verified for the subscription, or the
   VMSS is migrated to an initial-create resource/provider schema that exposes
   the complete security profile.
2. Confirm all required providers are registered with explicit authorization.
   `Microsoft.App` is required by Flex Consumption subnet delegation, and
   `Microsoft.Quota` is required only if the generic live quota API is used.
   A previous planning attempt automatically registered 31 subscription
   providers; `providers.tf` now sets
   `resource_provider_registrations = "none"` to prevent any future implicit
   registration. Never unregister providers without an explicit approval.
3. Bootstrap the separate platform backend account described by
   `backend.hcl.example`, grant the deployment identity data-plane access, and
   copy the example to ignored `backend.hcl`.
4. Replace the SSH public key and IDs in the selected profile.
5. Build `worker/Dockerfile`, push it to the profile ACR, resolve the manifest
   digest, and replace `runner_image_reference`. The reference must end in
   `@sha256:<64 lowercase hex characters>`.
6. Set `execution_scope_resource_id` only to a dedicated customer workload
   resource group. A Terraform check rejects the ZeroOps platform group. The
   current plan-only deployment grants Reader on this scope; it intentionally
   cannot apply changes.
7. Put `ai-repository-api-key` and `ai-repository-fallback-api-key` in the
   analysis vault, and `ai-terraform-api-key` and
   `ai-terraform-fallback-api-key` in the Terraform-generation vault, outside
   Terraform. Their versionless app-setting references are
   `AI_REPOSITORY_API_KEY`, `AI_REPOSITORY_FALLBACK_API_KEY`,
   `AI_TERRAFORM_API_KEY`, and `AI_TERRAFORM_FALLBACK_API_KEY`. A generic
   `GROQ_API_KEY` is not wired. The same Groq value may be entered into both
   fallback secrets only for an explicit local test; production credentials
   must remain independently rotatable.
8. Map the history managed identity to PostgreSQL principal
   `POSTGRES_ENTRA_USER` and grant only the required `operation_runs`,
   `activity_events`, `artifacts`, and tenant membership permissions. Azure
   RBAC cannot create that database-local role without crossing the existing
   database administration boundary.
9. Package and deploy the three Function projects separately.

Run locally before any deployment:

```powershell
terraform -chdir=infra fmt -check -recursive
terraform -chdir=infra init -backend=false
terraform -chdir=infra validate
tflint --chdir=infra --recursive
checkov --config-file infra/.checkov.yml --directory infra --framework terraform --var-file infra/environments/production.tfvars.example --compact
```

For a real plan, initialize with `-backend-config=backend.hcl` and use a copied,
ignored tfvars file. Save the exact plan. Applying it is not permitted in the
current phase; the isolated VMSS only produces plan evidence:

```powershell
terraform -chdir=infra plan -out=platform.tfplan -var-file=environments/test.tfvars
```

Never publish `backend.hcl`, `.tfstate`, `.tfplan`, plan JSON, or `terraform
show` output. The repository-specific `.gitignore` blocks these file types.

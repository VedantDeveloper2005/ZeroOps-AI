# ZeroOps Azure Functions

Three Python 3.13 Flex Consumption Function apps implement the asynchronous
trust boundaries:

| Project | Trigger queue | Identity boundary |
|---|---|---|
| `repository_analysis` | `repo-analysis` | Tenant artifacts, workflow events, repository model vault only |
| `terraform_generation` | `terraform-generation` | Tenant artifacts, plan queue/events, Terraform model vault only |
| `history_projector` | `workflow-events` | PostgreSQL Entra login only |

`common/zeroops_functions` is packaged into each Function deployment artifact.
It contains versioned ID-only queue contracts, managed-identity Blob and Service
Bus adapters, strict structured inference, digest verification, and redaction.
`ai_contracts.py` is a packaging-verified mirror of
`backend/contracts/ai.py`; Functions never import the backend application.

## Packaging contract

Each deployment ZIP must have this layout at its root:

```text
function_app.py
handler.py
host.json
requirements.txt
zeroops_functions/
prompts/
  instructions.md
```

For `repository_analysis`, copy
`ai-specs/repository-analysis/instructions.md` to `prompts/instructions.md`.
For `terraform_generation`, copy
`ai-specs/terraform-generation/instructions.md` instead and include the
application-owned `terraform.lock.hcl` runtime asset. The model cannot supply or
modify that lock. The history projector has no model prompt.

The CI package step must also copy `common/zeroops_functions` into each staging
root. Do not deploy the repository root as a Function app.

Build all three deterministic ZIPs with:

```text
python scripts/generate_ai_schemas.py --check
python scripts/package_functions.py --output dist/functions
```

Packaging fails when the Function contract mirror or generated response schemas
have drifted from the canonical backend contracts.

The repository-analysis evidence artifact must contain exactly
`RepositoryAnalysisRequest`. The approved-plan artifact must contain exactly
`TerraformGenerationRequest`; its Blob digest and the request's approved-plan
digest are separate integrity values. Unknown fields, secret-bearing properties,
identity mismatches, and stale revisions fail before model inference.

A generated Terraform result is written twice for different purposes:

- a canonical JSON audit artifact records model provenance, files, cost
  optimizations, and the not-yet-run validation state;
- a deterministic executor ZIP contains only validated root `.tf` files and the
  trusted `.terraform.lock.hcl`.

Both use the tenant container/path contract
`t-<40 hex>/objects/<artifact UUID>/v1/<SHA-256>`. The plan queue receives the
VMSS `ExecutionEnvelope` schema `1.0`, never Terraform source. Its immutable
digest binds the user, tenant, project, workflow, target subscription/tenant,
state key, Terraform `1.15.8`, bundle URI, ETag, digest, and size. Plan messages
use the workflow UUID as their Service Bus session ID. A blocked generation is
audited but is never enqueued.

## Required managed-identity settings

All apps:

```text
APP_ENV=production
AZURE_CLIENT_ID=<that Function's UAMI client ID>
AzureWebJobsStorage__credential=managedidentity
AzureWebJobsStorage__clientId=<same UAMI client ID>
AzureWebJobsStorage__blobServiceUri=https://<host-storage>.blob.core.windows.net
AzureWebJobsStorage__queueServiceUri=https://<host-storage>.queue.core.windows.net
AzureWebJobsStorage__tableServiceUri=https://<host-storage>.table.core.windows.net
ServiceBusConnection__fullyQualifiedNamespace=<namespace>.servicebus.windows.net
ServiceBusConnection__credential=managedidentity
ServiceBusConnection__clientId=<same UAMI client ID>
SERVICEBUS_FULLY_QUALIFIED_NAMESPACE=<namespace>.servicebus.windows.net
APPLICATIONINSIGHTS_CONNECTION_STRING=<Application Insights connection string>
APPLICATIONINSIGHTS_AUTHENTICATION_STRING=Authorization=AAD;ClientId=<same UAMI client ID>
WORKFLOW_EVENTS_QUEUE_NAME=workflow-events
```

History projector additionally requires:

```text
POSTGRES_HOST=<server>.postgres.database.azure.com
POSTGRES_PORT=5432
POSTGRES_DATABASE=<database>
POSTGRES_ENTRA_USER=<database principal mapped to the Function identity>
POSTGRES_SSL_MODE=verify-full
```

Repository analysis:

```text
REPOSITORY_ANALYSIS_QUEUE_NAME=repo-analysis
ARTIFACT_STORAGE_ACCOUNT_URL=https://<artifact-account>.blob.core.windows.net
AI_REPOSITORY_PROVIDER=nvidia
AI_REPOSITORY_ENDPOINT=https://integrate.api.nvidia.com/v1
AI_REPOSITORY_MODEL=z-ai/glm-5.2
AI_REPOSITORY_API_KEY=<Key Vault reference resolved by the Function platform>
AI_REPOSITORY_PROMPT_VERSION=repository-analysis.v1
```

`AI_REPOSITORY_API_KEY` is a versionless reference to the
`ai-repository-api-key` secret in the repository-analysis Key Vault.

Terraform generation:

```text
TERRAFORM_GENERATION_QUEUE_NAME=terraform-generation
TERRAFORM_PLAN_QUEUE_NAME=terraform-plan
ARTIFACT_STORAGE_ACCOUNT_URL=https://<artifact-account>.blob.core.windows.net
AI_TERRAFORM_PROVIDER=nvidia
AI_TERRAFORM_ENDPOINT=https://integrate.api.nvidia.com/v1
AI_TERRAFORM_MODEL=z-ai/glm-5.2
AI_TERRAFORM_API_KEY=<a different Key Vault reference>
AI_TERRAFORM_PROMPT_VERSION=terraform-generation.v1
```

`AI_TERRAFORM_API_KEY` is a versionless reference to the
`ai-terraform-api-key` secret in the Terraform-generation Key Vault. The two
workers use different managed identities and cannot read each other's vault.
There is no shared-key or automatic provider fallback.

The VMSS never receives either model setting or Key Vault permission.

## Local tests

Tests use in-memory adapters and never call Azure or a model:

```text
python -m unittest discover -s functions/tests -v
```

Install the pinned Function requirements into an isolated virtual environment
before running them.

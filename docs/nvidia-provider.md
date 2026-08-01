# NVIDIA Build API Provider

ZeroOps AI supports the [NVIDIA Build](https://build.nvidia.com/) hosted
inference API as a structured AI provider for repository analysis and Terraform
generation. The endpoint is OpenAI-compatible, so the existing OpenAI Python
SDK is used for transport.

## Architecture

```
ModelGateway
  └── build_provider("nvidia")
        └── NvidiaProvider
              └── OpenAI(base_url="https://integrate.api.nvidia.com/v1")
```

**NvidiaProvider** (`backend/services/providers/nvidia.py`) follows the
provider-neutral contract defined in `base.py`. The gateway retains full
authority over:

- JSON parsing and Pydantic validation
- The single repair attempt
- Repository analysis graceful degradation
- Terraform generation fail-closed policy
- All Terraform safety checks (`fmt`, `validate`, `plan`, policy, approval)

The provider never executes AI output directly and never allows model output to
trigger deployments.

---

## Configuration

### Environment Variables / Key Vault Secrets

The two production workers have separate user-assigned identities and separate
Key Vaults. Terraform wires versionless references to these workload-specific
secrets:

| Worker | Environment variable | Dedicated vault secret | Value |
|---|---|---|---|
| Repository analysis | `AI_REPOSITORY_API_KEY` | `ai-repository-api-key` | *(repository-route NVIDIA key)* |
| Terraform generation | `AI_TERRAFORM_API_KEY` | `ai-terraform-api-key` | *(Terraform-route NVIDIA key)* |

Each worker receives only its own non-secret route settings:

| Environment variable | Value |
|---|---|
| `AI_REPOSITORY_PROVIDER` | `nvidia` |
| `AI_REPOSITORY_ENDPOINT` | `https://integrate.api.nvidia.com/v1` |
| `AI_REPOSITORY_MODEL` | `z-ai/glm-5.2` |
| `AI_TERRAFORM_PROVIDER` | `nvidia` |
| `AI_TERRAFORM_ENDPOINT` | `https://integrate.api.nvidia.com/v1` |
| `AI_TERRAFORM_MODEL` | `z-ai/glm-5.2` |

> **Important:** `AI_REPOSITORY_API_KEY` and `AI_TERRAFORM_API_KEY` are
> workload-specific. They do not inherit from `NVIDIA_API_KEY` silently. Set
> them explicitly so each workload's credential can be rotated independently in
> production. For a small local demo the two vault secrets may temporarily hold
> the same NVIDIA key value, but the settings and access boundaries remain
> separate. Production must use two distinct credentials so either workload can
> be revoked and rotated independently. `NVIDIA_API_KEY` is used only by the
> opt-in local smoke script.

### Application Guardrails

These are ZeroOps request budgets, not NVIDIA service quotas or a promise of
free or unlimited usage. Hosted NVIDIA Build access should be treated as a
prototype/trial route: available credits and rate limits vary by account and
model. A production service needs an appropriate supported NVIDIA subscription
or model deployment, plus measured quota and capacity before promotion.

| Parameter | Repository analysis | Terraform generation |
|---|---|---|
| Max input characters | 40,000 | 40,000 |
| Max output tokens | 1,600 | 4,000 |
| Hidden SDK retries | 0 | 0 |
| Gateway repair attempts | 1 | 1 |
| Temperature | 0.0 | 0.0 |

---

## Security Requirements

- The API key is **never** printed, logged, included in error messages, or
  exposed in API responses. `ProviderConfiguration` marks `api_key` with
  `repr=False` and `NvidiaProvider` never formats it.
- SDK exceptions are caught and converted to the safe message
  `"NVIDIA inference failed."` — the upstream exception text is never surfaced.
- `.env` files, credentials, certificates, tokens, and connection strings are
  excluded from model context.
- Repository contents and log text are treated as untrusted prompt input.
- AI-generated Terraform is never executed automatically.

---

## Local Smoke Test

Read your API key from the environment, then run:

```powershell
# PowerShell
$env:APP_ENV = "test"
$env:NVIDIA_API_KEY = "<NVIDIA_API_KEY>"
python scripts/test_nvidia_provider.py
```

```bash
# bash
APP_ENV=test NVIDIA_API_KEY="<NVIDIA_API_KEY>" python scripts/test_nvidia_provider.py
```

Expected output:

```
Endpoint : https://integrate.api.nvidia.com/v1
Model    : z-ai/glm-5.2
API key  : [set, not printed]

Sending request to NVIDIA Build API …
Response received in <N> ms
Model    : z-ai/glm-5.2
Tokens   : <N> in / <N> out

=== Repository Analysis Smoke Test Result ===
Explanation       : ...
Deployment risk   : ...
Recommendations   : [...]
Unresolved        : [...]

PASS — NVIDIA provider is reachable and returns a valid structured response.
```

---

## Unit Tests

```powershell
# From the repository root
python -m pytest backend/tests/test_nvidia_provider.py backend/tests/test_model_gateway.py -v
python -m unittest functions.tests.test_function_contracts.ModelClientTests -v
```

All tests use a mocked OpenAI client. No test calls the real NVIDIA API.

---

## Production Worker Restart

After rotating either Key Vault secret, restart only the matching Function App
so its versionless Key Vault reference is refreshed:

```bash
az functionapp restart \
  --name <repository-analysis-function-name> \
  --resource-group <resource-group>
```

```bash
az functionapp restart \
  --name <terraform-generation-function-name> \
  --resource-group <resource-group>
```

---

## Alternate Provider: GitHub Models

GitHub Models (`github-models`) remains an explicitly configurable provider,
but it is no longer the default route. Provider selection never triggers an
automatic credential fallback.

To re-enable GitHub Models for a specific workload, set:

```
AI_REPOSITORY_PROVIDER=github-models
AI_REPOSITORY_ENDPOINT=https://models.github.ai/inference
AI_REPOSITORY_API_KEY=<github-pat>
AI_REPOSITORY_MODEL=openai/gpt-4o
```

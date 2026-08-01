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

All settings follow the `zeroops-<kebab-case>` Key Vault naming convention.

| Environment Variable | Key Vault Secret Name | Example Value |
|---|---|---|
| `NVIDIA_API_KEY` | `zeroops-nvidia-api-key` | *(your NVIDIA Build key)* |
| `NVIDIA_ENDPOINT` | `zeroops-nvidia-endpoint` | `https://integrate.api.nvidia.com/v1` |
| `NVIDIA_MODEL` | `zeroops-nvidia-model` | `z-ai/glm-5.2` |
| `AI_REPOSITORY_PROVIDER` | `zeroops-ai-repository-provider` | `nvidia` |
| `AI_REPOSITORY_ENDPOINT` | `zeroops-ai-repository-endpoint` | `https://integrate.api.nvidia.com/v1` |
| `AI_REPOSITORY_MODEL` | `zeroops-ai-repository-model` | `z-ai/glm-5.2` |
| `AI_REPOSITORY_API_KEY` | `zeroops-ai-repository-api-key` | *(your NVIDIA Build key)* |
| `AI_TERRAFORM_PROVIDER` | `zeroops-ai-terraform-provider` | `nvidia` |
| `AI_TERRAFORM_ENDPOINT` | `zeroops-ai-terraform-endpoint` | `https://integrate.api.nvidia.com/v1` |
| `AI_TERRAFORM_MODEL` | `zeroops-ai-terraform-model` | `z-ai/glm-5.2` |
| `AI_TERRAFORM_API_KEY` | `zeroops-ai-terraform-api-key` | *(your NVIDIA Build key)* |

> **Important:** `AI_REPOSITORY_API_KEY` and `AI_TERRAFORM_API_KEY` are
> workload-specific. They do not inherit from `NVIDIA_API_KEY` silently. Set
> them explicitly so each workload's credential can be rotated independently in
> production.

### Free Prototype Endpoint Limits

| Parameter | Repository analysis | Terraform generation |
|---|---|---|
| Max input characters | 40,000 | 40,000 |
| Max output tokens | 1,600 | 4,000 |
| Concurrency | 1 | 1 |
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
cd "d:\ZeroOps AI\backend"
python -m pytest tests/test_nvidia_provider.py tests/test_model_gateway.py -v
```

All tests use a mocked OpenAI client. No test calls the real NVIDIA API.

---

## Production Restart Command

After updating Key Vault secrets, restart the backend App Service:

```bash
az webapp restart --name <app-service-name> --resource-group <resource-group>
```

Or for Container Apps:

```bash
az containerapp revision restart \
  --name <container-app-name> \
  --resource-group <resource-group> \
  --revision <revision-name>
```

---

## Provider Retirement — GitHub Models

GitHub Models (`github-models`) has been retired as the active default testing
route. It remains importable for backward compatibility with existing test
fixtures but must not be configured as an active provider. The defaults in
`config.py` now point to the NVIDIA provider.

To re-enable GitHub Models for a specific workload, set:

```
AI_REPOSITORY_PROVIDER=github-models
AI_REPOSITORY_ENDPOINT=https://models.github.ai/inference
AI_REPOSITORY_API_KEY=<github-pat>
AI_REPOSITORY_MODEL=openai/gpt-4o
```

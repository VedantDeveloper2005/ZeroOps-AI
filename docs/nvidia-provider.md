# NVIDIA Build API Provider

ZeroOps AI supports the [NVIDIA Build](https://build.nvidia.com/) hosted
inference API as a structured AI provider for repository analysis and Terraform
generation. The endpoint is OpenAI-compatible, so the existing OpenAI Python
SDK is used for transport.

Each workload also has one explicit backup route through Groq's exact
`https://api.groq.com/openai/v1` endpoint and `openai/gpt-oss-120b` model. It is
selected only after an eligible NVIDIA availability or structured-contract
failure and never shares a credential across workloads.

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
| Repository analysis fallback | `AI_REPOSITORY_FALLBACK_API_KEY` | `ai-repository-fallback-api-key` | *(repository-route Groq key)* |
| Terraform generation | `AI_TERRAFORM_API_KEY` | `ai-terraform-api-key` | *(Terraform-route NVIDIA key)* |
| Terraform generation fallback | `AI_TERRAFORM_FALLBACK_API_KEY` | `ai-terraform-fallback-api-key` | *(Terraform-route Groq key)* |

Each worker receives only its own non-secret route settings:

| Environment variable | Value |
|---|---|
| `AI_REPOSITORY_PROVIDER` | `nvidia` |
| `AI_REPOSITORY_ENDPOINT` | `https://integrate.api.nvidia.com/v1` |
| `AI_REPOSITORY_MODEL` | `z-ai/glm-5.2` |
| `AI_REPOSITORY_FALLBACK_PROVIDER` | `groq` |
| `AI_REPOSITORY_FALLBACK_ENDPOINT` | `https://api.groq.com/openai/v1` |
| `AI_REPOSITORY_FALLBACK_MODEL` | `openai/gpt-oss-120b` |
| `AI_TERRAFORM_PROVIDER` | `nvidia` |
| `AI_TERRAFORM_ENDPOINT` | `https://integrate.api.nvidia.com/v1` |
| `AI_TERRAFORM_MODEL` | `z-ai/glm-5.2` |
| `AI_TERRAFORM_FALLBACK_PROVIDER` | `groq` |
| `AI_TERRAFORM_FALLBACK_ENDPOINT` | `https://api.groq.com/openai/v1` |
| `AI_TERRAFORM_FALLBACK_MODEL` | `openai/gpt-oss-120b` |

> **Important:** `AI_REPOSITORY_API_KEY` and `AI_TERRAFORM_API_KEY` are
> workload-specific. They do not inherit from `NVIDIA_API_KEY` silently. Set
> them explicitly so each workload's credential can be rotated independently in
> production. For a small local demo the two vault secrets may temporarily hold
> the same NVIDIA key value, but the settings and access boundaries remain
> separate. Production must use two distinct credentials so either workload can
> be revoked and rotated independently. `NVIDIA_API_KEY` is used only by the
> opt-in local smoke script.

The fallback variables are equally workload-specific. They never inherit from
`GROQ_API_KEY`, a primary route, or the other workload. For an explicit local
demo, both fallback secret names may be populated with the same test value;
production uses separately rotatable credentials.

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

The Groq backup is intentionally smaller: repository analysis uses 14,000
input characters and 800 output tokens, while Terraform generation uses 14,000
input characters and 1,000 output tokens. Each Groq route gets one strict JSON
Schema request and no repair call. Oversized input and deterministic policy
violations do not trigger fallback.

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
- `GROQ_API_KEY` is not read. Each workload resolves only its dedicated
  fallback Key Vault reference. The two fallback secrets may contain the same
  value only when a local tester sets both explicitly; production keys remain
  independently rotatable.

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

## Explicit Groq backup

Only an eligible NVIDIA availability or structured-output failure can select
the workload-local Groq route. The selected route and safe failure codes are
persisted with model provenance. Repository analysis degrades to deterministic
scanner evidence after both routes fail. Terraform generation fails closed,
enqueues no plan after both routes fail, and never bypasses validation, VMSS
isolation, or the separate human-approval gate before any future apply.

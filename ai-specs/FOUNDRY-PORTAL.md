# Microsoft Foundry configuration

ZeroOps uses the retained `zeroops-architecture-advisor` agent, version `3`, in
project `zeroops-aitest`. The `demo` agent was deleted by the user and its absence
was verified in Foundry on September 13, 2026. Do not recreate it or configure
NVIDIA, Groq, or GitHub Models as runtime providers.

## Live backend route

```text
FOUNDRY_PROJECT_ENDPOINT=https://zeroops-aitest-resource.services.ai.azure.com/api/projects/zeroops-aitest
FOUNDRY_AGENT_NAME=zeroops-architecture-advisor
FOUNDRY_AGENT_VERSION=3
```

The deployment uses the existing backend managed identity and cross-tenant
federation into Mohit's tenant. The agent-bound Responses client must use
`AIProjectClient(allow_preview=True)` and `get_openai_client(agent_name=...)`.
Project-wide Responses requests are not an equivalent authorization path.
The pinned SDK is `azure-ai-projects==2.1.0`.

The historical `ZEROOPS_DEMO_AI` setting selects the unified real Foundry route;
it does not authorize fabricated output or the development repository executor.
Production must keep `ZEROOPS_DEMO_EXECUTOR=false`.

Canonical retained-agent instructions are in
[foundry-advisor-instructions.txt](../docs/foundry-advisor-instructions.txt).
They cover analysis, architecture, chat, failure investigation, security,
Terraform generation and deployment guidance. Web/file search tools remain
attached; their use and returned citations must be reported from actual calls.
The model must never execute deployments or manufacture execution evidence.

## Isolated workload integration status

The Function packages now support the retained prompt agent with
`AI_REPOSITORY_PROVIDER=azure-foundry` and `AI_TERRAFORM_PROVIDER=azure-foundry`.
Set each workload's endpoint to the project URL above, and grant its own managed
identity the required project access. No API key is needed for this route.
The agent route performs real inference and validates structured output before
creating an immutable Terraform bundle. Partial responses fail closed.
The older Azure OpenAI route retains the deterministic App Service renderer.

The adapter passed a live agent connectivity test. Production Function deployment,
application-worker integration and full release verification remain in progress.
A Docker repository executor has been added with disposable, network-disabled
containers; it still needs live verification and integration with prepared images.

## Application invocation contract

- Repository input must conform to `RepositoryAnalysisRequest` and contain
  deterministic facts, bounded safe excerpts, an immutable commit SHA, and
  opaque tenant/project IDs.
- Terraform input must conform to `TerraformGenerationRequest`, have
  `plan_status=approved`, and include the immutable plan revision and SHA-256.
- Model output is accepted only after runtime Pydantic validation.
- Terraform output then passes deterministic source-policy validation,
  `terraform fmt`, `terraform init -backend=false`, `terraform validate`,
  lint/security checks, a saved plan, plan JSON comparison, verified pricing
  checks, and human approval before any apply.

## Evaluation and promotion gate

Require all of the following before promoting a new agent version:

- 100% JSON-schema validity.
- Zero secret or credential leakage.
- Zero instruction-following from repository or plan content.
- Zero invented numerical prices without a supplied verified pricing snapshot.
- Repository conclusions reference supplied evidence or remain unresolved.
- Terraform resources exactly match approved components and resource types.
- Zero forbidden provisioners, shell commands, public-network defaults, or
  privileged role assignments.
- Token and latency measurements remain inside the workload budget.

Use Foundry task-adherence and groundedness/relevance evaluators for quality,
plus deterministic validators for schema, secret leakage, Terraform safety,
resource parity, and pricing claims. An LLM judge is never a deployment safety
gate.

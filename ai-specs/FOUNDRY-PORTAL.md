# Microsoft Foundry portal and import guide

Use two separate prompt agents in the ZeroOps Foundry project.

| Agent | Suggested name | Canonical assets |
|---|---|---|
| Repository analysis | `zeroops-repository-analyst` | `repository-analysis/instructions.md`, `repository-analysis/response.foundry.schema.json` |
| Terraform generation | `zeroops-terraform-generator` | `terraform-generation/instructions.md`, `terraform-generation/response.foundry.schema.json` |

Do not combine these into a single general-purpose agent. Separation provides
independent access control, model selection, evaluation, quota, rotation, and
incident containment.

## Portal setup

For each agent:

1. Create a prompt agent in the intended Foundry project.
2. Choose a model deployment that supports strict structured JSON output.
3. Paste the complete matching `instructions.md` into Agent instructions.
4. Configure Text format as JSON Schema and paste the complete matching
   `response.foundry.schema.json`. The application retains
   `response.schema.json` for richer runtime validation.
5. Do not attach Code Interpreter, File Search, web search, Azure action, shell,
   MCP, or deployment tools. The agents only transform bounded input to
   bounded JSON.
6. Disable agent memory for application traffic. Invoke each request as an
   isolated operation; ZeroOps owns tenant history.
7. Enable Application Insights tracing, but record identifiers, model/version,
   token counts, latency, validation status, and error codes only. Do not
   export repository contents, Terraform source, secrets, or raw prompts to
   telemetry.
8. Create an evaluation using the matching `evaluation.dataset.jsonl`. Map
   `query` to the user input and use `expected_behavior`, `must_include`, and
   `must_not_include` in deterministic/custom evaluators.

Repository content and approved-plan JSON are untrusted request data. Never
interpolate them into persistent agent instructions or saved workflow
variables. Structured inputs may carry trusted, non-secret values such as
`prompt_version` or `policy_version`; they must not carry source code, access
tokens, SAS URLs, connection strings, or tenant display names.

## Runtime configuration

During GitHub Models testing, keep the two independent setting groups:

```text
AI_REPOSITORY_PROVIDER=github-models
AI_REPOSITORY_ENDPOINT=https://models.github.ai/inference
AI_REPOSITORY_MODEL=openai/gpt-4o
AI_REPOSITORY_API_KEY=<Key Vault secret>

AI_TERRAFORM_PROVIDER=github-models
AI_TERRAFORM_ENDPOINT=https://models.github.ai/inference
AI_TERRAFORM_MODEL=openai/gpt-4.1
AI_TERRAFORM_API_KEY=<different Key Vault secret>
```

After the managed identity Foundry runtime adapter is deployed for the
workload, use these settings and leave both API-key settings empty:

```text
AI_REPOSITORY_PROVIDER=azure-foundry
AI_REPOSITORY_ENDPOINT=https://<account>.ai.azure.com/api/projects/<project>
AI_REPOSITORY_AGENT_NAME=zeroops-repository-analyst

AI_TERRAFORM_PROVIDER=azure-foundry
AI_TERRAFORM_ENDPOINT=https://<account>.ai.azure.com/api/projects/<project>
AI_TERRAFORM_AGENT_NAME=zeroops-terraform-generator
```

Grant each workload identity only the Foundry role required to invoke its own
agent. The API, Terraform VMSS, and the other AI workload must not be able to
read that workload's GitHub Models credential.

The current Azure Function client intentionally fails closed for any provider
other than `github-models`. Creating the portal agents does not authorize a
runtime switch; promote the managed-identity adapter and pass its regression
suite before changing either provider setting.

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

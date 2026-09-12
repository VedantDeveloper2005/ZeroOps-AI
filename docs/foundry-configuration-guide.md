> Configuration update (2026-09-11): Microsoft Foundry is the sole supported AI provider. NVIDIA, Groq, GitHub Models, and their fallback settings below are historical and must not be configured. See [the live repair report](production-repair-2026-09-11.md).

# ZeroOps AI: Microsoft Foundry configuration guide

Prepared: 2026-09-10. Scope: configuration advice and knowledge documents; no application feature, Azure setting, or deployed agent was changed.

## 1. The recommendation for this application

Treat infrastructure advice and Terraform generation as different responsibilities.

1. Keep the existing repository analyst and Terraform generator bounded by their current instructions and JSON contracts.
2. For a document-aware architecture/cost assistant, use an advisory Foundry prompt agent with File Search. This is a proposed portal/advisory setup, not an implemented ZeroOps feature.
3. Give that advisory agent optional public-documentation Web Search. Obtain actual resource inventory, utilization, prices, and billing from authenticated, read-only application integrations or supplied snapshots.
4. Pass a reviewed, immutable plan to the Terraform generator. A document or search result must never authorize a change to an approved plan.

I interpret “terra” as the Terraform-generation workload. The actual model/deployment named Terra, if that is what you mean, has not been identified. Use the deployment name shown in your Foundry project; do not infer model capabilities from its nickname.

## 2. What the current code actually supports

These observations describe the local source inspected on 2026-09-10, not verified deployed Azure settings.

| Route | Local implementation | Will portal agent knowledge/tools reach this route? |
|---|---|---|
| `azure-openai`, including alias `foundry-openai` | `backend/services/providers/azure_openai.py`: direct Responses API call with a deployment name and API key | No. This implementation sends no agent reference, File Search configuration, vector-store IDs, or web tools. |
| `azure-foundry` with an agent name | `backend/services/providers/azure_foundry.py`: project client, Entra credentials, Responses API `agent_reference` | Agent configuration can apply, subject to model/tool compatibility and actual runtime verification. Existing product policy currently excludes these tools. |
| `azure-foundry` with only a model name | Same backend provider, direct model request | No attached agent is referenced. It does not add tools itself. |
| Azure Functions structured inference | `functions/common/zeroops_functions/model_client.py` supports the Azure OpenAI direct route | This client does not implement `azure-foundry` agent invocation. Setting that provider is not a complete migration. |

Both backend providers extract response text and basic usage. They do not expose a complete retrieval-citation/tool-call trace through `ProviderResponse`. Portal retrieval success alone therefore does not establish end-to-end knowledge use in ZeroOps.

The local defaults in `backend/config.py` still name NVIDIA. Environment/deployment settings can override them; this review did not read private `.env` files or verify live settings. Check the effective provider, endpoint shape, deployment name, and safe routing provenance for the process that actually handles each workload.

The existing [portal guide](../ai-specs/FOUNDRY-PORTAL.md) explicitly excludes File Search, Web Search, Code Interpreter, shell, MCP, and deployment tools for the two production JSON agents. The new advisory materials do not replace those contracts.

## 3. Which options to enable

| Foundry capability | Existing repository/Terraform agents | Proposed architecture/cost advisory agent | Reason |
|---|---|---|---|
| Correct workload instructions | On | On: use the advisory instructions file | Establish behavior and boundaries. |
| Strict JSON Schema | On: keep existing matching schema | Only if a consumer has an agreed schema | An advisory report is not a valid Terraform bundle. |
| File Search / uploaded documents | Off under current contract | On | Retrieve this master note and curated organization standards. |
| Azure AI Search | Off | Optional alternative for an existing managed knowledge index | Useful for a larger maintained corpus; access controls must be enforced by the system. |
| Web Search | Off | Optional, for current public documentation | It cannot see your Azure subscription utilization or private bill. |
| Grounding with Bing / Bing Custom Search | Off | Use the relevant alternative if required by your portal/API, or domain restriction | Do not enable multiple web tools without a specific reason. |
| Read-only functions/OpenAPI/MCP | Off | Later, only for implemented, authenticated, scoped APIs | Supplies authoritative inventory, metrics, prices, and costs. Tool definitions alone do not implement an API. |
| Code Interpreter | Off | Off initially; optional for sanitized data exploration | Cost arithmetic should have a reproducible calculator; interpreter output is not deployment validation. |
| Shell, browser/computer actions, Terraform apply, Azure write tools | Off | Off | Advice must not silently execute changes. |
| Cross-session agent memory | Off | Off initially | Keep tenant facts scoped to the authenticated request and approved storage. |
| Guardrails / content filtering | On | On | Retain applicable safety controls and test legitimate code/security inputs. |
| Prompt Shields | Enable supported controls and evaluate | Enable supported user/indirect-attack controls and evaluate | Retrieved documents and repository text are untrusted input. |
| Tracing/monitoring | On, sanitized | On, sanitized | Measure model, token use, latency, routing, retrieval, and validation. |
| Evaluation | On before promotion | On before relying on recommendations | Check evidence use, sizing, prices, and unsupported-feature claims. |

Microsoft documents File Search as retrieval over uploaded, indexed documents, and Azure AI Search as an alternative for existing indexes. File Search has additional charges. [File Search documentation](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/file-search).

Current Foundry Web Search supports public web grounding; general search and domain-restricted Bing Custom Search have different configurations. Prefer official Microsoft and HashiCorp documentation. A prompt saying “only search these sites” is not an enforced domain restriction. Web grounding has separate charges and data-processing terms; never send repository source, secrets, private names, or customer configuration in public search queries. [Web Search documentation](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/web-search).

Guardrail availability and intervention points depend on the model/API configuration. Detection complements application authorization, schema validation, and deterministic policy checks. [Configure Foundry guardrails](https://learn.microsoft.com/en-us/azure/ai-foundry/guardrails/how-to-create-guardrails?view=foundry).

## 4. How to use the supplied files

For an advisory agent in Foundry:

1. Select the intended project and a model deployment supporting the needed tool/API combination. Use its exact deployment name.
2. Create or select an advisory prompt agent. Suggested name: `zeroops-architecture-advisor`. Do not substitute it for `zeroops-terraform-generator` in application settings.
3. Paste [the advisory instructions](foundry-advisor-instructions.txt) into the agent's Instructions field.
4. Under the agent's knowledge/tools area, attach File Search and upload [the master note](zeroops-ai-knowledge-master.md). A `.txt` copy is also supplied if preferred by your upload UI.
5. Wait for ingestion/indexing to complete. Confirm the resulting vector store is attached to the agent/version you invoke.
6. Optionally add public Web Search after configuring its data policy and supported restrictions. Use generic product/SKU queries only.
7. Save/publish the agent version using the workflow offered by your portal. Record the actual version in your release notes.
8. Ask questions from the acceptance set in the master note. Inspect retrieved passages/file citations as well as the answer.
9. Verify the same invocation path from the application before claiming that the application uses this knowledge. Today the direct model route will not use this portal configuration.

Portal labels vary across Foundry experiences. Uploading a document to a project alone is insufficient; it must be indexed and connected to the invoked agent/tool. Retrieval supplies context at request time; uploading is not model fine-tuning. The supported upload/index/attach workflow is described in [Microsoft's File Search guide](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/file-search).

Use one copy of the master note, Markdown OR text, to avoid duplicate retrieval results. Do not upload secrets, `.env`, Terraform state, raw customer repositories, or an unredacted subscription export into a shared knowledge store.

## 5. Model and inference settings

These are starting policies, not values verified against your deployment. Keep current application contracts until evaluated changes are approved.

| Setting | Suggested policy |
|---|---|
| Model | Use the least costly deployed model that passes your workload evaluation. Evaluate a stronger model for Terraform correctness if the smaller one fails. |
| Deployment type | Start with a supported pay-as-you-go Standard variant compatible with residency needs. Consider provisioned capacity only after measuring a stable baseline and break-even cost. |
| Temperature | For an advisory model that supports it, 0–0.2 is a reasonable starting range. Omit unsupported parameters. The inspected Azure providers do not forward a temperature setting. |
| Reasoning effort | Use a supported moderate setting for advisory analysis; measure more demanding settings for complex generation. This is model-specific, and no new control was wired into the application. |
| Repository output | Current backend default: 1,600 tokens. Preserve its bounded JSON contract. |
| Terraform output | Current backend default: 4,000 tokens. Check realistic bundle sizes for truncation; raise only with evaluation and cost/latency review. Never accept partial JSON/HCL. |
| Advisory report output | Start around 3,000–5,000 output tokens if supported; request one scoped decision per call. This is separate from existing workload settings. |
| Input budget | Existing workload default: 40,000 characters, including prompt/schema overhead in the provider. Characters are not tokens. Do not paste the entire master note into every request. |
| Retrieval | Begin with service defaults; evaluate whether relevant sections are retrieved. For a custom retriever, an initial 4–8 short passages is a tunable experiment, not a native setting promised for every Foundry tool. |
| Concurrency | For an initial advisory rehearsal, 1–2 concurrent requests per deployment, then increase against measured RPM/TPM and latency. Enforce tenant limits in application code. |
| Timeout | Existing backend setting defaults to 30 seconds; Functions client defaults to 45 seconds unless overridden. Tool use may need a different measured budget. |
| Retries | Preserve bounded workload-local retry/fallback rules. Respect 429 retry information and do not retry policy violations. |
| Logging | Record safe identifiers, model/deployment, prompt/KB version, token use, latency, failure codes, and evidence IDs. Avoid raw prompts/source/secrets. |

Approximate quota planning example: 6 requests/minute × 7,000 combined tokens/request × 1.5 headroom = 63,000 TPM as an initial demand estimate. This is not a guaranteed Azure capacity assignment. Azure's enforcement may estimate tokens using requested output limits; RPM-to-TPM ratios vary by model and deployment type. Confirm both quotas and load-test. [Quota documentation](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/quota).

For normal managed Azure OpenAI inference, you choose a model/deployment and throughput limits, not the model server's CPU/RAM. The CPU/RAM tables in the master note concern applications, databases, and workers. Hosted agents or self-hosted models introduce separate compute sizing.

## 6. Integrating knowledge into ZeroOps later

There are two design choices; neither was implemented by this documentation task:

- Keep direct model calls and retrieve curated passages in the application, supplying them as bounded reference data. Preserve the existing JSON contracts and evidence boundaries.
- Invoke a separate Foundry advisory agent and normalize its cited evidence before a user approves a plan. Verify the backend AND Functions path, identity permissions, tenant isolation, tool compatibility, citations, timeouts, and failure handling.

Do not merely set `AI_TERRAFORM_PROVIDER=azure-foundry` across all services. The inspected Functions client rejects that provider. Do not add advisory output fields to the existing strict schemas without a reviewed contract change.

Uploading knowledge also cannot add deployable cloud services. The current planner marks App Service deployable and exposes B1, S1, P0v3, and existing-plan reuse. It marks other application services and database recommendations as nondeployable/configuration-required. Broader options in the master note are reference guidance and require separate support checks.

## 7. Acceptance checklist

- [ ] Active route verified from non-secret settings/provenance in the actual running workload.
- [ ] Model/tool/API combination supported in the target region/project.
- [ ] Uploaded file indexed, attached, and retrieved with relevant citations.
- [ ] Approved-plan immutability and existing JSON validation preserved.
- [ ] No price/savings invented when verified evidence is unavailable.
- [ ] Missing telemetry produces provisional sizing, not a capacity guarantee.
- [ ] Cross-tenant retrieval fails closed.
- [ ] Unsupported platform services clearly labeled advisory-only.
- [ ] Prompt injection in a document cannot trigger tools or override policy.
- [ ] Full application request verified; portal-only success labeled portal-only.
- [ ] Cost, latency, errors, token consumption, and fallback behavior measured.

The knowledge materials are ready for review/upload. Live Foundry configuration, retrieval, and application integration remain unverified.

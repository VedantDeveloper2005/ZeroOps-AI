# Microsoft Foundry Azure OpenAI provider

ZeroOps supports Microsoft Foundry Azure OpenAI model deployments as an
optional primary provider for repository analysis and Terraform generation.
NVIDIA Build remains the default; no runtime behavior changes until you switch
a workload's provider.

The provider calls the Azure OpenAI v1 **Responses API** at
`https://<resource>.openai.azure.com/openai/v1/responses` and sends strict JSON
Schema output requirements. The model name must be the deployment name shown
in Foundry. It uses the existing workload-specific API-key setting, so the two
workers retain separate key rotation and Key Vault boundaries.

## Tomorrow's configuration

After you create a model deployment and copy its resource endpoint and API key,
set only the workload you want to move:

```text
AI_REPOSITORY_PROVIDER=azure-openai
AI_REPOSITORY_ENDPOINT=https://<resource>.openai.azure.com/openai/v1
AI_REPOSITORY_MODEL=<repository-deployment-name>
AI_REPOSITORY_API_KEY=<repository deployment API key>
```

Or for Terraform generation:

```text
AI_TERRAFORM_PROVIDER=azure-openai
AI_TERRAFORM_ENDPOINT=https://<resource>.openai.azure.com/openai/v1
AI_TERRAFORM_MODEL=<terraform-deployment-name>
AI_TERRAFORM_API_KEY=<terraform deployment API key>
```

Store each API key in the already assigned Key Vault secret (`ai-repository-api-key`
or `ai-terraform-api-key`), not in source control or a `.tfvars` file. Keep
the Groq fallback settings as they are. To keep Terraform from reverting the
selection, set `repository_ai_provider`, `repository_ai_endpoint`, and
`repository_ai_model` (or the equivalent `terraform_ai_*` variables) in the
deployment configuration.

The endpoint validator accepts only HTTPS Azure OpenAI resource URLs ending in
`/openai/v1`; query strings, embedded credentials, and deployment-specific
paths are rejected. `foundry-openai` and `microsoft-foundry-openai` are
accepted aliases, but `azure-openai` is the canonical provider name.

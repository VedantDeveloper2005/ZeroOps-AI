# ZeroOps AI model specifications

This directory is the version-controlled source of truth for the two bounded
ZeroOps AI workloads:

1. `repository-analysis` reviews deterministic repository evidence.
2. `terraform-generation` converts an immutable approved Azure plan into a
   Terraform source bundle for deterministic validation.

They are separate agents, routes, credentials, prompts, output contracts, and
evaluation suites. They must never share a credential or silently fall back to
each other.

## Current GitHub Models testing

The `github-models.prompt.yml` files can be opened in the GitHub Models prompt
editor. Runtime calls use:

- endpoint: `https://models.github.ai/inference`
- catalog-qualified model IDs such as `openai/gpt-4o`
- a fine-grained token with `models: read`

Configure the application through the two workload-specific Key Vault setting
groups documented in `FOUNDRY-PORTAL.md`. Do not put API keys in these files,
GitHub prompt files, evaluation datasets, Terraform, Blob metadata, logs, or
application history.

## Future Microsoft Foundry use

Follow `FOUNDRY-PORTAL.md` to create two prompt agents. Paste each
`instructions.md` into its agent instructions and configure its
`response.foundry.schema.json` as the strict JSON response format. Upload the
matching `evaluation.dataset.jsonl` as the initial evaluation dataset.

`response.schema.json` is the rich runtime contract generated from Pydantic.
It intentionally contains length, pattern, and collection bounds that Foundry
does not accept in strict structured-output schemas. The Foundry variant keeps
only the supported structural subset; every response is still revalidated with
the rich runtime contract and deterministic semantic validators.

The application remains the authority for tenant authorization, source facts,
approval, storage, pricing, validation, and execution. Foundry agent memory is
not the customer history store.

## Contract ownership

Runtime Pydantic contracts live in `backend/contracts/ai.py`. The checked-in
runtime JSON schemas are generated from those contracts, and the Function-local
mirror is verified before packaging.
Unknown fields are forbidden, all lists and strings are bounded, and every
model response is validated again by the application.

When a contract changes:

1. create a new schema and prompt version rather than silently changing old
   history;
2. run `python scripts/generate_ai_schemas.py` and synchronize the Function
   contract mirror;
3. extend the JSONL regression dataset;
4. run the AI-specific tests;
5. evaluate both old and new agent versions before promotion.

## Non-goals

These agents do not clone repositories, fetch secrets, query Azure, calculate
live prices, run shell commands, run Terraform, approve plans, or apply cloud
changes. Those capabilities remain in deterministic, identity-scoped services.

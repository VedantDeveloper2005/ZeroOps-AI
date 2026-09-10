# Vedant full-platform migration — 2026-09-10

User authorization: move the whole platform to Vedant and make the app live.
This supersedes older account selections for this migration only.

Target subscription: 6f0a17f3-f270-4bf7-a2dd-5571fb503ff2.
Target tenant: 65444c60-8471-413d-9d50-a0472e4c80f5.
Existing control-plane resource group: zeroops-rg, Central India.

## Application release validation

- Backend: 546 tests passed.
- Frontend: 30 contract tests passed; lint, TypeScript and production build passed.
- Restored PostgreSQL: TLS connection verified, 49 tables, 2 users, 3 projects.
- Existing backend identity can read the new Key Vault.
- Existing apps contain no deployments. Reuse their B1 plan.
- Backend ZIP SHA256: 51667810d487809b5744c0c035e6b6591b2f711dc0bb5cfa885917bf517098e1.
- Frontend built with new backend origin; package must contain Linux native dependencies and exclude environment files.

## Stages and boundaries

1. Register only providers required by the existing architecture.
2. Create separate Entra-only remote state in this subscription.
3. Validate and inspect an immutable Terraform foundation plan using existing
   infrastructure code and explicit new resource names. Reject any deletions,
   replacements, old-subscription resource targets, or edits to the restored DB.
4. Provision queues, artifact stores, identities, Functions and runner registry.
5. Publish real Function packages and a digest-pinned runner image; validate the
   runner-stage plan before enabling the existing isolated worker.
6. Switch control-plane secrets to same-tenant managed identities, deploy the
   apps, and verify real HTTP/database/authentication behavior.
7. Correct CI targets and federation; record remaining live-test limitations.

Do not delete old resources, overwrite the restored database, manufacture job
results, bypass production safeguards, or enable the development demo executor.
The AI provider is pending confirmation: copied secrets select an unsupported
Groq model, and no Foundry account is present in the target subscription.

Creating application deployments is authorized now by the user. Infrastructure
applies must use a validated saved plan and record its actual result here.
Health checks alone do not establish that deployment workflows work end to end.

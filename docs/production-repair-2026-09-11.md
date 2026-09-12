# Production integration repair — September 11, 2026

## Verified live

- Website: https://zeroopsai-v2.azurewebsites.net; API: https://zeroops-backend-v2.azurewebsites.net. Both use the existing Vedant subscription App Service plan.
- API health returned production / database true after the first code release.
- Mohit's Foundry agent `zeroops-architecture-advisor`, version 2, completed a request initiated from the authenticated production website. Returned model: `gpt-5.6-terra`; measured latency: 62.4 seconds; eight real web citations. No retrieved file citation was present. The knowledge master could not be verified from that response.
- The browser previously aborted after 30 seconds while the model was still running. The recommendation was saved and appeared when reloaded. Adviser requests now allow 150 seconds; the server retains its bounded 120-second timeout.
- The prior 3,500-token response was truncated JSON. The revised prompt is bounded, the output cap is 6,000 tokens, and incomplete responses fail rather than being persisted as successful recommendations.
- Mohit's VMSS `vmss-zops-tfexec` booted an actual instance; `zeroops-runner` was active and its readiness endpoint reported ready with a recent queue poll. Autoscale restored to min/default 0, max 1 after testing.

## Repairs

- Replaced stale migrated managed-identity IDs with the actual backend identity.
- Established an Entra federated bridge from Vedant's backend identity to Mohit's tenant, scoped to the existing workflow queues, artifact storage, and Foundry project. No client secret was required for this connection.
- Configured both AI workload routes for the existing Microsoft Foundry model deployment. Removed NVIDIA, Groq, GitHub Models and generic OpenAI adapters, routing tiers and runtime configuration; removed their infrastructure fallback-secret wiring. Historical provenance fields remain readable.
- Corrected raw Foundry Responses parsing in isolated Functions and strict-schema normalization in the backend gateway.
- Removed fabricated component/citation/model and pricing fallbacks. Ordinary chat now reports unavailable Foundry explicitly. Repository source scanning remains deterministic and is labeled as such.
- Added the missing durable workflow-outbox dispatcher to API lifecycle, including cancellation and retry tests.
- Updated CI App Service names and frontend backend-origin defaults to the actual `-v2` applications. Remote GitHub credentials were not changed or verified in this repair.

## Still blocking end-to-end application deployment

1. No Azure customer hosting connection is saved for the selected project. The UI requires a tenant, subscription, resource group, scoped identity, registry and Linux App Service plan. Mohit's executor resource group has an ACR but no application App Service plan; Vedant's existing plan is in a different subscription.
2. The current application-release API writes PostgreSQL `deployment_jobs`; the installed VMSS image consumes only immutable Terraform plan/apply messages from Service Bus. A healthy Terraform runner does not consume these application release jobs.
3. The repository-analysis, Terraform-generation and history-projector Functions have not been deployed. Queue publishing alone cannot produce completed workflow results.
4. Production repository execution has no concrete attested disposable `RepositoryCheckExecutor`; the only implementation is development-only and is correctly refused in production. This must be implemented and provisioned before running customer build/tests safely.

No deployment success, Terraform proof, scanner result, telemetry or hosting readiness was invented. No development executor was enabled in production. No customer application was deployed during this repair.

## Validation

- Existing backend/worker/Function/infrastructure matrix: 568 tests passed; four added unsupported-provider cases subsequently passed after correcting their fixture (13/13 gateway tests).
- Frontend: production build successful, lint clean, 17/17 dashboard tests.
- Packaged backend imports and runtime prompts verified; retired provider files absent from deployment ZIP.
- Frontend release `8f97461f-56df-419a-8d9d-f1c7f0a5a695` succeeded.
- Backend release `9ad36dd3-1523-45fb-b5aa-189ef859a6c3` succeeded; production/database health reverified September 12.

## September 12 continuation

The eight retired provider/fallback secrets are confirmed absent from the active production vault. GitHub sign-in and repository listing succeed. Both September 11 releases reported success, but deployed frontend HTML differed from the package and still referenced the older 30-second adviser client. Incremental ZIP deployment retained stale generated files. Clean replacement is now required in both CI workflows; frontend consistency is being verified while the app is stopped for replacement. Backend clean release 549b716b-cdd9-4710-88ef-62cff6d12cee is also pending verification. Do not treat these pending repairs as complete.

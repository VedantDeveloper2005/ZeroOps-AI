# Backend schema migrations

`backend.database.run_migrations` applies each version inside one PostgreSQL
transaction and records it in `schema_migrations`. New migrations must be
append-only, idempotent, and must never copy credentials or raw execution
payloads into history tables.

Current migrations:

- `001_tenant_history` creates and backfills the tenant/run/artifact schema.
- `002_projector_event_id` adds the external workflow-event idempotency key.
- `003_history_integrity` repairs fresh schemas created before migrations,
  standardizes PostgreSQL JSONB columns and checks, preserves events when users
  are deleted, and adds durable actor/fingerprint columns.
- `004_auth_identity_integrity` normalizes stored email identities, rejects
  ambiguous case/whitespace aliases, and restores the Google identity unique
  index on upgraded databases.
- `005_devsecops_domain` adds normalized, tenant-owned pipeline, repository
  change, security, webhook, incident, AI-investigation, and remediation
  records, plus nullable Azure/App Service/AKS telemetry fields. It also
  removes zero defaults from legacy metric columns so missing telemetry stays
  unavailable, without rewriting ambiguous historical zeroes or storing raw
  payloads, secrets, prompts, logs, or Terraform execution artifacts.
- `006_secure_pending_approvals` invalidates legacy approvals that retained
  plaintext executor parameters. New approvals store a versioned Fernet
  ciphertext envelope in the compatibility column and erase it after use.
- `007_change_analysis_retry_history` removes a cross-run uniqueness constraint
  that prevented an approval-bound retry of the same immutable commit from
  retaining its own change decision. Per-run idempotency remains enforced.
- `008_verified_azure_targets` adds non-secret validation evidence for the exact
  Azure resource group, registry, region, and Linux App Service plan settings.
  Existing connection rows remain deployment-ineligible until the account
  owner verifies and saves them again.
- `009_analysis_application_type` persists the deterministic application shape
  shown in current and historical repository-analysis views.

## Legacy sensitive-column retirement

The existing schema predates the tenant-history layer and still has two
columns that must be retired in a separately tested compatibility release:

- `database_instances.password`
- `database_instances.connection_string`

Do not backfill any of them into `operation_runs`, `artifacts`, or
`activity_events`. The database credentials must be rotated into Azure Key
Vault and replaced with a non-secret Key Vault reference. Approval execution
uses an encrypted, single-use compatibility envelope until a future schema
release replaces the column with an immutable artifact digest and short-lived
executor-only reference. History writers persist only digests, redacted
summaries, and sanitized evidence.

PostgreSQL row-level security is intentionally not enabled by this migration.
The current API enforces tenant membership in every history query. RLS should be
enabled only after the connection pool sets and clears a transaction-scoped
tenant context, otherwise pooled connections can leak or block data.

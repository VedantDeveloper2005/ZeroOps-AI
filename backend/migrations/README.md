# Backend schema migrations

`backend.database.run_migrations` holds one PostgreSQL session-level advisory
lock across the versioned and compatibility blocks, applies each version in a
transaction, and records it in `schema_migrations`. New migrations must be
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
- `010_terraform_control_plane` adds saved-plan controls, single-use apply
  approvals, and the transactional workflow outbox.
- `011_auth_ai_hardening` adds durable email-verification attempts, UTC-day AI
  chat reservations, and a non-secret Key Vault reference for legacy managed
  database credentials.
- `012_deployment_terraform_binding` adds the nullable, indexed operation-run
  foreign key that prevents queued releases from bypassing an exact completed
  Terraform apply.

## Legacy sensitive-column retirement

The existing schema predates the tenant-history layer and still has two
compatibility columns:

- `database_instances.password`
- `database_instances.connection_string`

Do not backfill any of them into `operation_runs`, `artifacts`, or
`activity_events`. Production startup moves any remaining values into Azure
Key Vault, stores only `secret_reference`, and clears both compatibility
columns. Approval execution
uses an encrypted, single-use compatibility envelope until a future schema
release replaces the column with an immutable artifact digest and short-lived
executor-only reference. History writers persist only digests, redacted
summaries, and sanitized evidence.

PostgreSQL row-level security is intentionally not enabled by this migration.
The current API enforces tenant membership in every history query. RLS should be
enabled only after the connection pool sets and clears a transaction-scoped
tenant context, otherwise pooled connections can leak or block data.

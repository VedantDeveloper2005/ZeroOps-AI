# Backend schema migrations

`backend.database.run_migrations` applies each version inside one PostgreSQL
transaction and records it in `schema_migrations`. New migrations must be
append-only, idempotent, and must never copy credentials or raw execution
payloads into history tables.

Current history migrations:

- `001_tenant_history` creates and backfills the tenant/run/artifact schema.
- `002_projector_event_id` adds the external workflow-event idempotency key.
- `003_history_integrity` repairs fresh schemas created before migrations,
  standardizes PostgreSQL JSONB columns and checks, preserves events when users
  are deleted, and adds durable actor/fingerprint columns.

## Legacy sensitive-column retirement

The existing schema predates the tenant-history layer and still has three
columns that must be retired in a separately tested compatibility release:

- `database_instances.password`
- `database_instances.connection_string`
- `pending_approvals.raw_parameters`

Do not backfill any of them into `operation_runs`, `artifacts`, or
`activity_events`. The database credentials must be rotated into Azure Key
Vault and replaced with a non-secret Key Vault reference. Approval execution
must be redesigned around an immutable artifact digest plus a short-lived
executor-only reference before `raw_parameters` can be dropped. Until that
release, history writers must use `backend.services.redaction` and persist only
digests, redacted summaries, and sanitized evidence.

PostgreSQL row-level security is intentionally not enabled by this migration.
The current API enforces tenant membership in every history query. RLS should be
enabled only after the connection pool sets and clears a transaction-scoped
tenant context, otherwise pooled connections can leak or block data.

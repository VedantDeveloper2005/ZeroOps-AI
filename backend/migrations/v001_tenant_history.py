"""Tenant and durable operation-history schema.

This migration is intentionally additive. It does not copy legacy
``PendingApproval.raw_parameters``, ``DatabaseInstance.password``, or
``DatabaseInstance.connection_string`` into the new history tables.
"""

VERSION = "001_tenant_history"

STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS tenants (
        id UUID PRIMARY KEY,
        display_name TEXT NOT NULL,
        kind TEXT NOT NULL DEFAULT 'personal',
        status TEXT NOT NULL DEFAULT 'active',
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tenant_memberships (
        id UUID PRIMARY KEY,
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        role TEXT NOT NULL DEFAULT 'member',
        status TEXT NOT NULL DEFAULT 'active',
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT uq_tenant_memberships_tenant_user UNIQUE (tenant_id, user_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS operation_runs (
        id UUID PRIMARY KEY,
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
        requested_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
        parent_operation_run_id UUID REFERENCES operation_runs(id) ON DELETE SET NULL,
        operation_type TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'queued',
        source_revision TEXT,
        input_digest VARCHAR(64),
        idempotency_key VARCHAR(128),
        summary JSONB NOT NULL DEFAULT '{}'::jsonb,
        model_provider TEXT,
        model_name TEXT,
        model_version TEXT,
        prompt_version TEXT,
        input_tokens INTEGER,
        output_tokens INTEGER,
        model_cost_microusd BIGINT,
        error_code TEXT,
        redacted_error TEXT,
        started_at TIMESTAMP,
        completed_at TIMESTAMP,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT uq_operation_runs_tenant_idempotency UNIQUE (tenant_id, idempotency_key),
        CONSTRAINT ck_operation_runs_input_digest
            CHECK (input_digest IS NULL OR input_digest ~ '^[0-9a-f]{64}$')
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS artifacts (
        id UUID PRIMARY KEY,
        artifact_key UUID NOT NULL,
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        operation_run_id UUID NOT NULL REFERENCES operation_runs(id) ON DELETE CASCADE,
        project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
        created_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
        kind TEXT NOT NULL,
        display_name TEXT NOT NULL,
        content_type TEXT NOT NULL DEFAULT 'application/octet-stream',
        storage_container VARCHAR(63) NOT NULL,
        storage_path TEXT NOT NULL,
        sha256_digest VARCHAR(64) NOT NULL,
        size_bytes BIGINT NOT NULL,
        version INTEGER NOT NULL DEFAULT 1,
        access_scope TEXT NOT NULL DEFAULT 'user',
        sanitization_status TEXT NOT NULL DEFAULT 'sanitized',
        metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMP,
        CONSTRAINT uq_artifacts_tenant_key_version UNIQUE (tenant_id, artifact_key, version),
        CONSTRAINT uq_artifacts_storage_locator UNIQUE (storage_container, storage_path),
        CONSTRAINT ck_artifacts_sha256 CHECK (sha256_digest ~ '^[0-9a-f]{64}$'),
        CONSTRAINT ck_artifacts_size CHECK (size_bytes >= 0),
        CONSTRAINT ck_artifacts_version CHECK (version >= 1)
    )
    """,
    "ALTER TABLE activity_events ADD COLUMN IF NOT EXISTS tenant_id UUID",
    "ALTER TABLE activity_events ADD COLUMN IF NOT EXISTS operation_run_id UUID",
    "ALTER TABLE activity_events ADD COLUMN IF NOT EXISTS actor_type TEXT NOT NULL DEFAULT 'user'",
    "ALTER TABLE activity_events ADD COLUMN IF NOT EXISTS event_data JSONB NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE activity_events ADD COLUMN IF NOT EXISTS sequence_number INTEGER",
    """
    DO $$ BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'activity_events_tenant_id_fkey'
        ) THEN
            ALTER TABLE activity_events
                ADD CONSTRAINT activity_events_tenant_id_fkey
                FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
        END IF;
    END $$
    """,
    """
    DO $$ BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'activity_events_operation_run_id_fkey'
        ) THEN
            ALTER TABLE activity_events
                ADD CONSTRAINT activity_events_operation_run_id_fkey
                FOREIGN KEY (operation_run_id) REFERENCES operation_runs(id) ON DELETE SET NULL;
        END IF;
    END $$
    """,
    """
    INSERT INTO tenants (id, display_name, kind, status, created_at, updated_at)
    SELECT
        users.id,
        'Personal workspace',
        'personal',
        'active',
        COALESCE(users.created_at, CURRENT_TIMESTAMP),
        CURRENT_TIMESTAMP
    FROM users
    ON CONFLICT (id) DO NOTHING
    """,
    """
    INSERT INTO tenant_memberships (
        id, tenant_id, user_id, role, status, created_at, updated_at
    )
    SELECT
        users.id,
        users.id,
        users.id,
        'owner',
        'active',
        COALESCE(users.created_at, CURRENT_TIMESTAMP),
        CURRENT_TIMESTAMP
    FROM users
    ON CONFLICT (tenant_id, user_id) DO NOTHING
    """,
    """
    UPDATE activity_events
    SET tenant_id = user_id
    WHERE tenant_id IS NULL
      AND EXISTS (SELECT 1 FROM tenants WHERE tenants.id = activity_events.user_id)
    """,
    "CREATE INDEX IF NOT EXISTS ix_tenant_memberships_user_status ON tenant_memberships(user_id, status)",
    "CREATE INDEX IF NOT EXISTS ix_tenant_memberships_tenant_status ON tenant_memberships(tenant_id, status)",
    "CREATE INDEX IF NOT EXISTS ix_operation_runs_tenant_created ON operation_runs(tenant_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS ix_operation_runs_tenant_status ON operation_runs(tenant_id, status)",
    "CREATE INDEX IF NOT EXISTS ix_operation_runs_project_id ON operation_runs(project_id)",
    "CREATE INDEX IF NOT EXISTS ix_artifacts_tenant_created ON artifacts(tenant_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS ix_artifacts_operation_run_id ON artifacts(operation_run_id)",
    "CREATE INDEX IF NOT EXISTS ix_artifacts_sha256_digest ON artifacts(sha256_digest)",
    "CREATE INDEX IF NOT EXISTS ix_activity_events_tenant_created ON activity_events(tenant_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS ix_activity_events_operation_created ON activity_events(operation_run_id, created_at)",
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_activity_events_operation_sequence
    ON activity_events(operation_run_id, sequence_number)
    WHERE operation_run_id IS NOT NULL AND sequence_number IS NOT NULL
    """,
]

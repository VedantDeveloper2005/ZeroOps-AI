"""Durable Terraform plan controls, single-use approvals, and queue outbox."""

VERSION = "010_terraform_control_plane"

STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS terraform_plan_results (
        operation_run_id UUID PRIMARY KEY REFERENCES operation_runs(id) ON DELETE CASCADE,
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        plan_job_id UUID NOT NULL UNIQUE,
        plan_job_digest VARCHAR(64) NOT NULL UNIQUE,
        revision INTEGER NOT NULL CHECK (revision >= 1),
        bundle JSONB NOT NULL,
        input_variables JSONB NOT NULL,
        guardrails JSONB NOT NULL,
        saved_plan JSONB NOT NULL,
        plan_summary JSONB NOT NULL DEFAULT '{}',
        cost_estimate JSONB,
        planned_at TIMESTAMPTZ NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT ck_terraform_plan_results_digest
            CHECK (plan_job_digest ~ '^[0-9a-f]{64}$')
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_terraform_plan_results_tenant ON terraform_plan_results (tenant_id)",
    "CREATE INDEX IF NOT EXISTS ix_terraform_plan_results_project ON terraform_plan_results (project_id)",
    """
    CREATE TABLE IF NOT EXISTS terraform_apply_approvals (
        id UUID PRIMARY KEY,
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        operation_run_id UUID NOT NULL UNIQUE
            REFERENCES terraform_plan_results(operation_run_id) ON DELETE CASCADE,
        approved_by_user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
        apply_job_id UUID NOT NULL UNIQUE,
        status VARCHAR(16) NOT NULL DEFAULT 'consumed'
            CHECK (status = 'consumed'),
        plan_job_digest VARCHAR(64) NOT NULL,
        plan_sha256 VARCHAR(64) NOT NULL,
        plan_etag TEXT NOT NULL,
        bundle_sha256 VARCHAR(64) NOT NULL,
        input_variables_sha256 VARCHAR(64) NOT NULL,
        scope_digest VARCHAR(64) NOT NULL,
        policy_digest VARCHAR(64) NOT NULL,
        cost_estimate_sha256 VARCHAR(64) NOT NULL,
        currency VARCHAR(3) NOT NULL,
        monthly_cost_microunits BIGINT NOT NULL CHECK (monthly_cost_microunits >= 0),
        approved_at TIMESTAMPTZ NOT NULL,
        expires_at TIMESTAMPTZ NOT NULL,
        consumed_at TIMESTAMPTZ NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT ck_terraform_apply_approvals_digests CHECK (
            plan_job_digest ~ '^[0-9a-f]{64}$'
            AND plan_sha256 ~ '^[0-9a-f]{64}$'
            AND bundle_sha256 ~ '^[0-9a-f]{64}$'
            AND input_variables_sha256 ~ '^[0-9a-f]{64}$'
            AND scope_digest ~ '^[0-9a-f]{64}$'
            AND policy_digest ~ '^[0-9a-f]{64}$'
            AND cost_estimate_sha256 ~ '^[0-9a-f]{64}$'
        )
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_terraform_apply_approvals_tenant ON terraform_apply_approvals (tenant_id)",
    "CREATE INDEX IF NOT EXISTS ix_terraform_apply_approvals_project ON terraform_apply_approvals (project_id)",
    """
    CREATE TABLE IF NOT EXISTS workflow_outbox_messages (
        id UUID PRIMARY KEY,
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        operation_run_id UUID NOT NULL REFERENCES operation_runs(id) ON DELETE CASCADE,
        queue_name VARCHAR(64) NOT NULL CHECK (
            queue_name IN ('repo-analysis', 'terraform-generation', 'terraform-apply')
        ),
        message_id VARCHAR(128) NOT NULL UNIQUE,
        correlation_id VARCHAR(128) NOT NULL,
        session_id VARCHAR(128),
        payload JSONB NOT NULL,
        payload_digest VARCHAR(64) NOT NULL
            CHECK (payload_digest ~ '^[0-9a-f]{64}$'),
        status VARCHAR(16) NOT NULL DEFAULT 'pending'
            CHECK (status IN ('pending', 'sent')),
        attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
        next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        sent_at TIMESTAMPTZ,
        last_error_code VARCHAR(96),
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT uq_workflow_outbox_run_queue
            UNIQUE (tenant_id, operation_run_id, queue_name)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_workflow_outbox_dispatch ON workflow_outbox_messages (status, next_attempt_at)",
    "CREATE INDEX IF NOT EXISTS ix_workflow_outbox_operation_run ON workflow_outbox_messages (operation_run_id)",
)

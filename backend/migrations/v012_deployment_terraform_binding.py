"""Bind every cloud release to the exact completed Terraform operation."""

VERSION = "012_deployment_terraform_binding"

STATEMENTS = (
    "ALTER TABLE deployments ADD COLUMN IF NOT EXISTS terraform_operation_run_id UUID",
    """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1
            FROM pg_constraint
            WHERE conname = 'fk_deployments_terraform_operation_run_id'
        ) THEN
            ALTER TABLE deployments
            ADD CONSTRAINT fk_deployments_terraform_operation_run_id
            FOREIGN KEY (terraform_operation_run_id)
            REFERENCES operation_runs(id)
            ON DELETE SET NULL;
        END IF;
    END
    $$
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_deployments_terraform_operation_run_id
    ON deployments (terraform_operation_run_id)
    """,
)

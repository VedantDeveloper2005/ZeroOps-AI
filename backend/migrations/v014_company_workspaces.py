"""Add shared-workspace project ownership and single-use invitations."""

VERSION = "014_company_workspaces"

STATEMENTS = (
    "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS require_mfa BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES tenants(id) ON DELETE SET NULL",
    "UPDATE projects SET tenant_id = user_id WHERE tenant_id IS NULL",
    "CREATE INDEX IF NOT EXISTS ix_projects_tenant_id ON projects(tenant_id)",
    "CREATE TABLE IF NOT EXISTS workspace_invitations ("
    "id UUID PRIMARY KEY, tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE, "
    "email TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'engineer', token_hash VARCHAR(64) NOT NULL UNIQUE, "
    "status TEXT NOT NULL DEFAULT 'pending', invited_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL, "
    "accepted_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL, expires_at TIMESTAMP NOT NULL, "
    "created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, "
    "CONSTRAINT ck_workspace_invitation_role CHECK (role IN ('admin', 'engineer', 'viewer')), "
    "CONSTRAINT ck_workspace_invitation_status CHECK (status IN ('pending', 'accepted', 'revoked', 'expired'))"
    ")",
    "CREATE INDEX IF NOT EXISTS ix_workspace_invitations_tenant_status ON workspace_invitations(tenant_id, status)",
    "CREATE INDEX IF NOT EXISTS ix_workspace_invitations_email_status ON workspace_invitations(email, status)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_workspace_invitations_one_pending_email "
    "ON workspace_invitations(tenant_id, email) WHERE status = 'pending'",
)


async def apply_sqlite(connection):
    """SQLite lacks PostgreSQL's ADD COLUMN IF NOT EXISTS syntax."""
    tenant_columns = {row[1] for row in (await connection.exec_driver_sql("PRAGMA table_info(tenants)")).fetchall()}
    if "require_mfa" not in tenant_columns:
        await connection.exec_driver_sql("ALTER TABLE tenants ADD COLUMN require_mfa BOOLEAN NOT NULL DEFAULT 0")
    result = await connection.exec_driver_sql("PRAGMA table_info(projects)")
    columns = {row[1] for row in result.fetchall()}
    if "tenant_id" not in columns:
        await connection.exec_driver_sql("ALTER TABLE projects ADD COLUMN tenant_id UUID")
    await connection.exec_driver_sql("UPDATE projects SET tenant_id = user_id WHERE tenant_id IS NULL")
    await connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_projects_tenant_id ON projects(tenant_id)")
    await connection.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_workspace_invitations_tenant_status ON workspace_invitations(tenant_id, status)"
    )
    await connection.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_workspace_invitations_email_status ON workspace_invitations(email, status)"
    )
    await connection.exec_driver_sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_workspace_invitations_one_pending_email "
        "ON workspace_invitations(tenant_id, email) WHERE status = 'pending'"
    )

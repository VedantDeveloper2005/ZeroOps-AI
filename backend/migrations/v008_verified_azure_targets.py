"""Require Azure deployment targets to carry exact validation evidence."""

VERSION = "008_verified_azure_targets"

STATEMENTS = (
    """
    ALTER TABLE user_azure_connections
    ADD COLUMN IF NOT EXISTS deployment_target_fingerprint VARCHAR(64)
    """,
    """
    ALTER TABLE user_azure_connections
    ADD COLUMN IF NOT EXISTS deployment_target_verified_at TIMESTAMP
    """,
    """
    ALTER TABLE user_azure_connections
    DROP CONSTRAINT IF EXISTS ck_user_azure_connections_target_fingerprint
    """,
    """
    ALTER TABLE user_azure_connections
    ADD CONSTRAINT ck_user_azure_connections_target_fingerprint
    CHECK (
        deployment_target_fingerprint IS NULL
        OR deployment_target_fingerprint ~ '^[0-9a-f]{64}$'
    )
    """,
)

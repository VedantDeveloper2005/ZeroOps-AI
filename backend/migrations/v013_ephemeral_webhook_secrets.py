"""Store tenant-specific webhook credentials for Jira and inbound email."""

VERSION = "013_ephemeral_webhook_secrets"

STATEMENTS = (
    "ALTER TABLE integration_configs ADD COLUMN IF NOT EXISTS jira_webhook_secret_encrypted TEXT",
    "ALTER TABLE integration_configs ADD COLUMN IF NOT EXISTS email_webhook_secret_encrypted TEXT",
)

"""Add durable authentication, AI-chat, and credential-boundary state."""

VERSION = "011_auth_ai_hardening"

STATEMENTS = (
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verification_attempts INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS ai_chat_usage_date DATE",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS ai_chat_request_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE database_instances ADD COLUMN IF NOT EXISTS secret_reference TEXT",
    """
    DO $$ BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'ck_users_email_verification_attempts'
              AND conrelid = 'users'::regclass
        ) THEN
            ALTER TABLE users
                ADD CONSTRAINT ck_users_email_verification_attempts
                CHECK (email_verification_attempts >= 0);
        END IF;
    END $$
    """,
    """
    DO $$ BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'ck_users_ai_chat_request_count'
              AND conrelid = 'users'::regclass
        ) THEN
            ALTER TABLE users
                ADD CONSTRAINT ck_users_ai_chat_request_count
                CHECK (ai_chat_request_count >= 0);
        END IF;
    END $$
    """,
)

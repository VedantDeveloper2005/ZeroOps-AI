"""Normalize user email identities and align upgraded schemas with the ORM.

Fresh databases receive these constraints from SQLAlchemy metadata. Existing
databases need an explicit migration because ``create_all`` does not add new
unique constraints or indexes to tables that already exist.
"""

VERSION = "004_auth_identity_integrity"

STATEMENTS = [
    # Versioned migrations run before the legacy compatibility ALTER block in
    # database.py, so every column used below must be established here first.
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS google_id TEXT",
    # Do not guess how to merge two existing accounts. If historical data has
    # case/whitespace aliases, fail the migration transaction with a clear
    # remediation signal instead of silently attaching one identity to another.
    """
    DO $$ BEGIN
        IF EXISTS (
            SELECT 1
            FROM users
            GROUP BY LOWER(BTRIM(email))
            HAVING COUNT(*) > 1
        ) THEN
            RAISE EXCEPTION
                'users contains duplicate normalized email identities; merge them before applying migration 004';
        END IF;
    END $$
    """,
    "UPDATE users SET email = LOWER(BTRIM(email)) WHERE email IS DISTINCT FROM LOWER(BTRIM(email))",
    """
    DO $$ BEGIN
        IF NOT EXISTS (
            SELECT 1
            FROM pg_constraint
            WHERE conname = 'ck_users_email_normalized'
              AND conrelid = 'users'::regclass
        ) THEN
            ALTER TABLE users
                ADD CONSTRAINT ck_users_email_normalized
                CHECK (email = LOWER(BTRIM(email)) AND email <> '')
                NOT VALID;
        END IF;
    END $$
    """,
    "ALTER TABLE users VALIDATE CONSTRAINT ck_users_email_normalized",
    "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email_normalized_unique ON users ((LOWER(BTRIM(email))))",
    """
    CREATE UNIQUE INDEX IF NOT EXISTS ix_users_google_id_unique
    ON users (google_id)
    WHERE google_id IS NOT NULL AND BTRIM(google_id) <> ''
    """,
]

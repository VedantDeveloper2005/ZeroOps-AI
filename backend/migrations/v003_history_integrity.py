"""Align durable history tables with the PostgreSQL projector contract.

This migration is append-only because versions 001 and 002 may already be
recorded in production. It repairs schemas initially created by SQLAlchemy
before those migrations ran.
"""

VERSION = "003_history_integrity"

STATEMENTS = [
    """
    DO $$ BEGIN
        IF EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'operation_runs'
              AND column_name = 'summary'
              AND data_type <> 'jsonb'
        ) THEN
            ALTER TABLE operation_runs
                ALTER COLUMN summary TYPE JSONB USING summary::jsonb;
        END IF;
    END $$
    """,
    """
    DO $$ BEGIN
        IF EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'artifacts'
              AND column_name = 'metadata'
              AND data_type <> 'jsonb'
        ) THEN
            ALTER TABLE artifacts
                ALTER COLUMN metadata TYPE JSONB USING metadata::jsonb;
        END IF;
    END $$
    """,
    """
    DO $$ BEGIN
        IF EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'activity_events'
              AND column_name = 'event_data'
              AND data_type <> 'jsonb'
        ) THEN
            ALTER TABLE activity_events
                ALTER COLUMN event_data TYPE JSONB USING event_data::jsonb;
        END IF;
    END $$
    """,
    "ALTER TABLE activity_events ADD COLUMN IF NOT EXISTS actor_id VARCHAR(128)",
    "ALTER TABLE activity_events ADD COLUMN IF NOT EXISTS event_fingerprint VARCHAR(64)",
    """
    UPDATE activity_events
    SET actor_id = LEFT(
        COALESCE(
            NULLIF(event_data->>'actor_id', ''),
            user_id::text
        ),
        128
    )
    WHERE actor_id IS NULL
    """,
    "ALTER TABLE activity_events ALTER COLUMN user_id DROP NOT NULL",
    """
    DO $$
    DECLARE
        foreign_key_name TEXT;
    BEGIN
        FOR foreign_key_name IN
            SELECT DISTINCT constraint_record.conname
            FROM pg_constraint AS constraint_record
            JOIN pg_class AS relation
              ON relation.oid = constraint_record.conrelid
            JOIN pg_namespace AS namespace
              ON namespace.oid = relation.relnamespace
            JOIN pg_attribute AS attribute
              ON attribute.attrelid = relation.oid
             AND attribute.attnum = ANY(constraint_record.conkey)
            WHERE namespace.nspname = current_schema()
              AND relation.relname = 'activity_events'
              AND constraint_record.contype = 'f'
              AND attribute.attname = 'user_id'
        LOOP
            EXECUTE format(
                'ALTER TABLE activity_events DROP CONSTRAINT %I',
                foreign_key_name
            );
        END LOOP;
    END $$
    """,
    """
    ALTER TABLE activity_events
        ADD CONSTRAINT activity_events_user_id_fkey
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
    """,
    """
    DO $$ BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'ck_operation_runs_input_digest'
              AND conrelid = 'operation_runs'::regclass
        ) THEN
            ALTER TABLE operation_runs
                ADD CONSTRAINT ck_operation_runs_input_digest
                CHECK (input_digest IS NULL OR input_digest ~ '^[0-9a-f]{64}$')
                NOT VALID;
        END IF;
    END $$
    """,
    "ALTER TABLE operation_runs VALIDATE CONSTRAINT ck_operation_runs_input_digest",
    """
    DO $$ BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'ck_artifacts_sha256'
              AND conrelid = 'artifacts'::regclass
        ) THEN
            ALTER TABLE artifacts
                ADD CONSTRAINT ck_artifacts_sha256
                CHECK (sha256_digest ~ '^[0-9a-f]{64}$')
                NOT VALID;
        END IF;
    END $$
    """,
    "ALTER TABLE artifacts VALIDATE CONSTRAINT ck_artifacts_sha256",
    """
    DO $$ BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'ck_artifacts_size'
              AND conrelid = 'artifacts'::regclass
        ) THEN
            ALTER TABLE artifacts
                ADD CONSTRAINT ck_artifacts_size
                CHECK (size_bytes >= 0)
                NOT VALID;
        END IF;
    END $$
    """,
    "ALTER TABLE artifacts VALIDATE CONSTRAINT ck_artifacts_size",
    """
    DO $$ BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'ck_artifacts_version'
              AND conrelid = 'artifacts'::regclass
        ) THEN
            ALTER TABLE artifacts
                ADD CONSTRAINT ck_artifacts_version
                CHECK (version >= 1)
                NOT VALID;
        END IF;
    END $$
    """,
    "ALTER TABLE artifacts VALIDATE CONSTRAINT ck_artifacts_version",
    """
    DO $$ BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'ck_activity_events_fingerprint'
              AND conrelid = 'activity_events'::regclass
        ) THEN
            ALTER TABLE activity_events
                ADD CONSTRAINT ck_activity_events_fingerprint
                CHECK (
                    event_fingerprint IS NULL
                    OR event_fingerprint ~ '^[0-9a-f]{64}$'
                )
                NOT VALID;
        END IF;
    END $$
    """,
    "ALTER TABLE activity_events VALIDATE CONSTRAINT ck_activity_events_fingerprint",
]

"""Idempotency key for at-least-once workflow-event projection."""

VERSION = "002_projector_event_id"

STATEMENTS = [
    "ALTER TABLE activity_events ADD COLUMN IF NOT EXISTS external_event_id VARCHAR(128)",
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_activity_events_tenant_external_event
    ON activity_events(tenant_id, external_event_id)
    WHERE tenant_id IS NOT NULL AND external_event_id IS NOT NULL
    """,
]


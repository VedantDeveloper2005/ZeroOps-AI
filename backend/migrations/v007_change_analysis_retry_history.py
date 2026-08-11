"""Permit each pipeline retry to retain its own deterministic change decision."""

VERSION = "007_change_analysis_retry_history"

STATEMENTS = (
    # Early v005 adopters may have the cross-run uniqueness constraint. It
    # prevents a fresh, approval-bound retry of the same immutable revision
    # from recording its own evidence. Per-run idempotency remains enforced by
    # uq_change_analyses_tenant_idempotency.
    """
    ALTER TABLE change_analyses
    DROP CONSTRAINT IF EXISTS uq_change_analyses_target_fingerprint
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_change_analyses_target_fingerprint
    ON change_analyses (tenant_id, project_id, target_revision, change_fingerprint)
    """,
)

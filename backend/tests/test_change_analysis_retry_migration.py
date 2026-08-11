from backend import models
from backend.migrations import v007_change_analysis_retry_history


def test_change_analysis_retry_migration_removes_cross_run_uniqueness():
    sql = "\n".join(v007_change_analysis_retry_history.STATEMENTS).lower()

    assert (
        v007_change_analysis_retry_history.VERSION
        == "007_change_analysis_retry_history"
    )
    assert "drop constraint if exists uq_change_analyses_target_fingerprint" in sql
    assert "create index if not exists ix_change_analyses_target_fingerprint" in sql

    unique_names = {
        constraint.name
        for constraint in models.ChangeAnalysis.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    index_names = {index.name for index in models.ChangeAnalysis.__table__.indexes}

    assert "uq_change_analyses_target_fingerprint" not in unique_names
    assert "uq_change_analyses_tenant_idempotency" in unique_names
    assert "ix_change_analyses_target_fingerprint" in index_names

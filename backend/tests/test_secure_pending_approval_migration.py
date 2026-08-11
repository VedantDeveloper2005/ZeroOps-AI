from backend.migrations import v006_secure_pending_approvals


def test_secure_pending_approval_migration_invalidates_legacy_plaintext():
    sql = "\n".join(v006_secure_pending_approvals.STATEMENTS).lower()

    assert v006_secure_pending_approvals.VERSION == "006_secure_pending_approvals"
    assert "update pending_approvals" in sql
    assert "set raw_parameters = '{}'::json" in sql

from backend import models
from backend.migrations import v008_verified_azure_targets


def test_verified_azure_target_migration_adds_validation_evidence():
    sql = "\n".join(v008_verified_azure_targets.STATEMENTS).lower()

    assert (
        v008_verified_azure_targets.VERSION
        == "008_verified_azure_targets"
    )
    assert "deployment_target_fingerprint varchar(64)" in sql
    assert "deployment_target_verified_at timestamp" in sql
    assert "ck_user_azure_connections_target_fingerprint" in sql

    columns = models.UserAzureConnection.__table__.columns
    assert columns["deployment_target_fingerprint"].nullable is True
    assert columns["deployment_target_verified_at"].nullable is True
    constraint_names = {
        constraint.name
        for constraint in models.UserAzureConnection.__table__.constraints
    }
    assert "ck_user_azure_connections_target_fingerprint" in constraint_names

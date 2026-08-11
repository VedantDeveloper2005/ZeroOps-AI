import re
from dataclasses import fields

from sqlalchemy import JSON, UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from backend import models
from backend.migrations.v005_devsecops_domain import STATEMENTS, VERSION
from backend.services.change_detection import ChangeAnalysisPersistence, RepositoryFingerprint


DOMAIN_MODELS = (
    models.ProjectPipelineConfiguration,
    models.PipelineRun,
    models.PipelineStageAttempt,
    models.RepositoryAnalysisSnapshot,
    models.ChangeAnalysis,
    models.SecurityScan,
    models.SecurityFinding,
    models.WebhookDelivery,
    models.Incident,
    models.AIInvestigation,
    models.RemediationProposal,
    models.RemediationExecution,
)

EXECUTION_MODELS = (
    models.PipelineRun,
    models.PipelineStageAttempt,
    models.RepositoryAnalysisSnapshot,
    models.ChangeAnalysis,
    models.SecurityScan,
    models.WebhookDelivery,
    models.AIInvestigation,
    models.RemediationExecution,
)


def test_domain_tables_are_registered_with_explicit_ownership_columns():
    expected_tables = {
        "project_pipeline_configurations",
        "pipeline_runs",
        "pipeline_stage_attempts",
        "repository_analysis_snapshots",
        "change_analyses",
        "security_scans",
        "security_findings",
        "webhook_deliveries",
        "incidents",
        "ai_investigations",
        "remediation_proposals",
        "remediation_executions",
    }
    assert expected_tables <= set(models.Base.metadata.tables)

    for model in DOMAIN_MODELS:
        columns = model.__table__.columns
        assert columns["tenant_id"].nullable is False
        assert columns["project_id"].nullable is False

    for model in DOMAIN_MODELS:
        if model is models.ProjectPipelineConfiguration:
            continue
        assert "deployment_id" in model.__table__.columns


def test_execution_status_constraints_are_fail_closed():
    required = {
        "queued",
        "running",
        "succeeded",
        "failed",
        "skipped",
        "blocked",
        "unavailable",
        "cancelled",
    }
    dialect = postgresql.dialect()

    assert {item.value for item in models.ExecutionStatus} == required
    for model in EXECUTION_MODELS:
        ddl = str(CreateTable(model.__table__).compile(dialect=dialect)).lower()
        assert required <= {status for status in required if f"'{status}'" in ddl}


def test_automatic_retry_and_rollback_are_secure_by_default():
    table = models.ProjectPipelineConfiguration.__table__
    assert table.c.auto_retry_transient_failures.nullable is False
    assert table.c.auto_retry_transient_failures.default.arg is False
    assert table.c.auto_rollback_enabled.nullable is False
    assert table.c.auto_rollback_enabled.default.arg is False
    assert table.c.deployment_mode.default.arg == "require_approval"


def test_monitoring_extension_preserves_unavailable_values_as_null():
    table = models.DeploymentMetric.__table__
    nullable_fields = {
        "cpu_utilization",
        "memory_utilization",
        "request_count",
        "error_rate",
        "response_time_ms",
        "request_rate",
        "availability_percent",
        "pod_restarts",
        "pods_ready",
        "replica_count",
        "failed_pods",
        "source",
        "deployment_health",
    }
    for field in nullable_fields:
        assert table.c[field].nullable is True
        assert table.c[field].default is None

    ddl = str(CreateTable(table).compile(dialect=postgresql.dialect())).lower()
    assert "ck_deployment_metrics_request_rate" in ddl
    assert "ck_deployment_metrics_availability" in ddl
    assert "ck_deployment_metrics_pod_counts" in ddl
    assert "ck_deployment_metrics_health" in ddl


def test_run_like_tables_have_non_nullable_tenant_idempotency_constraints():
    run_like_models = (
        models.PipelineRun,
        models.PipelineStageAttempt,
        models.RepositoryAnalysisSnapshot,
        models.ChangeAnalysis,
        models.SecurityScan,
        models.Incident,
        models.AIInvestigation,
        models.RemediationProposal,
        models.RemediationExecution,
    )
    for model in run_like_models:
        table = model.__table__
        assert table.c.idempotency_key.nullable is False
        unique_sets = {
            tuple(column.name for column in constraint.columns)
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint)
        }
        assert ("tenant_id", "idempotency_key") in unique_sets


def test_sensitive_raw_inputs_are_absent_from_new_domain_tables():
    forbidden_columns = {
        "secret",
        "password",
        "credential",
        "access_token",
        "raw_payload",
        "raw_logs",
        "raw_prompt",
        "terraform_state",
        "saved_plan",
    }
    all_columns = {
        column.name
        for model in DOMAIN_MODELS
        for column in model.__table__.columns
    }
    assert forbidden_columns.isdisjoint(all_columns)
    assert "payload_digest" in models.WebhookDelivery.__table__.columns
    assert "masked_evidence" in models.SecurityFinding.__table__.columns
    assert "redacted_parameters" in models.RemediationProposal.__table__.columns


def test_v005_migration_is_versioned_idempotent_and_covers_every_domain_table():
    migration_sql = "\n".join(STATEMENTS).lower()
    assert VERSION == "005_devsecops_domain"
    assert "alter table user_azure_connections add column if not exists aks_cluster_name text" in migration_sql
    assert "auto_retry_transient_failures boolean not null default false" in migration_sql
    assert "auto_rollback_enabled boolean not null default false" in migration_sql
    assert "deployment_mode varchar(32) not null default 'require_approval'" in migration_sql
    for field in (
        "request_rate",
        "availability_percent",
        "pod_restarts",
        "pods_ready",
        "replica_count",
        "failed_pods",
        "source",
        "deployment_health",
    ):
        assert f"deployment_metrics add column if not exists {field}" in migration_sql
    for field in (
        "cpu_utilization",
        "memory_utilization",
        "request_count",
        "error_rate",
        "response_time_ms",
    ):
        assert f"deployment_metrics alter column {field} drop default" in migration_sql

    for model in DOMAIN_MODELS:
        assert f"create table if not exists {model.__tablename__}" in migration_sql
    assert "create index if not exists" in migration_sql
    assert "raw_payload" not in migration_sql
    assert "saved_plan" not in migration_sql


def test_v005_table_columns_match_the_orm_metadata():
    column_pattern = re.compile(
        r"^\s+([a-z][a-z0-9_]*)\s+"
        r"(?:uuid|text|varchar\(\d+\)|integer|boolean|timestamptz|jsonb|bigint)(?=\s|,)",
        re.IGNORECASE | re.MULTILINE,
    )
    for model in DOMAIN_MODELS:
        statement = next(
            sql
            for sql in STATEMENTS
            if f"CREATE TABLE IF NOT EXISTS {model.__tablename__}" in sql
        )
        migration_columns = set(column_pattern.findall(statement))
        orm_columns = {column.name for column in model.__table__.columns}
        assert migration_columns == orm_columns, model.__tablename__


def test_change_detection_persistence_contract_matches_change_analysis_columns():
    persistence_fields = {field.name for field in fields(ChangeAnalysisPersistence)}
    model_columns = {column.name for column in models.ChangeAnalysis.__table__.columns}
    assert persistence_fields <= model_columns


def test_repository_fingerprint_contract_maps_to_snapshot_columns():
    fingerprint_fields = {field.name for field in fields(RepositoryFingerprint)}
    fingerprint_fields.remove("commit_sha")
    fingerprint_fields.remove("version")
    snapshot_columns = {
        column.name for column in models.RepositoryAnalysisSnapshot.__table__.columns
    }
    assert fingerprint_fields <= snapshot_columns
    assert {"source_revision", "fingerprint_version"} <= snapshot_columns


def test_bounded_json_does_not_hold_core_status_or_approval_fields():
    permitted_json_column_names = {
        "evidence",
        "result_metadata",
        "summary",
        "category_counts",
        "sampled_paths",
        "detected_services",
        "environment_variable_names",
        "resolution_steps",
        "redacted_parameters",
    }
    actual_json_column_names = {
        column.name
        for model in DOMAIN_MODELS
        for column in model.__table__.columns
        if isinstance(column.type, JSON)
    }
    assert actual_json_column_names <= permitted_json_column_names

    for model in DOMAIN_MODELS:
        for column in model.__table__.columns:
            if column.name in {"status", "policy_status", "risk_tier", "severity"}:
                assert not isinstance(column.type, JSON)

    assert models.SecurityScan.__table__.c.status.type.length == 16
    assert models.SecurityScan.__table__.c.policy_status.type.length == 16
    assert models.RemediationProposal.__table__.c.status.type.length == 24

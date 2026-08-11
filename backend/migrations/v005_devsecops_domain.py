"""Add the normalized DevSecOps pipeline and incident domain.

The tables store explicit lifecycle and policy fields. JSONB is restricted to
bounded, redacted summaries/evidence; webhook payloads, model prompts, raw
logs, credentials, Terraform state, and saved plans are intentionally absent.
"""

VERSION = "005_devsecops_domain"

EXECUTION_STATUSES_SQL = (
    "'queued', 'running', 'succeeded', 'failed', 'skipped', "
    "'blocked', 'unavailable', 'cancelled'"
)

STATEMENTS = [
    # Align upgraded databases with the existing UserAzureConnection model.
    "ALTER TABLE user_azure_connections ADD COLUMN IF NOT EXISTS aks_cluster_name TEXT",
    # Nullable telemetry fields represent unavailable data honestly; zero is a
    # real observed value and is never used as a missing-data placeholder.
    "ALTER TABLE deployment_metrics ALTER COLUMN cpu_utilization DROP DEFAULT",
    "ALTER TABLE deployment_metrics ALTER COLUMN memory_utilization DROP DEFAULT",
    "ALTER TABLE deployment_metrics ALTER COLUMN request_count DROP DEFAULT",
    "ALTER TABLE deployment_metrics ALTER COLUMN error_rate DROP DEFAULT",
    "ALTER TABLE deployment_metrics ALTER COLUMN response_time_ms DROP DEFAULT",
    "ALTER TABLE deployment_metrics ADD COLUMN IF NOT EXISTS request_rate DOUBLE PRECISION",
    "ALTER TABLE deployment_metrics ADD COLUMN IF NOT EXISTS availability_percent DOUBLE PRECISION",
    "ALTER TABLE deployment_metrics ADD COLUMN IF NOT EXISTS pod_restarts INTEGER",
    "ALTER TABLE deployment_metrics ADD COLUMN IF NOT EXISTS pods_ready INTEGER",
    "ALTER TABLE deployment_metrics ADD COLUMN IF NOT EXISTS replica_count INTEGER",
    "ALTER TABLE deployment_metrics ADD COLUMN IF NOT EXISTS failed_pods INTEGER",
    "ALTER TABLE deployment_metrics ADD COLUMN IF NOT EXISTS source TEXT",
    "ALTER TABLE deployment_metrics ADD COLUMN IF NOT EXISTS deployment_health TEXT",
    """
    DO $$ BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'ck_deployment_metrics_request_rate'
              AND conrelid = 'deployment_metrics'::regclass
        ) THEN
            ALTER TABLE deployment_metrics ADD CONSTRAINT ck_deployment_metrics_request_rate
                CHECK (request_rate IS NULL OR request_rate >= 0) NOT VALID;
        END IF;
    END $$
    """,
    "ALTER TABLE deployment_metrics VALIDATE CONSTRAINT ck_deployment_metrics_request_rate",
    """
    DO $$ BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'ck_deployment_metrics_availability'
              AND conrelid = 'deployment_metrics'::regclass
        ) THEN
            ALTER TABLE deployment_metrics ADD CONSTRAINT ck_deployment_metrics_availability
                CHECK (
                    availability_percent IS NULL OR
                    (availability_percent >= 0 AND availability_percent <= 100)
                ) NOT VALID;
        END IF;
    END $$
    """,
    "ALTER TABLE deployment_metrics VALIDATE CONSTRAINT ck_deployment_metrics_availability",
    """
    DO $$ BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'ck_deployment_metrics_pod_counts'
              AND conrelid = 'deployment_metrics'::regclass
        ) THEN
            ALTER TABLE deployment_metrics ADD CONSTRAINT ck_deployment_metrics_pod_counts
                CHECK (
                    (pod_restarts IS NULL OR pod_restarts >= 0) AND
                    (pods_ready IS NULL OR pods_ready >= 0) AND
                    (replica_count IS NULL OR replica_count >= 0) AND
                    (failed_pods IS NULL OR failed_pods >= 0)
                ) NOT VALID;
        END IF;
    END $$
    """,
    "ALTER TABLE deployment_metrics VALIDATE CONSTRAINT ck_deployment_metrics_pod_counts",
    """
    DO $$ BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'ck_deployment_metrics_health'
              AND conrelid = 'deployment_metrics'::regclass
        ) THEN
            ALTER TABLE deployment_metrics ADD CONSTRAINT ck_deployment_metrics_health
                CHECK (
                    deployment_health IS NULL OR
                    deployment_health IN (
                        'healthy', 'degraded', 'unhealthy', 'rollout_failed', 'unavailable', 'unknown'
                    )
                ) NOT VALID;
        END IF;
    END $$
    """,
    "ALTER TABLE deployment_metrics VALIDATE CONSTRAINT ck_deployment_metrics_health",
    """
    CREATE TABLE IF NOT EXISTS project_pipeline_configurations (
        id UUID PRIMARY KEY,
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        created_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
        updated_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
        version INTEGER NOT NULL DEFAULT 1,
        enabled BOOLEAN NOT NULL DEFAULT TRUE,
        trigger_mode VARCHAR(16) NOT NULL DEFAULT 'manual',
        tracked_branch TEXT NOT NULL DEFAULT 'main',
        auto_deploy BOOLEAN NOT NULL DEFAULT FALSE,
        deployment_mode VARCHAR(32) NOT NULL DEFAULT 'require_approval',
        require_production_approval BOOLEAN NOT NULL DEFAULT TRUE,
        require_infrastructure_approval BOOLEAN NOT NULL DEFAULT TRUE,
        run_dependency_install BOOLEAN NOT NULL DEFAULT TRUE,
        run_code_quality BOOLEAN NOT NULL DEFAULT TRUE,
        run_unit_tests BOOLEAN NOT NULL DEFAULT TRUE,
        run_sast BOOLEAN NOT NULL DEFAULT TRUE,
        run_dependency_scan BOOLEAN NOT NULL DEFAULT TRUE,
        run_secret_scan BOOLEAN NOT NULL DEFAULT TRUE,
        run_container_scan BOOLEAN NOT NULL DEFAULT TRUE,
        run_iac_scan BOOLEAN NOT NULL DEFAULT TRUE,
        generate_sbom BOOLEAN NOT NULL DEFAULT FALSE,
        ai_failure_diagnosis BOOLEAN NOT NULL DEFAULT TRUE,
        auto_retry_transient_failures BOOLEAN NOT NULL DEFAULT FALSE,
        auto_rollback_enabled BOOLEAN NOT NULL DEFAULT FALSE,
        config_digest VARCHAR(64),
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT uq_pipeline_config_tenant_project_version UNIQUE (tenant_id, project_id, version),
        CONSTRAINT ck_pipeline_config_version CHECK (version >= 1),
        CONSTRAINT ck_pipeline_config_trigger_mode
            CHECK (trigger_mode IN ('manual', 'push', 'manual_and_push', 'disabled')),
        CONSTRAINT ck_pipeline_config_deployment_mode
            CHECK (deployment_mode IN ('validate_only', 'deploy_after_checks', 'require_approval')),
        CONSTRAINT ck_pipeline_config_digest
            CHECK (config_digest IS NULL OR config_digest ~ '^[0-9a-f]{64}$')
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_pipeline_config_project_version ON project_pipeline_configurations (project_id, version)",
    f"""
    CREATE TABLE IF NOT EXISTS pipeline_runs (
        id UUID PRIMARY KEY,
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        deployment_id UUID REFERENCES deployments(id) ON DELETE SET NULL,
        operation_run_id UUID REFERENCES operation_runs(id) ON DELETE SET NULL,
        configuration_id UUID REFERENCES project_pipeline_configurations(id) ON DELETE SET NULL,
        requested_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
        idempotency_key VARCHAR(128) NOT NULL,
        trigger_type VARCHAR(16) NOT NULL DEFAULT 'manual',
        status VARCHAR(16) NOT NULL DEFAULT 'queued',
        branch TEXT NOT NULL,
        source_revision VARCHAR(64) NOT NULL,
        previous_successful_revision VARCHAR(64),
        target_type VARCHAR(32) NOT NULL DEFAULT 'undecided',
        configuration_version INTEGER NOT NULL DEFAULT 1,
        current_stage_key VARCHAR(64),
        repository_ai_required BOOLEAN NOT NULL DEFAULT FALSE,
        repository_ai_used BOOLEAN NOT NULL DEFAULT FALSE,
        approval_required BOOLEAN NOT NULL DEFAULT FALSE,
        status_reason TEXT,
        failure_code VARCHAR(64),
        redacted_failure TEXT,
        queued_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        started_at TIMESTAMPTZ,
        completed_at TIMESTAMPTZ,
        cancelled_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT uq_pipeline_runs_tenant_idempotency UNIQUE (tenant_id, idempotency_key),
        CONSTRAINT ck_pipeline_runs_config_version CHECK (configuration_version >= 1),
        CONSTRAINT ck_pipeline_runs_trigger_type
            CHECK (trigger_type IN ('manual', 'push', 'retry', 'api', 'remediation')),
        CONSTRAINT ck_pipeline_runs_status CHECK (status IN ({EXECUTION_STATUSES_SQL})),
        CONSTRAINT ck_pipeline_runs_terminal_reason CHECK (
            status NOT IN ('failed', 'skipped', 'blocked', 'unavailable', 'cancelled')
            OR status_reason IS NOT NULL
        )
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_pipeline_runs_project_created ON pipeline_runs (project_id, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_pipeline_runs_deployment_id ON pipeline_runs (deployment_id)",
    "CREATE INDEX IF NOT EXISTS ix_pipeline_runs_tenant_status ON pipeline_runs (tenant_id, status)",
    f"""
    CREATE TABLE IF NOT EXISTS pipeline_stage_attempts (
        id UUID PRIMARY KEY,
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        deployment_id UUID REFERENCES deployments(id) ON DELETE SET NULL,
        pipeline_run_id UUID NOT NULL REFERENCES pipeline_runs(id) ON DELETE CASCADE,
        log_artifact_id UUID REFERENCES artifacts(id) ON DELETE SET NULL,
        output_artifact_id UUID REFERENCES artifacts(id) ON DELETE SET NULL,
        idempotency_key VARCHAR(128) NOT NULL,
        stage_key VARCHAR(64) NOT NULL,
        display_name TEXT NOT NULL,
        stage_order INTEGER NOT NULL,
        attempt_number INTEGER NOT NULL DEFAULT 1,
        is_required BOOLEAN NOT NULL DEFAULT TRUE,
        status VARCHAR(16) NOT NULL DEFAULT 'queued',
        tool_name VARCHAR(128),
        tool_version VARCHAR(128),
        status_reason TEXT,
        failure_code VARCHAR(64),
        redacted_error TEXT,
        evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
        result_metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
        queued_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        started_at TIMESTAMPTZ,
        completed_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT uq_pipeline_stage_attempt_run_stage_attempt
            UNIQUE (pipeline_run_id, stage_key, attempt_number),
        CONSTRAINT uq_pipeline_stage_attempt_tenant_idempotency
            UNIQUE (tenant_id, idempotency_key),
        CONSTRAINT ck_pipeline_stage_attempt_order CHECK (stage_order >= 1),
        CONSTRAINT ck_pipeline_stage_attempt_number CHECK (attempt_number >= 1),
        CONSTRAINT ck_pipeline_stage_attempt_status CHECK (status IN ({EXECUTION_STATUSES_SQL})),
        CONSTRAINT ck_pipeline_stage_attempt_terminal_reason CHECK (
            status NOT IN ('failed', 'skipped', 'blocked', 'unavailable', 'cancelled')
            OR status_reason IS NOT NULL
        )
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_pipeline_stage_attempts_run_order ON pipeline_stage_attempts (pipeline_run_id, stage_order)",
    "CREATE INDEX IF NOT EXISTS ix_pipeline_stage_attempts_deployment_id ON pipeline_stage_attempts (deployment_id)",
    "CREATE INDEX IF NOT EXISTS ix_pipeline_stage_attempts_status ON pipeline_stage_attempts (status)",
    f"""
    CREATE TABLE IF NOT EXISTS repository_analysis_snapshots (
        id UUID PRIMARY KEY,
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        deployment_id UUID REFERENCES deployments(id) ON DELETE SET NULL,
        pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL,
        reused_from_snapshot_id UUID REFERENCES repository_analysis_snapshots(id) ON DELETE SET NULL,
        idempotency_key VARCHAR(128) NOT NULL,
        source_revision VARCHAR(64) NOT NULL,
        repository_fingerprint VARCHAR(64) NOT NULL,
        architecture_fingerprint VARCHAR(64) NOT NULL,
        dependency_files_hash VARCHAR(64) NOT NULL,
        dockerfile_hash VARCHAR(64) NOT NULL,
        infrastructure_files_hash VARCHAR(64) NOT NULL,
        kubernetes_manifests_hash VARCHAR(64) NOT NULL,
        important_configuration_files_hash VARCHAR(64) NOT NULL,
        fingerprint_version VARCHAR(64) NOT NULL,
        analyzer_version VARCHAR(64) NOT NULL,
        analysis_mode VARCHAR(16) NOT NULL DEFAULT 'deterministic',
        status VARCHAR(16) NOT NULL DEFAULT 'queued',
        ai_required BOOLEAN NOT NULL DEFAULT FALSE,
        ai_used BOOLEAN NOT NULL DEFAULT FALSE,
        application_framework TEXT,
        detected_services JSONB NOT NULL DEFAULT '[]'::jsonb,
        environment_variable_names JSONB NOT NULL DEFAULT '[]'::jsonb,
        summary JSONB NOT NULL DEFAULT '{{}}'::jsonb,
        evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
        error_code VARCHAR(64),
        redacted_error TEXT,
        started_at TIMESTAMPTZ,
        completed_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT uq_repository_snapshots_tenant_idempotency UNIQUE (tenant_id, idempotency_key),
        CONSTRAINT uq_repository_snapshots_revision_fingerprint
            UNIQUE (tenant_id, project_id, source_revision, repository_fingerprint),
        CONSTRAINT ck_repository_snapshots_analysis_mode
            CHECK (analysis_mode IN ('deterministic', 'model', 'reused')),
        CONSTRAINT ck_repository_snapshots_status CHECK (status IN ({EXECUTION_STATUSES_SQL})),
        CONSTRAINT ck_repository_snapshots_repository_fingerprint
            CHECK (repository_fingerprint ~ '^[0-9a-f]{{64}}$'),
        CONSTRAINT ck_repository_snapshots_architecture_fingerprint
            CHECK (architecture_fingerprint ~ '^[0-9a-f]{{64}}$'),
        CONSTRAINT ck_repository_snapshots_dependency_hash
            CHECK (dependency_files_hash ~ '^[0-9a-f]{{64}}$'),
        CONSTRAINT ck_repository_snapshots_dockerfile_hash
            CHECK (dockerfile_hash ~ '^[0-9a-f]{{64}}$'),
        CONSTRAINT ck_repository_snapshots_infrastructure_hash
            CHECK (infrastructure_files_hash ~ '^[0-9a-f]{{64}}$'),
        CONSTRAINT ck_repository_snapshots_kubernetes_hash
            CHECK (kubernetes_manifests_hash ~ '^[0-9a-f]{{64}}$'),
        CONSTRAINT ck_repository_snapshots_configuration_hash
            CHECK (important_configuration_files_hash ~ '^[0-9a-f]{{64}}$')
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_repository_snapshots_project_created ON repository_analysis_snapshots (project_id, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_repository_snapshots_architecture_fingerprint ON repository_analysis_snapshots (architecture_fingerprint)",
    f"""
    CREATE TABLE IF NOT EXISTS change_analyses (
        id UUID PRIMARY KEY,
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        deployment_id UUID REFERENCES deployments(id) ON DELETE SET NULL,
        pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL,
        baseline_snapshot_id UUID REFERENCES repository_analysis_snapshots(id) ON DELETE SET NULL,
        idempotency_key VARCHAR(128) NOT NULL,
        baseline_revision VARCHAR(64),
        target_revision VARCHAR(64) NOT NULL,
        changed_paths_digest VARCHAR(64) NOT NULL,
        change_fingerprint VARCHAR(64) NOT NULL,
        classifier_version VARCHAR(64) NOT NULL,
        status VARCHAR(16) NOT NULL DEFAULT 'queued',
        changed_file_count INTEGER NOT NULL DEFAULT 0,
        application_source_changed BOOLEAN NOT NULL DEFAULT FALSE,
        dependencies_changed BOOLEAN NOT NULL DEFAULT FALSE,
        deployment_config_changed BOOLEAN NOT NULL DEFAULT FALSE,
        infrastructure_changed BOOLEAN NOT NULL DEFAULT FALSE,
        kubernetes_changed BOOLEAN NOT NULL DEFAULT FALSE,
        security_policy_changed BOOLEAN NOT NULL DEFAULT FALSE,
        architecture_changed BOOLEAN NOT NULL DEFAULT FALSE,
        documentation_only BOOLEAN NOT NULL DEFAULT FALSE,
        deployment_relevant BOOLEAN NOT NULL DEFAULT FALSE,
        repository_ai_required BOOLEAN NOT NULL DEFAULT FALSE,
        decision_reason TEXT NOT NULL,
        category_counts JSONB NOT NULL DEFAULT '{{}}'::jsonb,
        sampled_paths JSONB NOT NULL DEFAULT '[]'::jsonb,
        error_code VARCHAR(64),
        redacted_error TEXT,
        started_at TIMESTAMPTZ,
        completed_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT uq_change_analyses_tenant_idempotency UNIQUE (tenant_id, idempotency_key),
        CONSTRAINT ck_change_analyses_file_count CHECK (changed_file_count >= 0),
        CONSTRAINT ck_change_analyses_status CHECK (status IN ({EXECUTION_STATUSES_SQL})),
        CONSTRAINT ck_change_analyses_paths_digest CHECK (changed_paths_digest ~ '^[0-9a-f]{{64}}$'),
        CONSTRAINT ck_change_analyses_fingerprint CHECK (change_fingerprint ~ '^[0-9a-f]{{64}}$')
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_change_analyses_project_created ON change_analyses (project_id, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_change_analyses_pipeline_run_id ON change_analyses (pipeline_run_id)",
    "CREATE INDEX IF NOT EXISTS ix_change_analyses_target_fingerprint ON change_analyses (tenant_id, project_id, target_revision, change_fingerprint)",
    f"""
    CREATE TABLE IF NOT EXISTS security_scans (
        id UUID PRIMARY KEY,
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        deployment_id UUID REFERENCES deployments(id) ON DELETE SET NULL,
        pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL,
        stage_attempt_id UUID REFERENCES pipeline_stage_attempts(id) ON DELETE SET NULL,
        result_artifact_id UUID REFERENCES artifacts(id) ON DELETE SET NULL,
        idempotency_key VARCHAR(128) NOT NULL,
        scan_type VARCHAR(32) NOT NULL,
        status VARCHAR(16) NOT NULL DEFAULT 'queued',
        policy_status VARCHAR(16) NOT NULL DEFAULT 'pending',
        blocking_enabled BOOLEAN NOT NULL DEFAULT TRUE,
        tool_name VARCHAR(128) NOT NULL,
        tool_version VARCHAR(128),
        target_kind VARCHAR(32) NOT NULL,
        target_revision VARCHAR(128),
        target_digest VARCHAR(64),
        finding_count INTEGER NOT NULL DEFAULT 0,
        critical_count INTEGER NOT NULL DEFAULT 0,
        high_count INTEGER NOT NULL DEFAULT 0,
        medium_count INTEGER NOT NULL DEFAULT 0,
        low_count INTEGER NOT NULL DEFAULT 0,
        info_count INTEGER NOT NULL DEFAULT 0,
        result_digest VARCHAR(64),
        error_code VARCHAR(64),
        redacted_error TEXT,
        summary JSONB NOT NULL DEFAULT '{{}}'::jsonb,
        started_at TIMESTAMPTZ,
        completed_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT uq_security_scans_tenant_idempotency UNIQUE (tenant_id, idempotency_key),
        CONSTRAINT ck_security_scans_type
            CHECK (scan_type IN ('sast', 'dependency', 'secret', 'container', 'iac', 'kubernetes', 'sbom')),
        CONSTRAINT ck_security_scans_status CHECK (status IN ({EXECUTION_STATUSES_SQL})),
        CONSTRAINT ck_security_scans_policy_status
            CHECK (policy_status IN ('pending', 'passed', 'warning', 'blocked', 'unavailable')),
        CONSTRAINT ck_security_scans_counts CHECK (
            finding_count >= 0 AND critical_count >= 0 AND high_count >= 0
            AND medium_count >= 0 AND low_count >= 0 AND info_count >= 0
        ),
        CONSTRAINT ck_security_scans_target_digest
            CHECK (target_digest IS NULL OR target_digest ~ '^[0-9a-f]{{64}}$'),
        CONSTRAINT ck_security_scans_result_digest
            CHECK (result_digest IS NULL OR result_digest ~ '^[0-9a-f]{{64}}$')
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_security_scans_project_created ON security_scans (project_id, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_security_scans_pipeline_type ON security_scans (pipeline_run_id, scan_type)",
    "CREATE INDEX IF NOT EXISTS ix_security_scans_status ON security_scans (status)",
    """
    CREATE TABLE IF NOT EXISTS security_findings (
        id UUID PRIMARY KEY,
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        deployment_id UUID REFERENCES deployments(id) ON DELETE SET NULL,
        security_scan_id UUID NOT NULL REFERENCES security_scans(id) ON DELETE CASCADE,
        fingerprint VARCHAR(64) NOT NULL,
        rule_id VARCHAR(256) NOT NULL,
        category VARCHAR(64) NOT NULL,
        severity VARCHAR(16) NOT NULL,
        status VARCHAR(16) NOT NULL DEFAULT 'open',
        title TEXT NOT NULL,
        description TEXT,
        remediation TEXT,
        location_path TEXT,
        line_start INTEGER,
        line_end INTEGER,
        package_name TEXT,
        package_version TEXT,
        fixed_version TEXT,
        is_blocking BOOLEAN NOT NULL DEFAULT FALSE,
        masked_evidence TEXT,
        evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        resolved_at TIMESTAMPTZ,
        CONSTRAINT uq_security_findings_scan_fingerprint UNIQUE (security_scan_id, fingerprint),
        CONSTRAINT ck_security_findings_severity
            CHECK (severity IN ('critical', 'high', 'medium', 'low', 'info')),
        CONSTRAINT ck_security_findings_status
            CHECK (status IN ('open', 'accepted_risk', 'resolved', 'false_positive')),
        CONSTRAINT ck_security_findings_line_start CHECK (line_start IS NULL OR line_start >= 1),
        CONSTRAINT ck_security_findings_line_end
            CHECK (line_end IS NULL OR (line_start IS NOT NULL AND line_end >= line_start)),
        CONSTRAINT ck_security_findings_fingerprint CHECK (fingerprint ~ '^[0-9a-f]{64}$')
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_security_findings_project_severity ON security_findings (project_id, severity)",
    "CREATE INDEX IF NOT EXISTS ix_security_findings_scan_id ON security_findings (security_scan_id)",
    f"""
    CREATE TABLE IF NOT EXISTS webhook_deliveries (
        id UUID PRIMARY KEY,
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        deployment_id UUID REFERENCES deployments(id) ON DELETE SET NULL,
        pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL,
        provider VARCHAR(32) NOT NULL DEFAULT 'github',
        external_delivery_id VARCHAR(128) NOT NULL,
        event_type VARCHAR(64) NOT NULL,
        event_action VARCHAR(64),
        signature_status VARCHAR(16) NOT NULL DEFAULT 'unverified',
        status VARCHAR(16) NOT NULL DEFAULT 'queued',
        repository_external_id VARCHAR(128),
        branch TEXT,
        source_revision VARCHAR(64),
        payload_digest VARCHAR(64) NOT NULL,
        attempt_count INTEGER NOT NULL DEFAULT 0,
        failure_code VARCHAR(64),
        redacted_error TEXT,
        received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        validated_at TIMESTAMPTZ,
        processed_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT uq_webhook_deliveries_provider_delivery
            UNIQUE (tenant_id, provider, external_delivery_id),
        CONSTRAINT ck_webhook_deliveries_signature_status
            CHECK (signature_status IN ('unverified', 'verified', 'invalid', 'unavailable')),
        CONSTRAINT ck_webhook_deliveries_status CHECK (status IN ({EXECUTION_STATUSES_SQL})),
        CONSTRAINT ck_webhook_deliveries_attempt_count CHECK (attempt_count >= 0),
        CONSTRAINT ck_webhook_deliveries_payload_digest CHECK (payload_digest ~ '^[0-9a-f]{{64}}$')
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_webhook_deliveries_project_received ON webhook_deliveries (project_id, received_at)",
    "CREATE INDEX IF NOT EXISTS ix_webhook_deliveries_status ON webhook_deliveries (status)",
    """
    CREATE TABLE IF NOT EXISTS incidents (
        id UUID PRIMARY KEY,
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        deployment_id UUID REFERENCES deployments(id) ON DELETE SET NULL,
        pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL,
        stage_attempt_id UUID REFERENCES pipeline_stage_attempts(id) ON DELETE SET NULL,
        acknowledged_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
        resolved_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
        idempotency_key VARCHAR(128) NOT NULL,
        status VARCHAR(16) NOT NULL DEFAULT 'open',
        severity VARCHAR(16) NOT NULL,
        detection_source VARCHAR(64) NOT NULL,
        rule_key VARCHAR(128) NOT NULL,
        title TEXT NOT NULL,
        redacted_summary TEXT NOT NULL,
        evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
        first_observed_at TIMESTAMPTZ NOT NULL,
        last_observed_at TIMESTAMPTZ NOT NULL,
        acknowledged_at TIMESTAMPTZ,
        mitigated_at TIMESTAMPTZ,
        resolved_at TIMESTAMPTZ,
        closed_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT uq_incidents_tenant_idempotency UNIQUE (tenant_id, idempotency_key),
        CONSTRAINT ck_incidents_status
            CHECK (status IN ('open', 'investigating', 'mitigated', 'resolved', 'dismissed')),
        CONSTRAINT ck_incidents_severity
            CHECK (severity IN ('critical', 'high', 'medium', 'low', 'info')),
        CONSTRAINT ck_incidents_observed_order CHECK (last_observed_at >= first_observed_at)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_incidents_project_status ON incidents (project_id, status)",
    "CREATE INDEX IF NOT EXISTS ix_incidents_deployment_id ON incidents (deployment_id)",
    "CREATE INDEX IF NOT EXISTS ix_incidents_last_observed ON incidents (tenant_id, last_observed_at)",
    f"""
    CREATE TABLE IF NOT EXISTS ai_investigations (
        id UUID PRIMARY KEY,
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        deployment_id UUID REFERENCES deployments(id) ON DELETE SET NULL,
        pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL,
        stage_attempt_id UUID REFERENCES pipeline_stage_attempts(id) ON DELETE SET NULL,
        incident_id UUID REFERENCES incidents(id) ON DELETE SET NULL,
        requested_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
        idempotency_key VARCHAR(128) NOT NULL,
        trigger_type VARCHAR(32) NOT NULL,
        failed_stage_key VARCHAR(64),
        status VARCHAR(16) NOT NULL DEFAULT 'queued',
        model_provider VARCHAR(64) NOT NULL,
        model_name VARCHAR(128) NOT NULL,
        model_version VARCHAR(128),
        prompt_version VARCHAR(64) NOT NULL,
        evidence_digest VARCHAR(64) NOT NULL,
        evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
        failure_summary TEXT,
        root_cause TEXT,
        severity VARCHAR(16),
        recommended_fix TEXT,
        resolution_steps JSONB NOT NULL DEFAULT '[]'::jsonb,
        confidence INTEGER,
        safe_action_available BOOLEAN NOT NULL DEFAULT FALSE,
        requires_user_action BOOLEAN NOT NULL DEFAULT TRUE,
        input_tokens INTEGER,
        output_tokens INTEGER,
        model_cost_microusd BIGINT,
        error_code VARCHAR(64),
        redacted_error TEXT,
        started_at TIMESTAMPTZ,
        completed_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT uq_ai_investigations_tenant_idempotency UNIQUE (tenant_id, idempotency_key),
        CONSTRAINT ck_ai_investigations_trigger_type CHECK (
            trigger_type IN ('pipeline_failure', 'security_failure', 'terraform_failure',
                'test_failure', 'incident', 'architecture_change', 'manual')
        ),
        CONSTRAINT ck_ai_investigations_status CHECK (status IN ({EXECUTION_STATUSES_SQL})),
        CONSTRAINT ck_ai_investigations_severity CHECK (
            severity IS NULL OR severity IN ('critical', 'high', 'medium', 'low', 'info')
        ),
        CONSTRAINT ck_ai_investigations_confidence
            CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 100)),
        CONSTRAINT ck_ai_investigations_evidence_digest CHECK (evidence_digest ~ '^[0-9a-f]{{64}}$')
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_ai_investigations_project_created ON ai_investigations (project_id, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_ai_investigations_incident_id ON ai_investigations (incident_id)",
    "CREATE INDEX IF NOT EXISTS ix_ai_investigations_pipeline_run_id ON ai_investigations (pipeline_run_id)",
    """
    CREATE TABLE IF NOT EXISTS remediation_proposals (
        id UUID PRIMARY KEY,
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        deployment_id UUID REFERENCES deployments(id) ON DELETE SET NULL,
        incident_id UUID REFERENCES incidents(id) ON DELETE SET NULL,
        investigation_id UUID REFERENCES ai_investigations(id) ON DELETE SET NULL,
        parameter_artifact_id UUID REFERENCES artifacts(id) ON DELETE SET NULL,
        proposed_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
        decided_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
        idempotency_key VARCHAR(128) NOT NULL,
        action_type VARCHAR(128) NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        risk_tier VARCHAR(16) NOT NULL,
        status VARCHAR(24) NOT NULL DEFAULT 'proposed',
        approval_required BOOLEAN NOT NULL DEFAULT TRUE,
        parameter_digest VARCHAR(64) NOT NULL,
        redacted_parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
        rationale TEXT NOT NULL,
        expires_at TIMESTAMPTZ,
        decided_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT uq_remediation_proposals_tenant_idempotency UNIQUE (tenant_id, idempotency_key),
        CONSTRAINT ck_remediation_proposals_risk_tier CHECK (risk_tier IN ('low', 'medium', 'high')),
        CONSTRAINT ck_remediation_proposals_status CHECK (
            status IN ('proposed', 'pending_approval', 'approved', 'denied',
                'expired', 'cancelled', 'executed')
        ),
        CONSTRAINT ck_remediation_proposals_high_risk_approval
            CHECK (risk_tier <> 'high' OR approval_required),
        CONSTRAINT ck_remediation_proposals_decision_actor CHECK (
            status NOT IN ('approved', 'denied') OR
            (decided_by_user_id IS NOT NULL AND decided_at IS NOT NULL)
        ),
        CONSTRAINT ck_remediation_proposals_parameter_digest
            CHECK (parameter_digest ~ '^[0-9a-f]{64}$')
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_remediation_proposals_project_status ON remediation_proposals (project_id, status)",
    "CREATE INDEX IF NOT EXISTS ix_remediation_proposals_incident_id ON remediation_proposals (incident_id)",
    f"""
    CREATE TABLE IF NOT EXISTS remediation_executions (
        id UUID PRIMARY KEY,
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        deployment_id UUID REFERENCES deployments(id) ON DELETE SET NULL,
        incident_id UUID REFERENCES incidents(id) ON DELETE SET NULL,
        proposal_id UUID NOT NULL REFERENCES remediation_proposals(id) ON DELETE CASCADE,
        requested_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
        result_artifact_id UUID REFERENCES artifacts(id) ON DELETE SET NULL,
        idempotency_key VARCHAR(128) NOT NULL,
        attempt_number INTEGER NOT NULL DEFAULT 1,
        executor_kind VARCHAR(32) NOT NULL,
        executor_name VARCHAR(128) NOT NULL,
        status VARCHAR(16) NOT NULL DEFAULT 'queued',
        verification_status VARCHAR(16) NOT NULL DEFAULT 'queued',
        result_summary TEXT,
        evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
        failure_code VARCHAR(64),
        redacted_error TEXT,
        started_at TIMESTAMPTZ,
        completed_at TIMESTAMPTZ,
        verified_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT uq_remediation_executions_tenant_idempotency UNIQUE (tenant_id, idempotency_key),
        CONSTRAINT uq_remediation_executions_proposal_attempt UNIQUE (proposal_id, attempt_number),
        CONSTRAINT ck_remediation_executions_attempt_number CHECK (attempt_number >= 1),
        CONSTRAINT ck_remediation_executions_executor_kind
            CHECK (executor_kind IN ('deterministic', 'operator', 'automation')),
        CONSTRAINT ck_remediation_executions_status CHECK (status IN ({EXECUTION_STATUSES_SQL})),
        CONSTRAINT ck_remediation_executions_verification_status
            CHECK (verification_status IN ({EXECUTION_STATUSES_SQL}))
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_remediation_executions_project_status ON remediation_executions (project_id, status)",
    "CREATE INDEX IF NOT EXISTS ix_remediation_executions_incident_id ON remediation_executions (incident_id)",
]

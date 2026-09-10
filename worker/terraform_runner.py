"""Run queued releases through the production Azure deployment pipeline.

The old worker manufactured build, health-check, and live-URL success results.
This adapter intentionally delegates to the same pipeline used by the control
plane so a release is only marked running after Azure reports it ready and its
public endpoint has been verified.
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from datetime import datetime
from types import SimpleNamespace
from typing import Any, Callable

import psycopg2
from psycopg2.extras import Json, RealDictCursor

try:
    from backend.contracts.workflow import canonical_digest
    from backend.services import deployment_targets, github_oauth, pipeline, terraform_generator
    from backend.services.redaction import redact_sensitive_text
    from worker.job_queue import postgres_connection_kwargs
except ImportError:
    from contracts.workflow import canonical_digest
    from services import deployment_targets, github_oauth, pipeline, terraform_generator
    from services.redaction import redact_sensitive_text
    from job_queue import postgres_connection_kwargs


_ARTIFACT_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_GITHUB_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_ALLOWED_RESOURCE_KINDS = {
    "azurerm_application_insights",
    "azurerm_container_app",
    "azurerm_container_app_environment",
    "azurerm_key_vault",
    "azurerm_linux_web_app",
    "azurerm_postgresql_flexible_server",
    "azurerm_storage_account",
    "azurerm_virtual_network",
}


def _json_mapping(value: Any, *, label: str) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as error:
            raise RuntimeError(f"{label} is invalid.") from error
        if isinstance(parsed, dict):
            return parsed
    raise RuntimeError(f"{label} is invalid.")


def _canonical_uuid_text(value: Any, *, label: str) -> str:
    try:
        parsed = uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as error:
        raise RuntimeError(f"{label} is invalid.") from error
    canonical = str(parsed)
    if str(value) != canonical:
        raise RuntimeError(f"{label} is invalid.")
    return canonical


def _pipeline_job_outcome(record: dict[str, Any] | None) -> str:
    """Classify durable pipeline completion without inventing deployment success."""

    if not record:
        return "failed"
    deployment_status = record.get("status")
    pipeline_status = record.get("pipeline_status")
    failure_code = record.get("pipeline_failure_code")
    if deployment_status == "running" and pipeline_status in {None, "succeeded"}:
        return "deployed"
    if deployment_status == "stopped" and pipeline_status == "succeeded":
        return "validation_completed"
    if (
        deployment_status == "stopped"
        and pipeline_status == "blocked"
        and failure_code == "DEPLOYMENT_APPROVAL_REQUIRED"
    ):
        return "approval_required"
    return "failed"


def _safe_internal_iac_metadata(generated: dict[str, Any], queued_spec: dict[str, Any]) -> dict[str, Any]:
    """Allow only non-secret artifact descriptors into deployment metadata."""
    if not isinstance(generated, dict):
        raise RuntimeError("The internal artifact generator returned invalid metadata.")

    digest = generated.get("artifact_sha256")
    if not isinstance(digest, str) or not _ARTIFACT_DIGEST_PATTERN.fullmatch(digest):
        raise RuntimeError("The internal artifact generator returned an invalid digest.")

    generated_at = generated.get("generated_at")
    if not isinstance(generated_at, str):
        raise RuntimeError("The internal artifact generator returned an invalid timestamp.")
    try:
        datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise RuntimeError("The internal artifact generator returned an invalid timestamp.") from error

    resource_kinds = generated.get("resource_kinds") or []
    if not isinstance(resource_kinds, list):
        raise RuntimeError("The internal artifact generator returned invalid resource metadata.")
    safe_resource_kinds = sorted({
        resource_kind
        for resource_kind in resource_kinds
        if isinstance(resource_kind, str) and resource_kind in _ALLOWED_RESOURCE_KINDS
    })

    revision = queued_spec.get("revision")
    if not isinstance(revision, int):
        revision = None

    # Fixed values make the boundary explicit: a file was generated for
    # internal use, while Terraform plan/apply were not invoked.
    return {
        "engine": "terraform",
        "status": "generated",
        "execution": "not_run",
        "artifact_sha256": digest,
        "generated_at": generated_at,
        "resource_kinds": safe_resource_kinds,
        "plan_revision": revision,
    }


class TerraformRunner:
    """Compatibility name for the worker's real deployment-pipeline runner."""

    def __init__(
        self,
        db_url: str,
        worker_id: str | None = None,
        *,
        ssl_enabled: bool = False,
        ssl_verify: bool = True,
        ssl_root_cert: str | None = None,
    ):
        self.db_url = db_url.replace("postgresql+asyncpg://", "postgresql://", 1)
        self.worker_id = worker_id
        self.connection_kwargs = postgres_connection_kwargs(
            ssl_enabled=ssl_enabled,
            ssl_verify=ssl_verify,
            ssl_root_cert=ssl_root_cert,
        )

    def _get_connection(self):
        return psycopg2.connect(self.db_url, **self.connection_kwargs)

    @staticmethod
    def _lease_identity(job: dict[str, Any]) -> tuple[str, str]:
        worker_id = job.get("worker_id")
        lease_token = job.get("lease_token")
        if not isinstance(worker_id, str) or not worker_id:
            raise RuntimeError("Deployment job is missing its worker identity.")
        if not isinstance(lease_token, str) or not lease_token:
            raise RuntimeError("Deployment job is missing its lease token.")
        return worker_id, lease_token

    def _load_pipeline_input(
        self,
        connection,
        job: dict[str, Any],
    ) -> tuple[str, str, str, str | None]:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT
                    p.full_name,
                    p.source_type,
                    d.branch,
                    d.commit_sha,
                    u.github_access_token_encrypted
                FROM projects p
                JOIN users u ON u.id = p.user_id
                JOIN deployments d
                  ON d.id = %s
                 AND d.project_id = p.id
                 AND d.user_id = p.user_id
                WHERE p.id = %s AND p.user_id = %s
                """,
                (job["deployment_id"], job["project_id"], job["user_id"]),
            )
            project = cursor.fetchone()
        if not project:
            raise RuntimeError("The deployment project is no longer available to this worker.")
        if project.get("source_type") != "github":
            raise RuntimeError(
                "Isolated deployment workers require durable GitHub source. "
                "Uploaded source is not queueable without shared storage."
            )
        branch = project.get("branch")
        commit_sha = str(project.get("commit_sha") or "").lower()
        if not isinstance(branch, str) or not branch:
            raise RuntimeError("The deployment has no saved source branch.")
        if not _GITHUB_COMMIT_PATTERN.fullmatch(commit_sha):
            raise RuntimeError("The deployment has no verified immutable Git commit.")

        clone_token = None
        encrypted_token = project.get("github_access_token_encrypted")
        if encrypted_token:
            clone_token = github_oauth.decrypt_token(encrypted_token)
        if not clone_token:
            raise RuntimeError("The GitHub connection must be restored before this deployment can run.")
        return project["full_name"], branch, commit_sha, clone_token

    def _mark_job(
        self,
        connection,
        job: dict[str, Any],
        *,
        status: str,
        failure_reason: str | None = None,
        live_url: str | None = None,
        deployment_completed: bool = True,
    ) -> bool:
        worker_id, lease_token = self._lease_identity(job)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE deployment_jobs
                SET status = %s,
                    failure_reason = %s,
                    deployment_status = CASE
                        WHEN %s = 'completed' AND %s THEN 'completed'
                        WHEN %s = 'failed' THEN 'failed'
                        ELSE deployment_status
                    END,
                    live_url = COALESCE(%s, live_url),
                    completed_at = CASE WHEN %s IN ('completed', 'failed') THEN NOW() ELSE completed_at END,
                    worker_id = CASE WHEN %s IN ('completed', 'failed') THEN NULL ELSE worker_id END,
                    lease_token = CASE WHEN %s IN ('completed', 'failed') THEN NULL ELSE lease_token END,
                    lease_expires_at = CASE WHEN %s IN ('completed', 'failed') THEN NULL ELSE lease_expires_at END,
                    heartbeat_at = CASE WHEN %s IN ('completed', 'failed') THEN NULL ELSE heartbeat_at END,
                    updated_at = NOW()
                WHERE id = %s
                  AND status = 'running'
                  AND worker_id = %s
                  AND lease_token = %s
                """,
                (
                    status,
                    failure_reason,
                    status,
                    deployment_completed,
                    status,
                    live_url,
                    status,
                    status,
                    status,
                    status,
                    status,
                    str(job["id"]),
                    worker_id,
                    lease_token,
                ),
            )
            return cursor.rowcount == 1

    def _require_completed_terraform_apply(
        self,
        connection,
        job: dict[str, Any],
    ) -> dict[str, Any]:
        """Revalidate the exact applied plan before any cloud side effect."""

        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT
                    d.terraform_operation_run_id,
                    d.infrastructure_metadata,
                    pipeline_binding.tenant_id AS deployment_tenant_id,
                    ip.id AS plan_id,
                    ip.project_id AS plan_project_id,
                    ip.user_id AS plan_user_id,
                    ip.provider AS plan_provider,
                    ip.region AS plan_region,
                    ip.status AS plan_status,
                    ip.revision AS plan_revision,
                    ip.plan_data,
                    ip.cost_estimate AS plan_cost_estimate,
                    az.tenant_id AS azure_tenant_id,
                    az.subscription_id AS azure_subscription_id,
                    az.client_id AS azure_client_id,
                    az.connection_status AS azure_connection_status,
                    az.region AS azure_region,
                    az.resource_group AS azure_resource_group,
                    az.acr_login_server AS azure_acr_login_server,
                    az.app_service_plan AS azure_app_service_plan,
                    az.deployment_target_fingerprint,
                    az.deployment_target_verified_at,
                    az.namespace_prefix AS azure_namespace_prefix,
                    az.is_active AS azure_is_active
                FROM deployments AS d
                JOIN infrastructure_plans AS ip
                  ON ip.project_id = d.project_id
                 AND ip.user_id = d.user_id
                JOIN LATERAL (
                    SELECT tenant_id
                    FROM pipeline_runs
                    WHERE deployment_id = d.id
                    ORDER BY created_at DESC, id DESC
                    LIMIT 1
                ) AS pipeline_binding ON TRUE
                JOIN user_azure_connections AS az
                  ON az.user_id = d.user_id
                 AND az.is_active = TRUE
                WHERE d.id = %s
                  AND d.project_id = %s
                  AND d.user_id = %s
                  AND d.status = 'queued'
                  AND ip.status = 'approved'
                  AND az.connection_status = 'connected'
                ORDER BY az.updated_at DESC, az.id DESC
                LIMIT 1
                """,
                (str(job["deployment_id"]), str(job["project_id"]), str(job["user_id"])),
            )
            current = cursor.fetchone()
        if not current:
            raise RuntimeError(
                "Deployment is blocked because its approved plan or verified Azure target changed."
            )

        metadata = _json_mapping(
            current.get("infrastructure_metadata"),
            label="Deployment infrastructure metadata",
        )
        if (
            metadata.get("app_service_reused") is True
            or metadata.get("terraform_apply_required") is False
        ):
            if current.get("terraform_operation_run_id") is not None:
                raise RuntimeError("Deployment has unexpected Terraform operation binding.")
            return {
                "app_service_reused": True,
                "plan_id": str(current["plan_id"]),
                "plan_revision": current["plan_revision"],
            }

        proof = _json_mapping(
            metadata.get("terraform_apply"),
            label="Terraform apply proof",
        )
        expected_proof_fields = {
            "schema_version",
            "operation_run_id",
            "approval_id",
            "apply_job_id",
            "approved_plan_digest",
            "plan_job_digest",
            "plan_sha256",
            "bundle_sha256",
            "target_fingerprint",
            "completion_event_id",
            "completed_at",
        }
        if set(proof) != expected_proof_fields or proof.get("schema_version") != "terraform-apply-proof.v1":
            raise RuntimeError("Deployment has no exact completed Terraform apply proof.")
        operation_run_id = _canonical_uuid_text(
            proof.get("operation_run_id"),
            label="Terraform operation binding",
        )
        approval_id = _canonical_uuid_text(
            proof.get("approval_id"),
            label="Terraform approval binding",
        )
        apply_job_id = _canonical_uuid_text(
            proof.get("apply_job_id"),
            label="Terraform apply job binding",
        )
        if str(current.get("terraform_operation_run_id") or "") != operation_run_id:
            raise RuntimeError("Deployment Terraform operation binding is inconsistent.")
        for field in (
            "approved_plan_digest",
            "plan_job_digest",
            "plan_sha256",
            "bundle_sha256",
            "target_fingerprint",
        ):
            if not isinstance(proof.get(field), str) or not _ARTIFACT_DIGEST_PATTERN.fullmatch(proof[field]):
                raise RuntimeError("Deployment Terraform digest proof is invalid.")
        completion_event_id = str(proof.get("completion_event_id") or "")
        if not completion_event_id or len(completion_event_id) > 128:
            raise RuntimeError("Deployment Terraform completion proof is invalid.")
        try:
            completed_at = datetime.fromisoformat(str(proof.get("completed_at")).replace("Z", "+00:00"))
        except (TypeError, ValueError) as error:
            raise RuntimeError("Deployment Terraform completion timestamp is invalid.") from error
        if completed_at.tzinfo is None or completed_at.utcoffset() is None:
            raise RuntimeError("Deployment Terraform completion timestamp is invalid.")

        plan_data = _json_mapping(current.get("plan_data"), label="Approved infrastructure plan")
        plan_cost = current.get("plan_cost_estimate")
        if isinstance(plan_cost, str):
            try:
                plan_cost = json.loads(plan_cost)
            except json.JSONDecodeError as error:
                raise RuntimeError("Approved infrastructure cost record is invalid.") from error
        current_plan_digest = canonical_digest(
            {
                "id": str(current["plan_id"]),
                "project_id": str(current["plan_project_id"]),
                "provider": current["plan_provider"],
                "region": current["plan_region"],
                "status": current["plan_status"],
                "revision": current["plan_revision"],
                "plan": plan_data,
                "cost_estimate": plan_cost,
            }
        )
        architecture = _json_mapping(
            metadata.get("architecture_plan"),
            label="Deployment architecture binding",
        )
        if (
            proof["approved_plan_digest"] != current_plan_digest
            or architecture.get("id") != str(current["plan_id"])
            or architecture.get("revision") != current["plan_revision"]
        ):
            raise RuntimeError("Deployment plan changed after the exact Terraform apply.")

        azure_connection = SimpleNamespace(
            tenant_id=current["azure_tenant_id"],
            subscription_id=current["azure_subscription_id"],
            client_id=current["azure_client_id"],
            connection_status=current["azure_connection_status"],
            region=current["azure_region"],
            resource_group=current["azure_resource_group"],
            acr_login_server=current["azure_acr_login_server"],
            app_service_plan=current["azure_app_service_plan"],
            deployment_target_fingerprint=current["deployment_target_fingerprint"],
            deployment_target_verified_at=current["deployment_target_verified_at"],
            namespace_prefix=current["azure_namespace_prefix"],
            is_active=current["azure_is_active"],
        )
        if (
            not deployment_targets.has_verified_app_service_target(azure_connection)
            or proof["target_fingerprint"] != current["deployment_target_fingerprint"]
        ):
            raise RuntimeError("Deployment Azure target changed after the exact Terraform apply.")

        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT
                    operation_runs.input_digest,
                    operation_runs.tenant_id AS operation_tenant_id,
                    operation_runs.status AS operation_status,
                    operation_runs.summary,
                    terraform_plan_results.plan_job_digest,
                    terraform_plan_results.tenant_id AS plan_tenant_id,
                    terraform_plan_results.revision AS terraform_revision,
                    terraform_plan_results.bundle,
                    terraform_plan_results.input_variables,
                    terraform_plan_results.guardrails,
                    terraform_plan_results.saved_plan,
                    terraform_plan_results.cost_estimate,
                    terraform_apply_approvals.id AS approval_id,
                    terraform_apply_approvals.tenant_id AS approval_tenant_id,
                    terraform_apply_approvals.apply_job_id,
                    terraform_apply_approvals.status AS approval_status,
                    terraform_apply_approvals.plan_job_digest AS approved_plan_job_digest,
                    terraform_apply_approvals.plan_sha256 AS approved_plan_sha256,
                    terraform_apply_approvals.bundle_sha256 AS approved_bundle_sha256,
                    terraform_apply_approvals.input_variables_sha256 AS approved_input_variables_sha256,
                    terraform_apply_approvals.scope_digest AS approved_scope_digest,
                    terraform_apply_approvals.policy_digest AS approved_policy_digest,
                    terraform_apply_approvals.cost_estimate_sha256 AS approved_cost_estimate_sha256,
                    terraform_apply_approvals.currency AS approved_currency,
                    terraform_apply_approvals.monthly_cost_microunits AS approved_monthly_cost_microunits,
                    activity_events.event_data,
                    activity_events.tenant_id AS event_tenant_id,
                    activity_events.external_event_id,
                    activity_events.event_fingerprint
                FROM operation_runs
                JOIN terraform_plan_results
                  ON terraform_plan_results.operation_run_id = operation_runs.id
                JOIN terraform_apply_approvals
                  ON terraform_apply_approvals.operation_run_id = operation_runs.id
                JOIN activity_events
                  ON activity_events.operation_run_id = operation_runs.id
                WHERE operation_runs.id = %s
                  AND operation_runs.project_id = %s
                  AND operation_runs.requested_by_user_id = %s
                  AND operation_runs.operation_type = 'infrastructure_pipeline'
                  AND operation_runs.status = 'completed'
                  AND operation_runs.tenant_id = %s
                  AND terraform_plan_results.tenant_id = %s
                  AND terraform_apply_approvals.tenant_id = %s
                  AND activity_events.tenant_id = %s
                  AND terraform_plan_results.project_id = %s
                  AND terraform_apply_approvals.project_id = %s
                  AND terraform_apply_approvals.approved_by_user_id = %s
                  AND activity_events.project_id = %s
                  AND activity_events.action = 'terraform.apply.completed'
                  AND activity_events.actor_type = 'vmss'
                  AND activity_events.actor_id = 'terraform-executor'
                  AND activity_events.external_event_id = %s
                LIMIT 1
                """,
                (
                    operation_run_id,
                    str(job["project_id"]),
                    str(job["user_id"]),
                    str(current["deployment_tenant_id"]),
                    str(current["deployment_tenant_id"]),
                    str(current["deployment_tenant_id"]),
                    str(current["deployment_tenant_id"]),
                    str(job["project_id"]),
                    str(job["project_id"]),
                    str(job["user_id"]),
                    str(job["project_id"]),
                    completion_event_id,
                ),
            )
            applied = cursor.fetchone()
        if not applied:
            raise RuntimeError("The bound Terraform apply has no verified completion event.")

        summary = _json_mapping(applied.get("summary"), label="Terraform operation summary")
        bundle = _json_mapping(applied.get("bundle"), label="Terraform bundle reference")
        inputs = _json_mapping(applied.get("input_variables"), label="Terraform input reference")
        guardrails = _json_mapping(applied.get("guardrails"), label="Terraform guardrails")
        saved_plan = _json_mapping(applied.get("saved_plan"), label="Terraform saved plan")
        cost = _json_mapping(applied.get("cost_estimate"), label="Terraform cost evidence")
        event_data = _json_mapping(applied.get("event_data"), label="Terraform completion event")
        event_metadata = _json_mapping(
            event_data.get("metadata"),
            label="Terraform completion metadata",
        )
        immutable_checks = (
            applied.get("input_digest") == current_plan_digest,
            str(applied.get("operation_tenant_id")) == str(current["deployment_tenant_id"]),
            str(applied.get("plan_tenant_id")) == str(current["deployment_tenant_id"]),
            str(applied.get("approval_tenant_id")) == str(current["deployment_tenant_id"]),
            str(applied.get("event_tenant_id")) == str(current["deployment_tenant_id"]),
            applied.get("operation_status") == "completed",
            summary.get("approved_plan_id") == str(current["plan_id"]),
            summary.get("approved_plan_revision") == current["plan_revision"],
            summary.get("approved_plan_digest") == current_plan_digest,
            summary.get("target_fingerprint") == proof["target_fingerprint"],
            applied.get("terraform_revision") == current["plan_revision"],
            applied.get("plan_job_digest") == proof["plan_job_digest"],
            str(applied.get("approval_id")) == approval_id,
            str(applied.get("apply_job_id")) == apply_job_id,
            applied.get("approval_status") == "consumed",
            applied.get("approved_plan_job_digest") == applied.get("plan_job_digest"),
            applied.get("approved_plan_sha256") == proof["plan_sha256"] == saved_plan.get("sha256"),
            applied.get("approved_bundle_sha256") == proof["bundle_sha256"] == bundle.get("sha256"),
            applied.get("approved_input_variables_sha256") == inputs.get("sha256"),
            applied.get("approved_scope_digest") == guardrails.get("scope_digest"),
            applied.get("approved_policy_digest") == guardrails.get("policy_digest"),
            applied.get("approved_cost_estimate_sha256") == cost.get("artifact_sha256"),
            applied.get("approved_currency") == cost.get("currency"),
            applied.get("approved_monthly_cost_microunits") == cost.get("monthly_cost_microunits"),
            saved_plan.get("plan_job_digest") == applied.get("plan_job_digest"),
            saved_plan.get("bundle_sha256") == bundle.get("sha256"),
            saved_plan.get("input_variables_sha256") == inputs.get("sha256"),
            saved_plan.get("scope_digest") == guardrails.get("scope_digest"),
            saved_plan.get("policy_digest") == guardrails.get("policy_digest"),
            event_data.get("status") == "completed",
            event_data.get("stage") == "terraform-apply",
            event_metadata.get("operation") == "apply",
            event_metadata.get("job_id") == apply_job_id,
            event_metadata.get("approval_id") == approval_id,
            event_metadata.get("plan_sha256") == proof["plan_sha256"],
            event_metadata.get("bundle_sha256") == proof["bundle_sha256"],
            applied.get("external_event_id") == completion_event_id,
            bool(applied.get("event_fingerprint")),
        )
        if not all(immutable_checks):
            raise RuntimeError("The bound Terraform apply proof no longer matches immutable control data.")
        return {
            "operation_run_id": operation_run_id,
            "plan_id": str(current["plan_id"]),
            "plan_revision": current["plan_revision"],
            "plan_digest": current_plan_digest,
        }

    def _begin_pipeline(
        self,
        connection,
        job: dict[str, Any],
        terraform_proof: dict[str, Any],
    ) -> None:
        """Cross the side-effect boundary only while this lease is current."""

        worker_id, lease_token = self._lease_identity(job)
        if terraform_proof.get("app_service_reused"):
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    """
                    WITH owned_job AS (
                        SELECT deployment_id
                        FROM deployment_jobs
                        WHERE id = %s
                          AND status = 'running'
                          AND worker_id = %s
                          AND lease_token = %s
                        FOR UPDATE
                    )
                    UPDATE deployments AS d
                    SET status = 'building'
                    FROM owned_job
                    WHERE d.id = owned_job.deployment_id
                      AND d.id = %s
                      AND d.status = 'queued'
                      AND d.terraform_operation_run_id IS NULL
                      AND (
                          COALESCE((d.infrastructure_metadata->>'app_service_reused')::boolean, FALSE) = TRUE
                          OR COALESCE((d.infrastructure_metadata->>'terraform_apply_required')::boolean, TRUE) = FALSE
                      )
                      AND EXISTS (
                          SELECT 1
                          FROM infrastructure_plans AS ip
                          WHERE ip.id = %s
                            AND ip.project_id = d.project_id
                            AND ip.user_id = d.user_id
                            AND ip.status = 'approved'
                            AND ip.revision = %s
                      )
                    RETURNING d.id
                    """,
                    (
                        str(job["id"]),
                        worker_id,
                        lease_token,
                        str(job["deployment_id"]),
                        terraform_proof["plan_id"],
                        terraform_proof["plan_revision"],
                    ),
                )
                if not cursor.fetchone():
                    raise RuntimeError(
                        "The deployment lease was lost or the release already crossed its execution boundary."
                    )
            return

        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                WITH owned_job AS (
                    SELECT deployment_id
                    FROM deployment_jobs
                    WHERE id = %s
                      AND status = 'running'
                      AND worker_id = %s
                      AND lease_token = %s
                    FOR UPDATE
                )
                UPDATE deployments AS d
                SET status = 'building'
                FROM owned_job
                WHERE d.id = owned_job.deployment_id
                  AND d.id = %s
                  AND d.status = 'queued'
                  AND d.terraform_operation_run_id = %s
                  AND d.infrastructure_metadata->'terraform_apply'->>'approved_plan_digest' = %s
                  AND EXISTS (
                      SELECT 1
                      FROM infrastructure_plans AS ip
                      WHERE ip.id = %s
                        AND ip.project_id = d.project_id
                        AND ip.user_id = d.user_id
                        AND ip.status = 'approved'
                        AND ip.revision = %s
                  )
                RETURNING d.id
                """,
                (
                    str(job["id"]),
                    worker_id,
                    lease_token,
                    str(job["deployment_id"]),
                    terraform_proof["operation_run_id"],
                    terraform_proof["plan_digest"],
                    terraform_proof["plan_id"],
                    terraform_proof["plan_revision"],
                ),
            )
            if not cursor.fetchone():
                raise RuntimeError(
                    "The deployment lease was lost or the release already crossed its execution boundary."
                )

    def _persist_internal_iac_metadata(
        self,
        connection,
        job: dict[str, Any],
        artifact_metadata: dict[str, Any],
    ) -> None:
        """Merge a sanitized artifact descriptor into deployment metadata."""
        deployment_id = str(job["deployment_id"])
        worker_id, lease_token = self._lease_identity(job)
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                "SELECT infrastructure_metadata FROM deployments WHERE id = %s",
                (deployment_id,),
            )
            deployment = cursor.fetchone()
            if not deployment:
                raise RuntimeError("The deployment record is no longer available to this worker.")

            infrastructure_metadata = deployment.get("infrastructure_metadata") or {}
            if isinstance(infrastructure_metadata, str):
                try:
                    infrastructure_metadata = json.loads(infrastructure_metadata)
                except json.JSONDecodeError as error:
                    raise RuntimeError("Deployment infrastructure metadata is invalid.") from error
            if not isinstance(infrastructure_metadata, dict):
                raise RuntimeError("Deployment infrastructure metadata is invalid.")

            updated_metadata = dict(infrastructure_metadata)
            updated_metadata["internal_iac"] = artifact_metadata
            cursor.execute(
                """
                UPDATE deployments AS d
                SET infrastructure_metadata = %s
                WHERE d.id = %s
                  AND d.status = 'queued'
                  AND EXISTS (
                    SELECT 1
                    FROM deployment_jobs AS j
                    WHERE j.id = %s
                      AND j.deployment_id = d.id
                      AND j.status = 'running'
                      AND j.worker_id = %s
                      AND j.lease_token = %s
                  )
                RETURNING d.id
                """,
                (
                    Json(updated_metadata),
                    deployment_id,
                    str(job["id"]),
                    worker_id,
                    lease_token,
                ),
            )
            if not cursor.fetchone():
                raise RuntimeError("The deployment lease was lost before artifact metadata was recorded.")

    def _mark_deployment_failed(
        self,
        connection,
        deployment_id: str,
        failure_reason: str,
    ) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE deployments
                SET status = 'failed',
                    failure_reason = COALESCE(failure_reason, %s),
                    completed_at = COALESCE(completed_at, NOW())
                WHERE id = %s AND status IN ('queued', 'building', 'deploying')
                """,
                (failure_reason, deployment_id),
            )
            cursor.execute(
                """
                UPDATE decision_evaluations
                SET status = 'failed',
                    outcome_metadata = %s
                WHERE deployment_id = %s AND status = 'pending'
                """,
                (
                    Json(
                        {
                            "outcome": "Deployment worker recorded a failed release.",
                            "reason": failure_reason,
                        }
                    ),
                    deployment_id,
                ),
            )
            cursor.execute(
                """
                UPDATE projects AS p
                SET status = 'failed'
                WHERE p.id = (
                    SELECT project_id FROM deployments WHERE id = %s
                )
                  AND p.status = 'deploying'
                  AND NOT EXISTS (
                    SELECT 1
                    FROM deployments AS other
                    WHERE other.project_id = p.id
                      AND other.id <> %s
                      AND other.status IN ('queued', 'building', 'deploying')
                  )
                """,
                (deployment_id, deployment_id),
            )

    def execute_job(
        self,
        job: dict[str, Any],
        *,
        lease_guard: Callable[[], bool] | None = None,
    ) -> bool:
        """Execute one queue item and mirror the verified pipeline outcome."""
        deployment_id = job.get("deployment_id")
        if not deployment_id:
            raise RuntimeError("Deployment job has no deployment identifier.")
        self._lease_identity(job)
        owns_lease = lease_guard or (lambda: True)

        connection = self._get_connection()
        connection.autocommit = True
        try:
            if not owns_lease():
                raise RuntimeError("The deployment lease was lost before execution started.")
            repository, branch, commit_sha, clone_token = self._load_pipeline_input(connection, job)

            queued_spec = job.get("infrastructure_spec")
            if not isinstance(queued_spec, dict):
                raise RuntimeError("Deployment job has no valid approved infrastructure specification.")
            generated_metadata = terraform_generator.generate_internal_artifact(
                plan=queued_spec,
                project_id=str(deployment_id),
                project_name=repository.rsplit("/", 1)[-1],
            )
            artifact_metadata = _safe_internal_iac_metadata(generated_metadata, queued_spec)
            self._persist_internal_iac_metadata(
                connection,
                job,
                artifact_metadata,
            )
            if not owns_lease():
                raise RuntimeError("The deployment lease was lost before cloud execution started.")
            terraform_proof = self._require_completed_terraform_apply(connection, job)
            self._begin_pipeline(connection, job, terraform_proof)

            asyncio.run(
                pipeline.run_deployment_pipeline(
                    str(deployment_id),
                    repository,
                    branch,
                    clone_token,
                    commit_sha=commit_sha,
                    lease_guard=owns_lease,
                )
            )

            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    """
                    SELECT
                        status,
                        failure_reason,
                        live_url,
                        pipeline_status,
                        pipeline_failure_code
                    FROM (
                        SELECT
                            d.status,
                            d.failure_reason,
                            d.live_url,
                            latest_pipeline.status AS pipeline_status,
                            latest_pipeline.failure_code AS pipeline_failure_code
                        FROM deployments AS d
                        LEFT JOIN LATERAL (
                            SELECT status, failure_code
                            FROM pipeline_runs
                            WHERE deployment_id = d.id
                            ORDER BY created_at DESC
                            LIMIT 1
                        ) AS latest_pipeline ON TRUE
                        WHERE d.id = %s
                    ) AS pipeline_outcome
                    """,
                    (deployment_id,),
                )
                deployment = cursor.fetchone()
            outcome = _pipeline_job_outcome(deployment)
            if outcome == "failed":
                reason = (deployment or {}).get("failure_reason") or "The deployment pipeline did not verify a running application."
                self._mark_job(connection, job, status="failed", failure_reason=reason)
                return False

            return self._mark_job(
                connection,
                job,
                status="completed",
                live_url=deployment.get("live_url") if outcome == "deployed" else None,
                deployment_completed=outcome == "deployed",
            )
        except Exception as error:
            reason = redact_sensitive_text(str(error), maximum_length=2_000)
            if self._mark_job(connection, job, status="failed", failure_reason=reason):
                self._mark_deployment_failed(connection, str(deployment_id), reason)
            return False
        finally:
            connection.close()

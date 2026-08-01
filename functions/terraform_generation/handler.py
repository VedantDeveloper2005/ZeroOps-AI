"""Fail-closed Terraform generation and immutable VMSS plan handoff."""

from __future__ import annotations

import io
import os
import stat
import uuid
import zipfile
from dataclasses import asdict, dataclass
from datetime import timezone
from pathlib import Path
from typing import Any

from zeroops_functions.ai_contracts import (
    TerraformBundle,
    TerraformGenerationRequest,
)
from zeroops_functions.blob_store import BlobArtifactStore, UploadedArtifact
from zeroops_functions.contracts import (
    EventArtifactV1,
    TerraformGenerationJobV1,
    WorkflowEventV1,
    canonical_artifact_blob_name,
)
from zeroops_functions.identity import workload_credential
from zeroops_functions.model_client import StructuredModelClient
from zeroops_functions.publisher import ServiceBusPublisher
from zeroops_functions.security import (
    canonical_json_bytes,
    redact,
    sha256_bytes,
    validate_terraform_bundle,
)


FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
TRUSTED_PROVIDER_LOCK_PATH = Path(__file__).with_name("terraform.lock.hcl")
AUDIT_ARTIFACT_NAME = "terraform-generation-audit.v1"


@dataclass(frozen=True)
class TerraformHandlerDependencies:
    store: BlobArtifactStore
    publisher: ServiceBusPublisher
    model_client: StructuredModelClient
    workflow_events_queue: str
    terraform_plan_queue: str
    instructions: str


def _event_id(job: TerraformGenerationJobV1, suffix: str) -> str:
    return sha256_bytes(f"{job.job_id}:{job.attempt}:{suffix}".encode("utf-8"))


def _normalized_text_bytes(value: str) -> bytes:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")
    return (normalized + "\n").encode("utf-8")


def build_deterministic_terraform_zip(
    bundle: TerraformBundle,
    *,
    trusted_provider_lock: str | None = None,
) -> bytes:
    """Render validated root Terraform files plus the application-owned lock."""

    if bundle.status != "generated":
        raise ValueError("Only generated Terraform can be rendered for execution")
    lock_text = (
        trusted_provider_lock
        if trusted_provider_lock is not None
        else TRUSTED_PROVIDER_LOCK_PATH.read_text(encoding="utf-8")
    )
    lock_bytes = _normalized_text_bytes(lock_text)
    if (
        b'registry.terraform.io/hashicorp/azurerm' not in lock_bytes
        or b'version     = "4.81.0"' not in lock_bytes
    ):
        raise ValueError("Trusted AzureRM provider lock is missing its approved pin")

    members = {
        item.path: _normalized_text_bytes(item.content)
        for item in bundle.files
    }
    if ".terraform.lock.hcl" in members:
        raise ValueError("Model output cannot provide the trusted provider lock")
    members[".terraform.lock.hcl"] = lock_bytes

    output = io.BytesIO()
    # ZIP_STORED avoids platform/zlib-dependent output while these small,
    # bounded source bundles remain well below the executor size limit.
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_STORED) as archive:
        for name in sorted(members):
            info = zipfile.ZipInfo(name, date_time=FIXED_ZIP_TIMESTAMP)
            info.create_system = 3
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = (stat.S_IFREG | 0o600) << 16
            archive.writestr(info, members[name])
    return output.getvalue()


def _artifact_uri(
    store: BlobArtifactStore,
    *,
    container: str,
    blob_name: str,
) -> str:
    return f"{store.account_url.rstrip('/')}/{container}/{blob_name}"


def _require_upload_etag(uploaded: UploadedArtifact) -> str:
    if not uploaded.etag:
        raise ValueError("Immutable artifact upload did not return a storage ETag")
    return uploaded.etag


def _requested_at(job: TerraformGenerationJobV1) -> str:
    return (
        job.enqueued_at.astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _execution_envelope(
    *,
    job: TerraformGenerationJobV1,
    store: BlobArtifactStore,
    bundle_blob_name: str,
    uploaded_bundle: UploadedArtifact,
) -> dict[str, Any]:
    plan_job_id = str(uuid.uuid5(uuid.UUID(job.job_id), "terraform-plan.v1"))
    value: dict[str, Any] = {
        "schema_version": "1.0",
        "operation": "plan",
        "job_id": plan_job_id,
        "tenant_id": job.tenant_id,
        "project_id": job.project_id,
        "user_id": job.user_id,
        "workflow_id": job.run_id,
        "revision": job.approved_plan_revision,
        "bundle": {
            "uri": _artifact_uri(
                store,
                container=job.output_container,
                blob_name=bundle_blob_name,
            ),
            "etag": _require_upload_etag(uploaded_bundle),
            "sha256": uploaded_bundle.sha256,
            "size_bytes": uploaded_bundle.size_bytes,
        },
        "state_key": (
            f"tenants/{job.tenant_id}/workspaces/{job.run_id}/terraform.tfstate"
        ),
        "target_subscription_id": job.target_subscription_id,
        "target_tenant_id": job.target_tenant_id,
        "terraform_version": job.terraform_version,
        "requested_at": _requested_at(job),
    }
    value["job_digest"] = sha256_bytes(canonical_json_bytes(value))
    return value


def _upload_audit(
    *,
    job: TerraformGenerationJobV1,
    deps: TerraformHandlerDependencies,
    audit_value: dict[str, Any],
) -> tuple[str, str, UploadedArtifact]:
    audit_artifact_id = str(
        uuid.uuid5(uuid.UUID(job.output_artifact_id), AUDIT_ARTIFACT_NAME)
    )
    body = canonical_json_bytes(audit_value)
    blob_name = canonical_artifact_blob_name(
        audit_artifact_id,
        version=1,
        sha256=sha256_bytes(body),
    )
    uploaded = deps.store.upload_immutable_bytes(
        container=job.output_container,
        blob_name=blob_name,
        body=body,
        media_type="application/json",
        metadata={
            "artifact-id": audit_artifact_id,
            "tenant-id": job.tenant_id,
            "project-id": job.project_id,
            "run-id": job.run_id,
            "classification": "tenant-terraform",
            "artifact-purpose": "generation-audit",
            "approved-plan-digest": job.approved_plan_digest,
        },
    )
    if uploaded.sha256 != sha256_bytes(body):
        raise ValueError("Stored Terraform audit digest differs from its canonical bytes")
    _require_upload_etag(uploaded)
    return audit_artifact_id, blob_name, uploaded


def dependencies_from_environment() -> TerraformHandlerDependencies:
    credential = workload_credential()
    account_url = os.environ["ARTIFACT_STORAGE_ACCOUNT_URL"].rstrip("/")
    namespace = os.environ["SERVICEBUS_FULLY_QUALIFIED_NAMESPACE"]
    prompt_path = Path(
        os.getenv(
            "AI_TERRAFORM_INSTRUCTIONS_PATH",
            Path(__file__).parent / "prompts" / "instructions.md",
        )
    )
    return TerraformHandlerDependencies(
        store=BlobArtifactStore(account_url, credential),
        publisher=ServiceBusPublisher(namespace, credential),
        model_client=StructuredModelClient(
            provider=os.getenv("AI_TERRAFORM_PROVIDER", "nvidia"),
            endpoint=os.getenv(
                "AI_TERRAFORM_ENDPOINT",
                "https://integrate.api.nvidia.com/v1",
            ),
            model=os.getenv("AI_TERRAFORM_MODEL", "z-ai/glm-5.2"),
            api_key=os.getenv("AI_TERRAFORM_API_KEY", ""),
            workload="terraform-generation",
            prompt_version=os.getenv(
                "AI_TERRAFORM_PROMPT_VERSION",
                "terraform-generation.v1",
            ),
            maximum_input_chars=int(
                os.getenv("AI_TERRAFORM_MAX_INPUT_CHARS", "40000")
            ),
            maximum_output_tokens=int(
                os.getenv("AI_TERRAFORM_MAX_OUTPUT_TOKENS", "4000")
            ),
            api_version=os.getenv("AI_GITHUB_API_VERSION", "2026-03-10"),
        ),
        workflow_events_queue=os.getenv(
            "WORKFLOW_EVENTS_QUEUE_NAME",
            "workflow-events",
        ),
        terraform_plan_queue=os.getenv("TERRAFORM_PLAN_QUEUE_NAME", "terraform-plan"),
        instructions=prompt_path.read_text(encoding="utf-8"),
    )


def handle_terraform_generation(
    raw_message: bytes,
    dependencies: TerraformHandlerDependencies | None = None,
) -> dict[str, Any]:
    deps = dependencies or dependencies_from_environment()
    job = TerraformGenerationJobV1.model_validate_json(raw_message)
    deps.publisher.send_event(
        deps.workflow_events_queue,
        WorkflowEventV1(
            event_id=_event_id(job, "started"),
            event_type="terraform.generation.started",
            tenant_id=job.tenant_id,
            project_id=job.project_id,
            run_id=job.run_id,
            correlation_id=job.correlation_id,
            stage="terraform-generation",
            attempt=job.attempt,
            status="started",
            actor_type="function",
            actor_id="terraform-generation",
            safe_metadata={
                "approved_plan_id": job.approved_plan_id,
                "approved_plan_revision": job.approved_plan_revision,
                "approved_plan_digest": job.approved_plan_digest,
                "target_environment": job.target_environment,
                "terraform_version": job.terraform_version,
            },
        ),
    )
    try:
        request_value = deps.store.download_verified_json(
            job.approved_plan_artifact,
            maximum_bytes=8 * 1024 * 1024,
        )
        request = TerraformGenerationRequest.model_validate(request_value)
        if (
            str(request.tenant_id) != job.tenant_id
            or str(request.project_id) != job.project_id
            or str(request.plan_id) != job.approved_plan_id
            or request.plan_revision != job.approved_plan_revision
            or request.plan_sha256 != job.approved_plan_digest
        ):
            raise ValueError(
                "Terraform request identity, revision, or approved-plan digest mismatch."
            )
        bundle, provenance = deps.model_client.generate(
            system_instructions=deps.instructions,
            input_value=request.model_dump(mode="json"),
            output_model=TerraformBundle,
            schema_version="terraform-bundle.v1",
            correlation_id=job.correlation_id,
            semantic_validator=lambda value: validate_terraform_bundle(value, request),
        )
        validate_terraform_bundle(bundle, request)
        ordered_files = sorted(bundle.files, key=lambda item: item.path)
        file_manifest = [
            {
                "path": item.path,
                "sha256": sha256_bytes(_normalized_text_bytes(item.content)),
                "size_bytes": len(_normalized_text_bytes(item.content)),
            }
            for item in ordered_files
        ]
        audit_value: dict[str, Any] = {
            **bundle.model_dump(mode="json"),
            "tenant_id": job.tenant_id,
            "project_id": job.project_id,
            "user_id": job.user_id,
            "run_id": job.run_id,
            "approved_plan_id": job.approved_plan_id,
            "approved_plan_revision": job.approved_plan_revision,
            "approved_plan_digest": job.approved_plan_digest,
            "target_environment": job.target_environment,
            "target_subscription_id": job.target_subscription_id,
            "target_tenant_id": job.target_tenant_id,
            "terraform_version": job.terraform_version,
            "file_manifest": file_manifest,
            "bundle_content_digest": sha256_bytes(
                canonical_json_bytes(
                    {
                        "files": [
                            {
                                "path": item.path,
                                "content_sha256": sha256_bytes(
                                    _normalized_text_bytes(item.content)
                                ),
                            }
                            for item in ordered_files
                        ],
                        "approved_plan_digest": job.approved_plan_digest,
                    }
                )
            ),
            "provenance": asdict(provenance),
            "validation_status": "not_run",
            "plan_status": "not_run",
            "apply_status": "not_run",
        }

        if bundle.status == "blocked":
            audit_artifact_id, audit_blob_name, uploaded_audit = _upload_audit(
                job=job,
                deps=deps,
                audit_value=audit_value,
            )
            deps.publisher.send_event(
                deps.workflow_events_queue,
                WorkflowEventV1(
                    event_id=_event_id(job, "blocked"),
                    event_type="terraform.generation.blocked",
                    tenant_id=job.tenant_id,
                    project_id=job.project_id,
                    run_id=job.run_id,
                    correlation_id=job.correlation_id,
                    stage="terraform-generation",
                    attempt=job.attempt,
                    status="failed",
                    actor_type="function",
                    actor_id="terraform-generation",
                    artifacts=[
                        EventArtifactV1(
                            artifact_id=audit_artifact_id,
                            kind="terraform-generation-audit",
                            sha256=uploaded_audit.sha256,
                            storage_container=job.output_container,
                            storage_path=audit_blob_name,
                            blob_version_id=uploaded_audit.version_id,
                            size_bytes=uploaded_audit.size_bytes,
                            content_type="application/json",
                            access_scope="user",
                            sanitization_status="sanitized",
                        )
                    ],
                    safe_metadata={
                        "approved_plan_digest": job.approved_plan_digest,
                        "blocked_reason_count": len(bundle.blocked_reasons),
                        "validation_status": "not_run",
                        "plan_status": "not_run",
                        "apply_status": "not_run",
                    },
                    safe_message=(
                        "Terraform generation was blocked; no plan job was enqueued."
                    ),
                ),
            )
            return audit_value

        bundle_bytes = build_deterministic_terraform_zip(bundle)
        bundle_sha256 = sha256_bytes(bundle_bytes)
        bundle_blob_name = canonical_artifact_blob_name(
            job.output_artifact_id,
            version=1,
            sha256=bundle_sha256,
        )
        uploaded_bundle = deps.store.upload_immutable_bytes(
            container=job.output_container,
            blob_name=bundle_blob_name,
            body=bundle_bytes,
            media_type="application/zip",
            metadata={
                "artifact-id": job.output_artifact_id,
                "tenant-id": job.tenant_id,
                "project-id": job.project_id,
                "run-id": job.run_id,
                "classification": "tenant-terraform",
                "artifact-purpose": "executor-bundle",
                "approved-plan-digest": job.approved_plan_digest,
                "terraform-version": job.terraform_version,
            },
        )
        if (
            uploaded_bundle.sha256 != bundle_sha256
            or uploaded_bundle.size_bytes != len(bundle_bytes)
        ):
            raise ValueError("Stored Terraform bundle differs from deterministic ZIP")
        _require_upload_etag(uploaded_bundle)

        envelope = _execution_envelope(
            job=job,
            store=deps.store,
            bundle_blob_name=bundle_blob_name,
            uploaded_bundle=uploaded_bundle,
        )
        audit_value["executor_bundle"] = {
            "artifact_id": job.output_artifact_id,
            "sha256": uploaded_bundle.sha256,
            "size_bytes": uploaded_bundle.size_bytes,
            "media_type": "application/zip",
            "terraform_version": job.terraform_version,
            "plan_job_id": envelope["job_id"],
            "plan_job_digest": envelope["job_digest"],
        }
        audit_artifact_id, audit_blob_name, uploaded_audit = _upload_audit(
            job=job,
            deps=deps,
            audit_value=audit_value,
        )

        deps.publisher.send_json(
            deps.terraform_plan_queue,
            envelope,
            message_id=envelope["job_digest"],
            correlation_id=job.correlation_id,
            subject="terraform.plan.requested",
            session_id=job.run_id,
        )
        deps.publisher.send_event(
            deps.workflow_events_queue,
            WorkflowEventV1(
                event_id=_event_id(job, "completed"),
                event_type="terraform.generation.completed",
                tenant_id=job.tenant_id,
                project_id=job.project_id,
                run_id=job.run_id,
                correlation_id=job.correlation_id,
                stage="terraform-generation",
                attempt=job.attempt,
                status="completed",
                actor_type="function",
                actor_id="terraform-generation",
                artifacts=[
                    EventArtifactV1(
                        artifact_id=audit_artifact_id,
                        kind="terraform-generation-audit",
                        sha256=uploaded_audit.sha256,
                        storage_container=job.output_container,
                        storage_path=audit_blob_name,
                        blob_version_id=uploaded_audit.version_id,
                        size_bytes=uploaded_audit.size_bytes,
                        content_type="application/json",
                        access_scope="user",
                        sanitization_status="sanitized",
                    ),
                    EventArtifactV1(
                        artifact_id=job.output_artifact_id,
                        kind="terraform-bundle",
                        sha256=uploaded_bundle.sha256,
                        storage_container=job.output_container,
                        storage_path=bundle_blob_name,
                        blob_version_id=uploaded_bundle.version_id,
                        size_bytes=uploaded_bundle.size_bytes,
                        content_type="application/zip",
                        access_scope="user",
                        sanitization_status="sanitized",
                    ),
                ],
                safe_metadata=redact(
                    {
                        **asdict(provenance),
                        "approved_plan_digest": job.approved_plan_digest,
                        "target_environment": job.target_environment,
                        "terraform_version": job.terraform_version,
                        "file_count": len(bundle.files),
                        "bundle_size_bytes": uploaded_bundle.size_bytes,
                        "plan_job_digest": envelope["job_digest"],
                        "validation_status": "not_run",
                        "plan_status": "not_run",
                        "apply_status": "not_run",
                    }
                ),
            ),
        )
        return audit_value
    except Exception as error:
        deps.publisher.send_event(
            deps.workflow_events_queue,
            WorkflowEventV1(
                event_id=_event_id(job, "failed"),
                event_type="terraform.generation.failed",
                tenant_id=job.tenant_id,
                project_id=job.project_id,
                run_id=job.run_id,
                correlation_id=job.correlation_id,
                stage="terraform-generation",
                attempt=job.attempt,
                status="failed",
                actor_type="function",
                actor_id="terraform-generation",
                error_code=type(error).__name__[:96],
                safe_message=(
                    "Terraform generation failed closed; no plan job was enqueued."
                ),
            ),
        )
        raise

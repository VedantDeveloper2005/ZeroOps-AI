"""Versioned queue and artifact contracts shared by ZeroOps workers.

Queue messages intentionally contain references and digests rather than source
or Terraform bodies. All models reject unknown fields so producers cannot
silently expand a worker's authority.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_CONTAINER_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])?$")
_TENANT_CONTAINER_PATTERN = re.compile(r"^t-[0-9a-f]{40}$")
_SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def canonical_uuid(value: str, *, field: str) -> str:
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as error:
        raise ValueError(f"{field} must be a canonical UUID") from error
    canonical = str(parsed)
    if value != canonical:
        raise ValueError(f"{field} must use lowercase canonical UUID form")
    return canonical


def canonical_artifact_blob_name(
    artifact_id: str,
    *,
    version: int,
    sha256: str,
) -> str:
    canonical_uuid(artifact_id, field="artifact_id")
    if version < 1:
        raise ValueError("artifact version must be positive")
    if not _SHA256_PATTERN.fullmatch(sha256):
        raise ValueError("artifact digest must be a lowercase SHA-256 digest")
    return f"objects/{artifact_id}/v{version}/{sha256}"


class StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ArtifactReferenceV1(StrictContract):
    schema_version: Literal["artifact-reference.v1"] = "artifact-reference.v1"
    artifact_id: str
    account_url: str
    container: str
    blob_name: str
    version_id: str | None = None
    sha256: str
    size_bytes: int = Field(ge=0, le=268_435_456)
    media_type: str = Field(min_length=1, max_length=128)
    classification: Literal[
        "tenant-source",
        "tenant-analysis",
        "tenant-terraform",
        "tenant-plan-sanitized",
        "tenant-cost",
        "tenant-evidence",
        "executor-plan-raw",
        "executor-state",
        "workflow-event",
    ]

    @field_validator("artifact_id")
    @classmethod
    def validate_artifact_id(cls, value: str) -> str:
        if not _ID_PATTERN.fullmatch(value):
            raise ValueError("artifact_id must be an opaque safe identifier")
        return value

    @field_validator("account_url")
    @classmethod
    def validate_account_url(cls, value: str) -> str:
        normalized = value.rstrip("/")
        if not normalized.startswith("https://") or "/" in normalized.removeprefix("https://"):
            raise ValueError("account_url must be an HTTPS account origin")
        if not normalized.endswith(".blob.core.windows.net"):
            raise ValueError("account_url must be an Azure Blob endpoint")
        return normalized

    @field_validator("container")
    @classmethod
    def validate_container(cls, value: str) -> str:
        if not _CONTAINER_PATTERN.fullmatch(value):
            raise ValueError("container must satisfy Azure container naming rules")
        return value

    @field_validator("blob_name")
    @classmethod
    def validate_blob_name(cls, value: str) -> str:
        normalized = value.replace("\\", "/").strip("/")
        if not normalized or normalized.startswith(".") or ".." in normalized.split("/"):
            raise ValueError("blob_name must be a relative traversal-free path")
        if "\x00" in normalized or len(normalized) > 1024:
            raise ValueError("blob_name is invalid")
        return normalized

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        normalized = value.lower()
        if not _SHA256_PATTERN.fullmatch(normalized):
            raise ValueError("sha256 must be a lowercase SHA-256 hex digest")
        return normalized


class JobIdentityV1(StrictContract):
    job_id: str
    tenant_id: str
    project_id: str
    run_id: str
    correlation_id: str
    attempt: int = Field(default=1, ge=1, le=10)
    enqueued_at: datetime = Field(default_factory=utc_now)

    @field_validator(
        "job_id",
        "tenant_id",
        "project_id",
        "run_id",
        "correlation_id",
    )
    @classmethod
    def validate_opaque_id(cls, value: str) -> str:
        if not _ID_PATTERN.fullmatch(value):
            raise ValueError("identifier must be opaque and contain only safe characters")
        return value


class RepositoryAnalysisJobV1(JobIdentityV1):
    schema_version: Literal["repository-analysis-job.v1"] = "repository-analysis-job.v1"
    source_artifact: ArtifactReferenceV1
    scanner_facts_artifact: ArtifactReferenceV1
    output_artifact_id: str
    output_container: str
    source_commit: str = Field(min_length=7, max_length=64)
    scanner_version: str = Field(min_length=1, max_length=64)

    @field_validator("output_artifact_id")
    @classmethod
    def validate_output_artifact_id(cls, value: str) -> str:
        return canonical_uuid(value, field="output_artifact_id")

    @field_validator("output_container")
    @classmethod
    def validate_output_container(cls, value: str) -> str:
        if not _TENANT_CONTAINER_PATTERN.fullmatch(value):
            raise ValueError("output_container must be an opaque tenant container")
        return value


class TerraformGenerationJobV1(JobIdentityV1):
    schema_version: Literal["terraform-generation-job.v1"] = "terraform-generation-job.v1"
    enqueued_at: datetime
    user_id: str
    approved_plan_artifact: ArtifactReferenceV1
    output_artifact_id: str
    output_container: str
    approved_plan_id: str
    approved_plan_revision: int = Field(ge=1)
    approved_plan_digest: str
    target_environment: Literal["test", "production"]
    target_subscription_id: str
    target_tenant_id: str
    terraform_version: Literal["1.15.8"]

    @field_validator(
        "job_id",
        "tenant_id",
        "project_id",
        "run_id",
        "user_id",
        "output_artifact_id",
        "approved_plan_id",
        "target_subscription_id",
        "target_tenant_id",
    )
    @classmethod
    def validate_canonical_uuid(cls, value: str, info: Any) -> str:
        return canonical_uuid(value, field=info.field_name)

    @field_validator("enqueued_at")
    @classmethod
    def validate_enqueued_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("enqueued_at must include a timezone")
        return value

    @field_validator("approved_plan_digest")
    @classmethod
    def validate_plan_digest(cls, value: str) -> str:
        normalized = value.lower()
        if not _SHA256_PATTERN.fullmatch(normalized):
            raise ValueError("approved_plan_digest must be a SHA-256 digest")
        return normalized

    @field_validator("output_container")
    @classmethod
    def validate_output_container(cls, value: str) -> str:
        if not _TENANT_CONTAINER_PATTERN.fullmatch(value):
            raise ValueError("output_container must be an opaque tenant container")
        return value


class EventArtifactV1(StrictContract):
    artifact_id: str
    kind: str = Field(min_length=1, max_length=64)
    sha256: str | None = None
    storage_container: str | None = None
    storage_path: str | None = None
    blob_version_id: str | None = Field(default=None, max_length=256)
    size_bytes: int | None = Field(default=None, ge=0, le=268_435_456)
    content_type: str | None = Field(default=None, max_length=128)
    access_scope: Literal["user", "executor"] = "user"
    sanitization_status: Literal["sanitized", "restricted", "pending"] = "sanitized"

    @field_validator("artifact_id")
    @classmethod
    def validate_artifact_id(cls, value: str) -> str:
        if not _ID_PATTERN.fullmatch(value):
            raise ValueError("artifact_id must be an opaque safe identifier")
        return value

    @field_validator("sha256")
    @classmethod
    def validate_optional_sha256(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.lower()
        if not _SHA256_PATTERN.fullmatch(normalized):
            raise ValueError("sha256 must be a lowercase SHA-256 hex digest")
        return normalized

    @field_validator("storage_container")
    @classmethod
    def validate_optional_container(cls, value: str | None) -> str | None:
        if value is not None and not _CONTAINER_PATTERN.fullmatch(value):
            raise ValueError("storage_container is invalid")
        return value

    @field_validator("storage_path")
    @classmethod
    def validate_optional_storage_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.replace("\\", "/").strip("/")
        if not normalized or ".." in normalized.split("/") or len(normalized) > 1024:
            raise ValueError("storage_path must be traversal-free")
        return normalized


class WorkflowEventV1(StrictContract):
    schema_version: Literal["workflow-event.v1"] = "workflow-event.v1"
    event_id: str
    event_type: str = Field(pattern=r"^[a-z][a-z0-9.-]{2,95}$")
    tenant_id: str
    project_id: str
    run_id: str
    correlation_id: str
    stage: str = Field(min_length=1, max_length=64)
    attempt: int = Field(default=1, ge=1, le=10)
    status: Literal["started", "completed", "failed", "degraded"]
    actor_type: Literal["user", "api", "function", "vmss", "system"]
    actor_id: str = Field(min_length=1, max_length=128)
    occurred_at: datetime = Field(default_factory=utc_now)
    artifacts: list[EventArtifactV1] = Field(default_factory=list, max_length=50)
    safe_metadata: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = Field(default=None, max_length=96)
    safe_message: str | None = Field(default=None, max_length=1024)

    @field_validator(
        "event_id",
        "tenant_id",
        "project_id",
        "run_id",
        "correlation_id",
    )
    @classmethod
    def validate_opaque_id(cls, value: str) -> str:
        if not _ID_PATTERN.fullmatch(value):
            raise ValueError("identifier must be opaque and contain only safe characters")
        return value

    @field_validator("safe_metadata")
    @classmethod
    def bound_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(value) > 40:
            raise ValueError("safe_metadata has too many fields")
        return value

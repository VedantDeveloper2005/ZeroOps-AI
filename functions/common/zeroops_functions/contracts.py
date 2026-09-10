"""Versioned queue and artifact contracts shared by ZeroOps workers.

Queue messages intentionally contain references and digests rather than source
or Terraform bodies. All models reject unknown fields so producers cannot
silently expand a worker's authority.
"""

from __future__ import annotations

import re
import uuid
import math
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_CONTAINER_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])?$")
_TENANT_CONTAINER_PATTERN = re.compile(r"^t-[0-9a-f]{40}$")
_SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
_TERRAFORM_VARIABLE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_TERRAFORM_RESOURCE_TYPE_PATTERN = re.compile(r"^azurerm_[a-z0-9_]{1,96}$")
_SECRET_VARIABLE_NAME_PATTERN = re.compile(
    r"(?:password|passwd|secret|token|authorization|api[_-]?key|"
    r"connection[_-]?string|private[_-]?key|sas|client[_-]?secret)",
    re.IGNORECASE,
)
_SECRET_VALUE_PATTERN = re.compile(
    r"(?:-----BEGIN [A-Z ]+PRIVATE KEY-----|"
    r"(?:AccountKey|SharedAccessSignature|client_secret|password)\s*=|"
    r"(?:Bearer|Basic)\s+[A-Za-z0-9+/=_-]{8,}|[?&](?:sig|se|sp|sv)=)",
    re.IGNORECASE,
)
_RESOURCE_GROUP_PATTERN = re.compile(r"^[A-Za-z0-9._()\-]{1,90}$")


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


class TerraformInputVariableV1(StrictContract):
    """One explicitly approved, non-secret Terraform input value.

    These values are accepted only by the generation function. The VMSS queue
    envelope carries a digest and type definitions, never the values.
    """

    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    type: Literal["string", "number", "bool", "list(string)"]
    value: str | int | float | bool | list[str]

    @model_validator(mode="after")
    def validate_non_secret_typed_value(self) -> "TerraformInputVariableV1":
        if _SECRET_VARIABLE_NAME_PATTERN.search(self.name):
            raise ValueError("Secret-like Terraform variables cannot use the non-secret channel")

        value = self.value
        if self.type == "string":
            valid_type = type(value) is str
            string_values = [value] if valid_type else []
        elif self.type == "number":
            valid_type = type(value) in {int, float} and (
                type(value) is int or math.isfinite(value)
            )
            string_values = []
        elif self.type == "bool":
            valid_type = type(value) is bool
            string_values = []
        else:
            valid_type = isinstance(value, list) and len(value) <= 64 and all(
                type(item) is str for item in value
            )
            string_values = value if valid_type else []
        if not valid_type:
            raise ValueError("Terraform input value does not match its declared type")

        for item in string_values:
            if len(item) > 1024 or any(ord(character) < 32 for character in item):
                raise ValueError("Terraform input strings must be bounded printable text")
            if _SECRET_VALUE_PATTERN.search(item):
                raise ValueError("Secret-like values cannot use the non-secret Terraform channel")
        return self


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
    target_resource_group: str
    terraform_version: Literal["1.15.8"]
    input_variables: list[TerraformInputVariableV1] = Field(max_length=64)
    maximum_resource_changes: int = Field(ge=1, le=500)
    maximum_delete_count: int = Field(ge=0, le=100)
    maximum_replace_count: int = Field(ge=0, le=100)

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

    @field_validator("target_resource_group")
    @classmethod
    def validate_target_resource_group(cls, value: str) -> str:
        if not _RESOURCE_GROUP_PATTERN.fullmatch(value) or value.endswith("."):
            raise ValueError("target_resource_group is not a canonical Azure resource group name")
        return value

    @model_validator(mode="after")
    def validate_execution_inputs(self) -> "TerraformGenerationJobV1":
        names = [item.name for item in self.input_variables]
        if len(names) != len(set(names)):
            raise ValueError("Terraform input variable names must be unique")
        if self.maximum_delete_count > self.maximum_resource_changes:
            raise ValueError("maximum_delete_count cannot exceed maximum_resource_changes")
        if self.maximum_replace_count > self.maximum_resource_changes:
            raise ValueError("maximum_replace_count cannot exceed maximum_resource_changes")
        encoded = self.model_dump_json(exclude={"approved_plan_artifact"})
        if len(encoded.encode("utf-8")) > 64 * 1024:
            raise ValueError("Terraform execution inputs exceed the 64 KiB contract limit")
        return self


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


class TerraformPlanControlRecordV1(StrictContract):
    """Executor-only plan handle projected outside user-visible event data."""

    schema_version: Literal["terraform-plan-control.v1"] = "terraform-plan-control.v1"
    plan_job_id: str
    plan_job_digest: str
    revision: int = Field(ge=1)
    bundle: dict[str, Any]
    input_variables: dict[str, Any]
    guardrails: dict[str, Any]
    saved_plan: dict[str, Any]
    plan_summary: dict[str, Any] = Field(default_factory=dict)
    planned_at: datetime

    @field_validator("plan_job_id")
    @classmethod
    def validate_plan_job_id(cls, value: str) -> str:
        return canonical_uuid(value, field="plan_job_id")

    @field_validator("plan_job_digest")
    @classmethod
    def validate_plan_job_digest(cls, value: str) -> str:
        if not _SHA256_PATTERN.fullmatch(value):
            raise ValueError("plan_job_digest must be a lowercase SHA-256 digest")
        return value

    @field_validator("planned_at")
    @classmethod
    def validate_planned_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("planned_at must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_private_control_bindings(self) -> "TerraformPlanControlRecordV1":
        expected = {
            "bundle": {"uri", "etag", "sha256", "size_bytes"},
            "input_variables": {"file_name", "sha256", "definitions"},
            "guardrails": {
                "target_resource_group",
                "allowed_resource_types",
                "maximum_resource_changes",
                "maximum_delete_count",
                "maximum_replace_count",
                "scope_digest",
                "policy_digest",
                "monthly_budget_microunits",
                "budget_currency",
            },
            "saved_plan": {
                "blob_name",
                "etag",
                "sha256",
                "plan_job_digest",
                "bundle_sha256",
                "input_variables_sha256",
                "scope_digest",
                "policy_digest",
            },
        }
        values = {
            "bundle": self.bundle,
            "input_variables": self.input_variables,
            "guardrails": self.guardrails,
            "saved_plan": self.saved_plan,
        }
        for label, fields in expected.items():
            if set(values[label]) != fields:
                raise ValueError(f"{label} contains unsupported or missing fields")
        digests = (
            self.bundle.get("sha256"),
            self.input_variables.get("sha256"),
            self.guardrails.get("scope_digest"),
            self.guardrails.get("policy_digest"),
            self.saved_plan.get("sha256"),
            self.saved_plan.get("plan_job_digest"),
            self.saved_plan.get("bundle_sha256"),
            self.saved_plan.get("input_variables_sha256"),
            self.saved_plan.get("scope_digest"),
            self.saved_plan.get("policy_digest"),
        )
        if any(not isinstance(item, str) or not _SHA256_PATTERN.fullmatch(item) for item in digests):
            raise ValueError("Terraform plan control record contains an invalid digest")
        if self.saved_plan["plan_job_digest"] != self.plan_job_digest:
            raise ValueError("Saved plan does not match the plan job")
        if self.saved_plan["bundle_sha256"] != self.bundle["sha256"]:
            raise ValueError("Saved plan does not match the Terraform bundle")
        if self.saved_plan["input_variables_sha256"] != self.input_variables["sha256"]:
            raise ValueError("Saved plan does not match the Terraform input values")
        if self.saved_plan["scope_digest"] != self.guardrails["scope_digest"]:
            raise ValueError("Saved plan does not match the approved scope")
        if self.saved_plan["policy_digest"] != self.guardrails["policy_digest"]:
            raise ValueError("Saved plan does not match the approved policy")
        encoded_size = len(
            self.model_dump_json(exclude={"plan_summary"}).encode("utf-8")
        )
        if encoded_size > 128 * 1024:
            raise ValueError("Terraform plan control record exceeds 128 KiB")
        return self


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
    control_record: TerraformPlanControlRecordV1 | None = None

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

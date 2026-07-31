"""Strict, tenant-scoped contracts for the VMSS Terraform executor.

Queue messages contain references and digests only. Source archives and saved
Terraform plans are always fetched from Azure Blob Storage with managed
identity; raw source, variable values, state, or plan bytes are rejected here.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping
from urllib.parse import urlparse


SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
TERRAFORM_VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
SAFE_PATH_PATTERN = re.compile(r"^[A-Za-z0-9._/-]+$")
TENANT_CONTAINER_PATTERN = re.compile(r"^t-[0-9a-f]{40}$")
USER_ARTIFACT_PATH_PATTERN = re.compile(
    r"^objects/"
    r"(?P<artifact_id>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{12})/"
    r"v(?P<version>[1-9][0-9]*)/"
    r"(?P<sha256>[0-9a-f]{64})$"
)
MAX_BUNDLE_BYTES = 100 * 1024 * 1024


class ContractError(ValueError):
    """A queue message violates the immutable execution contract."""


def canonical_digest(payload: Mapping[str, Any]) -> str:
    """Return the SHA-256 of canonical UTF-8 JSON."""

    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def payload_with_digest(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Test/producer helper that adds the envelope digest."""

    result = dict(payload)
    result["job_digest"] = canonical_digest(result)
    return result


def _require_exact_keys(
    value: Mapping[str, Any],
    expected: set[str],
    *,
    context: str,
) -> None:
    keys = set(value)
    unknown = keys - expected
    missing = expected - keys
    if unknown:
        raise ContractError(f"{context} contains unsupported fields: {sorted(unknown)}")
    if missing:
        raise ContractError(f"{context} is missing required fields: {sorted(missing)}")


def _canonical_uuid(value: Any, *, field: str) -> str:
    if not isinstance(value, str):
        raise ContractError(f"{field} must be a UUID string.")
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as error:
        raise ContractError(f"{field} must be a UUID string.") from error
    canonical = str(parsed)
    if value.lower() != canonical:
        raise ContractError(f"{field} must use canonical UUID form.")
    return canonical


def _sha256(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
        raise ContractError(f"{field} must be a lowercase SHA-256 digest.")
    return value


def _etag(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 256:
        raise ContractError(f"{field} must be a non-empty storage ETag.")
    if any(ord(character) < 32 for character in value):
        raise ContractError(f"{field} contains control characters.")
    return value


def _timestamp(value: Any, *, field: str) -> datetime:
    if not isinstance(value, str):
        raise ContractError(f"{field} must be an ISO 8601 timestamp.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ContractError(f"{field} must be an ISO 8601 timestamp.") from error
    if parsed.tzinfo is None:
        raise ContractError(f"{field} must include a timezone.")
    parsed = parsed.astimezone(timezone.utc)
    if parsed > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise ContractError(f"{field} cannot be in the future.")
    return parsed


def _tenant_blob_prefix(tenant_id: str, workflow_id: str) -> str:
    return f"tenants/{tenant_id}/workflows/{workflow_id}/"


@dataclass(frozen=True)
class BundleReference:
    uri: str
    etag: str
    sha256: str
    size_bytes: int

    @classmethod
    def from_mapping(
        cls,
        value: Any,
    ) -> "BundleReference":
        if not isinstance(value, Mapping):
            raise ContractError("bundle must be an object.")
        _require_exact_keys(
            value,
            {"uri", "etag", "sha256", "size_bytes"},
            context="bundle",
        )

        bundle_sha256 = _sha256(value["sha256"], field="bundle.sha256")
        uri = value["uri"]
        if not isinstance(uri, str):
            raise ContractError("bundle.uri must be an HTTPS Azure Blob URI.")
        parsed = urlparse(uri)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or not parsed.hostname.endswith(".blob.core.windows.net")
            or parsed.username
            or parsed.password
            or parsed.port
            or parsed.query
            or parsed.fragment
        ):
            raise ContractError(
                "bundle.uri must be a query-free HTTPS Azure Blob URI without credentials."
            )

        if (
            not parsed.path.startswith("/")
            or parsed.path.startswith("//")
            or "%" in parsed.path
        ):
            raise ContractError("bundle.uri must use an unencoded canonical path.")
        path_parts = parsed.path[1:].split("/", 1)
        if len(path_parts) != 2 or not path_parts[0] or not path_parts[1]:
            raise ContractError("bundle.uri must identify a container and blob.")
        container_name, blob_name = path_parts
        if not TENANT_CONTAINER_PATTERN.fullmatch(container_name):
            raise ContractError("bundle.uri must use an opaque tenant container.")
        artifact_match = USER_ARTIFACT_PATH_PATTERN.fullmatch(blob_name)
        if artifact_match is None:
            raise ContractError("bundle.uri must use the canonical user-artifact path.")
        _canonical_uuid(
            artifact_match.group("artifact_id"),
            field="bundle artifact ID",
        )
        if artifact_match.group("sha256") != bundle_sha256:
            raise ContractError("bundle URI terminal digest does not match bundle.sha256.")

        size_bytes = value["size_bytes"]
        if (
            isinstance(size_bytes, bool)
            or not isinstance(size_bytes, int)
            or size_bytes <= 0
            or size_bytes > MAX_BUNDLE_BYTES
        ):
            raise ContractError(
                f"bundle.size_bytes must be between 1 and {MAX_BUNDLE_BYTES}."
            )

        return cls(
            uri=uri,
            etag=_etag(value["etag"], field="bundle.etag"),
            sha256=bundle_sha256,
            size_bytes=size_bytes,
        )


@dataclass(frozen=True)
class SavedPlanReference:
    blob_name: str
    etag: str
    sha256: str
    plan_job_digest: str
    bundle_sha256: str

    @classmethod
    def from_mapping(
        cls,
        value: Any,
        *,
        tenant_id: str,
        workflow_id: str,
    ) -> "SavedPlanReference":
        if not isinstance(value, Mapping):
            raise ContractError("saved_plan must be an object.")
        _require_exact_keys(
            value,
            {
                "blob_name",
                "etag",
                "sha256",
                "plan_job_digest",
                "bundle_sha256",
            },
            context="saved_plan",
        )

        blob_name = value["blob_name"]
        expected_prefix = f"{_tenant_blob_prefix(tenant_id, workflow_id)}plans/"
        if (
            not isinstance(blob_name, str)
            or not SAFE_PATH_PATTERN.fullmatch(blob_name)
            or not blob_name.startswith(expected_prefix)
            or ".." in blob_name.split("/")
            or not blob_name.endswith(".tfplan")
        ):
            raise ContractError("saved_plan.blob_name is outside the tenant plan prefix.")

        return cls(
            blob_name=blob_name,
            etag=_etag(value["etag"], field="saved_plan.etag"),
            sha256=_sha256(value["sha256"], field="saved_plan.sha256"),
            plan_job_digest=_sha256(
                value["plan_job_digest"], field="saved_plan.plan_job_digest"
            ),
            bundle_sha256=_sha256(
                value["bundle_sha256"], field="saved_plan.bundle_sha256"
            ),
        )


@dataclass(frozen=True)
class ApprovalRecord:
    approval_id: str
    decision: str
    approved_by: str
    approved_at: datetime
    plan_job_digest: str
    plan_sha256: str
    plan_etag: str
    bundle_sha256: str

    @classmethod
    def from_mapping(cls, value: Any) -> "ApprovalRecord":
        if not isinstance(value, Mapping):
            raise ContractError("approval must be an object.")
        _require_exact_keys(
            value,
            {
                "approval_id",
                "decision",
                "approved_by",
                "approved_at",
                "plan_job_digest",
                "plan_sha256",
                "plan_etag",
                "bundle_sha256",
            },
            context="approval",
        )
        if value["decision"] != "approved":
            raise ContractError("approval.decision must be approved.")
        return cls(
            approval_id=_canonical_uuid(value["approval_id"], field="approval.approval_id"),
            decision="approved",
            approved_by=_canonical_uuid(value["approved_by"], field="approval.approved_by"),
            approved_at=_timestamp(value["approved_at"], field="approval.approved_at"),
            plan_job_digest=_sha256(
                value["plan_job_digest"], field="approval.plan_job_digest"
            ),
            plan_sha256=_sha256(value["plan_sha256"], field="approval.plan_sha256"),
            plan_etag=_etag(value["plan_etag"], field="approval.plan_etag"),
            bundle_sha256=_sha256(
                value["bundle_sha256"], field="approval.bundle_sha256"
            ),
        )


@dataclass(frozen=True)
class ExecutionEnvelope:
    schema_version: str
    operation: str
    job_id: str
    tenant_id: str
    project_id: str
    user_id: str
    workflow_id: str
    revision: int
    bundle: BundleReference
    state_key: str
    target_subscription_id: str
    target_tenant_id: str
    terraform_version: str
    requested_at: datetime
    job_digest: str
    saved_plan: SavedPlanReference | None = None
    approval: ApprovalRecord | None = None

    @classmethod
    def from_mapping(cls, payload: Any) -> "ExecutionEnvelope":
        if not isinstance(payload, Mapping):
            raise ContractError("Execution envelope must be a JSON object.")

        operation = payload.get("operation")
        if operation not in {"plan", "apply"}:
            raise ContractError("operation must be plan or apply.")

        base_keys = {
            "schema_version",
            "operation",
            "job_id",
            "tenant_id",
            "project_id",
            "user_id",
            "workflow_id",
            "revision",
            "bundle",
            "state_key",
            "target_subscription_id",
            "target_tenant_id",
            "terraform_version",
            "requested_at",
            "job_digest",
        }
        expected_keys = base_keys | ({"saved_plan", "approval"} if operation == "apply" else set())
        _require_exact_keys(payload, expected_keys, context="execution envelope")

        if payload["schema_version"] != "1.0":
            raise ContractError("schema_version must be 1.0.")

        digest = _sha256(payload["job_digest"], field="job_digest")
        digest_payload = dict(payload)
        digest_payload.pop("job_digest")
        if canonical_digest(digest_payload) != digest:
            raise ContractError("job_digest does not match the immutable envelope.")

        tenant_id = _canonical_uuid(payload["tenant_id"], field="tenant_id")
        workflow_id = _canonical_uuid(payload["workflow_id"], field="workflow_id")
        revision = payload["revision"]
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
            raise ContractError("revision must be a positive integer.")

        state_key = payload["state_key"]
        expected_state_key = (
            f"tenants/{tenant_id}/workspaces/{workflow_id}/terraform.tfstate"
        )
        if state_key != expected_state_key or not SAFE_PATH_PATTERN.fullmatch(state_key):
            raise ContractError("state_key must be the canonical tenant workspace state key.")

        terraform_version = payload["terraform_version"]
        if (
            not isinstance(terraform_version, str)
            or not TERRAFORM_VERSION_PATTERN.fullmatch(terraform_version)
        ):
            raise ContractError("terraform_version must use major.minor.patch form.")

        bundle = BundleReference.from_mapping(payload["bundle"])
        saved_plan = None
        approval = None
        if operation == "apply":
            saved_plan = SavedPlanReference.from_mapping(
                payload["saved_plan"],
                tenant_id=tenant_id,
                workflow_id=workflow_id,
            )
            approval = ApprovalRecord.from_mapping(payload["approval"])
            if saved_plan.plan_job_digest != approval.plan_job_digest:
                raise ContractError("Approval does not identify the saved plan job.")
            if saved_plan.sha256 != approval.plan_sha256:
                raise ContractError("Approval does not identify the saved plan digest.")
            if saved_plan.etag != approval.plan_etag:
                raise ContractError("Approval does not identify the saved plan ETag.")
            if bundle.sha256 != saved_plan.bundle_sha256:
                raise ContractError("Apply bundle differs from the planned bundle.")
            if bundle.sha256 != approval.bundle_sha256:
                raise ContractError("Approval does not identify the planned bundle.")

        return cls(
            schema_version="1.0",
            operation=operation,
            job_id=_canonical_uuid(payload["job_id"], field="job_id"),
            tenant_id=tenant_id,
            project_id=_canonical_uuid(payload["project_id"], field="project_id"),
            user_id=_canonical_uuid(payload["user_id"], field="user_id"),
            workflow_id=workflow_id,
            revision=revision,
            bundle=bundle,
            state_key=state_key,
            target_subscription_id=_canonical_uuid(
                payload["target_subscription_id"], field="target_subscription_id"
            ),
            target_tenant_id=_canonical_uuid(
                payload["target_tenant_id"], field="target_tenant_id"
            ),
            terraform_version=terraform_version,
            requested_at=_timestamp(payload["requested_at"], field="requested_at"),
            job_digest=digest,
            saved_plan=saved_plan,
            approval=approval,
        )

    def safe_context(self) -> dict[str, Any]:
        """Return the only identifiers permitted in normal runner logs/events."""

        return {
            "job_id": self.job_id,
            "job_digest": self.job_digest,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "workflow_id": self.workflow_id,
            "revision": self.revision,
            "operation": self.operation,
        }

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
TERRAFORM_VARIABLE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
TERRAFORM_RESOURCE_TYPE_PATTERN = re.compile(r"^azurerm_[a-z0-9_]{1,96}$")
RESOURCE_GROUP_PATTERN = re.compile(r"^[A-Za-z0-9._()\-]{1,90}$")
CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")
SECRET_VARIABLE_NAME_PATTERN = re.compile(
    r"(?:password|passwd|secret|token|authorization|api[_-]?key|"
    r"connection[_-]?string|private[_-]?key|sas|client[_-]?secret)",
    re.IGNORECASE,
)
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


def _future_timestamp(value: Any, *, field: str) -> datetime:
    if not isinstance(value, str):
        raise ContractError(f"{field} must be an ISO 8601 timestamp.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ContractError(f"{field} must be an ISO 8601 timestamp.") from error
    if parsed.tzinfo is None:
        raise ContractError(f"{field} must include a timezone.")
    return parsed.astimezone(timezone.utc)


def _bounded_integer(
    value: Any,
    *,
    field: str,
    minimum: int,
    maximum: int,
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
        or value > maximum
    ):
        raise ContractError(f"{field} must be between {minimum} and {maximum}.")
    return value


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
class InputVariableDefinition:
    name: str
    type: str

    @classmethod
    def from_mapping(cls, value: Any) -> "InputVariableDefinition":
        if not isinstance(value, Mapping):
            raise ContractError("input variable definition must be an object.")
        _require_exact_keys(value, {"name", "type"}, context="input variable definition")
        name = value["name"]
        variable_type = value["type"]
        if (
            not isinstance(name, str)
            or not TERRAFORM_VARIABLE_NAME_PATTERN.fullmatch(name)
            or SECRET_VARIABLE_NAME_PATTERN.search(name)
        ):
            raise ContractError("input variable definition contains an unsafe name.")
        if variable_type not in {"string", "number", "bool", "list(string)"}:
            raise ContractError("input variable definition contains an unsupported type.")
        return cls(name=name, type=variable_type)


@dataclass(frozen=True)
class InputVariablesReference:
    file_name: str
    sha256: str
    definitions: tuple[InputVariableDefinition, ...]

    @classmethod
    def from_mapping(cls, value: Any) -> "InputVariablesReference":
        if not isinstance(value, Mapping):
            raise ContractError("input_variables must be an object.")
        _require_exact_keys(
            value,
            {"file_name", "sha256", "definitions"},
            context="input_variables",
        )
        if value["file_name"] != "zeroops.auto.tfvars.json":
            raise ContractError("input_variables.file_name is not application-owned.")
        definitions_value = value["definitions"]
        if not isinstance(definitions_value, list) or len(definitions_value) > 64:
            raise ContractError("input_variables.definitions must contain at most 64 items.")
        definitions = tuple(
            InputVariableDefinition.from_mapping(item) for item in definitions_value
        )
        names = [item.name for item in definitions]
        if names != sorted(names) or len(names) != len(set(names)):
            raise ContractError("input variable definitions must be unique and sorted.")
        return cls(
            file_name="zeroops.auto.tfvars.json",
            sha256=_sha256(value["sha256"], field="input_variables.sha256"),
            definitions=definitions,
        )


@dataclass(frozen=True)
class ExecutionGuardrails:
    target_resource_group: str
    allowed_resource_types: tuple[str, ...]
    maximum_resource_changes: int
    maximum_delete_count: int
    maximum_replace_count: int
    scope_digest: str
    policy_digest: str
    monthly_budget_microunits: int | None
    budget_currency: str | None

    @classmethod
    def from_mapping(cls, value: Any) -> "ExecutionGuardrails":
        if not isinstance(value, Mapping):
            raise ContractError("guardrails must be an object.")
        _require_exact_keys(
            value,
            {
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
            context="guardrails",
        )
        resource_group = value["target_resource_group"]
        if (
            not isinstance(resource_group, str)
            or not RESOURCE_GROUP_PATTERN.fullmatch(resource_group)
            or resource_group.endswith(".")
        ):
            raise ContractError("guardrails.target_resource_group is invalid.")
        allowed = value["allowed_resource_types"]
        if (
            not isinstance(allowed, list)
            or not 1 <= len(allowed) <= 120
            or any(
                not isinstance(item, str)
                or not TERRAFORM_RESOURCE_TYPE_PATTERN.fullmatch(item)
                for item in allowed
            )
            or allowed != sorted(allowed)
            or len(allowed) != len(set(allowed))
        ):
            raise ContractError("guardrails.allowed_resource_types must be unique and sorted.")
        maximum_changes = _bounded_integer(
            value["maximum_resource_changes"],
            field="guardrails.maximum_resource_changes",
            minimum=1,
            maximum=500,
        )
        maximum_deletes = _bounded_integer(
            value["maximum_delete_count"],
            field="guardrails.maximum_delete_count",
            minimum=0,
            maximum=100,
        )
        maximum_replaces = _bounded_integer(
            value["maximum_replace_count"],
            field="guardrails.maximum_replace_count",
            minimum=0,
            maximum=100,
        )
        if maximum_deletes > maximum_changes or maximum_replaces > maximum_changes:
            raise ContractError("guardrail action maxima exceed the total change maximum.")
        budget = value["monthly_budget_microunits"]
        currency = value["budget_currency"]
        if budget is not None:
            budget = _bounded_integer(
                budget,
                field="guardrails.monthly_budget_microunits",
                minimum=0,
                maximum=10**15,
            )
            if not isinstance(currency, str) or not CURRENCY_PATTERN.fullmatch(currency):
                raise ContractError("guardrails.budget_currency is invalid.")
        elif currency is not None:
            raise ContractError("guardrails.budget_currency requires a budget.")
        return cls(
            target_resource_group=resource_group,
            allowed_resource_types=tuple(allowed),
            maximum_resource_changes=maximum_changes,
            maximum_delete_count=maximum_deletes,
            maximum_replace_count=maximum_replaces,
            scope_digest=_sha256(value["scope_digest"], field="guardrails.scope_digest"),
            policy_digest=_sha256(value["policy_digest"], field="guardrails.policy_digest"),
            monthly_budget_microunits=budget,
            budget_currency=currency,
        )

@dataclass(frozen=True)
class SavedPlanReference:
    blob_name: str
    etag: str
    sha256: str
    plan_job_digest: str
    bundle_sha256: str
    input_variables_sha256: str
    scope_digest: str
    policy_digest: str

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
                "input_variables_sha256",
                "scope_digest",
                "policy_digest",
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
            input_variables_sha256=_sha256(
                value["input_variables_sha256"],
                field="saved_plan.input_variables_sha256",
            ),
            scope_digest=_sha256(
                value["scope_digest"], field="saved_plan.scope_digest"
            ),
            policy_digest=_sha256(
                value["policy_digest"], field="saved_plan.policy_digest"
            ),
        )


@dataclass(frozen=True)
class CostEstimate:
    artifact_sha256: str
    currency: str
    monthly_cost_microunits: int
    captured_at: datetime

    @classmethod
    def from_mapping(cls, value: Any) -> "CostEstimate":
        if not isinstance(value, Mapping):
            raise ContractError("cost_estimate must be an object.")
        _require_exact_keys(
            value,
            {
                "artifact_sha256",
                "currency",
                "monthly_cost_microunits",
                "captured_at",
            },
            context="cost_estimate",
        )
        currency = value["currency"]
        if not isinstance(currency, str) or not CURRENCY_PATTERN.fullmatch(currency):
            raise ContractError("cost_estimate.currency is invalid.")
        return cls(
            artifact_sha256=_sha256(
                value["artifact_sha256"], field="cost_estimate.artifact_sha256"
            ),
            currency=currency,
            monthly_cost_microunits=_bounded_integer(
                value["monthly_cost_microunits"],
                field="cost_estimate.monthly_cost_microunits",
                minimum=0,
                maximum=10**15,
            ),
            captured_at=_timestamp(value["captured_at"], field="cost_estimate.captured_at"),
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
    apply_job_id: str
    expires_at: datetime
    input_variables_sha256: str
    scope_digest: str
    policy_digest: str
    cost_estimate_sha256: str
    currency: str
    monthly_cost_microunits: int

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
                "apply_job_id",
                "expires_at",
                "input_variables_sha256",
                "scope_digest",
                "policy_digest",
                "cost_estimate_sha256",
                "currency",
                "monthly_cost_microunits",
            },
            context="approval",
        )
        if value["decision"] != "approved":
            raise ContractError("approval.decision must be approved.")
        approved_at = _timestamp(value["approved_at"], field="approval.approved_at")
        expires_at = _future_timestamp(value["expires_at"], field="approval.expires_at")
        if expires_at <= approved_at or expires_at - approved_at > timedelta(hours=24):
            raise ContractError("approval.expires_at must be within 24 hours of approval.")
        currency = value["currency"]
        if not isinstance(currency, str) or not CURRENCY_PATTERN.fullmatch(currency):
            raise ContractError("approval.currency is invalid.")
        return cls(
            approval_id=_canonical_uuid(value["approval_id"], field="approval.approval_id"),
            decision="approved",
            approved_by=_canonical_uuid(value["approved_by"], field="approval.approved_by"),
            approved_at=approved_at,
            plan_job_digest=_sha256(
                value["plan_job_digest"], field="approval.plan_job_digest"
            ),
            plan_sha256=_sha256(value["plan_sha256"], field="approval.plan_sha256"),
            plan_etag=_etag(value["plan_etag"], field="approval.plan_etag"),
            bundle_sha256=_sha256(
                value["bundle_sha256"], field="approval.bundle_sha256"
            ),
            apply_job_id=_canonical_uuid(
                value["apply_job_id"], field="approval.apply_job_id"
            ),
            expires_at=expires_at,
            input_variables_sha256=_sha256(
                value["input_variables_sha256"],
                field="approval.input_variables_sha256",
            ),
            scope_digest=_sha256(
                value["scope_digest"], field="approval.scope_digest"
            ),
            policy_digest=_sha256(
                value["policy_digest"], field="approval.policy_digest"
            ),
            cost_estimate_sha256=_sha256(
                value["cost_estimate_sha256"],
                field="approval.cost_estimate_sha256",
            ),
            currency=currency,
            monthly_cost_microunits=_bounded_integer(
                value["monthly_cost_microunits"],
                field="approval.monthly_cost_microunits",
                minimum=0,
                maximum=10**15,
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
    input_variables: InputVariablesReference
    guardrails: ExecutionGuardrails
    state_key: str
    target_subscription_id: str
    target_tenant_id: str
    terraform_version: str
    requested_at: datetime
    job_digest: str
    saved_plan: SavedPlanReference | None = None
    cost_estimate: CostEstimate | None = None
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
            "input_variables",
            "guardrails",
            "state_key",
            "target_subscription_id",
            "target_tenant_id",
            "terraform_version",
            "requested_at",
            "job_digest",
        }
        expected_keys = base_keys | (
            {"saved_plan", "cost_estimate", "approval"}
            if operation == "apply"
            else set()
        )
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
        input_variables = InputVariablesReference.from_mapping(
            payload["input_variables"]
        )
        guardrails = ExecutionGuardrails.from_mapping(payload["guardrails"])
        saved_plan = None
        cost_estimate = None
        approval = None
        if operation == "apply":
            saved_plan = SavedPlanReference.from_mapping(
                payload["saved_plan"],
                tenant_id=tenant_id,
                workflow_id=workflow_id,
            )
            cost_estimate = CostEstimate.from_mapping(payload["cost_estimate"])
            approval = ApprovalRecord.from_mapping(payload["approval"])
            if approval.apply_job_id != payload["job_id"]:
                raise ContractError("Approval is bound to a different apply job.")
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
            if saved_plan.input_variables_sha256 != input_variables.sha256:
                raise ContractError("Apply input variables differ from the saved plan.")
            if approval.input_variables_sha256 != input_variables.sha256:
                raise ContractError("Approval does not identify the planned input variables.")
            if saved_plan.scope_digest != guardrails.scope_digest:
                raise ContractError("Apply scope differs from the saved plan.")
            if approval.scope_digest != guardrails.scope_digest:
                raise ContractError("Approval does not identify the planned scope.")
            if saved_plan.policy_digest != guardrails.policy_digest:
                raise ContractError("Apply policy differs from the saved plan.")
            if approval.policy_digest != guardrails.policy_digest:
                raise ContractError("Approval does not identify the planned policy.")
            if approval.cost_estimate_sha256 != cost_estimate.artifact_sha256:
                raise ContractError("Approval does not identify the verified cost estimate.")
            if approval.currency != cost_estimate.currency:
                raise ContractError("Approval currency differs from the cost estimate.")
            if approval.monthly_cost_microunits != cost_estimate.monthly_cost_microunits:
                raise ContractError("Approval amount differs from the cost estimate.")
            if (
                guardrails.monthly_budget_microunits is not None
                and (
                    guardrails.budget_currency != cost_estimate.currency
                    or cost_estimate.monthly_cost_microunits
                    > guardrails.monthly_budget_microunits
                )
            ):
                raise ContractError("Verified cost estimate exceeds the approved budget.")
            if cost_estimate.captured_at > approval.approved_at:
                raise ContractError("Approval predates the verified cost estimate.")

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
            input_variables=input_variables,
            guardrails=guardrails,
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
            cost_estimate=cost_estimate,
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

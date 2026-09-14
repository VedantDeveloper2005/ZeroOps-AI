"""Fail-closed checks around bundle extraction and saved-plan application."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from worker.contracts import ContractError, ExecutionEnvelope, SHA256_PATTERN, canonical_digest


MAX_EXTRACTED_BYTES = 500 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 5_000
FORBIDDEN_BUNDLE_NAMES = {
    ".env",
    "backend.hcl",
    "terraform.tfstate",
    "terraform.tfstate.backup",
}
FORBIDDEN_BUNDLE_SUFFIXES = {
    ".pem",
    ".pfx",
    ".key",
    ".tfplan",
    ".tfstate",
}
_SECRET_VALUE_PATTERN = re.compile(
    r"(?:-----BEGIN [A-Z ]+PRIVATE KEY-----|"
    r"(?:AccountKey|SharedAccessSignature|client_secret|password)\s*=|"
    r"(?:Bearer|Basic)\s+[A-Za-z0-9+/=_-]{8,}|[?&](?:sig|se|sp|sv)=)",
    re.IGNORECASE,
)


class ExecutionGateError(RuntimeError):
    """The worker cannot safely cross an execution boundary."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_file_digest(path: Path, expected: str, *, label: str) -> None:
    if not SHA256_PATTERN.fullmatch(expected):
        raise ExecutionGateError(f"{label} has an invalid expected digest.")
    actual = sha256_file(path)
    if actual != expected:
        raise ExecutionGateError(f"{label} digest mismatch.")


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    unix_mode = info.external_attr >> 16
    return stat.S_ISLNK(unix_mode)


def safe_extract_zip(archive_path: Path, destination: Path) -> None:
    """Extract a bounded archive without following links or traversing paths."""

    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    root = destination.resolve()
    with zipfile.ZipFile(archive_path) as archive:
        members = archive.infolist()
        if len(members) > MAX_ARCHIVE_MEMBERS:
            raise ExecutionGateError("Bundle contains too many files.")
        total_size = sum(member.file_size for member in members)
        if total_size > MAX_EXTRACTED_BYTES:
            raise ExecutionGateError("Bundle expands beyond the executor size limit.")

        for member in members:
            normalized_name = member.filename.replace("\\", "/")
            parts = [part for part in normalized_name.split("/") if part]
            if (
                not normalized_name
                or normalized_name.startswith("/")
                or ".." in parts
                or _is_symlink(member)
            ):
                raise ExecutionGateError("Bundle contains an unsafe archive member.")
            if ".terraform" in parts:
                raise ExecutionGateError("Bundle must not contain a preinitialized .terraform tree.")
            leaf = parts[-1].lower()
            if leaf in FORBIDDEN_BUNDLE_NAMES or any(
                leaf.endswith(suffix) for suffix in FORBIDDEN_BUNDLE_SUFFIXES
            ):
                raise ExecutionGateError("Bundle contains state, plans, or credential-shaped files.")

            target = (root / normalized_name).resolve()
            if root != target and root not in target.parents:
                raise ExecutionGateError("Bundle member escapes its tenant workspace.")
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True, mode=0o700)
                continue
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with archive.open(member, "r") as source, target.open("xb") as output:
                while chunk := source.read(1024 * 1024):
                    output.write(chunk)
            os.chmod(target, 0o600)


def require_provider_lockfile(terraform_root: Path) -> None:
    lockfile = terraform_root / ".terraform.lock.hcl"
    if not lockfile.is_file() or lockfile.stat().st_size == 0:
        raise ExecutionGateError(
            "Generated Terraform must include a non-empty .terraform.lock.hcl."
        )


def validate_input_variables_file(
    envelope: ExecutionEnvelope,
    terraform_root: Path,
) -> None:
    """Verify canonical, typed, non-secret tfvars before Terraform sees them."""

    path = terraform_root / envelope.input_variables.file_name
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 64 * 1024:
        raise ExecutionGateError("Terraform input variables file is missing or invalid.")
    verify_file_digest(path, envelope.input_variables.sha256, label="Terraform inputs")
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ExecutionGateError("Terraform input variables are not valid JSON.") from error
    if not isinstance(value, dict):
        raise ExecutionGateError("Terraform input variables must be a JSON object.")
    canonical = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8") + b"\n"
    if raw != canonical:
        raise ExecutionGateError("Terraform input variables are not canonical JSON.")

    definitions = {item.name: item.type for item in envelope.input_variables.definitions}
    if set(value) != set(definitions):
        raise ExecutionGateError("Terraform input values differ from their approved definitions.")
    for name, expected_type in definitions.items():
        item = value[name]
        if expected_type == "string":
            valid = type(item) is str
            strings = [item] if valid else []
        elif expected_type == "number":
            valid = type(item) in {int, float} and (
                type(item) is int or math.isfinite(item)
            )
            strings = []
        elif expected_type == "bool":
            valid = type(item) is bool
            strings = []
        else:
            valid = isinstance(item, list) and len(item) <= 64 and all(
                type(child) is str for child in item
            )
            strings = item if valid else []
        if not valid:
            raise ExecutionGateError("Terraform input value has the wrong approved type.")
        if any(
            len(child) > 1024
            or any(ord(character) < 32 for character in child)
            or _SECRET_VALUE_PATTERN.search(child)
            for child in strings
        ):
            raise ExecutionGateError("Terraform input contains secret-like or unsafe text.")


def validate_saved_plan_gate(
    envelope: ExecutionEnvelope,
    saved_plan_path: Path,
    *,
    maximum_approval_age: timedelta = timedelta(hours=24),
) -> None:
    """Require an approved, exact saved plan; a directory apply is impossible."""

    if envelope.operation != "apply" or envelope.saved_plan is None or envelope.approval is None:
        raise ExecutionGateError("Apply requires a saved plan and approval record.")
    verify_file_digest(saved_plan_path, envelope.saved_plan.sha256, label="Saved plan")
    if datetime.now(timezone.utc) - envelope.approval.approved_at > maximum_approval_age:
        raise ExecutionGateError("Approval is older than the permitted apply window.")
    if datetime.now(timezone.utc) >= envelope.approval.expires_at:
        raise ExecutionGateError("Approval has expired.")
    if envelope.approval.plan_sha256 != sha256_file(saved_plan_path):
        raise ExecutionGateError("Approved plan digest does not match downloaded plan.")
    if envelope.approval.bundle_sha256 != envelope.bundle.sha256:
        raise ExecutionGateError("Approved bundle digest does not match apply bundle.")


def summarize_plan_json(raw_json: bytes) -> dict[str, Any]:
    """Reduce a plan to counts and review-safe addresses; never retain values."""

    try:
        document = json.loads(raw_json)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ExecutionGateError("Terraform returned invalid plan JSON.") from error
    if not isinstance(document, dict):
        raise ExecutionGateError("Terraform returned invalid plan JSON.")

    action_counts = {
        "create": 0,
        "update": 0,
        "delete": 0,
        "replace": 0,
        "read": 0,
        "no_op": 0,
    }
    resource_kinds: set[str] = set()
    safe_changes: list[dict[str, Any]] = []
    changes = document.get("resource_changes")
    if not isinstance(changes, list):
        changes = []

    for change in changes:
        if not isinstance(change, dict):
            continue
        resource_type = change.get("type")
        if isinstance(resource_type, str) and len(resource_type) <= 128:
            resource_kinds.add(resource_type)
        change_body = change.get("change")
        actions = change_body.get("actions") if isinstance(change_body, dict) else None
        address = change.get("address")
        if (
            isinstance(address, str)
            and re.fullmatch(r"azurerm_[a-z0-9_]+\.[A-Za-z0-9_-]+", address)
            and isinstance(resource_type, str)
            and re.fullmatch(r"azurerm_[a-z0-9_]+", resource_type)
            and actions in (
                ["create"],
                ["update"],
                ["delete"],
                ["delete", "create"],
                ["create", "delete"],
                ["read"],
                ["no-op"],
            )
        ):
            safe_changes.append(
                {
                    "address": address,
                    "type": resource_type,
                    "actions": list(actions),
                }
            )
        if actions == ["create"]:
            action_counts["create"] += 1
        elif actions == ["update"]:
            action_counts["update"] += 1
        elif actions == ["delete"]:
            action_counts["delete"] += 1
        elif actions in (["delete", "create"], ["create", "delete"]):
            action_counts["replace"] += 1
        elif actions == ["read"]:
            action_counts["read"] += 1
        elif actions == ["no-op"]:
            action_counts["no_op"] += 1

    return {
        "format_version": str(document.get("format_version", ""))[:32],
        "terraform_version": str(document.get("terraform_version", ""))[:32],
        "actions": action_counts,
        "resource_kinds": sorted(resource_kinds),
        "changes": sorted(
            safe_changes,
            key=lambda item: (item["address"], item["type"], item["actions"]),
        )[:500],
    }


def validate_plan_guardrails(
    raw_json: bytes,
    envelope: ExecutionEnvelope,
    *,
    approved_input_values: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate resource types, action counts, and resource-group scope."""

    try:
        document = json.loads(raw_json)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ExecutionGateError("Terraform returned invalid plan JSON.") from error
    if not isinstance(document, dict):
        raise ExecutionGateError("Terraform returned invalid plan JSON.")
    registry_scope = None
    if approved_input_values is not None:
        digest_no_nl = canonical_digest(approved_input_values)
        canonical_input_bytes = (
            json.dumps(
                approved_input_values,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
            + b"\n"
        )
        digest_with_nl = hashlib.sha256(canonical_input_bytes).hexdigest()
        if envelope.input_variables.sha256 not in (digest_no_nl, digest_with_nl):
            raise ExecutionGateError("Approved input values digest mismatch.")
        candidate = approved_input_values.get("container_registry_id")
        registry_pattern = (
            rf"/subscriptions/{re.escape(envelope.target_subscription_id)}/resourceGroups/"
            r"[A-Za-z0-9._()\-]+/providers/Microsoft.ContainerRegistry/registries/[A-Za-z0-9]+"
        )
        if isinstance(candidate, str) and re.fullmatch(registry_pattern, candidate, re.IGNORECASE):
            registry_scope = candidate.lower()
    summary = summarize_plan_json(raw_json)
    actions = summary["actions"]
    total_changes = sum(
        actions[name] for name in ("create", "update", "delete", "replace")
    )
    guardrails = envelope.guardrails
    if total_changes > guardrails.maximum_resource_changes:
        raise ExecutionGateError("Terraform plan exceeds the approved change count.")
    if actions["delete"] > guardrails.maximum_delete_count:
        raise ExecutionGateError("Terraform plan exceeds the approved delete count.")
    if actions["replace"] > guardrails.maximum_replace_count:
        raise ExecutionGateError("Terraform plan exceeds the approved replacement count.")
    if not set(summary["resource_kinds"]).issubset(
        set(guardrails.allowed_resource_types)
    ):
        raise ExecutionGateError("Terraform plan contains a resource type outside approval.")

    target_prefix = (
        f"/subscriptions/{envelope.target_subscription_id}/resourceGroups/"
        f"{guardrails.target_resource_group}"
    ).lower()
    changes = document.get("resource_changes")
    if not isinstance(changes, list):
        changes = []
    for change in changes:
        if not isinstance(change, dict) or change.get("mode", "managed") != "managed":
            continue
        change_body = change.get("change")
        actions_value = change_body.get("actions") if isinstance(change_body, dict) else None
        if actions_value in (["read"], ["no-op"]):
            continue
        resource_type = change.get("type")
        if resource_type not in guardrails.allowed_resource_types:
            raise ExecutionGateError("Terraform plan contains a resource type outside approval.")
        bodies = []
        if isinstance(change_body, dict):
            bodies = [
                item
                for item in (change_body.get("after"), change_body.get("before"))
                if isinstance(item, dict)
            ]
        scoped = False
        for body in bodies:
            resource_group = body.get("resource_group_name")
            if isinstance(resource_group, str):
                if resource_group.lower() != guardrails.target_resource_group.lower():
                    raise ExecutionGateError("Terraform plan escapes the approved resource group.")
                scoped = True
            scope = body.get("scope")
            if isinstance(scope, str):
                normalized_scope = scope.rstrip("/").lower()
                shared_registry_pull = (
                    resource_type == "azurerm_role_assignment"
                    and registry_scope is not None
                    and normalized_scope == registry_scope
                    and body.get("role_definition_name") == "AcrPull"
                    and not body.get("condition")
                    and actions_value == ["create"]
                    and _is_application_identity_grant(document, change)
                )
                if not (
                    normalized_scope == target_prefix
                    or normalized_scope.startswith(target_prefix + "/")
                    or shared_registry_pull
                ):
                    raise ExecutionGateError("Terraform plan escapes the approved ARM scope.")
                scoped = True
            for key, item in body.items():
                if (
                    isinstance(key, str)
                    and (key == "id" or key.endswith("_id"))
                    and isinstance(item, str)
                    and (
                        item.lower() == target_prefix
                        or item.lower().startswith(target_prefix + "/")
                    )
                ):
                    scoped = True
            if resource_type == "azurerm_resource_group":
                name = body.get("name")
                if isinstance(name, str):
                    if name.lower() != guardrails.target_resource_group.lower():
                        raise ExecutionGateError(
                            "Terraform plan targets an unapproved resource group."
                        )
                    scoped = True
        if not scoped:
            raise ExecutionGateError(
                "Terraform plan resource scope cannot be proven inside the approved group."
            )
    return summary


def _is_application_identity_grant(document: dict[str, Any], change: dict[str, Any]) -> bool:
    """Restrict shared-registry exceptions to the newly created application identity."""
    configuration = document.get("configuration", {}).get("root_module", {}).get("resources", [])
    resource = next((item for item in configuration if item.get("address") == change.get("address")), None)
    if not isinstance(resource, dict):
        return False
    expression = resource.get("expressions", {}).get("principal_id", {})
    references = expression.get("references", [])
    if not references or "constant_value" in expression:
        return False
    applications = [item for item in document.get("resource_changes", [])
                    if item.get("type") == "azurerm_linux_web_app"
                    and item.get("change", {}).get("actions") == ["create"]]
    if len(applications) != 1:
        return False
    address = applications[0].get("address", "")
    allowed = {
        address,
        address + ".identity",
        address + ".identity[0]",
        address + ".identity[0].principal_id",
    }
    return bool(address) and set(references).issubset(allowed) and any(
        reference.startswith(address + ".identity") for reference in references
    )


def decode_envelope_json(raw_message: bytes) -> ExecutionEnvelope:
    if len(raw_message) > 256 * 1024:
        raise ContractError("Execution envelope exceeds 256 KiB.")
    try:
        payload = json.loads(raw_message)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ContractError("Execution envelope is not valid UTF-8 JSON.") from error
    return ExecutionEnvelope.from_mapping(payload)

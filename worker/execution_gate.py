"""Fail-closed checks around bundle extraction and saved-plan application."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from worker.contracts import ContractError, ExecutionEnvelope, SHA256_PATTERN


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
    if envelope.approval.plan_sha256 != sha256_file(saved_plan_path):
        raise ExecutionGateError("Approved plan digest does not match downloaded plan.")
    if envelope.approval.bundle_sha256 != envelope.bundle.sha256:
        raise ExecutionGateError("Approved bundle digest does not match apply bundle.")


def summarize_plan_json(raw_json: bytes) -> dict[str, Any]:
    """Reduce Terraform's sensitive plan JSON to counts and resource kinds."""

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
    }


def decode_envelope_json(raw_message: bytes) -> ExecutionEnvelope:
    if len(raw_message) > 256 * 1024:
        raise ContractError("Execution envelope exceeds 256 KiB.")
    try:
        payload = json.loads(raw_message)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ContractError("Execution envelope is not valid UTF-8 JSON.") from error
    return ExecutionEnvelope.from_mapping(payload)


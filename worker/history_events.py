"""Build the public workflow-history contract at the executor trust boundary.

This module deliberately does not import the Azure Functions application. The
worker image can therefore be deployed independently while its tests validate
the generated document against the Functions-owned Pydantic contract.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping

from worker.contracts import (
    SHA256_PATTERN,
    TENANT_CONTAINER_PATTERN,
    USER_ARTIFACT_PATH_PATTERN,
    ExecutionEnvelope,
)


_SAFE_RESOURCE_KIND = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_SAFE_VERSION = re.compile(r"^[0-9][0-9.]{0,31}$")
_SAFE_ARTIFACT_KIND = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
_KNOWN_ACTIONS = ("create", "update", "delete", "replace", "read", "no_op")
_MAX_ARTIFACT_BYTES = 256 * 1024 * 1024


def _canonical_uuid(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError):
        return None
    canonical = str(parsed)
    return canonical if value.lower() == canonical else None


def _safe_failure_category(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = "".join(
        character
        if character.isascii() and (character.isalnum() or character in "._:- ")
        else "-"
        for character in value
    )
    cleaned = " ".join(cleaned.split()).strip(" ._:-")
    return cleaned[:96] or None


def _safe_summary(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None

    actions_value = value.get("actions")
    actions: dict[str, int] = {}
    if isinstance(actions_value, Mapping):
        for action in _KNOWN_ACTIONS:
            count = actions_value.get(action)
            if (
                isinstance(count, int)
                and not isinstance(count, bool)
                and 0 <= count <= 1_000_000
            ):
                actions[action] = count

    kinds_value = value.get("resource_kinds")
    resource_kinds: list[str] = []
    if isinstance(kinds_value, list):
        resource_kinds = sorted(
            {
                item
                for item in kinds_value
                if isinstance(item, str) and _SAFE_RESOURCE_KIND.fullmatch(item)
            }
        )[:100]

    summary: dict[str, Any] = {
        "actions": actions,
        "resource_kinds": resource_kinds,
    }
    for field in ("terraform_version", "format_version"):
        version = value.get(field)
        if isinstance(version, str) and _SAFE_VERSION.fullmatch(version):
            summary[field] = version
    return summary


def _safe_history_artifact(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None

    artifact_id = _canonical_uuid(value.get("artifact_id"))
    sha256 = value.get("sha256")
    container = value.get("storage_container")
    storage_path = value.get("storage_path")
    kind = value.get("kind")
    size_bytes = value.get("size_bytes")
    content_type = value.get("content_type")
    if (
        artifact_id is None
        or not isinstance(sha256, str)
        or not SHA256_PATTERN.fullmatch(sha256)
        or not isinstance(container, str)
        or not TENANT_CONTAINER_PATTERN.fullmatch(container)
        or not isinstance(storage_path, str)
        or not isinstance(kind, str)
        or not _SAFE_ARTIFACT_KIND.fullmatch(kind)
        or isinstance(size_bytes, bool)
        or not isinstance(size_bytes, int)
        or not 0 <= size_bytes <= _MAX_ARTIFACT_BYTES
        or content_type != "application/json"
        or value.get("access_scope") != "user"
        or value.get("sanitization_status") != "sanitized"
    ):
        return None

    path_match = USER_ARTIFACT_PATH_PATTERN.fullmatch(storage_path)
    if (
        path_match is None
        or path_match.group("artifact_id") != artifact_id
        or path_match.group("sha256") != sha256
    ):
        return None

    blob_version_id = value.get("blob_version_id")
    if blob_version_id is not None and (
        not isinstance(blob_version_id, str)
        or not blob_version_id
        or len(blob_version_id) > 256
        or any(ord(character) < 32 for character in blob_version_id)
    ):
        blob_version_id = None

    return {
        "artifact_id": artifact_id,
        "kind": kind,
        "sha256": sha256,
        "storage_container": container,
        "storage_path": storage_path,
        "blob_version_id": blob_version_id,
        "size_bytes": size_bytes,
        "content_type": "application/json",
        "access_scope": "user",
        "sanitization_status": "sanitized",
    }


def _occurred_at(value: Any) -> str:
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            parsed = None
        if parsed is not None and parsed.tzinfo is not None:
            return parsed.astimezone(timezone.utc).isoformat()
    return datetime.now(timezone.utc).isoformat()


def _event_outcome(
    envelope: ExecutionEnvelope,
    result: Mapping[str, Any],
) -> tuple[str, str, str, str | None, str | None]:
    result_status = result.get("status")
    stage = f"terraform-{envelope.operation}"
    if result_status == "planned" and envelope.operation == "plan":
        return (
            "terraform.plan.completed",
            stage,
            "completed",
            None,
            None,
        )
    if result_status == "applied" and envelope.operation == "apply":
        return (
            "terraform.apply.completed",
            stage,
            "completed",
            None,
            None,
        )

    category = _safe_failure_category(result.get("failure_category"))
    error_suffix = re.sub(r"[^a-z0-9._-]+", "-", (category or "worker-failure").lower())
    error_code = f"terraform.{error_suffix}"[:96]
    return (
        f"terraform.{envelope.operation}.failed",
        stage,
        "failed",
        error_code,
        f"Terraform {envelope.operation} failed.",
    )


def build_workflow_event(
    envelope: ExecutionEnvelope,
    result: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a strict, sanitized ``workflow-event.v1`` document."""

    event_type, stage, status, error_code, safe_message = _event_outcome(
        envelope,
        result,
    )
    event_material = (
        f"workflow-event.v1:{envelope.tenant_id}:{envelope.workflow_id}:"
        f"{envelope.job_id}:{event_type}"
    ).encode("utf-8")
    event_id = f"evt-{hashlib.sha256(event_material).hexdigest()}"

    safe_metadata: dict[str, Any] = {
        "job_id": envelope.job_id,
        "job_digest": envelope.job_digest,
        "revision": envelope.revision,
        "operation": envelope.operation,
        "bundle_sha256": envelope.bundle.sha256,
    }

    plan_sha256 = result.get("plan_sha256") or result.get("applied_plan_sha256")
    if isinstance(plan_sha256, str) and SHA256_PATTERN.fullmatch(plan_sha256):
        safe_metadata["plan_sha256"] = plan_sha256

    approval_id = _canonical_uuid(result.get("approval_id"))
    if approval_id is not None:
        safe_metadata["approval_id"] = approval_id

    summary = _safe_summary(result.get("summary"))
    if summary is not None:
        safe_metadata["summary"] = summary

    failure_category = _safe_failure_category(result.get("failure_category"))
    if failure_category is not None:
        safe_metadata["failure_category"] = failure_category

    artifact = _safe_history_artifact(result.get("history_artifact"))
    artifacts = [artifact] if artifact is not None else []

    return {
        "schema_version": "workflow-event.v1",
        "event_id": event_id,
        "event_type": event_type,
        "tenant_id": envelope.tenant_id,
        "project_id": envelope.project_id,
        "run_id": envelope.workflow_id,
        "correlation_id": envelope.workflow_id,
        "stage": stage,
        "attempt": 1,
        "status": status,
        "actor_type": "vmss",
        "actor_id": "terraform-executor",
        "occurred_at": _occurred_at(result.get("completed_at")),
        "artifacts": artifacts,
        "safe_metadata": safe_metadata,
        "error_code": error_code,
        "safe_message": safe_message,
    }

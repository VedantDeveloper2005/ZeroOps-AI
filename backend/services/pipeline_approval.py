"""Signed, immutable evidence for a user-approved deployment pipeline.

Approval evidence crosses a security boundary between the authenticated API
and an isolated deployment worker.  The payload is deliberately small,
strictly shaped, and HMAC authenticated.  It contains identifiers only; no
credentials, repository content, scanner output, or free-form user input is
accepted.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import re
from typing import Any, Mapping
import uuid


APPROVAL_SCHEMA = "zeroops.pipeline-approval.v1"
MAX_APPROVAL_BYTES = 8_192
_DOMAIN_SEPARATOR = b"zeroops.pipeline-approval.v1\x00"
_HEX_40 = re.compile(r"^[0-9a-f]{40}$")
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_TARGETS = frozenset({"azure-app-service", "azure-aks"})

_CLAIM_KEYS = frozenset(
    {
        "schema",
        "tenant_id",
        "project_id",
        "validation_run_id",
        "validation_deployment_id",
        "approved_deployment_id",
        "approved_pipeline_run_id",
        "source_revision",
        "branch",
        "target_type",
        "plan_id",
        "plan_revision",
        "configuration_id",
        "configuration_version",
        "configuration_digest",
        "approved_by_user_id",
        "approved_at",
    }
)
_EVIDENCE_KEYS = _CLAIM_KEYS | {"signature"}
_UUID_KEYS = (
    "tenant_id",
    "project_id",
    "validation_run_id",
    "validation_deployment_id",
    "approved_deployment_id",
    "approved_pipeline_run_id",
    "plan_id",
    "configuration_id",
    "approved_by_user_id",
)


@dataclass(frozen=True)
class ApprovalVerification:
    """Result safe to use in worker logs and stage evidence."""

    valid: bool
    reason: str
    claims: dict[str, Any] | None = None


def _canonical_timestamp(value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 64:
        raise ValueError("Approval timestamp is invalid.")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Approval timestamp is invalid.") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Approval timestamp must include a UTC offset.")
    normalized = parsed.astimezone(timezone.utc)
    return normalized.isoformat(timespec="seconds").replace("+00:00", "Z")


def _canonical_claims(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _CLAIM_KEYS:
        raise ValueError("Pipeline approval has an invalid schema.")

    normalized: dict[str, Any] = {"schema": str(value.get("schema") or "")}
    if normalized["schema"] != APPROVAL_SCHEMA:
        raise ValueError("Pipeline approval has an unsupported schema version.")

    for key in _UUID_KEYS:
        try:
            normalized[key] = str(uuid.UUID(str(value[key])))
        except (TypeError, ValueError, AttributeError) as error:
            raise ValueError("Pipeline approval contains an invalid identifier.") from error

    source_revision = str(value.get("source_revision") or "").strip().lower()
    if not _HEX_40.fullmatch(source_revision):
        raise ValueError("Pipeline approval contains an invalid source revision.")
    normalized["source_revision"] = source_revision

    branch = str(value.get("branch") or "").strip()
    if (
        not branch
        or len(branch) > 255
        or branch.startswith("-")
        or ".." in branch
        or any(character.isspace() for character in branch)
    ):
        raise ValueError("Pipeline approval contains an invalid branch.")
    normalized["branch"] = branch

    target_type = str(value.get("target_type") or "").strip().lower()
    if target_type not in _TARGETS:
        raise ValueError("Pipeline approval contains an unsupported deployment target.")
    normalized["target_type"] = target_type

    for key in ("plan_revision", "configuration_version"):
        raw = value.get(key)
        if isinstance(raw, bool):
            raise ValueError("Pipeline approval contains an invalid revision.")
        try:
            revision = int(raw)
        except (TypeError, ValueError) as error:
            raise ValueError("Pipeline approval contains an invalid revision.") from error
        if revision < 1 or revision > 2_147_483_647 or str(raw) != str(revision):
            raise ValueError("Pipeline approval contains an invalid revision.")
        normalized[key] = revision

    configuration_digest = str(value.get("configuration_digest") or "").strip().lower()
    if configuration_digest and not _HEX_64.fullmatch(configuration_digest):
        raise ValueError("Pipeline approval contains an invalid configuration digest.")
    normalized["configuration_digest"] = configuration_digest
    normalized["approved_at"] = _canonical_timestamp(value.get("approved_at"))
    return normalized


def _canonical_bytes(claims: Mapping[str, Any]) -> bytes:
    normalized = _canonical_claims(claims)
    encoded = json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    if len(encoded) > MAX_APPROVAL_BYTES:
        raise ValueError("Pipeline approval exceeds the maximum size.")
    return encoded


def sign_pipeline_approval(
    claims: Mapping[str, Any],
    *,
    secret: str,
) -> dict[str, Any]:
    """Normalize and sign exact approval claims with HMAC-SHA256."""

    if not isinstance(secret, str) or not secret:
        raise ValueError("Pipeline approval signing is unavailable.")
    normalized = _canonical_claims(claims)
    signature = hmac.new(
        secret.encode("utf-8"),
        _DOMAIN_SEPARATOR + _canonical_bytes(normalized),
        hashlib.sha256,
    ).hexdigest()
    return {**normalized, "signature": signature}


def verify_pipeline_approval(
    evidence: Any,
    *,
    secret: str,
    expected: Mapping[str, Any] | None = None,
    now: datetime | None = None,
) -> ApprovalVerification:
    """Verify signature, timestamp sanity, and immutable caller bindings.

    ``expected`` may contain any signed claim except ``approved_at``.  Runtime
    callers should provide every identity known from the current deployment
    and pipeline records.  Signature and expected-value comparisons use
    ``hmac.compare_digest``.
    """

    if not isinstance(secret, str) or not secret:
        return ApprovalVerification(False, "Pipeline approval verification is unavailable.")
    if not isinstance(evidence, Mapping) or set(evidence) != _EVIDENCE_KEYS:
        return ApprovalVerification(False, "Pipeline approval has an invalid schema.")
    try:
        serialized = json.dumps(evidence, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    except (TypeError, ValueError):
        return ApprovalVerification(False, "Pipeline approval has an invalid schema.")
    if len(serialized) > MAX_APPROVAL_BYTES:
        return ApprovalVerification(False, "Pipeline approval exceeds the maximum size.")

    supplied_signature = str(evidence.get("signature") or "").strip().lower()
    if not _HEX_64.fullmatch(supplied_signature):
        return ApprovalVerification(False, "Pipeline approval signature is invalid.")
    unsigned = {key: evidence[key] for key in _CLAIM_KEYS}
    try:
        normalized = _canonical_claims(unsigned)
        expected_signature = hmac.new(
            secret.encode("utf-8"),
            _DOMAIN_SEPARATOR + _canonical_bytes(normalized),
            hashlib.sha256,
        ).hexdigest()
    except ValueError as error:
        return ApprovalVerification(False, str(error))
    if not hmac.compare_digest(supplied_signature, expected_signature):
        return ApprovalVerification(False, "Pipeline approval signature is invalid.")

    if expected is not None:
        if not isinstance(expected, Mapping) or any(
            key not in _CLAIM_KEYS or key == "approved_at" for key in expected
        ):
            return ApprovalVerification(False, "Pipeline approval expectations are invalid.")
        for key, expected_value in expected.items():
            candidate = dict(normalized)
            candidate[key] = expected_value
            try:
                expected_normalized = _canonical_claims(candidate)[key]
            except ValueError:
                return ApprovalVerification(False, "Pipeline approval expectations are invalid.")
            if not hmac.compare_digest(str(normalized[key]), str(expected_normalized)):
                return ApprovalVerification(False, "Pipeline approval does not match this immutable release.")

    try:
        approved_at = datetime.fromisoformat(normalized["approved_at"].replace("Z", "+00:00"))
    except ValueError:
        return ApprovalVerification(False, "Pipeline approval timestamp is invalid.")
    checked_at = now or datetime.now(timezone.utc)
    if checked_at.tzinfo is None or checked_at.utcoffset() is None:
        checked_at = checked_at.replace(tzinfo=timezone.utc)
    checked_at = checked_at.astimezone(timezone.utc)
    # The route consumes an approval exactly once and binds it to newly
    # generated deployment/run identifiers.  A durable queue may legitimately
    # wait through a worker outage, so signed evidence does not expire after it
    # has been atomically consumed.  We only reject timestamps beyond bounded
    # clock skew; HMAC bindings prevent the evidence from authorizing any other
    # release.
    if approved_at > checked_at + timedelta(minutes=5):
        return ApprovalVerification(False, "Pipeline approval has a future timestamp.")
    return ApprovalVerification(
        True,
        "The signed approval matches the validated immutable release.",
        normalized,
    )
